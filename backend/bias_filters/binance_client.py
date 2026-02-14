"""
Market Microstructure Client (Binance + OKX fallback)
Fetches BTC spot orderbook depth and perp-vs-spot basis with geo-safe fallbacks.

BINANCE_PROXY_URL env var: Set to VPS proxy base URL to route fapi.binance.com
requests through a non-geo-restricted server.  The proxy must accept:
  GET {BINANCE_PROXY_URL}/fapi/v1/<path>?<original-query-params>
and forward them verbatim to https://fapi.binance.com.
Example: BINANCE_PROXY_URL=http://5.78.134.70:8090
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# API Configuration
BINANCE_SPOT_URL = "https://data-api.binance.vision/api/v3"  # geo-friendly mirror
_BINANCE_PROXY_URL = os.environ.get("BINANCE_PROXY_URL", "").rstrip("/")
# If a proxy is configured, route fapi calls through it; otherwise try direct (will 451 on Railway)
BINANCE_FUTURES_URL = f"{_BINANCE_PROXY_URL}/fapi/v1" if _BINANCE_PROXY_URL else "https://fapi.binance.com/fapi/v1"
OKX_MARKET_URL = "https://www.okx.com/api/v5/market"

if _BINANCE_PROXY_URL:
    logger.info("Binance Futures routed via proxy: %s", _BINANCE_PROXY_URL)

# Cache for API responses
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_ORDERBOOK = 60  # 1 minute for orderbook
CACHE_TTL_BASIS = 300  # 5 minutes for basis


def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    """Get cached response if not expired"""
    if key in _cache:
        cached = _cache[key]
        if datetime.now(timezone.utc) < cached["expires_at"]:
            return cached["data"]
    return None


def _set_cache(key: str, data: Any, ttl: int):
    """Cache response with TTL"""
    _cache[key] = {
        "data": data,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl)
    }


async def _make_request(url: str, params: Dict[str, Any] = None) -> Optional[Dict]:
    """Make request to a public market API endpoint"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)

            if response.status_code not in (200,):
                if response.status_code == 451:
                    if _BINANCE_PROXY_URL:
                        logger.warning(f"Binance proxy returned 451 geo-block ({url}) - proxy may not be working")
                    else:
                        logger.debug(f"Binance Futures geo-restricted ({url}): 451 - using OKX fallback")
                else:
                    logger.warning(f"Market API error ({url}): {response.status_code} - {response.text[:200]}")
                return None

            return response.json()

    except Exception as e:
        logger.warning(f"Market API request failed ({url}): {e}")
        return None


