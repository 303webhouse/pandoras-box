"""
Sector Strength Snapshot — Polygon.io

Real-time sector ETF prices via Polygon bulk snapshot (1 API call).
SMA data cached separately (refreshed once daily).

Data source: Polygon.io (primary), yfinance (fallback).
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
POLYGON_BASE = "https://api.polygon.io"

SECTOR_ETFS = {
    "Technology": "XLK",
    "Consumer Discretionary": "XLY",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Industrials": "XLI",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

ALL_TICKERS = ["SPY"] + list(SECTOR_ETFS.values())
TICKER_LIST_STR = ",".join(ALL_TICKERS)  # "SPY,XLK,XLY,..."

# Redis keys
SECTOR_SNAPSHOT_KEY = "sector:snapshot"        # Real-time prices (15s TTL)
SECTOR_SMA_KEY = "sector:sma_cache"            # Daily SMA data (24h TTL)
SECTOR_STRENGTH_KEY = "sector:strength"        # Computed strength scores (15s TTL)


async def fetch_sector_prices_polygon() -> Dict[str, float]:
    """
    Fetch current prices for all sector ETFs + SPY in ONE Polygon API call.
    Uses the multi-ticker snapshot endpoint.
    Returns: {"SPY": 542.30, "XLK": 198.50, ...}
    """
    if not POLYGON_API_KEY:
        logger.warning("POLYGON_API_KEY not set — cannot fetch sector prices")
        return {}

    try:
        url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={
                "apiKey": POLYGON_API_KEY,
                "tickers": TICKER_LIST_STR,
            })
            resp.raise_for_status()
            data = resp.json()

        prices = {}
        for t in data.get("tickers", []):
            ticker = t.get("ticker")
            # Use day close if available, else last trade, else prevDay close
            day = t.get("day", {})
            last_trade = t.get("lastTrade", {})
            prev_day = t.get("prevDay", {})
            price = (
                day.get("c")
                or last_trade.get("p")
                or prev_day.get("c")
            )
            if ticker and price:
                prices[ticker] = float(price)

        if prices:
            logger.debug(f"Polygon sector snapshot: {len(prices)} tickers")
        return prices

    except Exception as e:
        logger.warning(f"Polygon sector snapshot failed: {e}")
        return {}


async def fetch_sector_prices_yfinance() -> Dict[str, float]:
    """yfinance fallback for sector prices."""
    import asyncio
    prices = {}
    try:
        import yfinance as yf
        for ticker in ALL_TICKERS:
            try:
                t = yf.Ticker(ticker)
                hist = await asyncio.to_thread(lambda: t.history(period="1d"))
                if not hist.empty:
                    prices[ticker] = float(hist["Close"].iloc[-1])
            except Exception:
                continue
    except Exception as e:
        logger.error(f"yfinance sector fallback failed: {e}")
    return prices


async def fetch_sector_prices() -> Dict[str, float]:
    """yfinance only — Polygon is deprecated."""
    return await fetch_sector_prices_yfinance()


async def refresh_sma_cache() -> Dict[str, Dict[str, float]]:
    """
    Compute 20-day and 50-day SMAs via yfinance (Polygon is deprecated).
    Called once daily after close. Cached in Redis with 24h TTL.
    Returns: {"SPY": {"sma20": 540.5, "sma50": 535.2, "pct_1mo": 2.3}, ...}
    """
    return await _refresh_sma_yfinance()

    sma_data = {}
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=80)  # ~55 trading days for 50-day SMA

    async with httpx.AsyncClient(timeout=10.0) as client:
        for ticker in ALL_TICKERS:
            try:
                url = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"
                resp = await client.get(url, params={
                    "apiKey": POLYGON_API_KEY,
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": 100,
                })
                resp.raise_for_status()
                results = resp.json().get("results", [])

                if not results:
                    continue

                closes = [r["c"] for r in results]

                sma20 = sum(closes[-20:]) / min(20, len(closes)) if len(closes) >= 20 else None
                sma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 50 else None

                # 1-month performance (21 trading days)
                pct_1mo = None
                if len(closes) >= 22:
                    pct_1mo = ((closes[-1] - closes[-22]) / closes[-22]) * 100

                sma_data[ticker] = {
                    "sma20": round(sma20, 2) if sma20 else None,
                    "sma50": round(sma50, 2) if sma50 else None,
                    "pct_1mo": round(pct_1mo, 2) if pct_1mo else None,
                }

            except Exception as e:
                logger.warning(f"Polygon SMA fetch failed for {ticker}: {e}")

    # Cache in Redis
    if sma_data:
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis:
                payload = json.dumps(sma_data)
                await redis.set(SECTOR_SMA_KEY, payload, ex=86400)  # 24h TTL
                logger.info(f"Sector SMA cache refreshed: {len(sma_data)} tickers")
        except Exception as e:
            logger.warning(f"Redis SMA cache write failed: {e}")

    return sma_data


async def _refresh_sma_yfinance() -> Dict[str, Dict[str, float]]:
    """yfinance fallback for SMA data."""
    import asyncio
    sma_data = {}
    try:
        import yfinance as yf
        for ticker in ALL_TICKERS:
            try:
                t = yf.Ticker(ticker)
                hist = await asyncio.to_thread(lambda: t.history(period="3mo"))
                if hist.empty or len(hist) < 20:
                    continue
                closes = hist["Close"].tolist()
                sma20 = sum(closes[-20:]) / 20
                sma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 50 else None
                pct_1mo = ((closes[-1] - closes[-22]) / closes[-22]) * 100 if len(closes) >= 22 else None
                sma_data[ticker] = {
                    "sma20": round(sma20, 2),
                    "sma50": round(sma50, 2) if sma50 else None,
                    "pct_1mo": round(pct_1mo, 2) if pct_1mo else None,
                }
            except Exception:
                continue
    except Exception as e:
        logger.error(f"yfinance SMA fallback failed: {e}")
    return sma_data


async def get_cached_sma() -> Dict[str, Dict[str, float]]:
    """Read SMA data from Redis cache."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            raw = await redis.get(SECTOR_SMA_KEY)
            if raw:
                return json.loads(raw)
    except Exception as e:
        logger.warning(f"Failed to read SMA cache: {e}")
    return {}


