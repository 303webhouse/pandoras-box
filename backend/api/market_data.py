"""
Market Data API — Polygon.io passthrough endpoints.

Read-only endpoints wrapping existing Polygon integration functions
so Pivot (and other clients) can query live market data through the
Trading Hub without needing direct Polygon credentials.

All data is 15-min delayed (Polygon Starter plan). Existing 5-min
in-memory caches in the integration layer apply automatically.
"""

import logging
import os
import time
from datetime import date, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY") or ""
POLYGON_BASE = "https://api.polygon.io"

# News cache: (timestamp, data)
_news_cache: dict = {}
_NEWS_CACHE_TTL = 600  # 10 minutes


@router.get("/market/quote/{ticker}")
async def get_quote(ticker: str):
    """Current stock/ETF snapshot (price, volume, change %)."""
    from integrations.uw_api import get_snapshot

    result = await get_snapshot(ticker.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    return result


@router.get("/market/previous-close/{ticker}")
async def get_previous_close(ticker: str):
    """Previous trading day OHLCV."""
    from integrations.uw_api import get_previous_close as _get_prev

    result = await _get_prev(ticker.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    return result


@router.get("/market/bars/{ticker}")
async def get_bars(
    ticker: str,
    days: int = Query(30, ge=1, le=365),
    timespan: str = Query("day"),
    multiplier: int = Query(1, ge=1, le=60),
):
    """OHLCV price history bars."""
    from integrations.uw_api import get_bars as _get_bars

    from_date = (date.today() - timedelta(days=int(days * 1.6) + 5)).isoformat()
    to_date = date.today().isoformat()

    result = await _get_bars(ticker.upper(), multiplier, timespan, from_date, to_date)
    if not result:
        raise HTTPException(status_code=404, detail=f"No bars for {ticker}")
    return result


@router.get("/market/options-chain/{ticker}")
async def get_options_chain(
    ticker: str,
    expiration: Optional[str] = Query(None),
    strike_gte: Optional[float] = Query(None),
    strike_lte: Optional[float] = Query(None),
    contract_type: Optional[str] = Query(None),
):
    """Options chain snapshot with greeks, IV, bid/ask."""
    from integrations.uw_api import get_options_snapshot

    result = await get_options_snapshot(
        ticker.upper(),
        expiration_date=expiration,
        strike_gte=strike_gte,
        strike_lte=strike_lte,
        contract_type=contract_type,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"No options data for {ticker}")
    return result


@router.get("/market/option-value")
async def get_option_value(
    underlying: str = Query(...),
    long_strike: float = Query(...),
    expiry: str = Query(...),
    option_type: str = Query(...),
    short_strike: Optional[float] = Query(None),
    structure: Optional[str] = Query(None),
):
    """Single option or spread valuation + greeks."""
    from integrations.polygon_options import get_spread_value, get_single_option_value

    if short_strike is not None:
        if not structure:
            raise HTTPException(
                status_code=400,
                detail="'structure' is required when short_strike is provided",
            )
        result = await get_spread_value(
            underlying.upper(), long_strike, short_strike, expiry, structure
        )
    else:
        result = await get_single_option_value(
            underlying.upper(), long_strike, expiry, option_type
        )

    if result is None:
        raise HTTPException(status_code=404, detail="No option data found")
    return result


@router.get("/market/news")
async def get_news(
    limit: int = Query(10, ge=1, le=50),
):
    """Top market headlines — UW API primary, Polygon fallback."""
    cache_key = f"news:{limit}"
    cached = _news_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _NEWS_CACHE_TTL:
        return cached[1]

    # Try UW API first
    try:
        from integrations.uw_api import get_news_headlines
        uw_data = await get_news_headlines(limit=limit)
        if uw_data:
            articles = []
            for item in uw_data:
                articles.append({
                    "title": item.get("headline"),
                    "url": None,
                    "source": item.get("source"),
                    "published": item.get("created_at"),
                    "tickers": item.get("tickers", []),
                    "image_url": None,
                    "sentiment": item.get("sentiment"),
                    "is_major": item.get("is_major", False),
                })
            result = {"articles": articles, "count": len(articles), "source": "uw_api"}
            _news_cache[cache_key] = (time.time(), result)
            return result
    except Exception as e:
        logger.debug("UW news fetch failed, trying Polygon: %s", e)

    # Polygon fallback
    if not POLYGON_API_KEY:
        raise HTTPException(status_code=503, detail="No news source configured")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{POLYGON_BASE}/v2/reference/news",
                params={
                    "apiKey": POLYGON_API_KEY,
                    "limit": limit,
                    "order": "desc",
                    "sort": "published_utc",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        articles = []
        for item in data.get("results", []):
            articles.append({
                "title": item.get("title"),
                "url": item.get("article_url"),
                "source": (item.get("publisher") or {}).get("name"),
                "published": item.get("published_utc"),
                "tickers": item.get("tickers", []),
                "image_url": item.get("image_url"),
            })

        result = {"articles": articles, "count": len(articles), "source": "polygon"}
        _news_cache[cache_key] = (time.time(), result)
        return result

    except httpx.HTTPStatusError as e:
        logger.warning("Polygon news API error: %s", e)
        raise HTTPException(status_code=502, detail="News unavailable")
    except Exception as e:
        logger.warning("Failed to fetch news: %s", e)
        raise HTTPException(status_code=502, detail="News fetch failed")
