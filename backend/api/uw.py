"""
API endpoints for receiving UW flow data from Pivot and caching in Redis.
Also broadcasts flow updates via WebSocket for real-time frontend updates.
"""
import json
import logging
from datetime import datetime, timezone

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
RECENT_LIST_MAX = 50   # Max items in the recent alerts list


@router.post("/flow")
async def receive_uw_flow(request: Request, _: str = Depends(verify_pivot_key)):
    """
    Receive per-ticker flow summaries from Pivot.
    Write each to Redis as uw:flow:{SYMBOL}.
    Also push notable trades to uw:flow:recent for the Recent Alerts feed,
    and broadcast via WebSocket for real-time frontend updates.
    """
    try:
        body = await request.json()
        summaries = body.get("summaries", [])

        client = await get_redis_client()
        if not client:
            return {"status": "error", "message": "Redis unavailable"}

        written = 0
        tickers_updated = []

        for summary in summaries:
            ticker = summary.get("ticker")
            if not ticker:
                continue
            key = f"uw:flow:{ticker.upper()}"
            await client.set(key, json.dumps(summary), ex=FLOW_TTL)
            written += 1
            tickers_updated.append(ticker.upper())

            # Push notable trade info to the recent alerts list
            # Build an alert record from the summary for the Recent Alerts feed
            alert_record = {
                "ticker": ticker.upper(),
                "sentiment": summary.get("sentiment", "UNKNOWN"),
                "type": "SWEEP" if summary.get("unusual_count", 0) > 2 else "BLOCK",
                "premium": summary.get("call_premium", 0) + summary.get("put_premium", 0),
                "net_premium": summary.get("net_premium", 0),
                "call_premium": summary.get("call_premium", 0),
                "put_premium": summary.get("put_premium", 0),
                "unusualness_score": summary.get("unusualness_score", 0),
                "unusual_count": summary.get("unusual_count", 0),
                "avg_dte": summary.get("avg_dte"),
                "source": "discord_bot",
                "received_at": datetime.now(timezone.utc).isoformat(),
                "timestamp": body.get("timestamp", datetime.now(timezone.utc).isoformat())
            }

            # Include largest trade details if available
            largest = summary.get("largest_trade")
            if largest:
                alert_record["strike"] = largest.get("strike")
                alert_record["expiry"] = largest.get("expiry")
                alert_record["option_type"] = largest.get("option_type")
                alert_record["largest_premium"] = largest.get("premium")

            await client.lpush("uw:flow:recent", json.dumps(alert_record))

        # Trim the recent list to keep it bounded
        await client.ltrim("uw:flow:recent", 0, RECENT_LIST_MAX - 1)

        # Broadcast via WebSocket for real-time frontend updates
        if written > 0:
            try:
                from websocket.broadcaster import manager
                await manager.broadcast({
                    "type": "FLOW_UPDATE",
                    "tickers_updated": tickers_updated,
                    "count": written
                })
            except Exception as e:
                logger.warning(f"Could not broadcast flow update: {e}")

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
