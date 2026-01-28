"""
DeFiLlama API Client
Fetches stablecoin yield data for risk sentiment analysis

API Documentation: https://api-docs.defillama.com/
No authentication required
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger(__name__)

# API Configuration
DEFILLAMA_BASE_URL = "https://yields.llama.fi"

# Stablecoins to track
STABLECOINS = ["USDC", "USDT", "DAI", "USDE", "FRAX"]

# Minimum TVL for pools to consider (avoid low liquidity noise)
MIN_TVL = 10_000_000  # $10M

# Cache for API responses
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 900  # 15 minutes (yields don't change that fast)


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


async def _make_request(endpoint: str) -> Optional[Dict]:
    """Make request to DeFiLlama API"""
    url = f"{DEFILLAMA_BASE_URL}{endpoint}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.error(f"DeFiLlama API error: {response.status_code} - {response.text}")
                return None
            
            return response.json()
    
    except Exception as e:
        logger.error(f"DeFiLlama request failed: {e}")
        return None


async def get_stablecoin_aprs() -> Dict[str, Any]:
    """
    Get average stablecoin APRs across DeFi protocols
    
    High yields (>8%) = Risk-on, yield chasing behavior
    Low yields (<2%) = Risk-off, flight to safety
    
    Returns:
        {
            "average_apy": 4.5,
            "median_apy": 3.8,
            "top_pools": [...],
            "sentiment": "risk_on" | "risk_off" | "neutral",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "stablecoin_aprs"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get all yield pools
    data = await _make_request("/pools")
    
    if not data or "data" not in data:
        return {
            "average_apy": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch yield data"
        }
    
    pools = data["data"]
    
    # Filter for stablecoin pools with sufficient TVL
    stablecoin_pools = []
    
    for pool in pools:
        symbol = pool.get("symbol", "").upper()
        tvl = pool.get("tvlUsd", 0)
        apy = pool.get("apy", 0)
        
        # Check if this is a stablecoin pool
        is_stablecoin = any(stable in symbol for stable in STABLECOINS)
        
        # Filter by TVL and reasonable APY (exclude outliers)
        if is_stablecoin and tvl >= MIN_TVL and 0 < apy < 50:
            stablecoin_pools.append({
                "pool": pool.get("pool"),
                "project": pool.get("project"),
                "chain": pool.get("chain"),
                "symbol": symbol,
                "tvl": tvl,
                "apy": apy,
                "apy_base": pool.get("apyBase", 0),
                "apy_reward": pool.get("apyReward", 0)
            })
    
    if not stablecoin_pools:
        return {
            "average_apy": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "error": "No qualifying stablecoin pools found"
        }
    
    # Sort by TVL (weight by liquidity)
    stablecoin_pools.sort(key=lambda x: x["tvl"], reverse=True)
    
    # Calculate TVL-weighted average APY (top 50 pools)
    top_pools = stablecoin_pools[:50]
    total_tvl = sum(p["tvl"] for p in top_pools)
    weighted_apy = sum(p["apy"] * p["tvl"] for p in top_pools) / total_tvl if total_tvl > 0 else 0
    
    # Calculate median
    apys = sorted([p["apy"] for p in top_pools])
    median_apy = apys[len(apys) // 2] if apys else 0
    
    # Determine sentiment and signal
    # High yields = risk-on behavior (people chasing yield in risky protocols)
    # Low yields = risk-off (flight to safety, lower demand for leverage)
    if weighted_apy > 8:
        sentiment = "risk_on"
        signal = "FIRING"  # Extreme yield chasing = potential market top
    elif weighted_apy < 2:
        sentiment = "risk_off"
        signal = "FIRING"  # Extreme risk aversion = potential market bottom
    else:
        sentiment = "neutral"
        signal = "NEUTRAL"
    
    result = {
        "average_apy": round(weighted_apy, 2),
        "median_apy": round(median_apy, 2),
        "min_apy": round(min(apys), 2) if apys else 0,
        "max_apy": round(max(apys), 2) if apys else 0,
        "pools_analyzed": len(top_pools),
        "total_tvl": total_tvl,
        "top_pools": top_pools[:10],  # Top 10 by TVL
        "sentiment": sentiment,
        "signal": signal,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"DeFiLlama Stablecoin APY: {weighted_apy:.2f}% avg ({len(top_pools)} pools) -> {sentiment}")
    return result


async def get_yield_by_protocol(protocol: str = None) -> Dict[str, Any]:
    """Get yields for a specific protocol or all protocols"""
    data = await _make_request("/pools")
    
    if not data or "data" not in data:
        return {"error": "Failed to fetch data"}
    
    pools = data["data"]
    
    if protocol:
        pools = [p for p in pools if p.get("project", "").lower() == protocol.lower()]
    
    return {
        "pools": pools[:100],
        "count": len(pools)
    }
