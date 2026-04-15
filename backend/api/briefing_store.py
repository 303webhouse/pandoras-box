"""
Briefing storage — stores and retrieves pre-market briefing summaries.

POST /api/briefing/premarket — store a new briefing (from VPS premarket script)
GET  /api/briefing/premarket  — retrieve last N briefings (for PIVOT context)
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from database.redis_client import get_redis_client
from utils.pivot_auth import require_api_key

logger = logging.getLogger("api.briefing_store")
router = APIRouter()

REDIS_KEY = "briefing:premarket:history"
MAX_ENTRIES = 5
TTL_SECONDS = 604800  # 7 days


class BriefingEntry(BaseModel):
    date: str
    synthesis: str
    conviction: str = "MEDIUM"
    invalidation: Optional[str] = None


@router.post("/briefing/premarket")
async def store_briefing(entry: BriefingEntry, _=Depends(require_api_key)):
    """Store a pre-market briefing summary (called by VPS premarket script)."""
    redis = await get_redis_client()
    if not redis:
        return {"status": "error", "detail": "Redis unavailable"}

    value = entry.model_dump_json()
    await redis.lpush(REDIS_KEY, value)
    await redis.ltrim(REDIS_KEY, 0, MAX_ENTRIES - 1)
    await redis.expire(REDIS_KEY, TTL_SECONDS)

    logger.info("Stored premarket briefing for %s (conviction=%s)", entry.date, entry.conviction)
    return {"status": "ok", "date": entry.date}


@router.get("/briefing/premarket")
async def get_briefings(limit: int = Query(5, ge=1, le=10)):
    """Retrieve recent pre-market briefings."""
    redis = await get_redis_client()
    if not redis:
        return {"briefings": [], "count": 0}

    raw = await redis.lrange(REDIS_KEY, 0, limit - 1)
    briefings = []
    for item in raw:
        try:
            briefings.append(json.loads(item))
        except Exception:
            continue

    return {"briefings": briefings, "count": len(briefings)}
