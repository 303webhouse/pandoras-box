"""
Dev shadow view — 3-10 Oscillator shadow-mode signals.

Returns Holy Grail signals tagged gate_type='3-10' (fired by the 3-10 gate
only, not RSI). Used during the 6-month shadow period to compare 3-10 vs RSI
signal quality. Not linked from main nav — direct URL access only.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from utils.pivot_auth import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dev", tags=["dev-shadow"])


@router.get("/shadow-3-10")
async def get_shadow_3_10_signals(
    limit: int = Query(50, ge=1, le=200),
    since_hours: int = Query(168, ge=1, le=720),
    _auth: str = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Return 3-10-only Holy Grail signals for shadow-mode review.
    X-API-Key required. No nav link — direct URL access only.

    Query params:
        limit: max signals to return (1–200, default 50)
        since_hours: how far back to look (1–720h, default 168 = 7 days)
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id, ticker, direction, gate_type, entry_price, stop_loss, target_1,
                   adx, rsi, enrichment_data, created_at
            FROM signals
            WHERE gate_type = '3-10'
              AND created_at > NOW() - ($1 * INTERVAL '1 hour')
            ORDER BY created_at DESC
            LIMIT $2
            """,
            since_hours,
            limit,
        )

    signals = []
    for r in rows:
        row_dict = dict(r)
        # enrichment_data comes back as a string from asyncpg — parse if needed
        if isinstance(row_dict.get("enrichment_data"), str):
            import json
            try:
                row_dict["enrichment_data"] = json.loads(row_dict["enrichment_data"])
            except Exception:
                pass
        # Convert datetime to ISO string for JSON serialization
        if row_dict.get("created_at"):
            row_dict["created_at"] = row_dict["created_at"].isoformat()
        signals.append(row_dict)

    return {
        "signals": signals,
        "count": len(signals),
        "since_hours": since_hours,
        "note": "gate_type=3-10 signals are shadow-mode only — not surfaced to main feed",
    }
