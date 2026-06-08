"""A3 — FWD_RETURN resolver.

Computes direction-adjusted T+1 and T+5 trading-day forward returns for signals
and writes one row per (signal_id, horizon_days) into signal_forward_returns.
Sets signals.outcome_source = 'FWD_RETURN' as a secondary label under IS-NULL guard.

Design:
- Anchor: signals.timestamp (market time), NOT created_at.
- Bars: UW primary (get_bars daily), yfinance fallback. Never Polygon/FMP.
- Batch by ticker: pull each unique ticker's daily series once per resolver tick,
  compute all that ticker's horizons off the same series.
- Direction-adjusted return stored as PERCENT (2.34 = +2.34%, negative = wrong-way).
  LONG:  fwd_return_pct = (horizon_close - entry) / entry * 100
  SHORT: fwd_return_pct = (entry - horizon_close) / entry * 100
- Trading-day counting: Mon–Fri only (no holiday calendar in Phase 1; Phase 2 fix).
- IS-NULL guard: signals.outcome_source only written when currently NULL.
- Shadow mode: A3_SHADOW_MODE=true (default) → compute + log, do NOT write DB.
  Set A3_SHADOW_MODE=false to enable writes.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

A3_SHADOW_MODE = os.getenv("A3_SHADOW_MODE", "true").lower() != "false"

HORIZONS = [1, 5]  # trading days

# Normalise direction strings to canonical LONG/SHORT
_LONG_DIRS  = {"LONG", "BUY", "BULLISH"}
_SHORT_DIRS = {"SHORT", "SELL", "BEARISH"}


def _nth_trading_day(anchor: date, n: int) -> date:
    """Return the nth Mon–Fri day strictly after anchor."""
    day = anchor
    count = 0
    while count < n:
        day += timedelta(days=1)
        if day.weekday() < 5:   # Mon=0 … Fri=4
            count += 1
    return day


def _build_close_index(bars: List[Dict[str, Any]]) -> Dict[date, float]:
    """Build {date → close_price} from a get_bars() list (t in ms)."""
    index: Dict[date, float] = {}
    for b in bars:
        ts_ms = b.get("t")
        close  = b.get("c")
        if ts_ms is None or close is None:
            continue
        try:
            d = datetime.utcfromtimestamp(ts_ms / 1000).date()
            index[d] = float(close)
        except (OSError, ValueError, OverflowError):
            continue
    return index


async def _fetch_close_index(ticker: str, from_date: date) -> Optional[Dict[date, float]]:
    """Fetch daily bars for ticker and return {date → close}. UW primary."""
    try:
        from integrations.uw_api import get_bars
    except ImportError:
        from backend.integrations.uw_api import get_bars

    # Extra buffer so the series covers T+5 reliably (weekends, holidays)
    fetch_from = (from_date - timedelta(days=2)).isoformat()
    fetch_to   = date.today().isoformat()

    try:
        bars = await get_bars("TSLA" if False else ticker, 1, "day",
                              from_date=fetch_from, to_date=fetch_to)
        if bars:
            return _build_close_index(bars)
    except Exception as exc:
        logger.warning("a3_fwd: UW bars failed for %s: %s — trying yfinance", ticker, exc)

    # yfinance fallback
    try:
        import asyncio, yfinance as yf
        loop = asyncio.get_event_loop()
        def _yf():
            data = yf.download(ticker, start=fetch_from, end=fetch_to,
                               interval="1d", progress=False, auto_adjust=True)
            if data is None or data.empty:
                return {}
            if hasattr(data.columns, "nlevels") and data.columns.nlevels > 1:
                data.columns = data.columns.get_level_values(0)
            idx = {}
            for ts, row in data.iterrows():
                try:
                    d = ts.date() if hasattr(ts, "date") else ts
                    idx[d] = float(row["Close"])
                except Exception:
                    pass
            return idx
        idx = await loop.run_in_executor(None, _yf)
        if idx:
            return idx
    except Exception as exc:
        logger.warning("a3_fwd: yfinance fallback also failed for %s: %s", ticker, exc)

    return None


def _direction_adjusted_return(entry: float, close: float, direction: str) -> float:
    """Direction-adjusted return in percent. Positive = correct call."""
    dir_upper = direction.upper()
    raw = (close - entry) / entry * 100
    if dir_upper in _SHORT_DIRS:
        raw = -raw  # SHORT: up move is a loss
    return round(raw, 6)


async def resolve_fwd_returns(
    pool,
    signal_ids: Optional[List[str]] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    Main resolver tick.

    signal_ids: if provided, restrict to these signals (Gate 2 sample mode).
    limit: max signals to process per call (full-run throttle).

    Returns a summary dict with row counts and any skip reasons.
    """
    shadow = A3_SHADOW_MODE
    if shadow:
        logger.info("a3_fwd: SHADOW MODE — compute+log only, no DB writes")

    async with pool.acquire() as conn:
        if signal_ids:
            rows = await conn.fetch(
                """
                SELECT signal_id, ticker, direction,
                       timestamp AS signal_ts, entry_price
                FROM signals
                WHERE signal_id = ANY($1::text[])
                  AND entry_price IS NOT NULL
                  AND outcome_source IS NULL
                """,
                signal_ids,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT signal_id, ticker, direction,
                       timestamp AS signal_ts, entry_price
                FROM signals
                WHERE outcome_source IS NULL
                  AND entry_price IS NOT NULL
                  AND timestamp < NOW() - INTERVAL '1 day'
                  AND UPPER(direction) = ANY($1::text[])
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                list(_LONG_DIRS | _SHORT_DIRS),
                limit,
            )

    if not rows:
        logger.info("a3_fwd: no eligible signals")
        return {"eligible": 0, "written": 0, "skipped": 0}

    # Already-resolved: exclude signals that already have forward-return rows
    already_ids: set = set()
    existing_ids = [r["signal_id"] for r in rows]
    async with pool.acquire() as conn:
        existing_rows = await conn.fetch(
            "SELECT DISTINCT signal_id FROM signal_forward_returns WHERE signal_id = ANY($1::text[])",
            existing_ids,
        )
    already_ids = {r["signal_id"] for r in existing_rows}

    eligible = [r for r in rows if r["signal_id"] not in already_ids]
    logger.info("a3_fwd: %d eligible signals (%d already have rows)", len(eligible), len(already_ids))

    # Group by ticker for batched bar fetches
    by_ticker: Dict[str, List[Any]] = {}
    for sig in eligible:
        t = (sig["ticker"] or "").upper()
        by_ticker.setdefault(t, []).append(sig)

    written = skipped = 0

    for ticker, signals in by_ticker.items():
        # Earliest signal date for this ticker — fetch bars from there
        earliest = min(
            (sig["signal_ts"].date() if hasattr(sig["signal_ts"], "date") else sig["signal_ts"])
            for sig in signals
        )
        close_index = await _fetch_close_index(ticker, earliest)

        if not close_index:
            logger.warning("a3_fwd: no bars for %s — skipping %d signals", ticker, len(signals))
            skipped += len(signals)
            continue

        for sig in signals:
            sig_id   = sig["signal_id"]
            entry    = float(sig["entry_price"])
            direction = (sig["direction"] or "").upper()
            sig_date  = sig["signal_ts"].date() if hasattr(sig["signal_ts"], "date") else sig["signal_ts"]

            computed_any = False
            for horizon in HORIZONS:
                target_date = _nth_trading_day(sig_date, horizon)

                if target_date > date.today():
                    logger.debug("a3_fwd: %s T+%d not yet (%s) — skip", sig_id, horizon, target_date)
                    continue

                horizon_close = close_index.get(target_date)
                if horizon_close is None:
                    # Try ±1 day (holiday / missing bar tolerance)
                    for delta in [1, -1, 2, -2]:
                        horizon_close = close_index.get(target_date + timedelta(days=delta))
                        if horizon_close is not None:
                            logger.debug("a3_fwd: %s T+%d used ±%d fallback date", sig_id, horizon, delta)
                            break

                if horizon_close is None:
                    logger.debug("a3_fwd: %s T+%d bar missing for %s", sig_id, horizon, target_date)
                    skipped += 1
                    continue

                ret_pct = _direction_adjusted_return(entry, horizon_close, direction)

                logger.info(
                    "a3_fwd: %s %s T+%d entry=%.4f close=%.4f ret=%+.4f%% [%s]",
                    sig_id, ticker, horizon, entry, horizon_close, ret_pct,
                    "SHADOW" if shadow else "WRITE",
                )

                if not shadow:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """
                            INSERT INTO signal_forward_returns
                                (signal_id, horizon_days, reference_price,
                                 horizon_close_price, fwd_return_pct, computed_at)
                            VALUES ($1, $2, $3, $4, $5, NOW())
                            ON CONFLICT (signal_id, horizon_days) DO UPDATE
                                SET horizon_close_price = EXCLUDED.horizon_close_price,
                                    fwd_return_pct      = EXCLUDED.fwd_return_pct,
                                    computed_at         = NOW()
                            """,
                            sig_id, horizon, entry, horizon_close, ret_pct,
                        )
                computed_any = True
                written += 1

            # Set secondary label on signals — only when at least one horizon computed
            # and outcome_source is still NULL (IS-NULL guard).
            if computed_any and not shadow:
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE signals
                        SET outcome_source = 'FWD_RETURN'
                        WHERE signal_id = $1
                          AND outcome_source IS NULL
                        """,
                        sig_id,
                    )

    logger.info("a3_fwd: done — written=%d skipped=%d shadow=%s", written, skipped, shadow)
    return {"eligible": len(eligible), "written": written, "skipped": skipped, "shadow": shadow}
