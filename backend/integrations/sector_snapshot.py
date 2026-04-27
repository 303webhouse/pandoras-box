"""
Sector Strength Snapshot

Real-time sector ETF prices via yfinance.
SMA data cached separately (refreshed once daily).

Data source: yfinance (UW API migration in progress — see POST-CUTOVER-TODO.md P3).
"""
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    Compute 20-day and 50-day SMAs via yfinance.
    Called once daily after close. Cached in Redis with 24h TTL.
    Returns: {"SPY": {"sma20": 540.5, "sma50": 535.2, "pct_1mo": 2.3}, ...}
    """
    sma_data = await _refresh_sma_yfinance()

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
