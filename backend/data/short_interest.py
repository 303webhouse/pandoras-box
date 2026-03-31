"""
Short Interest Data Provider
Tries Polygon first, falls back to yfinance.
Caches results in Redis (24h TTL) to avoid repeated API calls.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

import httpx

logger = logging.getLogger("short_interest")

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY") or ""


async def get_short_interest(ticker: str) -> Optional[Dict]:
    """
    Get short interest data for a ticker.
    Returns dict with short_pct_float, days_to_cover, etc. or None.
    """
    from database.redis_client import get_redis_client

    redis = await get_redis_client()
    if redis:
        cached = await redis.get(f"hydra:short:{ticker}")
        if cached:
            return json.loads(cached)

    data = await _try_polygon(ticker)
    if not data:
        data = await _try_yfinance(ticker)

    if data and redis:
        await redis.set(f"hydra:short:{ticker}", json.dumps(data), ex=86400)

    return data


async def _try_polygon(ticker: str) -> Optional[Dict]:
    """Attempt to get short interest from Polygon ticker details."""
    if not POLYGON_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.polygon.io/v3/reference/tickers/{ticker}",
                params={"apiKey": POLYGON_API_KEY},
            )
            if resp.status_code == 200:
                result = resp.json().get("results", {})
                if result.get("share_class_shares_outstanding"):
                    short_pct = result.get("short_percent_of_float", 0)
                    if short_pct:
                        return {
                            "ticker": ticker,
                            "short_pct_float": round(short_pct * 100, 2) if short_pct < 1 else round(short_pct, 2),
                            "days_to_cover": round(result.get("short_ratio", 0) or 0, 2),
                            "shares_short": result.get("shares_short", 0) or 0,
                            "shares_short_prior": result.get("shares_short_prior_month", 0) or 0,
                            "source": "polygon",
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
    except Exception as e:
        logger.debug("Polygon short interest failed for %s: %s", ticker, e)
    return None


async def _try_yfinance(ticker: str) -> Optional[Dict]:
    """Fallback: get short interest from yfinance."""
    try:
        import yfinance as yf

        def _fetch():
            t = yf.Ticker(ticker)
            info = t.info
            return {
                "ticker": ticker,
                "short_pct_float": round((info.get("shortPercentOfFloat") or 0) * 100, 2),
                "days_to_cover": round(info.get("shortRatio") or 0, 2),
                "shares_short": info.get("sharesShort") or 0,
                "shares_short_prior": info.get("sharesShortPriorMonth") or 0,
                "source": "yfinance",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        data = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return data
    except Exception as e:
        logger.warning("yfinance short interest failed for %s: %s", ticker, e)
    return None


async def get_short_interest_batch(tickers: list) -> Dict[str, Dict]:
    """Get short interest for multiple tickers with rate limiting."""
    results = {}
    for ticker in tickers:
        data = await get_short_interest(ticker)
        if data:
            results[ticker] = data
        await asyncio.sleep(0.5)
    return results
