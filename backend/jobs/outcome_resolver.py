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
        bars = yf.download(
            ticker,
            start=signal_ts - timedelta(minutes=15),  # include the signal bar
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


async def resolve_signal_outcomes() -> None:
    """
    Scan accepted signals with no outcome. For each, walk bars from signal
    timestamp to now to detect first touch of target or stop.

    Filters: user_action = 'SELECTED' (set by Nick's ACCEPTED action),
    outcome IS NULL, signal within 60 days.
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        pending = await conn.fetch("""
            SELECT signal_id, ticker, direction, entry_price,
                   stop_loss, target_1, timestamp
            FROM signals
            WHERE user_action = 'SELECTED'
              AND outcome IS NULL
              AND timestamp > NOW() - INTERVAL '60 days'
        """)

    if not pending:
        return

    logger.info("Outcome resolver: checking %d accepted signals", len(pending))

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
                        outcome_resolved_at = $3
                    WHERE signal_id = $4
                """, outcome, pnl_pct, resolved_at, sig["signal_id"])
            logger.info(
                "Resolved %s %s %s: %s (%.2f%%) at %s",
                ticker, direction, sig["signal_id"], outcome, pnl_pct or 0, resolved_at,
            )
