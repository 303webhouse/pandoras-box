"""
Coinalyze API Client
Fetches real-time BTC derivatives data: funding rates, open interest, liquidations

API Documentation: https://api.coinalyze.net/v1/doc/
Rate Limit: 40 calls/minute
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger(__name__)

# API Configuration
COINALYZE_BASE_URL = "https://api.coinalyze.net/v1"
COINALYZE_API_KEY = os.getenv("COINALYZE_API_KEY", "")

# BTC perpetual symbols across major exchanges (aggregated)
BTC_PERP_SYMBOLS = [
    "BTCUSDT_PERP.A",  # Aggregated across all exchanges
]

# Cache for API responses (avoid hitting rate limits)
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    """Get cached response if not expired"""
    if key in _cache:
        cached = _cache[key]
        if datetime.now(timezone.utc) < cached["expires_at"]:
            return cached["data"]
    return None


def _set_cache(key: str, data: Any, ttl: int = CACHE_TTL_SECONDS):
    """Cache response with TTL"""
    _cache[key] = {
        "data": data,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl)
    }


async def _make_request(endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict]:
    """Make authenticated request to Coinalyze API"""
    if not COINALYZE_API_KEY:
        logger.warning("COINALYZE_API_KEY not set - cannot fetch data")
        return None
    
    url = f"{COINALYZE_BASE_URL}{endpoint}"
    headers = {
        "api_key": COINALYZE_API_KEY
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 429:
                logger.warning("Coinalyze rate limit hit - waiting 60s")
                await asyncio.sleep(60)
                return None
            
            if response.status_code != 200:
                logger.error(f"Coinalyze API error: {response.status_code} - {response.text}")
                return None
            
            return response.json()
    
    except Exception as e:
        logger.error(f"Coinalyze request failed: {e}")
        return None


async def get_funding_rate() -> Dict[str, Any]:
    """
    Get current BTC perpetual funding rate (aggregated)
    
    Returns:
        {
            "funding_rate": 0.0123,  # Current 8h funding rate (%)
            "predicted_rate": 0.0098,  # Predicted next funding
            "sentiment": "overleveraged_longs" | "overleveraged_shorts" | "neutral",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "2026-01-28T08:00:00Z"
        }
    """
    cache_key = "funding_rate"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get current funding rate
    data = await _make_request("/funding-rate", {
        "symbols": ",".join(BTC_PERP_SYMBOLS)
    })
    
    if not data or not isinstance(data, list) or len(data) == 0:
        return {
            "funding_rate": None,
            "predicted_rate": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch funding rate"
        }
    
    # Parse response - Coinalyze returns array of symbols
    item = data[0]
    funding_rate = item.get("value", 0) * 100  # Convert to percentage
    predicted_rate = item.get("predictedValue", 0) * 100 if "predictedValue" in item else None
    
    # Determine sentiment and signal
    # High positive funding = longs paying shorts = overleveraged longs
    # High negative funding = shorts paying longs = overleveraged shorts
    if funding_rate > 0.05:
        sentiment = "overleveraged_longs"
        signal = "FIRING"  # Potential short squeeze / reversal setup
    elif funding_rate < -0.03:
        sentiment = "overleveraged_shorts"
        signal = "FIRING"  # Potential long squeeze / reversal setup
    else:
        sentiment = "neutral"
        signal = "NEUTRAL"
    
    result = {
        "funding_rate": round(funding_rate, 4),
        "predicted_rate": round(predicted_rate, 4) if predicted_rate else None,
        "sentiment": sentiment,
        "signal": signal,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Coinalyze Funding Rate: {funding_rate:.4f}% -> {signal}")
    return result


async def get_open_interest() -> Dict[str, Any]:
    """
    Get BTC open interest data and detect divergences
    
    Divergence logic:
    - OI rising + price falling = accumulation (bullish)
    - OI falling + price rising = distribution (bearish)
    
    Returns:
        {
            "current_oi": 12500000000,  # Current OI in USD
            "oi_change_4h": -2.5,  # % change in last 4 hours
            "price_change_4h": 1.2,  # % change in last 4 hours
            "divergence": "accumulation" | "distribution" | "none",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "open_interest"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get OI history (last 6 hours for 4h comparison)
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=6)).timestamp() * 1000)
    
    data = await _make_request("/open-interest-history", {
        "symbols": ",".join(BTC_PERP_SYMBOLS),
        "interval": "1h",
        "from": from_ts
    })
    
    if not data or not isinstance(data, list) or len(data) == 0:
        return {
            "current_oi": None,
            "oi_change_4h": None,
            "price_change_4h": None,
            "divergence": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch OI data"
        }
    
    # Parse OI history
    item = data[0]
    history = item.get("history", [])
    
    if len(history) < 4:
        return {
            "current_oi": None,
            "oi_change_4h": None,
            "divergence": "unknown",
            "signal": "UNKNOWN",
            "error": "Insufficient OI history"
        }
    
    # Get current and 4h ago values
    current_oi = history[-1].get("o", 0)  # 'o' is open interest value
    oi_4h_ago = history[-5].get("o", current_oi) if len(history) >= 5 else history[0].get("o", current_oi)
    
    # Calculate changes
    oi_change_4h = ((current_oi - oi_4h_ago) / oi_4h_ago * 100) if oi_4h_ago > 0 else 0
    
    # Get price change (from close prices in history)
    current_price = history[-1].get("c", 0)  # 'c' is close price
    price_4h_ago = history[-5].get("c", current_price) if len(history) >= 5 else history[0].get("c", current_price)
    price_change_4h = ((current_price - price_4h_ago) / price_4h_ago * 100) if price_4h_ago > 0 else 0
    
    # Detect divergence
    divergence = "none"
    signal = "NEUTRAL"
    
    # Significant thresholds
    if abs(oi_change_4h) > 2 and abs(price_change_4h) > 0.5:
        if oi_change_4h > 0 and price_change_4h < 0:
            divergence = "accumulation"  # OI up, price down = smart money buying
            signal = "FIRING"
        elif oi_change_4h < 0 and price_change_4h > 0:
            divergence = "distribution"  # OI down, price up = smart money selling
            signal = "FIRING"
    
    result = {
        "current_oi": current_oi,
        "oi_change_4h": round(oi_change_4h, 2),
        "price_change_4h": round(price_change_4h, 2),
        "divergence": divergence,
        "signal": signal,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Coinalyze OI: {oi_change_4h:+.2f}% vs Price: {price_change_4h:+.2f}% -> {divergence}")
    return result


async def get_liquidations() -> Dict[str, Any]:
    """
    Get BTC liquidation data (last hour)
    
    High one-sided liquidations often mark local tops/bottoms
    
    Returns:
        {
            "long_liquidations": 5000000,  # USD value
            "short_liquidations": 2000000,
            "total_liquidations": 7000000,
            "long_pct": 71.4,
            "composition": "long_heavy" | "short_heavy" | "balanced",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "liquidations"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get liquidation history (last 2 hours)
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=2)).timestamp() * 1000)
    
    data = await _make_request("/liquidation-history", {
        "symbols": ",".join(BTC_PERP_SYMBOLS),
        "interval": "1h",
        "from": from_ts
    })
    
    if not data or not isinstance(data, list) or len(data) == 0:
        return {
            "long_liquidations": None,
            "short_liquidations": None,
            "total_liquidations": None,
            "long_pct": None,
            "composition": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch liquidation data"
        }
    
    # Parse liquidation data
    item = data[0]
    history = item.get("history", [])
    
    if not history:
        return {
            "long_liquidations": 0,
            "short_liquidations": 0,
            "total_liquidations": 0,
            "long_pct": 50,
            "composition": "balanced",
            "signal": "NEUTRAL"
        }
    
    # Sum liquidations from last hour
    long_liq = sum(h.get("l", 0) for h in history[-2:])  # 'l' is long liquidations
    short_liq = sum(h.get("s", 0) for h in history[-2:])  # 's' is short liquidations
    total_liq = long_liq + short_liq
    
    # Calculate composition
    long_pct = (long_liq / total_liq * 100) if total_liq > 0 else 50
    
    # Determine signal
    # Significant liquidation cascade (>$5M) with one-sided composition
    composition = "balanced"
    signal = "NEUTRAL"
    
    if total_liq > 5_000_000:  # $5M threshold
        if long_pct > 75:
            composition = "long_heavy"
            signal = "FIRING"  # Longs got rekt = potential bottom
        elif long_pct < 25:
            composition = "short_heavy"
            signal = "FIRING"  # Shorts got rekt = potential top
    
    result = {
        "long_liquidations": long_liq,
        "short_liquidations": short_liq,
        "total_liquidations": total_liq,
        "long_pct": round(long_pct, 1),
        "composition": composition,
        "signal": signal,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Coinalyze Liquidations: ${total_liq/1e6:.1f}M ({long_pct:.0f}% long) -> {composition}")
    return result


async def get_term_structure() -> Dict[str, Any]:
    """
    Derive term structure signal from funding rate trend
    
    Contango (positive funding) + price weakness = bearish divergence
    Backwardation (negative funding) + price strength = bullish divergence
    
    Returns:
        {
            "structure": "contango" | "backwardation" | "flat",
            "funding_trend": "rising" | "falling" | "stable",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "term_structure"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get funding rate history
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=24)).timestamp() * 1000)
    
    data = await _make_request("/funding-rate-history", {
        "symbols": ",".join(BTC_PERP_SYMBOLS),
        "interval": "8h",  # Standard funding interval
        "from": from_ts
    })
    
    if not data or not isinstance(data, list) or len(data) == 0:
        return {
            "structure": "unknown",
            "funding_trend": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch funding history"
        }
    
    # Parse funding history
    item = data[0]
    history = item.get("history", [])
    
    if len(history) < 2:
        return {
            "structure": "unknown",
            "funding_trend": "unknown",
            "signal": "UNKNOWN",
            "error": "Insufficient funding history"
        }
    
    # Get current and average funding
    current_funding = history[-1].get("v", 0) * 100  # Convert to %
    avg_funding = sum(h.get("v", 0) for h in history) / len(history) * 100
    
    # Determine structure
    if avg_funding > 0.02:
        structure = "contango"
    elif avg_funding < -0.01:
        structure = "backwardation"
    else:
        structure = "flat"
    
    # Determine trend
    if len(history) >= 3:
        recent_avg = sum(h.get("v", 0) for h in history[-2:]) / 2 * 100
        older_avg = sum(h.get("v", 0) for h in history[:-2]) / max(len(history) - 2, 1) * 100
        
        if recent_avg > older_avg + 0.01:
            funding_trend = "rising"
        elif recent_avg < older_avg - 0.01:
            funding_trend = "falling"
        else:
            funding_trend = "stable"
    else:
        funding_trend = "stable"
    
    # Signal: divergence between structure and price action
    # This is derived - would need price data too for full logic
    signal = "NEUTRAL"
    if structure == "contango" and funding_trend == "rising":
        signal = "FIRING"  # Extreme bullish positioning = potential reversal
    elif structure == "backwardation" and funding_trend == "falling":
        signal = "FIRING"  # Extreme bearish positioning = potential reversal
    
    result = {
        "structure": structure,
        "funding_trend": funding_trend,
        "current_funding": round(current_funding, 4),
        "avg_funding_24h": round(avg_funding, 4),
        "signal": signal,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Coinalyze Term Structure: {structure}, trend: {funding_trend} -> {signal}")
    return result


async def get_all_coinalyze_data() -> Dict[str, Any]:
    """Fetch all Coinalyze data in parallel"""
    results = await asyncio.gather(
        get_funding_rate(),
        get_open_interest(),
        get_liquidations(),
        get_term_structure(),
        return_exceptions=True
    )
    
    return {
        "funding": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
        "open_interest": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
        "liquidations": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
        "term_structure": results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
