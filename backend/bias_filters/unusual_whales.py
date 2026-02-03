"""
Unusual Whales Integration
Options Flow & Dark Pool Data for Signal Confirmation

When connected, this module will:
1. Receive flow alerts via webhook or API polling
2. Track unusual options activity by ticker
3. Boost CTA/other signal scores when flow confirms direction
4. Alert on high-conviction flow (large premium, sweeps, etc.)

Requires: Unusual Whales subscription (~$40/mo)
API Docs: https://docs.unusualwhales.com/
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class FlowSentiment(str, Enum):
    """Options flow sentiment"""
    BULLISH = "BULLISH"      # Heavy call buying, put selling
    BEARISH = "BEARISH"      # Heavy put buying, call selling
    NEUTRAL = "NEUTRAL"      # Mixed or low activity
    UNKNOWN = "UNKNOWN"      # No data


class FlowType(str, Enum):
    """Type of unusual flow"""
    SWEEP = "SWEEP"          # Aggressive, hits multiple exchanges
    BLOCK = "BLOCK"          # Large single transaction
    SPLIT = "SPLIT"          # Broken into pieces to hide size
    UNUSUAL_VOLUME = "UNUSUAL_VOLUME"  # Volume >> open interest
    DARK_POOL = "DARK_POOL"  # Off-exchange print


# In-memory storage for flow data
# In production, this would be in Redis with TTL
_flow_cache: Dict[str, Dict[str, Any]] = {}
_recent_alerts: List[Dict[str, Any]] = []
_highest_volume_cache: Dict[str, Any] = {
    "contracts": [],
    "total_calls": 0,
    "total_puts": 0,
    "sentiment": FlowSentiment.UNKNOWN,
    "last_updated": None
}

# Configuration
UW_CONFIG = {
    "enabled": False,  # Set to True when API key is configured
    "api_key": None,   # Set via environment variable
    "webhook_secret": None,  # For webhook verification
    "min_premium_threshold": 50000,  # $50k minimum to track
    "lookback_minutes": 60,  # How long to remember flow
    "score_boost": {
        "sweep": 15,
        "block": 10,
        "unusual_volume": 8,
        "dark_pool": 5
    }
}


def configure_unusual_whales(api_key: str, webhook_secret: str = None):
    """Configure Unusual Whales API access"""
    global UW_CONFIG
    UW_CONFIG["api_key"] = api_key
    UW_CONFIG["webhook_secret"] = webhook_secret
    UW_CONFIG["enabled"] = True
    logger.info("✅ Unusual Whales integration configured")


def is_configured() -> bool:
    """Check if Unusual Whales is configured"""
    return UW_CONFIG["enabled"] and UW_CONFIG["api_key"] is not None


async def process_webhook_alert(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process incoming webhook from Unusual Whales
    
    Expected payload format (example):
    {
        "ticker": "AAPL",
        "type": "SWEEP",
        "sentiment": "BULLISH",
        "strike": 230,
        "expiry": "2026-01-23",
        "premium": 150000,
        "volume": 500,
        "open_interest": 1200,
        "timestamp": "2026-01-21T14:30:00Z"
    }
    """
    ticker = payload.get("ticker", "").upper()
    
    if not ticker:
        return {"status": "error", "message": "No ticker provided"}
    
    # Create flow record
    flow_record = {
        "ticker": ticker,
        "type": payload.get("type", "UNKNOWN"),
        "sentiment": payload.get("sentiment", "NEUTRAL"),
        "strike": payload.get("strike"),
        "expiry": payload.get("expiry"),
        "premium": payload.get("premium", 0),
        "volume": payload.get("volume", 0),
        "open_interest": payload.get("open_interest", 0),
        "timestamp": payload.get("timestamp", datetime.now().isoformat()),
        "received_at": datetime.now().isoformat()
    }
    
    # Store in cache
    if ticker not in _flow_cache:
        _flow_cache[ticker] = {
            "alerts": [],
            "sentiment": FlowSentiment.UNKNOWN,
            "total_premium": 0,
            "last_updated": None
        }
    
    _flow_cache[ticker]["alerts"].append(flow_record)
    _flow_cache[ticker]["last_updated"] = datetime.now().isoformat()
    
    # Update sentiment based on recent flow
    _update_ticker_sentiment(ticker)
    
    # Add to recent alerts (keep last 50)
    _recent_alerts.insert(0, flow_record)
    if len(_recent_alerts) > 50:
        _recent_alerts.pop()
    
    logger.info(f"🐋 UW Alert: {ticker} {flow_record['type']} {flow_record['sentiment']} ${flow_record['premium']:,}")
    
    return {"status": "success", "flow": flow_record}


