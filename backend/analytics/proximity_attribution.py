"""
Signal-to-Trade Proximity Attribution

When a trade is opened or closed on ticker X, check if any signal arrived
for that ticker in the preceding N hours.  If found, link the trade to
the signal via `linked_signal_id` and `attribution_type` columns on the
trades table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

async def ensure_attribution_columns() -> None:
    """Add linked_signal_id and attribution_type columns to trades if they
    don't already exist.  Safe to call repeatedly."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute("""
            ALTER TABLE trades
                ADD COLUMN IF NOT EXISTS linked_signal_id TEXT,
                ADD COLUMN IF NOT EXISTS attribution_type  TEXT
        """)
    logger.info("ensure_attribution_columns: trades table columns verified")


# ---------------------------------------------------------------------------
# Single-trade attribution
# ---------------------------------------------------------------------------

async def attribute_trade(
    trade_id: int,
    ticker: str,
    action: str,
    timestamp: Any,
    window_hours: int = 6,
) -> Optional[Dict[str, Any]]:
    """Find the best-matching signal for *ticker* within *window_hours*
    before *timestamp* and link it to the trade.

    Parameters
    ----------
    trade_id : int
        Primary key of the trade row.
    ticker : str
        Underlying ticker symbol (e.g. ``"SPY"``).
    action : str
        ``"open"`` or ``"close"`` — stored as the ``attribution_type``.
    timestamp : datetime | str | None
        Reference point for the look-back window.  If *None* or missing,
        falls back to ``NOW()``.
    window_hours : int
        How far back (in hours) to search for a matching signal.

    Returns
    -------
    dict | None
        Attribution result with keys ``signal_id``, ``strategy``, ``score``,
        ``attribution_type``, and ``time_delta_minutes``, or *None* if no
        qualifying signal was found.
    """
    ts = _normalise_timestamp(timestamp)
    window_start = ts - timedelta(hours=window_hours)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Pick the most recent signal for this ticker inside the window.
        # If multiple exist, prefer the one closest to the trade timestamp.
        row = await conn.fetchrow(
            """
            SELECT signal_id,
                   strategy,
                   score,
                   COALESCE(timestamp, created_at) AS signal_ts
              FROM signals
             WHERE UPPER(ticker) = UPPER($1)
               AND COALESCE(timestamp, created_at) >= $2
               AND COALESCE(timestamp, created_at) <= $3
             ORDER BY COALESCE(timestamp, created_at) DESC
             LIMIT 1
            """,
            ticker,
            window_start,
            ts,
        )

        if row is None:
            logger.debug(
                "No signal found for %s within %dh before %s",
                ticker,
                window_hours,
                ts.isoformat(),
            )
            return None

        signal_id: str = row["signal_id"]
        signal_ts: datetime = row["signal_ts"]
        delta_minutes = round((ts - signal_ts).total_seconds() / 60, 1)

        attribution_type = f"proximity_{action}"

        await conn.execute(
            """
            UPDATE trades
               SET linked_signal_id = $1,
                   attribution_type = $2
             WHERE id = $3
            """,
            signal_id,
            attribution_type,
            trade_id,
        )

        result = {
            "signal_id": signal_id,
            "strategy": row["strategy"],
            "score": float(row["score"]) if row["score"] is not None else None,
            "attribution_type": attribution_type,
            "time_delta_minutes": delta_minutes,
        }
        logger.info(
            "Attributed trade %d → signal %s (%s, %.1f min prior)",
            trade_id,
            signal_id,
            attribution_type,
            delta_minutes,
        )
        return result


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

async def backfill_all_attributions(window_hours: int = 6) -> Dict[str, int]:
    """Retroactively scan all trades that lack attribution and attempt to
    link them to a signal.

    Only trades where ``linked_signal_id IS NULL`` are considered.  For each
    qualifying trade the function:

    1. Tries open-attribution using ``opened_at``.
    2. If the trade is closed (``closed_at IS NOT NULL``) and step 1 found
       nothing, tries close-attribution using ``closed_at``.

    Returns
    -------
    dict
        ``{"total_scanned": N, "attributed": N, "unmatched": N}``
    """
    await ensure_attribution_columns()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        trades = await conn.fetch(
            """
            SELECT id, ticker, opened_at, closed_at
              FROM trades
             WHERE linked_signal_id IS NULL
             ORDER BY id
            """
        )

    total = len(trades)
    attributed = 0

    for trade in trades:
        trade_id: int = trade["id"]
        ticker: str = trade["ticker"]
        opened_at = trade["opened_at"]
        closed_at = trade["closed_at"]

        # 1. Try open-attribution
        if opened_at is not None:
            result = await attribute_trade(
                trade_id, ticker, "open", opened_at, window_hours
            )
            if result is not None:
                attributed += 1
                continue

        # 2. Try close-attribution (only if trade is closed and open didn't match)
        if closed_at is not None:
            result = await attribute_trade(
                trade_id, ticker, "close", closed_at, window_hours
            )
            if result is not None:
                attributed += 1
                continue

    summary = {
        "total_scanned": total,
        "attributed": attributed,
        "unmatched": total - attributed,
    }
    logger.info("Backfill complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_timestamp(raw: Any) -> datetime:
    """Return a timezone-naive UTC datetime suitable for comparison against
    the signals table (which stores ``TIMESTAMP`` without timezone)."""
    if raw is None:
        return datetime.utcnow()
    if isinstance(raw, str):
        normalised = raw.strip()
        if normalised.endswith("Z"):
            normalised = normalised[:-1] + "+00:00"
        raw = datetime.fromisoformat(normalised)
    if not isinstance(raw, datetime):
        return datetime.utcnow()
    # Strip timezone — DB stores naive UTC timestamps
    if raw.tzinfo is not None:
        raw = raw.astimezone(timezone.utc).replace(tzinfo=None)
    return raw