def _normalize_okx_book(okx_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert OKX orderbook payload into Binance-like shape."""
    if not okx_data or okx_data.get("code") != "0":
        return None

    rows = okx_data.get("data") or []
    if not rows:
        return None

    row = rows[0]
    bids = row.get("bids") or []
    asks = row.get("asks") or []
    if not bids or not asks:
        return None

    # Keep [price, qty] shape used by the existing depth math.
    return {
        "bids": [[b[0], b[1]] for b in bids if len(b) >= 2],
        "asks": [[a[0], a[1]] for a in asks if len(a) >= 2],
    }


async def get_spot_orderbook_skew() -> Dict[str, Any]:
    """
    Get BTC/USDT spot orderbook depth and calculate bid/ask imbalance
    
    High bid depth = buyers waiting below (support)
    High ask depth = sellers waiting above (resistance)
    
    Returns:
        {
            "bid_depth": 150.5,  # BTC in top 20 bid levels
            "ask_depth": 120.3,  # BTC in top 20 ask levels
            "imbalance": 0.11,  # (bid - ask) / (bid + ask)
            "imbalance_pct": 11.0,
            "sentiment": "bid_heavy" | "ask_heavy" | "balanced",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "orderbook_skew"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Try Binance spot depth first (geo-friendly mirror), then OKX spot books.
    data = await _make_request(f"{BINANCE_SPOT_URL}/depth", {
        "symbol": "BTCUSDT",
        "limit": 1000
    })

    source = "binance_vision"
    if not data or "bids" not in data or "asks" not in data:
        okx_data = await _make_request(f"{OKX_MARKET_URL}/books", {
            "instId": "BTC-USDT",
            "sz": 400
        })
        data = _normalize_okx_book(okx_data or {})
        source = "okx_spot"
    
    if not data or "bids" not in data or "asks" not in data:
        return {
            "bid_depth": None,
            "ask_depth": None,
            "imbalance": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "source": "unavailable",
            "error": "Failed to fetch orderbook from Binance Vision or OKX"
        }
    
    bids = data["bids"]  # [[price, qty], ...]
    asks = data["asks"]
    
    # Calculate depth within 2% of mid price
    if not bids or not asks:
        return {
            "bid_depth": 0,
            "ask_depth": 0,
            "imbalance": 0,
            "sentiment": "balanced",
            "signal": "NEUTRAL"
        }
    
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    mid_price = (best_bid + best_ask) / 2
    
    # Define price range (2% from mid)
    bid_threshold = mid_price * 0.98
    ask_threshold = mid_price * 1.02
    
    # Sum depth within range
    bid_depth = sum(float(b[1]) for b in bids if float(b[0]) >= bid_threshold)
    ask_depth = sum(float(a[1]) for a in asks if float(a[0]) <= ask_threshold)
    
    # Calculate imbalance
    total_depth = bid_depth + ask_depth
    imbalance = (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0
    imbalance_pct = imbalance * 100
    
    # Determine sentiment and signal
    # >15% imbalance is significant
    if imbalance > 0.15:
        sentiment = "bid_heavy"
        signal = "FIRING"  # Strong bid support = bullish
    elif imbalance < -0.15:
        sentiment = "ask_heavy"
        signal = "FIRING"  # Strong ask resistance = bearish
    else:
        sentiment = "balanced"
        signal = "NEUTRAL"
    
    result = {
        "bid_depth": round(bid_depth, 2),
        "ask_depth": round(ask_depth, 2),
        "total_depth": round(total_depth, 2),
        "imbalance": round(imbalance, 4),
        "imbalance_pct": round(imbalance_pct, 1),
        "mid_price": round(mid_price, 2),
        "spread": round(best_ask - best_bid, 2),
        "spread_bps": round((best_ask - best_bid) / mid_price * 10000, 2),
        "sentiment": sentiment,
        "signal": signal,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result, CACHE_TTL_ORDERBOOK)
    logger.info(f"Binance Orderbook: Bid {bid_depth:.1f} BTC, Ask {ask_depth:.1f} BTC, Imbalance {imbalance_pct:+.1f}% -> {sentiment}")
    return result


async def get_quarterly_basis() -> Dict[str, Any]:
    """
    Calculate quarterly futures basis (futures premium over spot)
    
    Basis = (Futures - Spot) / Spot * (365 / days_to_expiry) * 100
    
    High basis (>10% annualized) = Overleveraged longs, potential top
    Negative basis = Panic/capitulation, potential bottom
    
    Returns:
        {
            "spot_price": 100000,
            "futures_price": 101500,
            "basis_pct": 1.5,
            "basis_annualized": 12.5,
            "days_to_expiry": 45,
            "sentiment": "contango" | "backwardation" | "neutral",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "quarterly_basis"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get spot price (Binance Vision first, OKX spot fallback).
    spot_data = await _make_request(f"{BINANCE_SPOT_URL}/ticker/price", {
        "symbol": "BTCUSDT"
    })

    spot_source = "binance_vision"
    if not spot_data or "price" not in spot_data:
        okx_spot = await _make_request(f"{OKX_MARKET_URL}/ticker", {
            "instId": "BTC-USDT"
        })
        if okx_spot and okx_spot.get("code") == "0" and okx_spot.get("data"):
            spot_data = {"price": okx_spot["data"][0].get("last")}
            spot_source = "okx_spot"
    
    if not spot_data or "price" not in spot_data:
        return {
            "spot_price": None,
            "basis_annualized": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "source": "unavailable",
            "error": "Failed to fetch spot price from Binance Vision or OKX"
        }
    
    spot_price = float(spot_data["price"])
    
    # Get perpetual futures price (Binance Futures first, OKX swap fallback).
    perp_data = await _make_request(f"{BINANCE_FUTURES_URL}/ticker/price", {
        "symbol": "BTCUSDT"
    })

    perp_source = "binance_futures"
    if not perp_data or "price" not in perp_data:
        okx_perp = await _make_request(f"{OKX_MARKET_URL}/ticker", {
            "instId": "BTC-USDT-SWAP"
        })
        if okx_perp and okx_perp.get("code") == "0" and okx_perp.get("data"):
            perp_data = {"price": okx_perp["data"][0].get("last")}
            perp_source = "okx_swap"
    
    if not perp_data or "price" not in perp_data:
        return {
            "spot_price": spot_price,
            "basis_annualized": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "source": f"{spot_source}->unavailable",
            "error": "Failed to fetch perp/futures price from Binance Futures or OKX"
        }
    
    futures_price = float(perp_data["price"])
    
    # Calculate basis
    basis_pct = (futures_price - spot_price) / spot_price * 100
    
    # For perpetuals, annualize based on funding rate equivalent
    # Assume 8-hour funding, so annualize by multiplying by 3 * 365
    # But for simplicity, just use the raw premium
    basis_annualized = basis_pct * 365 / 7  # Assume weekly equivalent
    
    # Try to get actual quarterly futures
    # Binance quarterly futures format: BTCUSDT_YYMMDD
    # For now, use perpetual premium as approximation
    
    # Determine sentiment and signal
    if basis_annualized > 15:
        sentiment = "extreme_contango"
        signal = "FIRING"  # Extreme bullish positioning = potential top
    elif basis_annualized > 5:
        sentiment = "contango"
        signal = "NEUTRAL"
    elif basis_annualized < -5:
        sentiment = "backwardation"
        signal = "FIRING"  # Panic selling = potential bottom
    else:
        sentiment = "neutral"
        signal = "NEUTRAL"
    
    result = {
        "spot_price": round(spot_price, 2),
        "futures_price": round(futures_price, 2),
        "basis_pct": round(basis_pct, 4),
        "basis_annualized": round(basis_annualized, 2),
        "sentiment": sentiment,
        "signal": signal,
        "source": f"{spot_source}+{perp_source}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result, CACHE_TTL_BASIS)
    logger.info(f"Binance Basis: {basis_pct:.4f}% ({basis_annualized:.2f}% ann.) -> {sentiment}")
    return result


async def get_all_binance_data() -> Dict[str, Any]:
    """Fetch all Binance data"""
    import asyncio
    
    results = await asyncio.gather(
        get_spot_orderbook_skew(),
        get_quarterly_basis(),
        return_exceptions=True
    )
    
    return {
        "orderbook": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
        "basis": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
