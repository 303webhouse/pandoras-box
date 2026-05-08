"""
Outcome Resolver — Brief C v1.1

Closes the feedback loop on committee-reviewed signals.

Resolves ACCEPTED signals by walking forward through 15-minute bars from
signal timestamp to find the FIRST touch of target or stop. Uses yfinance
for price history. Runs every 15 min during market hours.

v1.1 change from v1.0: walks intraday bars instead of current-price spot check.
Fixes the silent-loss bug where intraday wicks were missed.

Edge case — same bar touches both target and stop: conservative — assume stop first
(we cannot know intra-bar ordering from OHLC alone).

yfinance 15m history limit is ~60 days. Signals older than 55 days fall back to
daily bars (lower precision, flagged in logs).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def _walk_bars(
    ticker: str,
    direction: str,
    entry: float,
    target: float,
    stop: float,
    signal_ts: datetime,
) -> Tuple[Optional[str], Optional[float], Optional[datetime]]:
    """
    Synchronous walk-forward (called via asyncio.to_thread).
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

    for bar_ts, bar in bars.iterrows():
        try:
            high = float(bar["High"])
            low = float(bar["Low"])
        except (KeyError, ValueError, TypeError):
            continue

        # Phase B: skip bars stamped before signal creation. yfinance's bar-aligned
        # start parameter cannot prevent the bar containing signal_ts (which is
        # timestamped at the bar's start, before signal_ts) from being returned.
        # Without this guard the resolver matches on pre-signal price action and
        # registers phantom WINs.
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
        if bar_ts_utc < signal_ts:
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


async def resolve_signal_outcomes(backfill_days: int = 60) -> None:
    """
    Walk-forward outcome resolution for all measurable signals.

    Scope: any signal with entry_price + stop_loss + target_1 that hasn't been
    resolved yet and hasn't been explicitly DISMISSED by Nick.  No longer gated
    on user_action='SELECTED' — we measure every signal the system fires so that
    score bands have real win-rate data for URSA gates.

    The resolver is idempotent: if bars don't yet show a target or stop touch,
    it returns (None, None, None) and the signal stays unresolved until next run.
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        pending = await conn.fetch("""
            SELECT signal_id, ticker, direction, entry_price,
                   stop_loss, target_1, timestamp
            FROM signals
            WHERE outcome IS NULL
              AND timestamp > NOW() - INTERVAL '%s days'
              AND status NOT IN ('DISMISSED', 'EXPIRED')
              AND signal_type NOT IN ('SCOUT_ALERT')
              AND entry_price IS NOT NULL
              AND stop_loss IS NOT NULL
              AND target_1 IS NOT NULL
        """ % backfill_days)

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

        if not (entry and stop and target and signal_ts):
            continue
        if direction not in ("LONG", "SHORT"):
            continue

        # Ensure signal_ts is timezone-aware for age calculation
        if signal_ts.tzinfo is None:
            signal_ts = signal_ts.replace(tzinfo=timezone.utc)

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
