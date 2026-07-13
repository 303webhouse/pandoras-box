"""
Outcome Resolver — Brief C v1.1, extended S-1 Phase 2 (F-2) for crypto parity

Closes the feedback loop on committee-reviewed signals.

Resolves ACCEPTED signals by walking forward through 15-minute bars from
signal timestamp to find the FIRST touch of target or stop. Runs every 15
min during market hours. Equity/ETF signals use yfinance (unchanged from
v1.1). Crypto signals (asset_class='CRYPTO') use per-symbol bar sources
dispatched via crypto_bars.fetch_crypto_bars() -- NOT yfinance, and NOT a
single universal crypto source (see crypto_bars.py docstring: UW covers
BTC/ETH/SOL bars but not ZEC/HYPE/FARTCOIN; Binance spot klines cover ZEC;
OKX candles cover HYPE/FARTCOIN). A crypto symbol with no LIVE
bar_walk_source in the matrix stays shadow-only/ungraded -- enforced by
fetch_crypto_bars() returning [] rather than guessing a fallback.

v1.1 change from v1.0: walks intraday bars instead of current-price spot check.
Fixes the silent-loss bug where intraday wicks were missed.

Edge case — same bar touches both target and stop: conservative — assume stop first
(we cannot know intra-bar ordering from OHLC alone). Shared by both the
equity and crypto paths via _walk_touch().

yfinance 15m history limit is ~60 days. Signals older than 55 days fall back to
daily bars (lower precision, flagged in logs). The same 55-day threshold is
reused for crypto for consistency; crypto vendors' actual intraday history
depth was not independently benchmarked against that figure (out of scope
for S-1 -- the common case is signals resolved within hours/days of firing).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pandas as pd

from jobs.crypto_bars import normalize_crypto_ticker, fetch_crypto_bars

logger = logging.getLogger(__name__)


def _walk_touch(
    bars: List[Tuple[datetime, float, float]],
    direction: str,
    entry: float,
    target: float,
    stop: float,
    signal_ts: datetime,
) -> Tuple[Optional[str], Optional[float], Optional[datetime]]:
    """Shared touch-detection walk, asset-class-agnostic. `bars` is a list of
    (bar_ts, high, low) tuples in any order (sorted here). Both the equity
    (yfinance) and crypto paths normalize their vendor-specific bar shapes
    into this common form before calling it, so the WIN/LOSS/same-bar-tie
    logic lives in exactly one place.
    """
    for bar_ts, high, low in sorted(bars, key=lambda b: b[0]):
        # Phase B guard: skip bars stamped before signal creation (the bar
        # *containing* signal_ts is timestamped at its own start, before
        # signal_ts) — without this, the resolver matches pre-signal price
        # action and registers phantom WINs.
        if bar_ts < signal_ts:
            continue

        if direction == "LONG":
            target_hit = high >= target
            stop_hit = low <= stop
            if target_hit and stop_hit:
                # Both in same bar — conservative: stop first
                return "LOSS", (stop - entry) / entry * 100.0, bar_ts
            if target_hit:
                return "WIN", (target - entry) / entry * 100.0, bar_ts
            if stop_hit:
                return "LOSS", (stop - entry) / entry * 100.0, bar_ts

        elif direction == "SHORT":
            target_hit = low <= target
            stop_hit = high >= stop
            if target_hit and stop_hit:
                return "LOSS", (entry - stop) / entry * 100.0, bar_ts
            if target_hit:
                return "WIN", (entry - target) / entry * 100.0, bar_ts
            if stop_hit:
                return "LOSS", (entry - stop) / entry * 100.0, bar_ts

    return None, None, None  # no touch yet


def _walk_bars(
    ticker: str,
    direction: str,
    entry: float,
    target: float,
    stop: float,
    signal_ts: datetime,
) -> Tuple[Optional[str], Optional[float], Optional[datetime]]:
    """
    Synchronous walk-forward (called via asyncio.to_thread). EQUITY path only.
    Walks 15m bars from signal_ts looking for first touch of target or stop.
    Returns (outcome, pnl_pct, resolved_at) or (None, None, None) if no touch yet.
    """
    import yfinance as yf

    signal_age_days = (datetime.now(timezone.utc) - signal_ts).days
    interval = "15m" if signal_age_days <= 55 else "1d"

    if interval == "1d":
        logger.info(
            "Signal for %s is %d days old — falling back to daily bars",
            ticker, signal_age_days,
        )

    try:
        # Phase B: do not subtract 15min — would deliberately reach pre-signal bars.
        # Note: yfinance still returns the bar-aligned bar that *contains* signal_ts
        # (whose bar_ts is before signal_ts), so the loop below has an explicit
        # bar_ts < signal_ts guard. See docs/codex-briefs/outcome-tracking-phase-b-resolver-fix-2026-05-08.md
        bars = yf.download(
            ticker,
            start=signal_ts,
            interval=interval,
            progress=False,
            auto_adjust=False,
            prepost=False,
        )
    except Exception as e:
        logger.warning("yfinance download failed for %s: %s", ticker, e)
        return None, None, None

    if bars is None or bars.empty:
        return None, None, None

    # Flatten if multi-index (yfinance wraps columns when ambiguous symbol)
    if isinstance(bars.columns, pd.MultiIndex):
        bars.columns = bars.columns.get_level_values(0)

    bar_tuples: List[Tuple[datetime, float, float]] = []
    for bar_ts, bar in bars.iterrows():
        try:
            high = float(bar["High"])
            low = float(bar["Low"])
        except (KeyError, ValueError, TypeError):
            continue

        try:
            if hasattr(bar_ts, "tz_convert"):
                bar_ts_utc = (
                    bar_ts.tz_convert("UTC")
                    if getattr(bar_ts, "tzinfo", None) is not None
                    else bar_ts.tz_localize("UTC")
                )
            else:
                bar_ts_utc = (
                    bar_ts
                    if getattr(bar_ts, "tzinfo", None) is not None
                    else bar_ts.replace(tzinfo=timezone.utc)
                )
        except Exception:
            bar_ts_utc = bar_ts
        bar_tuples.append((bar_ts_utc, high, low))

    return _walk_touch(bar_tuples, direction, entry, target, stop, signal_ts)


async def _walk_bars_crypto(
    ticker: str,
    direction: str,
    entry: float,
    target: float,
    stop: float,
    signal_ts: datetime,
) -> Tuple[Optional[str], Optional[float], Optional[datetime]]:
    """CRYPTO path. Normalizes `ticker` to a base symbol, fetches bars from
    that symbol's matrix-designated bar_walk_source, and applies the same
    _walk_touch() logic as the equity path. Returns (None, None, None) with
    no error if the ticker can't be normalized or has no LIVE bar source —
    the signal stays shadow-only/ungraded, per F-2 task 2.1.
    """
    base_symbol = normalize_crypto_ticker(ticker)
    if base_symbol is None:
        logger.debug("Cannot normalize crypto ticker '%s' to a tracked base symbol — shadow-only, skipping", ticker)
        return None, None, None

    signal_age_days = (datetime.now(timezone.utc) - signal_ts).days
    use_daily = signal_age_days > 55
    if use_daily:
        logger.info("Crypto signal for %s (%s) is %d days old — falling back to daily bars", ticker, base_symbol, signal_age_days)

    bars = await fetch_crypto_bars(base_symbol, signal_ts, use_daily)
    if not bars:
        return None, None, None

    return _walk_touch(bars, direction, entry, target, stop, signal_ts)


async def resolve_signal_outcomes(backfill_days: int = 60, asset_class_filter: Optional[str] = None) -> None:
    """
    Walk-forward outcome resolution for all measurable signals.

    Scope: any signal with entry_price + stop_loss + target_1 that hasn't been
    resolved yet and hasn't been explicitly DISMISSED by Nick.  No longer gated
    on user_action='SELECTED' — we measure every signal the system fires so that
    score bands have real win-rate data for URSA gates.

    The resolver is idempotent: if bars don't yet show a target or stop touch,
    it returns (None, None, None) and the signal stays unresolved until next run.

    `asset_class_filter` (S-1 Phase 2, F-2): restricts the sweep to a single
    asset_class value (e.g. 'EQUITY' or 'CRYPTO'). Lets main.py run two
    independently-scheduled loops — equity-hours-gated and 24/7 crypto —
    without double-processing the same signals.
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    base_query = """
        SELECT signal_id, ticker, direction, entry_price,
               stop_loss, target_1, timestamp, asset_class
        FROM signals
        WHERE outcome IS NULL
          AND timestamp > NOW() - INTERVAL '%s days'
          AND status NOT IN ('DISMISSED', 'EXPIRED')
          AND signal_type NOT IN ('SCOUT_ALERT')
          AND entry_price IS NOT NULL
          AND stop_loss IS NOT NULL
          AND target_1 IS NOT NULL
    """ % backfill_days

    async with pool.acquire() as conn:
        if asset_class_filter:
            pending = await conn.fetch(base_query + " AND asset_class = $1", asset_class_filter)
        else:
            pending = await conn.fetch(base_query)

    if not pending:
        logger.info("Outcome resolver: no unresolved signals found")
        return

    logger.info("Outcome resolver: checking %d signals for WIN/LOSS", len(pending))

    for sig in pending:
        ticker = sig["ticker"]
        direction = (sig["direction"] or "").upper()
        entry = float(sig["entry_price"] or 0)
        stop = float(sig["stop_loss"] or 0)
        target = float(sig["target_1"] or 0)
        signal_ts = sig["timestamp"]
        asset_class = (sig["asset_class"] or "EQUITY").upper()

        if not (entry and stop and target and signal_ts):
            continue
        if direction not in ("LONG", "SHORT"):
            continue

        # Ensure signal_ts is timezone-aware for age calculation
        if signal_ts.tzinfo is None:
            signal_ts = signal_ts.replace(tzinfo=timezone.utc)

        # S-1 Phase 2 (F-2): asset-class-aware dispatch. CRYPTO uses per-symbol
        # vendor bars (crypto_bars.py); everything else keeps the unchanged
        # yfinance equity path. A crypto ticker that can't be normalized or
        # has no LIVE bar_walk_source returns (None, None, None) -- the
        # signal stays shadow-only/ungraded, it does not error or fall back
        # to yfinance (which would silently mis-resolve on a non-equity
        # ticker format, the exact bug Phase 0 found in Session_Sweep).
        if asset_class == "CRYPTO":
            outcome, pnl_pct, resolved_at = await _walk_bars_crypto(
                ticker, direction, entry, target, stop, signal_ts
            )
        else:
            outcome, pnl_pct, resolved_at = await asyncio.to_thread(
                _walk_bars, ticker, direction, entry, target, stop, signal_ts
            )

        if outcome:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE signals
                    SET outcome = $1,
                        outcome_pnl_pct = $2,
                        outcome_resolved_at = NOW(),
                        outcome_source = 'BAR_WALK'
                    WHERE signal_id = $3
                """, outcome, pnl_pct, sig["signal_id"])
            logger.info(
                "Resolved %s %s %s: %s (%.2f%%) — matched bar at %s",
                ticker, direction, sig["signal_id"], outcome, pnl_pct or 0, resolved_at,
            )


if __name__ == "__main__":
    import argparse
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

    parser = argparse.ArgumentParser(description="Outcome resolver backfill")
    parser.add_argument("--backfill", action="store_true", help="Run a one-shot backfill pass")
    parser.add_argument("--days", type=int, default=30, help="How many days back to resolve (default: 30)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    if args.backfill:
        logger.info("Running backfill: resolving signals from last %d days", args.days)
        asyncio.run(resolve_signal_outcomes(backfill_days=args.days))
        logger.info("Backfill complete")
    else:
        parser.print_help()
