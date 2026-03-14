"""
Footprint vs Whale Hunter Correlation Engine

Compares FOOTPRINT and DARK_POOL signals over a time window to measure
confluence and relative performance. Forward-test: Mar 14 – Mar 28, 2026.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from database.postgres_client import get_postgres_client, serialize_db_row

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics/footprint-correlation")
async def footprint_correlation(
    days: int = Query(default=14, ge=1, le=90),
    window_minutes: int = Query(default=30, ge=5, le=120),
):
    """
    Compute correlation between Whale Hunter (DARK_POOL) and Footprint signals.

    Buckets:
    - whale_solo: DARK_POOL with no FOOTPRINT within window
    - footprint_solo: FOOTPRINT with no DARK_POOL within window
    - confluence: both fired within window on same ticker
    """
    pool = await get_postgres_client()

    cutoff = datetime.utcnow() - timedelta(days=days)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT signal_id, ticker, signal_category, direction,
                   created_at, user_action, status
            FROM signals
            WHERE signal_category IN ('DARK_POOL', 'FOOTPRINT')
              AND created_at > $1
            ORDER BY created_at ASC
        """, cutoff)

    if not rows:
        return {
            "period_days": days,
            "window_minutes": window_minutes,
            "buckets": {
                "whale_solo": {"count": 0, "wins": 0, "losses": 0, "pending": 0, "win_rate": None},
                "footprint_solo": {"count": 0, "wins": 0, "losses": 0, "pending": 0, "win_rate": None},
                "confluence": {"count": 0, "wins": 0, "losses": 0, "pending": 0, "win_rate": None},
            },
            "signals": [],
        }

    # Parse into dicts
    signals = []
    for r in rows:
        signals.append({
            "signal_id": r["signal_id"],
            "ticker": (r["ticker"] or "").upper(),
            "category": r["signal_category"],
            "direction": r["direction"],
            "created_at": r["created_at"],
            "user_action": r["user_action"],
            "status": r["status"],
        })

    window_td = timedelta(minutes=window_minutes)

    # Build confluence pairs: for each signal, check if opposite category exists
    # within window on same ticker
    confluence_ids = set()
    for i, sig in enumerate(signals):
        for j, other in enumerate(signals):
            if i == j:
                continue
            if sig["ticker"] != other["ticker"]:
                continue
            if sig["category"] == other["category"]:
                continue
            if abs((sig["created_at"] - other["created_at"]).total_seconds()) <= window_minutes * 60:
                confluence_ids.add(sig["signal_id"])
                confluence_ids.add(other["signal_id"])

    # Classify each signal
    result_signals = []
    buckets = {
        "whale_solo": {"count": 0, "wins": 0, "losses": 0, "pending": 0},
        "footprint_solo": {"count": 0, "wins": 0, "losses": 0, "pending": 0},
        "confluence": {"count": 0, "wins": 0, "losses": 0, "pending": 0},
    }

    for sig in signals:
        if sig["signal_id"] in confluence_ids:
            bucket = "confluence"
        elif sig["category"] == "DARK_POOL":
            bucket = "whale_solo"
        else:
            bucket = "footprint_solo"

        # Determine outcome
        action = (sig["user_action"] or "").upper()
        status = (sig["status"] or "").upper()
        if action == "SELECTED" or status in ("ACCEPTED_STOCKS", "ACCEPTED_OPTIONS"):
            outcome = "win"
        elif action == "DISMISSED" or status == "DISMISSED":
            outcome = "loss"
        elif status == "EXPIRED":
            outcome = "expired"
        else:
            outcome = "pending"

        buckets[bucket]["count"] += 1
        if outcome == "win":
            buckets[bucket]["wins"] += 1
        elif outcome == "loss":
            buckets[bucket]["losses"] += 1
        else:
            buckets[bucket]["pending"] += 1

        result_signals.append({
            "signal_id": sig["signal_id"],
            "ticker": sig["ticker"],
            "category": sig["category"],
            "direction": sig["direction"],
            "bucket": bucket,
            "created_at": sig["created_at"].isoformat() + "Z" if sig["created_at"] else None,
            "outcome": outcome,
        })

    # Compute win rates
    for b in buckets.values():
        decided = b["wins"] + b["losses"]
        b["win_rate"] = round(b["wins"] / decided * 100, 1) if decided > 0 else None

    return {
        "period_days": days,
        "window_minutes": window_minutes,
        "buckets": buckets,
        "signals": result_signals,
    }
