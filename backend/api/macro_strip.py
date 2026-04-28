"""
Macro Strip — persistent cross-asset ticker strip.

Fetches latest quotes for ~16 macro ETF proxies in parallel via UW snapshot.
Cached 10s during market hours, 5min when closed.

Migration history:
- Originally Polygon batch snapshot endpoint
- Migrated to UW (via get_snapshot) on 2026-04-28 after Polygon plan cancellation
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from database.redis_client import get_redis_client
from integrations.uw_api import get_snapshot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/macro", tags=["macro"])

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
    "EWG":  {"label": "DE",   "name": "Germany (DAX)"},
    "EWU":  {"label": "UK",   "name": "United Kingdom (FTSE)"},
    "FXI":  {"label": "CN",   "name": "China Large-Cap"},
    "EWY":  {"label": "KR",   "name": "South Korea (KOSPI)"},
    "EWJ":  {"label": "JP",   "name": "Japan (Nikkei)"},
    "INDA": {"label": "IN",   "name": "India (Nifty)"},
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


async def _fetch_one(ticker: str) -> dict | None:
    """Fetch one snapshot via UW; return ticker entry or None on failure."""
    try:
        snap = await get_snapshot(ticker)
        if not snap:
            return None
        info = MACRO_TICKERS[ticker]
        # get_snapshot returns Polygon-compatible schema: day.c (close), prevDay.c (prev close)
        day = snap.get("day") or {}
        prev = snap.get("prevDay") or {}
        price = day.get("c") or prev.get("c") or 0
        prev_close = prev.get("c") or 0
        change_pct = (
            round((price - prev_close) / prev_close * 100, 2)
            if prev_close
            else 0
        )
        return {
            "ticker": ticker,
            "label": info["label"],
            "name": info["name"],
            "price": round(price, 2) if price else 0,
            "change_pct": change_pct,
        }
    except Exception as e:
        logger.warning("Macro strip UW fetch failed for %s: %s", ticker, e)
        return None


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

    # Fetch all snapshots in parallel via UW
    results = await asyncio.gather(
        *(_fetch_one(t) for t in tickers),
        return_exceptions=False,
    )
    result_data = [r for r in results if r is not None]

    # Sort by MACRO_TICKERS order (gather() may return in any order)
    ticker_order = list(MACRO_TICKERS.keys())
    result_data.sort(
        key=lambda x: ticker_order.index(x["ticker"]) if x["ticker"] in ticker_order else 99
    )

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
