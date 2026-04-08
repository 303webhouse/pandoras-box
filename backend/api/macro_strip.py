"""
Macro Strip — persistent cross-asset ticker strip.
Single Polygon snapshot call for macro tickers, 10s cache during market hours.
"""

import json
import logging
import os
from datetime import datetime, timezone

import aiohttp
from fastapi import APIRouter

from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/macro", tags=["macro"])

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"

# Macro tickers: ETF proxies for cross-asset monitoring
MACRO_TICKERS = {
    "SPY":  {"label": "SPY",  "name": "S&P 500"},
    "QQQ":  {"label": "QQQ",  "name": "Nasdaq"},
    "IWM":  {"label": "IWM",  "name": "Russell 2K"},
    "USO":  {"label": "OIL",  "name": "Crude Oil"},
    "GLD":  {"label": "GOLD", "name": "Gold"},
    "SHY":  {"label": "2Y",   "name": "2Y Treasury"},
    "IEF":  {"label": "10Y",  "name": "7-10Y Treasury"},
    "TLT":  {"label": "20Y",  "name": "20Y Treasury"},
    "UUP":  {"label": "DXY",  "name": "US Dollar"},
    "HYG":  {"label": "HY",   "name": "High Yield"},
}

MACRO_CACHE_KEY = "macro:strip"
MACRO_CACHE_TTL_LIVE = 10     # 10s during market hours
MACRO_CACHE_TTL_CLOSED = 300  # 5 min when closed


def _is_market_hours():
    import pytz
    et = datetime.now(pytz.timezone("America/New_York"))
    if et.weekday() >= 5:
        return False
    if et.hour == 9 and et.minute >= 30:
        return True
    if 10 <= et.hour < 16:
        return True
    return False


@router.get("/strip")
async def get_macro_strip():
    """Return cross-asset macro data for the persistent ticker strip."""
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(MACRO_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    tickers = list(MACRO_TICKERS.keys())
    result_data = []

    if POLYGON_API_KEY:
        try:
            ticker_str = ",".join(tickers)
            url = f"{SNAPSHOT_URL}?tickers={ticker_str}&apiKey={POLYGON_API_KEY}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for t in data.get("tickers", []):
                            sym = t.get("ticker", "")
                            if sym not in MACRO_TICKERS:
                                continue
                            day = t.get("day", {})
                            prev = t.get("prevDay", {})
                            price = day.get("c") or prev.get("c") or 0
                            prev_close = prev.get("c") or 0
                            change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
                            info = MACRO_TICKERS[sym]
                            result_data.append({
                                "ticker": sym,
                                "label": info["label"],
                                "name": info["name"],
                                "price": round(price, 2),
                                "change_pct": change_pct,
                            })
        except Exception as e:
            logger.error("Macro strip Polygon fetch failed: %s", e)

    # Sort by MACRO_TICKERS order
    ticker_order = list(MACRO_TICKERS.keys())
    result_data.sort(key=lambda x: ticker_order.index(x["ticker"]) if x["ticker"] in ticker_order else 99)

    result = {
        "tickers": result_data,
        "is_market_hours": _is_market_hours(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if redis and result_data:
        ttl = MACRO_CACHE_TTL_LIVE if _is_market_hours() else MACRO_CACHE_TTL_CLOSED
        try:
            await redis.set(MACRO_CACHE_KEY, json.dumps(result), ex=ttl)
        except Exception:
            pass

    return result
