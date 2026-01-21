"""
Options Flow API Endpoints
Unusual Whales Integration for Flow Confirmation

Endpoints:
- POST /flow/webhook - Receive alerts from Unusual Whales
- GET /flow/sentiment/{ticker} - Get flow sentiment for ticker
- GET /flow/recent - Get recent flow alerts
- GET /flow/hot - Get tickers with highest activity
- POST /flow/manual - Manually add flow observation
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flow", tags=["Options Flow"])

# Import flow module
from bias_filters.unusual_whales import (
    process_webhook_alert,
    get_flow_sentiment,
    get_recent_alerts,
    get_hot_tickers,
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


@router.get("/status")
async def get_flow_status():
    """Check if Unusual Whales integration is configured"""
    return {
        "configured": is_configured(),
        "message": "Unusual Whales integration ready" if is_configured() 
                   else "Not configured - add API key to enable"
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
    Get current flow sentiment for a ticker
    
    Returns sentiment (BULLISH/BEARISH/NEUTRAL), confidence,
    total premium, and recent alert count.
    """
    try:
        sentiment = get_flow_sentiment(ticker)
        return sentiment
    except Exception as e:
        logger.error(f"Error getting sentiment for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boost/{ticker}/{direction}")
async def get_score_boost(ticker: str, direction: str):
    """
    Calculate score boost for a signal based on flow
    
    Args:
        ticker: Stock ticker (e.g., AAPL)
        direction: LONG or SHORT
    
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
    """Get most recent flow alerts across all tickers"""
    try:
        alerts = get_recent_alerts(limit)
        return {
            "status": "success",
            "count": len(alerts),
            "alerts": alerts
        }
    except Exception as e:
        logger.error(f"Error getting recent flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hot")
async def get_hot_flow():
    """
    Get tickers with highest flow activity
    
    These are stocks with unusual options activity right now.
    Great for finding momentum plays or confirming your signals.
    """
    try:
        hot = get_hot_tickers()
        return {
            "status": "success",
            "count": len(hot),
            "tickers": hot
        }
    except Exception as e:
        logger.error(f"Error getting hot tickers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual")
async def add_manual_observation(entry: ManualFlowEntry):
    """
    Manually add a flow observation
    
    Use this when you see unusual activity on Unusual Whales
    but haven't set up the webhook yet.
    
    Example:
    {
        "ticker": "NVDA",
        "sentiment": "BULLISH",
        "flow_type": "SWEEP",
        "premium": 500000,
        "notes": "Large call sweep, Jan 26 expiry"
    }
    """
    try:
        result = await add_manual_flow(
            ticker=entry.ticker,
            sentiment=entry.sentiment,
            flow_type=entry.flow_type,
            premium=entry.premium,
            notes=entry.notes
        )
        return result
    except Exception as e:
        logger.error(f"Error adding manual flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/confirm/{ticker}")
async def check_flow_confirmation(ticker: str, direction: str = "LONG"):
    """
    Check if flow confirms a trade idea
    
    Quick endpoint to check before taking a trade.
    
    Example: /flow/confirm/AAPL?direction=LONG
    
    Returns:
    - ✅ CONFIRMED if bullish flow for LONG (or bearish for SHORT)
    - ⚠️ CONTRADICTED if flow goes against your direction
    - ➖ NO DATA if no recent flow
    """
    try:
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
