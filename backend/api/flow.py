"""
Options Flow API Endpoints
Unified flow data from Discord bot (UW) + manual entries

Endpoints:
- GET /flow/status - Check connection status (Redis-backed)
- GET /flow/hot - Get tickers with highest activity (Redis + in-memory)
- GET /flow/recent - Get recent flow alerts (Redis + in-memory)
- GET /flow/ticker/{ticker} - Get flow for a specific ticker
- POST /flow/manual - Manually add flow observation
- GET /flow/sentiment/{ticker} - Get flow sentiment
- GET /flow/confirm/{ticker} - Check flow confirmation for trade ideas
- POST /flow/webhook - Receive direct UW webhook alerts
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
import json
import logging

from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flow", tags=["Options Flow"])

# Import in-memory flow module (for manual entries and sentiment calculation)
from bias_filters.unusual_whales import (
    process_webhook_alert,
    get_flow_sentiment,
    get_recent_alerts as get_inmemory_recent_alerts,
    get_hot_tickers as get_inmemory_hot_tickers,
    add_manual_flow,
    calculate_flow_score_boost,
    is_configured,
    configure_unusual_whales
)


class ManualFlowEntry(BaseModel):
    """Request body for manual flow entry"""
    ticker: str
    sentiment: str  # BULLISH, BEARISH, NEUTRAL
    flow_type: str = "UNUSUAL_VOLUME"  # SWEEP, BLOCK, SPLIT, UNUSUAL_VOLUME, DARK_POOL
    premium: int = 100000
    notes: Optional[str] = None


class FlowConfigRequest(BaseModel):
    """Request body for configuring UW API"""
    api_key: str
    webhook_secret: Optional[str] = None


# =========================================================================
# REDIS HELPERS - Read UW flow data written by Discord bot
# =========================================================================

async def _get_redis_flow_summaries() -> list:
    """Scan Redis for all uw:flow:* keys and return parsed summaries."""
    client = await get_redis_client()
    if not client:
        return []

    try:
        keys = []
        cursor = b"0"
        while True:
            cursor, batch = await client.scan(cursor, match="uw:flow:*", count=100)
            # Exclude the recent list key
            keys.extend(k for k in batch if k != b"uw:flow:recent" and k != "uw:flow:recent")
            if cursor == b"0" or cursor == 0:
                break

        if not keys:
            return []

        values = await client.mget(*keys)
        summaries = []
        for val in values:
            if val:
                try:
                    summaries.append(json.loads(val))
                except (json.JSONDecodeError, TypeError):
                    pass
        return summaries
    except Exception as e:
        logger.warning(f"Error scanning Redis for flow summaries: {e}")
        return []


async def _get_redis_recent_alerts(limit: int = 20) -> list:
    """Read the uw:flow:recent Redis list for individual alert entries."""
    client = await get_redis_client()
    if not client:
        return []

    try:
        raw = await client.lrange("uw:flow:recent", 0, limit - 1)
        alerts = []
        for item in raw:
            try:
                alerts.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                pass
        return alerts
    except Exception as e:
        logger.warning(f"Error reading Redis recent alerts: {e}")
        return []


async def _get_redis_ticker_flow(ticker: str) -> dict:
    """Read UW flow summary for a specific ticker from Redis."""
    client = await get_redis_client()
    if not client:
        return None

    try:
        data = await client.get(f"uw:flow:{ticker.upper()}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Error reading Redis flow for {ticker}: {e}")
    return None


# =========================================================================
# ENDPOINTS
# =========================================================================

@router.get("/status")
async def get_flow_status():
    """
    Check if flow data is available.
    Returns connected if UW data exists in Redis (Discord bot is active),
    or if direct UW API is configured.
    """
    redis_summaries = await _get_redis_flow_summaries()
    redis_count = len(redis_summaries)

    if redis_count > 0:
        return {
            "configured": True,
            "source": "discord_bot",
            "active_tickers": redis_count,
            "message": f"Live - tracking {redis_count} tickers via UW Discord"
        }
    elif is_configured():
        return {
            "configured": True,
            "source": "api",
            "active_tickers": 0,
            "message": "Unusual Whales API configured"
        }
    else:
        return {
            "configured": False,
            "source": "manual",
            "active_tickers": 0,
            "message": "Manual mode - add flow observations manually"
        }


@router.post("/configure")
async def configure_flow(config: FlowConfigRequest):
    """Configure Unusual Whales API access"""
    try:
        configure_unusual_whales(config.api_key, config.webhook_secret)
        return {"status": "success", "message": "Unusual Whales configured"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receive webhook alerts from Unusual Whales

    Set this URL in your UW webhook settings:
    https://your-domain.com/api/flow/webhook
    """
    try:
        payload = await request.json()
        result = await process_webhook_alert(payload)
        return result
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sentiment/{ticker}")
async def get_ticker_sentiment(ticker: str):
    """
    Get current flow sentiment for a ticker.
    Checks Redis (UW bot data) first, falls back to in-memory.
    """
    try:
        # Check Redis for UW bot data
        redis_flow = await _get_redis_ticker_flow(ticker)
        if redis_flow:
            sentiment = redis_flow.get("sentiment", "UNKNOWN")
            net_premium = redis_flow.get("net_premium", 0)
            call_premium = redis_flow.get("call_premium", 0)
            put_premium = redis_flow.get("put_premium", 0)
            total_premium = call_premium + put_premium

            if total_premium > 500000:
                confidence = "HIGH"
            elif total_premium > 100000:
                confidence = "MEDIUM"
            elif total_premium > 0:
                confidence = "LOW"
            else:
                confidence = "NONE"

            return {
                "ticker": ticker.upper(),
                "sentiment": sentiment,
                "confidence": confidence,
                "total_premium": total_premium,
                "net_premium": net_premium,
                "call_premium": call_premium,
                "put_premium": put_premium,
                "recent_alerts": redis_flow.get("unusual_count", 0),
                "unusualness_score": redis_flow.get("unusualness_score", 0),
                "dominant_type": None,
                "source": "discord_bot"
            }

        # Fall back to in-memory
        sentiment = get_flow_sentiment(ticker)
        sentiment["source"] = "in_memory"
        return sentiment
    except Exception as e:
        logger.error(f"Error getting sentiment for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boost/{ticker}/{direction}")
