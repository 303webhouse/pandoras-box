"""
Committee History API — stores and retrieves committee review recommendations.
Enables Claude.ai / Cowork to query historical committee decisions without
scrolling Discord.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request
from utils.pivot_auth import require_api_key
from fastapi import Depends

from database.postgres_client import get_postgres_client

logger = logging.getLogger("committee_history")
router = APIRouter(prefix="/committee", tags=["committee-history"])


@router.get("/history")
async def get_committee_history(
    ticker: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    _=Depends(require_api_key),
):
    """Retrieve recent committee recommendations."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if ticker:
            rows = await conn.fetch(
                """SELECT signal_id, ticker, action, conviction, synthesis,
                          invalidation, structure, levels, size, raw_json, timestamp
                   FROM committee_recommendations
                   WHERE ticker = $1
                   ORDER BY timestamp DESC LIMIT $2""",
                ticker.upper(), limit,
            )
        else:
            rows = await conn.fetch(
                """SELECT signal_id, ticker, action, conviction, synthesis,
                          invalidation, structure, levels, size, raw_json, timestamp
                   FROM committee_recommendations
                   ORDER BY timestamp DESC LIMIT $1""",
                limit,
            )

    recommendations = []
    for r in rows:
        rec = {
            "signal_id": r["signal_id"],
            "ticker": r["ticker"],
            "action": r["action"],
            "conviction": r["conviction"],
            "synthesis": r["synthesis"],
            "invalidation": r["invalidation"],
            "structure": r["structure"],
            "levels": r["levels"],
            "size": r["size"],
            "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
        }
        if r["raw_json"]:
            rec["raw"] = r["raw_json"]
        recommendations.append(rec)

    return {"recommendations": recommendations, "count": len(recommendations)}


@router.post("/history")
async def store_committee_recommendation(request: Request, _=Depends(require_api_key)):
    """Store a committee recommendation (called by VPS bridge after review)."""
    body = await request.json()
    signal_id = body.get("signal_id")
    if not signal_id:
        return {"error": "signal_id required"}

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO committee_recommendations
               (signal_id, ticker, action, conviction, synthesis,
                invalidation, structure, levels, size, raw_json)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
               ON CONFLICT (signal_id) DO UPDATE SET
                   action = EXCLUDED.action,
                   conviction = EXCLUDED.conviction,
                   synthesis = EXCLUDED.synthesis,
                   invalidation = EXCLUDED.invalidation,
                   raw_json = EXCLUDED.raw_json,
                   timestamp = NOW()""",
            signal_id,
            (body.get("ticker") or "").upper(),
            body.get("action"),
            body.get("conviction"),
            body.get("synthesis"),
            body.get("invalidation"),
            body.get("structure"),
            body.get("levels"),
            body.get("size"),
            json.dumps(body) if body else None,
        )

    logger.info("Committee recommendation stored: %s %s %s",
                body.get("ticker"), body.get("action"), body.get("conviction"))
    return {"status": "ok", "signal_id": signal_id}