def _update_ticker_sentiment(ticker: str):
    """Update overall sentiment for a ticker based on recent flow"""
    if ticker not in _flow_cache:
        return
    
    cache = _flow_cache[ticker]
    alerts = cache["alerts"]
    
    # Only consider recent alerts (within lookback window)
    cutoff = datetime.now() - timedelta(minutes=UW_CONFIG["lookback_minutes"])
    recent = [a for a in alerts if datetime.fromisoformat(a["received_at"]) > cutoff]
    
    if not recent:
        cache["sentiment"] = FlowSentiment.UNKNOWN
        return
    
    # Calculate sentiment
    bullish_premium = sum(a["premium"] for a in recent if a["sentiment"] == "BULLISH")
    bearish_premium = sum(a["premium"] for a in recent if a["sentiment"] == "BEARISH")
    total_premium = bullish_premium + bearish_premium
    
    cache["total_premium"] = total_premium
    
    if total_premium == 0:
        cache["sentiment"] = FlowSentiment.NEUTRAL
    elif bullish_premium > bearish_premium * 1.5:
        cache["sentiment"] = FlowSentiment.BULLISH
    elif bearish_premium > bullish_premium * 1.5:
        cache["sentiment"] = FlowSentiment.BEARISH
    else:
        cache["sentiment"] = FlowSentiment.NEUTRAL


