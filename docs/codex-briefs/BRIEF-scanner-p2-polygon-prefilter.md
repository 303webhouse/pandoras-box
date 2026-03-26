# BRIEF: Polygon Pre-Filter — Two-Stage Scanner Architecture (P2)

## Overview
All scanners currently use a hardcoded ~200 ticker universe from `scanners/universe.py`. This brief adds a **Stage 1 pre-filter** using Polygon's snapshot endpoint to scan the ENTIRE US equity market in a single API call, filter for unusual activity, and feed only the active subset (~50-200 tickers) to existing scanner logic (Stage 2).

This scales coverage from 200 hardcoded names to the full US market while using **fewer** API calls.

## Architecture

```
Stage 1: Polygon Snapshot (1 API call)
  └── /v2/snapshot/locale/us/markets/stocks/tickers
  └── Returns ALL US equities: price, volume, day change, prev day volume
  └── Filter: price $5-$500, volume > 500K or > 2x avg, day change > ±1.5%
  └── Output: "hot list" of 50-200 tickers

Stage 2: Existing Scanner Logic (unchanged)
  └── Holy Grail, Scout Sniper, Sell the Rip, CTA
  └── Receive hot list instead of hardcoded universe
  └── Bar data still from yfinance (Polygon bar migration is separate brief)
```

## New File: `backend/scanners/polygon_prefilter.py`

```python
"""
Polygon Pre-Filter (Stage 1) — "The Dragnet"
Scans the entire US equity market via Polygon's snapshot endpoint.
Filters for unusual volume, movement, and liquidity.
Feeds active subset to scanner Stage 2.

One API call = entire market. Cached in Redis for 5 minutes.
"""

import logging
import json
import asyncio
import aiohttp
import os
from datetime import datetime
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
            day_open = day.get("o", 0)
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
        if symbols:
            await redis.set(CACHE_KEY, json.dumps(symbols), ex=CACHE_TTL)

        return symbols

    except Exception as e:
        logger.error("Polygon pre-filter error: %s", e)
        return None
```

## Modify: `backend/scanners/universe.py`

At the top of `build_scan_universe()`, attempt Polygon pre-filter first. If it succeeds, merge with always-scan instruments and position tickers. If it fails, fall through to existing logic.

Find:
```python
async def build_scan_universe(
    max_tickers: int = 300,
    include_scanner_universe: bool = True,
    respect_muted: bool = True,
) -> List[str]:
    """
    Build deduplicated scan universe in priority order:
    1. Active position tickers (priority='high')
    2. Manual watchlist tickers (source='manual', not muted)
    3. Always-scan instruments (sector ETFs, indices, commodities, currencies, international)
    4. Scanner universe tickers (source='scanner', not muted)
    5. Fallback to hardcoded lists if DB unavailable
    """
    universe: List[str] = []
    seen = set()
```

Replace with:
```python
async def build_scan_universe(
    max_tickers: int = 300,
    include_scanner_universe: bool = True,
    respect_muted: bool = True,
    use_polygon_prefilter: bool = True,
) -> List[str]:
    """
    Build deduplicated scan universe in priority order:
    0. Polygon pre-filter active universe (if available) — dynamic full-market scan
    1. Active position tickers (priority='high')
    2. Manual watchlist tickers (source='manual', not muted)
    3. Always-scan instruments (sector ETFs, indices, commodities, currencies, international)
    4. Scanner universe tickers (source='scanner', not muted)
    5. Fallback to hardcoded lists if DB unavailable
    """
    universe: List[str] = []
    seen = set()
```

Then right after the `add_unique` helper function definition, before the `try:` block, add:

```python
    # Stage 1: Polygon pre-filter (dynamic full-market scan)
    if use_polygon_prefilter:
        try:
            from scanners.polygon_prefilter import get_active_universe
            polygon_tickers = await get_active_universe()
            if polygon_tickers:
                logger.info("Polygon pre-filter provided %d active tickers", len(polygon_tickers))
                add_unique(polygon_tickers)
        except Exception as e:
            logger.warning("Polygon pre-filter failed, using standard universe: %s", e)
```

This goes BEFORE the existing `try:` block that queries the DB. The Polygon tickers get added first (highest dynamic priority), then position/watchlist/always-scan tickers fill in gaps.

## API Endpoint (optional but useful for monitoring)

Add a simple endpoint to check what the pre-filter is producing. Add to `backend/api/scanner.py` or create a new route:

```python
@router.get("/scanner/polygon-prefilter")
async def get_polygon_prefilter_status():
    """Check current Polygon pre-filter active universe."""
    from scanners.polygon_prefilter import get_active_universe, PREFILTER_CONFIG
    universe = await get_active_universe()
    return {
        "active_tickers": len(universe) if universe else 0,
        "tickers": universe[:20] if universe else [],
        "config": PREFILTER_CONFIG,
        "source": "polygon_snapshot",
    }
```

## Environment Variable
Ensure `POLYGON_API_KEY` is set in Railway environment. It should already be there from existing Polygon usage.

## Testing
1. Deploy and check logs for `Polygon snapshot: X tickers received`
2. Check logs for `Polygon pre-filter: X active tickers from Y total`
3. Verify scanners still produce signals (they should find MORE setups now)
4. From VPS: `curl -s -H "X-API-Key: $KEY" "$BASE/api/scanner/polygon-prefilter" | python3 -m json.tool`
5. Compare active universe vs hardcoded — are there movers the old list missed?

## Risk
Low. The pre-filter is additive — if Polygon fails, the system falls through to the existing DB/hardcoded universe with zero disruption. The `use_polygon_prefilter=True` flag allows disabling without code changes.

## Future (separate brief)
- Migrate scanner bar data from yfinance to Polygon (15m, 1H, daily bars)
- Add market cap filter using Polygon reference data
- Dynamic threshold adjustment based on market regime (tighter in low-vol, looser in high-vol)
