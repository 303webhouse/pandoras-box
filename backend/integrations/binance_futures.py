"""
Binance Futures REST client — funding rates, klines, ticker data.
Used by crypto_setups.py for strategy signal generation.

Uses the same geo-friendly patterns as crypto_market.py:
  - data-api.binance.vision for spot
  - fapi.binance.com for futures (with optional proxy)
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import httpx

logger = logging.getLogger(__name__)

# Geo-friendly endpoints
BINANCE_FUTURES_BASE = "https://fapi.binance.com"
BINANCE_VISION_BASE = "https://data-api.binance.vision"

# Optional proxy for futures (same env var as crypto_market.py)
PERP_PROXY = os.getenv("CRYPTO_BINANCE_PERP_HTTP_PROXY") or None

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PivotHub/1.0)",
    "Accept": "application/json",
}

# Module-level cache
_cache: Dict[str, Any] = {}
_CACHE_TTL = 30  # seconds


def _cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data: Any):
    _cache[key] = {"data": data, "ts": time.time()}


async def _fetch_json(url: str, params: Optional[dict] = None, use_proxy: bool = False) -> Optional[dict]:
    """Fetch JSON with geo-block handling."""
    proxy = PERP_PROXY if use_proxy else None
    try:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=10.0,
            follow_redirects=True,
            proxy=proxy,
        ) as client:
            resp = await client.get(url, params=params)
            if resp.status_code in (403, 451):
                logger.warning(f"Binance geo-blocked: {url} → {resp.status_code}")
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Binance fetch error {url}: {e}")
        return None


async def get_funding_rate(symbol: str = "BTCUSDT") -> Optional[Dict]:
    """Get current funding rate and time to next settlement."""
    cache_key = f"funding:{symbol}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = await _fetch_json(
        f"{BINANCE_FUTURES_BASE}/fapi/v1/premiumIndex",
        params={"symbol": symbol},
        use_proxy=True,
    )
    if not data:
        return None

    funding_rate = float(data.get("lastFundingRate", 0))
    next_funding_ms = int(data.get("nextFundingTime", 0))
    now_ms = int(time.time() * 1000)
    minutes_to_settlement = max(0, (next_funding_ms - now_ms) / 60000)

    result = {
        "funding_rate": funding_rate,
        "funding_rate_pct": funding_rate * 100,
        "next_funding_time": datetime.fromtimestamp(next_funding_ms / 1000, tz=timezone.utc).isoformat(),
        "minutes_to_settlement": round(minutes_to_settlement, 1),
        "mark_price": float(data.get("markPrice", 0)),
        "index_price": float(data.get("indexPrice", 0)),
    }
    _cache_set(cache_key, result)
    return result


async def get_klines(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    limit: int = 100,
) -> Optional[List[List]]:
    """Get OHLCV klines from Binance futures."""
    cache_key = f"klines:{symbol}:{interval}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = await _fetch_json(
        f"{BINANCE_FUTURES_BASE}/fapi/v1/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        use_proxy=True,
    )
    if not data:
        return None

    _cache_set(cache_key, data)
    return data


async def get_ticker_24h(symbol: str = "BTCUSDT") -> Optional[Dict]:
    """Get 24h ticker stats."""
    cache_key = f"ticker24h:{symbol}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = await _fetch_json(
        f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/24hr",
        params={"symbol": symbol},
        use_proxy=True,
    )
    if not data:
        return None

    result = {
        "last_price": float(data.get("lastPrice", 0)),
        "volume_24h": float(data.get("volume", 0)),
        "quote_volume_24h": float(data.get("quoteVolume", 0)),
        "price_change_pct": float(data.get("priceChangePercent", 0)),
        "high_24h": float(data.get("highPrice", 0)),
        "low_24h": float(data.get("lowPrice", 0)),
    }
    _cache_set(cache_key, result)
    return result


async def get_recent_agg_trades(
    symbol: str = "BTCUSDT",
    limit: int = 500,
) -> Optional[List[Dict]]:
    """Get recent aggregated trades for liquidation/flow analysis."""
    cache_key = f"aggtrades:{symbol}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = await _fetch_json(
        f"{BINANCE_FUTURES_BASE}/fapi/v1/aggTrades",
        params={"symbol": symbol, "limit": limit},
        use_proxy=True,
    )
    if not data:
        return None

    trades = []
    for t in data:
        trades.append({
            "price": float(t["p"]),
            "qty": float(t["q"]),
            "time": int(t["T"]),
            "is_buyer_maker": t["m"],  # True = sell, False = buy
        })

    _cache_set(cache_key, trades)
    return trades


async def get_orderbook_depth(symbol: str = "BTCUSDT", limit: int = 20) -> Optional[Dict]:
    """Fetch orderbook depth from Binance Futures."""
    cache_key = f"depth:{symbol}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = await _fetch_json(
        f"{BINANCE_FUTURES_BASE}/fapi/v1/depth",
        params={"symbol": symbol, "limit": limit},
        use_proxy=True,
    )
    if not data:
        return None

    result = {
        "bids": [[float(p), float(q)] for p, q in data.get("bids", [])],
        "asks": [[float(p), float(q)] for p, q in data.get("asks", [])],
    }
    _cache_set(cache_key, result)
    return result
