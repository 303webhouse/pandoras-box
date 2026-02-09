"""
API endpoints for receiving UW flow data from Pivot and caching in Redis.
"""
import json
import logging

from fastapi import APIRouter, Request, Depends

from database.redis_client import get_redis_client

try:
    from utils.pivot_auth import verify_pivot_key
except Exception:  # pragma: no cover
    from backend.utils.pivot_auth import verify_pivot_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uw", tags=["unusual-whales"])

FLOW_TTL = 3600        # 1 hour
DISCOVERY_TTL = 14400  # 4 hours


@router.post("/flow")
async def receive_uw_flow(request: Request, _: str = Depends(verify_pivot_key)):
    """
    Receive per-ticker flow summaries from Pivot.
    Write each to Redis as uw:flow:{SYMBOL}.
    """
    try:
        body = await request.json()
        summaries = body.get("summaries", [])

        client = await get_redis_client()
        if not client:
            return {"status": "error", "message": "Redis unavailable"}

        written = 0
        for summary in summaries:
            ticker = summary.get("ticker")
            if not ticker:
                continue
            key = f"uw:flow:{ticker.upper()}"
            await client.set(key, json.dumps(summary), ex=FLOW_TTL)
            written += 1

        logger.info("UW flow: cached %s ticker summaries", written)
        return {"status": "success", "cached": written}

    except Exception as e:
        logger.error(f"Error receiving UW flow: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/discovery")
async def receive_uw_discovery(request: Request, _: str = Depends(verify_pivot_key)):
    """
    Receive discovery list from Pivot.
    Write to Redis as uw:discovery (single key, list of tickers or dicts).
    """
    try:
        body = await request.json()
        tickers = body.get("tickers", [])

        client = await get_redis_client()
        if not client:
            return {"status": "error", "message": "Redis unavailable"}

        await client.set("uw:discovery", json.dumps(tickers), ex=DISCOVERY_TTL)

        logger.info("UW discovery: cached %s tickers", len(tickers))
        return {"status": "success", "cached": len(tickers)}

    except Exception as e:
        logger.error(f"Error receiving UW discovery: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/flow/{ticker}")
async def get_uw_flow(ticker: str):
    """
    Read cached UW flow data for a specific ticker.
    Used by the frontend to display flow context alongside signals.
    """
    client = await get_redis_client()
    if not client:
        return {"status": "error", "available": False}

    data = await client.get(f"uw:flow:{ticker.upper()}")
    if data:
        return {"status": "success", "available": True, "flow": json.loads(data)}
    return {"status": "success", "available": False, "flow": None}


@router.get("/discovery")
async def get_uw_discovery():
    """
    Read the current discovery list.
    Used by the dashboard and the CTA scanner.
    """
    client = await get_redis_client()
    if not client:
        return {"status": "error", "tickers": []}

    data = await client.get("uw:discovery")
    if data:
        return {"status": "success", "tickers": json.loads(data)}
    return {"status": "success", "tickers": []}