def get_flow_sentiment(ticker: str) -> Dict[str, Any]:
    """
    Get current flow sentiment for a ticker
    
    Returns:
    {
        "ticker": "AAPL",
        "sentiment": "BULLISH",
        "confidence": "HIGH",
        "total_premium": 500000,
        "recent_alerts": 5,
        "dominant_type": "SWEEP"
    }
    """
    ticker = ticker.upper()
    
    if ticker not in _flow_cache:
        return {
            "ticker": ticker,
            "sentiment": FlowSentiment.UNKNOWN,
            "confidence": "NONE",
            "total_premium": 0,
            "recent_alerts": 0,
            "dominant_type": None,
            "message": "No flow data available"
        }
    
    cache = _flow_cache[ticker]
    alerts = cache["alerts"]
    
    # Filter to recent
    cutoff = datetime.now() - timedelta(minutes=UW_CONFIG["lookback_minutes"])
    recent = [a for a in alerts if datetime.fromisoformat(a["received_at"]) > cutoff]
    
    # Determine confidence
    total = cache.get("total_premium", 0)
    if total > 500000:
        confidence = "HIGH"
    elif total > 100000:
        confidence = "MEDIUM"
    elif total > 0:
        confidence = "LOW"
    else:
        confidence = "NONE"
    
    # Find dominant flow type
    type_counts = {}
    for a in recent:
        t = a.get("type", "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1
    dominant_type = max(type_counts, key=type_counts.get) if type_counts else None
    
    return {
        "ticker": ticker,
        "sentiment": cache["sentiment"],
        "confidence": confidence,
        "total_premium": total,
        "recent_alerts": len(recent),
        "dominant_type": dominant_type,
        "last_updated": cache.get("last_updated")
    }


def calculate_flow_score_boost(ticker: str, direction: str) -> int:
    """
    Calculate score boost for a signal based on flow confirmation
    
    Args:
        ticker: Stock ticker
        direction: "LONG" or "SHORT"
    
    Returns:
        Score boost (0 if no confirmation, positive if confirms, negative if contradicts)
    """
    flow = get_flow_sentiment(ticker)
    
    if flow["sentiment"] == FlowSentiment.UNKNOWN:
        return 0
    
    # Check if flow confirms direction
    direction = direction.upper()
    
    if direction in ["LONG", "BUY", "BULLISH"]:
        if flow["sentiment"] == FlowSentiment.BULLISH:
            # Flow confirms bullish
            boost = UW_CONFIG["score_boost"].get(flow["dominant_type"].lower(), 5)
            if flow["confidence"] == "HIGH":
                boost *= 1.5
            return int(boost)
        elif flow["sentiment"] == FlowSentiment.BEARISH:
            # Flow contradicts - reduce score
            return -10
    
    elif direction in ["SHORT", "SELL", "BEARISH"]:
        if flow["sentiment"] == FlowSentiment.BEARISH:
            # Flow confirms bearish
            boost = UW_CONFIG["score_boost"].get(flow["dominant_type"].lower(), 5)
            if flow["confidence"] == "HIGH":
                boost *= 1.5
            return int(boost)
        elif flow["sentiment"] == FlowSentiment.BULLISH:
            # Flow contradicts - reduce score
            return -10
    
    return 0


def get_recent_alerts(limit: int = 20) -> List[Dict[str, Any]]:
    """Get most recent flow alerts across all tickers"""
    return _recent_alerts[:limit]


def get_hot_tickers() -> List[Dict[str, Any]]:
    """Get tickers with highest recent flow activity"""
    hot = []
    
    for ticker, cache in _flow_cache.items():
        if cache.get("total_premium", 0) > UW_CONFIG["min_premium_threshold"]:
            hot.append({
                "ticker": ticker,
                "sentiment": cache["sentiment"],
                "total_premium": cache["total_premium"],
                "alert_count": len(cache["alerts"]),
                "last_updated": cache.get("last_updated")
            })
    
    # Sort by premium
    hot.sort(key=lambda x: x["total_premium"], reverse=True)
    
    return hot[:10]


def clear_old_data():
    """Clear flow data older than lookback window"""
    cutoff = datetime.now() - timedelta(minutes=UW_CONFIG["lookback_minutes"] * 2)
    
    for ticker in list(_flow_cache.keys()):
        cache = _flow_cache[ticker]
        cache["alerts"] = [
            a for a in cache["alerts"]
            if datetime.fromisoformat(a["received_at"]) > cutoff
        ]
        
        if not cache["alerts"]:
            del _flow_cache[ticker]
    
    # Clear old recent alerts
    global _recent_alerts
    _recent_alerts = [
        a for a in _recent_alerts
        if datetime.fromisoformat(a["received_at"]) > cutoff
    ]


async def process_highest_volume(
    contracts: List[Dict[str, Any]],
    total_calls: Optional[int] = None,
    total_puts: Optional[int] = None
) -> Dict[str, Any]:
    """
    Store highest volume contracts and derive a simple sentiment.
    """
    calls = total_calls
    puts = total_puts

    if calls is None or puts is None:
        calls = 0
        puts = 0
        for contract in contracts:
            option_type = str(contract.get("option_type", "")).upper()
            if option_type in ["CALL", "C"]:
                calls += 1
            elif option_type in ["PUT", "P"]:
                puts += 1

    if calls > puts * 1.5:
        sentiment = FlowSentiment.BULLISH
    elif puts > calls * 1.5:
        sentiment = FlowSentiment.BEARISH
    else:
        sentiment = FlowSentiment.NEUTRAL

    _highest_volume_cache["contracts"] = contracts
    _highest_volume_cache["total_calls"] = calls
    _highest_volume_cache["total_puts"] = puts
    _highest_volume_cache["sentiment"] = sentiment
    _highest_volume_cache["last_updated"] = datetime.now().isoformat()

    logger.info(
        f"📊 Highest Volume stored: {len(contracts)} contracts, "
        f"calls={calls}, puts={puts}, sentiment={sentiment}"
    )

    return _highest_volume_cache.copy()


# Manual flow entry (for when API isn't connected)
async def add_manual_flow(
    ticker: str,
    sentiment: str,
    flow_type: str = "UNUSUAL_VOLUME",
    premium: int = 100000,
    notes: str = None
) -> Dict[str, Any]:
    """
    Manually add flow observation
    Use this when you see something on UW but webhook isn't set up
    """
    payload = {
        "ticker": ticker.upper(),
        "type": flow_type,
        "sentiment": sentiment.upper(),
        "premium": premium,
        "notes": notes,
        "source": "manual"
    }
    
    return await process_webhook_alert(payload)
