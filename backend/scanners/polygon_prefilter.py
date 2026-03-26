"""
Polygon Pre-Filter (Stage 1) — "The Dragnet"
Scans the entire US equity market via Polygon's snapshot endpoint.
Filters for unusual volume, movement, and liquidity.
Feeds active subset to scanner Stage 2.

One API call = entire market. Cached in Redis for 5 minutes.
"""

import logging
import json
import aiohttp
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
CACHE_KEY = "scanner:polygon_prefilter:active_universe"
CACHE_TTL = 300  # 5 minutes

# Pre-filter thresholds
PREFILTER_CONFIG = {
    "min_price": 5.0,
    "max_price": 500.0,
    "min_volume": 500_000,       # Minimum absolute volume
    "rvol_threshold": 2.0,       # OR relative volume vs prev day
    "min_day_change_pct": 1.5,   # Minimum absolute day change %
    "max_results": 200,          # Cap the hot list
}


async def fetch_polygon_snapshot() -> Optional[List[Dict]]:
    """Fetch full market snapshot from Polygon. One API call."""
    if not POLYGON_API_KEY:
        logger.warning("Polygon pre-filter: POLYGON_API_KEY not set")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            params = {"apiKey": POLYGON_API_KEY}
            async with session.get(SNAPSHOT_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.error("Polygon snapshot failed: HTTP %d", resp.status)
                    return None
                data = await resp.json()
                tickers = data.get("tickers", [])
                logger.info("Polygon snapshot: %d tickers received", len(tickers))
                return tickers
    except Exception as e:
        logger.error("Polygon snapshot error: %s", e)
        return None


def filter_active_universe(snapshot: List[Dict]) -> List[str]:
    """Apply pre-filter criteria to snapshot data. Returns list of active ticker symbols."""
    cfg = PREFILTER_CONFIG
    active = []

    for t in snapshot:
        try:
            ticker_symbol = t.get("ticker", "")
            day = t.get("day", {})
            prev_day = t.get("prevDay", {})

            price = day.get("c", 0)  # close price
            volume = day.get("v", 0)  # volume
            prev_close = prev_day.get("c", 0)
            prev_volume = prev_day.get("v", 0)

            # Skip if missing critical data
            if not price or not volume or not prev_close:
                continue

            # Price filter
            if price < cfg["min_price"] or price > cfg["max_price"]:
                continue

            # Day change %
            day_change_pct = abs((price - prev_close) / prev_close * 100) if prev_close > 0 else 0

            # Relative volume
            rvol = volume / prev_volume if prev_volume > 0 else 0

            # Must pass EITHER volume gate OR movement gate
            volume_pass = volume >= cfg["min_volume"] or rvol >= cfg["rvol_threshold"]
            movement_pass = day_change_pct >= cfg["min_day_change_pct"]

            if volume_pass and movement_pass:
                active.append({
                    "symbol": ticker_symbol,
                    "price": round(price, 2),
                    "volume": volume,
                    "rvol": round(rvol, 2),
                    "day_change_pct": round(day_change_pct, 2),
                })

        except Exception:
            continue

    # Sort by day_change_pct descending (biggest movers first)
    active.sort(key=lambda x: x["day_change_pct"], reverse=True)

    # Cap results
    active = active[:cfg["max_results"]]

    symbols = [a["symbol"] for a in active]
    logger.info(
        "Polygon pre-filter: %d active tickers from %d total (top movers: %s)",
        len(symbols), len(snapshot),
        ", ".join(symbols[:5]) if symbols else "none",
    )
    return symbols


async def get_active_universe() -> Optional[List[str]]:
    """Get the active universe, using Redis cache if fresh."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()

        # Check cache
        if redis:
            cached = await redis.get(CACHE_KEY)
            if cached:
                symbols = json.loads(cached)
                logger.debug("Polygon pre-filter: using cached universe (%d tickers)", len(symbols))
                return symbols

        # Fetch fresh snapshot
        snapshot = await fetch_polygon_snapshot()
        if not snapshot:
            return None

        symbols = filter_active_universe(snapshot)

        # Cache result
        if symbols and redis:
            await redis.set(CACHE_KEY, json.dumps(symbols), ex=CACHE_TTL)

        return symbols

    except Exception as e:
        logger.error("Polygon pre-filter error: %s", e)
        return None
