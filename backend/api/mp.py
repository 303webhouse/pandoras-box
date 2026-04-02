"""
PYTHIA Market Profile Levels — API Endpoints

GET /mp/levels/{ticker}  — Get cached MP levels for a ticker
GET /mp/levels           — Get all cached MP levels
"""
import json
import logging

from fastapi import APIRouter

from database.redis_client import get_redis_client

logger = logging.getLogger("mp_api")
router = APIRouter(prefix="/mp")


@router.get("/levels/{ticker}")
async def get_mp_levels(ticker: str):
    """Get cached Market Profile levels for a specific ticker."""
    redis = await get_redis_client()
    if not redis:
        return {"available": False, "levels": None}

    key = f"mp_levels:{ticker.upper()}"
    data = await redis.get(key)
    if data:
        return {"available": True, "levels": json.loads(data)}
    return {"available": False, "levels": None}


@router.get("/levels")
async def get_all_mp_levels():
    """Return MP levels for all tickers that have them cached."""
    redis = await get_redis_client()
    if not redis:
        return {"available": False, "levels": {}}

    keys = await redis.keys("mp_levels:*")
    result = {}
    for key in keys:
        ticker = key.split(":")[1] if isinstance(key, str) else key.decode().split(":")[1]
        data = await redis.get(key)
        if data:
            result[ticker] = json.loads(data)
    return {"available": bool(result), "levels": result}