async def get_score_boost(ticker: str, direction: str):
    """
    Calculate score boost for a signal based on flow

    Returns:
        Score adjustment (+15 if confirms, -10 if contradicts, 0 if no data)
    """
    try:
        boost = calculate_flow_score_boost(ticker, direction)
        sentiment = get_flow_sentiment(ticker)

        return {
            "ticker": ticker.upper(),
            "direction": direction.upper(),
            "score_boost": boost,
            "flow_sentiment": sentiment["sentiment"],
            "confirms": boost > 0,
            "contradicts": boost < 0
        }
    except Exception as e:
        logger.error(f"Error calculating boost: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent_flow(limit: int = 20):
    """
    Get most recent flow alerts across all tickers.
    Merges Redis alerts (from Discord bot) with in-memory manual entries.
    """
    try:
        # Get from both sources
        redis_alerts = await _get_redis_recent_alerts(limit)
        inmemory_alerts = get_inmemory_recent_alerts(limit)

        # Merge and sort by timestamp (newest first)
        combined = redis_alerts + inmemory_alerts
        combined.sort(
            key=lambda x: x.get("received_at") or x.get("timestamp") or "",
            reverse=True
        )

        return {
            "status": "success",
            "count": len(combined[:limit]),
            "alerts": combined[:limit]
        }
    except Exception as e:
        logger.error(f"Error getting recent flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hot")
async def get_hot_flow():
    """
    Get tickers with highest flow activity.
    Merges Redis summaries (from Discord bot) with in-memory data.
    """
    try:
        # Get UW bot summaries from Redis
        redis_summaries = await _get_redis_flow_summaries()

        # Convert Redis summaries to hot ticker format
        redis_hot = []
        for s in redis_summaries:
            ticker = s.get("ticker")
            if not ticker:
                continue
            call_premium = s.get("call_premium", 0)
            put_premium = s.get("put_premium", 0)
            total_premium = call_premium + put_premium

            redis_hot.append({
                "ticker": ticker,
                "sentiment": s.get("sentiment", "UNKNOWN"),
                "total_premium": total_premium,
                "net_premium": s.get("net_premium", 0),
                "call_premium": call_premium,
                "put_premium": put_premium,
                "alert_count": s.get("unusual_count", 0),
                "unusualness_score": s.get("unusualness_score", 0),
                "avg_dte": s.get("avg_dte"),
                "largest_trade": s.get("largest_trade"),
                "last_updated": s.get("last_updated"),
                "source": "discord_bot"
            })

        # Get in-memory hot tickers (manual entries)
        inmemory_hot = get_inmemory_hot_tickers()
        for h in inmemory_hot:
            h["source"] = "manual"

        # Merge: Redis tickers take priority, add any manual-only tickers
        redis_tickers = {h["ticker"] for h in redis_hot}
        for h in inmemory_hot:
            if h["ticker"] not in redis_tickers:
                redis_hot.append(h)

        # Sort by unusualness score (if available) then by total premium
        redis_hot.sort(
            key=lambda x: (x.get("unusualness_score", 0), x.get("total_premium", 0)),
            reverse=True
        )

        return {
            "status": "success",
            "count": len(redis_hot[:15]),
            "tickers": redis_hot[:15]
        }
    except Exception as e:
        logger.error(f"Error getting hot tickers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ticker/{ticker}")
async def get_ticker_flow(ticker: str):
    """
    Get full flow data for a specific ticker.
    Returns UW bot summary from Redis if available.
    """
    try:
        redis_flow = await _get_redis_ticker_flow(ticker)

        if redis_flow:
            return {
                "status": "success",
                "available": True,
                "flow": redis_flow,
                "source": "discord_bot"
            }

        # Fall back to in-memory sentiment
        sentiment = get_flow_sentiment(ticker)
        if sentiment.get("sentiment") != "UNKNOWN":
            return {
                "status": "success",
                "available": True,
                "flow": sentiment,
                "source": "in_memory"
            }

        return {
            "status": "success",
            "available": False,
            "flow": None
        }
    except Exception as e:
        logger.error(f"Error getting flow for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual")
async def add_manual_observation(entry: ManualFlowEntry):
    """
    Manually add a flow observation.
    Stores in both in-memory cache AND Redis for persistence.
    """
    try:
        # Store in in-memory cache
        result = await add_manual_flow(
            ticker=entry.ticker,
            sentiment=entry.sentiment,
            flow_type=entry.flow_type,
            premium=entry.premium,
            notes=entry.notes
        )

        # Also store in Redis for persistence and merging
        await _store_manual_in_redis(entry)

        return result
    except Exception as e:
        logger.error(f"Error adding manual flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _store_manual_in_redis(entry: ManualFlowEntry):
    """Write a manual flow entry to Redis so it persists and merges with UW data."""
    client = await get_redis_client()
    if not client:
        return

    try:
        from datetime import datetime

        ticker = entry.ticker.upper()

        # Build an alert record for the recent list
        alert_record = {
            "ticker": ticker,
            "type": entry.flow_type,
            "sentiment": entry.sentiment.upper(),
            "premium": entry.premium,
            "notes": entry.notes,
            "source": "manual",
            "received_at": datetime.now().isoformat(),
            "timestamp": datetime.now().isoformat()
        }

        # Push to recent alerts list
        await client.lpush("uw:flow:recent", json.dumps(alert_record))
        await client.ltrim("uw:flow:recent", 0, 49)

        # Update per-ticker summary if no UW bot data exists
        existing = await client.get(f"uw:flow:{ticker}")
        if not existing:
            summary = {
                "ticker": ticker,
                "sentiment": entry.sentiment.upper(),
                "net_premium": entry.premium if entry.sentiment.upper() == "BULLISH" else -entry.premium,
                "call_premium": entry.premium if entry.sentiment.upper() == "BULLISH" else 0,
                "put_premium": entry.premium if entry.sentiment.upper() == "BEARISH" else 0,
                "unusual_count": 1,
                "unusualness_score": 0,
                "source": "manual",
                "last_updated": datetime.now().isoformat()
            }
            await client.set(f"uw:flow:{ticker}", json.dumps(summary), ex=3600)

        logger.info(f"Manual flow stored in Redis: {ticker} {entry.sentiment} ${entry.premium:,}")
    except Exception as e:
        logger.warning(f"Could not store manual flow in Redis: {e}")


@router.get("/confirm/{ticker}")
async def check_flow_confirmation(ticker: str, direction: str = "LONG"):
    """
    Check if flow confirms a trade idea.

    Returns:
    - CONFIRMED if flow aligns with direction
    - CONTRADICTED if flow goes against direction
    - NO_DATA if no recent flow
    """
    try:
        # Check Redis first for UW bot data
        redis_flow = await _get_redis_ticker_flow(ticker)

        if redis_flow and redis_flow.get("sentiment") not in (None, "UNKNOWN"):
            sentiment = redis_flow["sentiment"]
            net_premium = redis_flow.get("net_premium", 0)
            total_premium = redis_flow.get("call_premium", 0) + redis_flow.get("put_premium", 0)
            score = redis_flow.get("unusualness_score", 0)

            direction_upper = direction.upper()
            if direction_upper in ["LONG", "BUY", "BULLISH"]:
                confirms = sentiment == "BULLISH"
                contradicts = sentiment == "BEARISH"
            else:
                confirms = sentiment == "BEARISH"
                contradicts = sentiment == "BULLISH"

            if confirms:
                return {
                    "ticker": ticker.upper(),
                    "direction": direction_upper,
                    "status": "CONFIRMED",
                    "emoji": "✅",
                    "message": f"Flow confirms {direction}: {sentiment} sentiment with ${total_premium:,.0f} premium (score: {score:.0f})",
                    "score_boost": 15,
                    "details": redis_flow
                }
            elif contradicts:
                return {
                    "ticker": ticker.upper(),
                    "direction": direction_upper,
                    "status": "CONTRADICTED",
                    "emoji": "⚠️",
                    "message": f"Flow contradicts {direction}: {sentiment} sentiment detected",
                    "score_boost": -10,
                    "details": redis_flow
                }
            else:
                return {
                    "ticker": ticker.upper(),
                    "direction": direction_upper,
                    "status": "NEUTRAL",
                    "emoji": "➖",
                    "message": f"Mixed flow for {ticker}",
                    "score_boost": 0,
                    "details": redis_flow
                }

        # Fall back to in-memory
        sentiment = get_flow_sentiment(ticker)
        boost = calculate_flow_score_boost(ticker, direction)

        if sentiment["sentiment"] == "UNKNOWN" or sentiment["confidence"] == "NONE":
            status = "NO_DATA"
            emoji = "➖"
            message = f"No recent flow data for {ticker}"
        elif boost > 0:
            status = "CONFIRMED"
            emoji = "✅"
            message = f"Flow confirms {direction}: {sentiment['sentiment']} sentiment with ${sentiment['total_premium']:,} premium"
        elif boost < 0:
            status = "CONTRADICTED"
            emoji = "⚠️"
            message = f"Flow contradicts {direction}: {sentiment['sentiment']} sentiment detected"
        else:
            status = "NEUTRAL"
            emoji = "➖"
            message = f"Mixed flow for {ticker}"

        return {
            "ticker": ticker.upper(),
            "direction": direction.upper(),
            "status": status,
            "emoji": emoji,
            "message": message,
            "score_boost": boost,
            "details": sentiment
        }
    except Exception as e:
        logger.error(f"Error checking confirmation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