async def compute_sector_strength() -> Dict[str, Any]:
    """
    Compute real-time sector strength scores.
    Combines live prices (Polygon snapshot) with cached SMAs.
    Called every 15 seconds during market hours.

    Returns sector_scores dict suitable for update_sector_strength().
    """
    prices = await fetch_sector_prices()
    if not prices:
        return {}

    sma_cache = await get_cached_sma()
    spy_price = prices.get("SPY")
    spy_sma = sma_cache.get("SPY", {})
    spy_pct_1mo = spy_sma.get("pct_1mo", 0) or 0

    sector_scores = {}

    for sector_name, etf in SECTOR_ETFS.items():
        price = prices.get(etf)
        if not price:
            continue

        sma = sma_cache.get(etf, {})
        sma20 = sma.get("sma20")
        sma50 = sma.get("sma50")
        pct_1mo = sma.get("pct_1mo", 0) or 0

        above_20sma = price > sma20 if sma20 else None
        above_50sma = price > sma50 if sma50 else None
        relative_strength = pct_1mo - spy_pct_1mo

        # Score: higher = stronger sector
        score = 0
        if above_20sma:
            score += 1
        if above_50sma:
            score += 1
        if relative_strength > 1:
            score += 2
        elif relative_strength > 0:
            score += 1
        elif relative_strength < -1:
            score -= 1

        sector_scores[sector_name] = {
            "etf": etf,
            "price": round(price, 2),
            "above_20sma": above_20sma,
            "above_50sma": above_50sma,
            "pct_change_month": round(pct_1mo, 2),
            "relative_strength": round(relative_strength, 2),
            "strength": score,
            "trend": "leading" if score >= 3 else ("lagging" if score <= 0 else "neutral"),
        }

    # Add rank
    sorted_sectors = sorted(sector_scores.items(), key=lambda x: x[1]["strength"], reverse=True)
    for rank, (name, data) in enumerate(sorted_sectors, 1):
        sector_scores[name]["rank"] = rank

    # Cache in Redis (short TTL — refreshed every 15s)
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            await redis.set(SECTOR_STRENGTH_KEY, json.dumps(sector_scores), ex=30)  # 30s TTL
    except Exception:
        pass

    return sector_scores
