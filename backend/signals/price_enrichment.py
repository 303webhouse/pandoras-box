"""
Price Range Enrichment — fetches 10-day daily bars and injects
ten_day_high, ten_day_low, range_consumed into signal metadata.
Feeds the freshness penalty in trade_ideas_scorer.py.

Uses Redis cache (2h TTL) to avoid rate-limit failures on Polygon
when burst signals arrive for the same ticker.
"""

import asyncio
import json as _json
import logging
import os
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger("pipeline")

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
RANGE_CACHE_TTL = 7200  # 2 hours — 10d range doesn't change fast


async def enrich_price_range(signal_data: dict) -> dict:
    """
    Fetch 10-day daily bars for the signal's ticker and inject
    ten_day_high, ten_day_low, and range_consumed into metadata.
    """
    ticker = (signal_data.get("ticker") or "").upper()
    entry_price = signal_data.get("entry_price")
    direction = (signal_data.get("direction") or "").upper()

    if not ticker or not entry_price or float(entry_price) <= 0:
        return signal_data

    metadata = signal_data.get("metadata") or {}
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    # Skip if already enriched
    if "ten_day_high" in metadata:
        return signal_data

    ten_day_high = None
    ten_day_low = None

    # Check Redis cache first (avoids rate limits on burst signals)
    cache_key = f"price_range:{ticker}"
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                cached_data = _json.loads(cached)
                ten_day_high = cached_data["high"]
                ten_day_low = cached_data["low"]
                logger.debug("Price range cache hit for %s", ticker)
    except Exception:
        pass  # Redis unavailable — proceed to fetch

    # Fetch from API if not cached
    if ten_day_high is None or ten_day_low is None:
        # Try Polygon first
        if POLYGON_API_KEY:
            try:
                ten_day_high, ten_day_low = await _fetch_range_polygon(ticker)
            except Exception as e:
                logger.debug("Polygon range fetch failed for %s: %s", ticker, e)

        # Fallback to yfinance
        if ten_day_high is None or ten_day_low is None:
            try:
                ten_day_high, ten_day_low = await _fetch_range_yfinance(ticker)
            except Exception as e2:
                logger.debug("yfinance range fetch also failed for %s: %s", ticker, e2)
                return signal_data

        # Cache successful result in Redis
        if ten_day_high is not None and ten_day_low is not None:
            try:
                redis = await get_redis_client()
                if redis:
                    await redis.set(cache_key, _json.dumps({
                        "high": ten_day_high, "low": ten_day_low
                    }), ex=RANGE_CACHE_TTL)
            except Exception:
                pass

    if ten_day_high is None or ten_day_low is None or ten_day_high <= ten_day_low:
        return signal_data

    # Compute range_consumed
    entry = float(entry_price)
    rng = ten_day_high - ten_day_low
    if direction in ("LONG", "BUY", "BULLISH"):
        range_consumed = (entry - ten_day_low) / rng
    else:
        range_consumed = (ten_day_high - entry) / rng
    range_consumed = max(0.0, min(1.0, range_consumed))

    metadata["ten_day_high"] = round(ten_day_high, 4)
    metadata["ten_day_low"] = round(ten_day_low, 4)
    metadata["range_consumed"] = round(range_consumed, 4)
    signal_data["metadata"] = metadata

    logger.info("Price range enriched for %s: hi=%.2f lo=%.2f consumed=%.0f%%",
                ticker, ten_day_high, ten_day_low, range_consumed * 100)
    return signal_data


async def _fetch_range_polygon(ticker: str) -> tuple:
    """Fetch 10-day high/low from Polygon daily bars."""
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=15)).strftime("%Y-%m-%d")
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day"
        f"/{start}/{end}?adjusted=true&sort=desc&limit=10"
        f"&apiKey={POLYGON_API_KEY}"
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", [])
    if not results or len(results) < 3:
        raise ValueError(f"Not enough bars for {ticker}: {len(results)}")
    highs = [bar["h"] for bar in results]
    lows = [bar["l"] for bar in results]
    return max(highs), min(lows)


def _fetch_range_yfinance_sync(ticker: str) -> tuple:
    """Synchronous yfinance fetch (run in executor)."""
    import yfinance as yf
    tk = yf.Ticker(ticker)
    hist = tk.history(period="10d")
    if hist.empty or len(hist) < 3:
        raise ValueError(f"Not enough yfinance data for {ticker}")
    return float(hist["High"].max()), float(hist["Low"].min())


async def _fetch_range_yfinance(ticker: str) -> tuple:
    """Async wrapper for yfinance."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_range_yfinance_sync, ticker)
