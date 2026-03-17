# Brief 6C: Sector Data — Polygon Migration + 15-Second Refresh

**Target Agent:** Claude Code (VSCode)
**Priority:** HIGH
**Rule:** Polygon.io is the PRIMARY data source for ALL market data. yfinance is FALLBACK ONLY.

---

## What This Does

Two changes:
1. Migrate `scan_sector_strength()` from yfinance to Polygon.io bulk snapshot (1 API call for all 12 tickers)
2. Increase refresh from 4x/day to every **15 seconds** during market hours

**Architecture:**
- **Real-time prices (every 15s):** Polygon multi-ticker snapshot — ONE call returns current price for all 12 sector ETFs + SPY
- **SMA data (once daily after close):** Polygon historical bars for 20-day and 50-day SMA — 12 calls, cached in Redis
- **Scoring:** Current price vs cached SMA = real-time sector strength with near-zero API cost

---

## Step 1: Create Sector Snapshot Module

**File:** `backend/integrations/sector_snapshot.py` (NEW FILE)

```python
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
    """Polygon first, yfinance fallback."""
    prices = await fetch_sector_prices_polygon()
    if len(prices) >= 6:  # At least half the tickers
        return prices
    logger.warning(f"Polygon returned only {len(prices)} tickers — trying yfinance fallback")
    return await fetch_sector_prices_yfinance()


async def refresh_sma_cache() -> Dict[str, Dict[str, float]]:
    """
    Fetch historical daily bars from Polygon and compute 20-day and 50-day SMAs.
    Called once daily after close. Cached in Redis with 24h TTL.
    Returns: {"SPY": {"sma20": 540.5, "sma50": 535.2, "pct_1mo": 2.3}, ...}
    """
    if not POLYGON_API_KEY:
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
```

---

## Step 2: Replace `scan_sector_strength()` in Scheduler

**File:** `backend/scheduler/bias_scheduler.py`

**Find** the entire `async def scan_sector_strength()` function. It starts with:
```python
async def scan_sector_strength():
    """
    Scan sector ETFs to determine which sectors are leading/lagging.
    Updates the watchlist with sector strength rankings.
```

And ends just before `async def start_scheduler():`.

**Replace the entire function** with:

```python
async def scan_sector_strength():
    """
    Scan sector ETFs to determine which sectors are leading/lagging.
    Uses Polygon.io bulk snapshot for real-time prices (1 API call).
    SMA data from Redis cache (refreshed daily via refresh_sector_sma_cache).

    Data source: Polygon.io (primary), yfinance (fallback).
    Runs every 15 seconds during market hours.
    """
    try:
        from integrations.sector_snapshot import compute_sector_strength

        sector_scores = await compute_sector_strength()

        if not sector_scores:
            logger.warning("Sector strength scan returned no data")
            return {}

        # Log top and bottom (only every 60s to avoid log spam)
        import time
        _now = time.time()
        if not hasattr(scan_sector_strength, "_last_log") or (_now - scan_sector_strength._last_log) > 60:
            scan_sector_strength._last_log = _now
            sorted_sectors = sorted(sector_scores.items(), key=lambda x: x[1]["strength"], reverse=True)
            if sorted_sectors:
                top = sorted_sectors[0]
                bottom = sorted_sectors[-1]
                logger.info(f"📊 Sector scan: Leading={top[0]} ({top[1]['etf']}, score {top[1]['strength']}), Lagging={bottom[0]} ({bottom[1]['etf']}, score {bottom[1]['strength']})")

        # Update watchlist with sector strength
        try:
            from api.watchlist import SectorStrengthUpdate, update_sector_strength
            await update_sector_strength(SectorStrengthUpdate(sector_strength=sector_scores), _="internal")
        except Exception as e:
            logger.warning(f"Could not update watchlist with sector strength: {e}")

        return sector_scores

    except Exception as e:
        logger.error(f"Error in sector strength scan: {e}")
        return {}
```

---

## Step 3: Add SMA Daily Refresh Job

**File:** `backend/scheduler/bias_scheduler.py`

Add a wrapper function (near the other `run_*_job` functions, e.g. after `run_strc_poller_job`):

```python
async def refresh_sector_sma_cache():
    """Refresh sector SMA cache from Polygon daily bars. Runs once daily after close."""
    try:
        from integrations.sector_snapshot import refresh_sma_cache
        result = await refresh_sma_cache()
        logger.info(f"Sector SMA cache refreshed: {len(result)} tickers")
    except Exception as e:
        logger.error(f"Sector SMA cache refresh failed: {e}")
```

Then register the daily SMA refresh in the APScheduler section. **Find:**
```python
        # WRR Buy Model countertrend scanner (4:20 PM ET, after market close)
```

**Before it**, add:
```python
        # Sector SMA cache refresh (daily after close — historical bars for 20/50-day SMAs)
        scheduler.add_job(
            refresh_sector_sma_cache,
            CronTrigger(day_of_week='mon-fri', hour=16, minute=5, timezone=ET),
            id='sector_sma_refresh',
            name='Sector SMA Cache Refresh',
            replace_existing=True
        )

```

And add the log line after the other startup logs:
```python
        logger.info("✅ Sector SMA cache refresh scheduled daily at 4:05 PM ET")
```

---

## Step 4: Add 15-Second Sector Loop

The sector strength scan needs to run every 15 seconds during market hours. APScheduler's minimum practical interval is ~1 second, but for sub-minute precision, use the same `asyncio.create_task()` loop pattern already used for the scanner loop.

**File:** `backend/scheduler/bias_scheduler.py`

**Add this new function** (near `_scanner_loop()`):

```python
async def _sector_refresh_loop():
    """
    Dedicated loop for real-time sector strength refresh.
    Runs every 15 seconds during market hours using Polygon bulk snapshot.
    Uses ONE Polygon API call per cycle (all 12 sector ETFs + SPY).
    """
    import pytz
    et = pytz.timezone('America/New_York')
    logger.info("Starting sector refresh loop (15s interval, market hours)")

    while True:
        try:
            now = datetime.now(et)
            hour = now.hour
            minute = now.minute
            time_decimal = hour + minute / 60.0

            # Only run during market hours (9:30 AM - 4:00 PM ET, weekdays)
            is_market = (
                is_trading_day()
                and 9.5 <= time_decimal <= 16.0
            )

            if is_market:
                await scan_sector_strength()

            await asyncio.sleep(15)

        except Exception as e:
            logger.error(f"Error in sector refresh loop: {e}")
            await asyncio.sleep(15)
```

**Then**, in `start_scheduler()`, find where the scanner loop is started:
```python
        # ALSO start the scanner loop (APScheduler doesn't handle the variable-interval scanners)
        asyncio.create_task(_scanner_loop())
        logger.info("✅ Scanner loop started (CTA + Crypto)")
```

**After it**, add:
```python
        asyncio.create_task(_sector_refresh_loop())
        logger.info("✅ Sector refresh loop started (15s interval, market hours)")
```

---

## Step 5: Remove Old 4x/Day Sector Calls

`scan_sector_strength()` is currently called inside `run_scheduled_refreshes()` which runs at 9:45 AM, 11 AM, 1 PM, and 3 PM. Remove it from there since the 15-second loop handles it now.

**File:** `backend/scheduler/bias_scheduler.py`

**Find** in `run_scheduled_refreshes()`:
```python
    # Run sector strength scan every morning
    await scan_sector_strength()
```

**Replace with:**
```python
    # Sector strength scan now runs via dedicated 15-second loop — no longer called here
```

---

## Step 6: Seed SMA Cache on Startup

The SMA cache needs to exist before the 15-second loop starts, otherwise the first cycles will have no SMA data to compare prices against.

**In `start_scheduler()`**, find the initial refresh block:
```python
    # Run initial refresh on startup (Railway has ephemeral filesystem)
    logger.info("  🔄 Running initial bias refresh on startup...")
    try:
        await refresh_daily_bias()
        await refresh_weekly_bias()
        await refresh_cyclical_bias()
```

**After** `await refresh_cyclical_bias()`, add:
```python
        # Seed sector SMA cache so the 15-second loop has data immediately
        try:
            from integrations.sector_snapshot import refresh_sma_cache
            await refresh_sma_cache()
            logger.info("  ✅ Sector SMA cache seeded")
        except Exception as sma_err:
            logger.warning(f"  Sector SMA seed failed: {sma_err}")
```

---

## Step 7: Reduce Redis TTL on Sector RS Cache

The sector RS data currently has an 18-hour Redis TTL. With 15-second refresh, reduce it.

Search for any Redis TTL related to sector data:
```
grep -rn "sector.*ttl\|sector.*ex=\|sector.*expire\|18.*hour\|64800" backend/ --include="*.py"
```

If found, reduce to **60 seconds** (4x the refresh interval, safety buffer for missed cycles).

---

## Testing Checklist

1. **Polygon snapshot:** `compute_sector_strength()` returns prices for all 12 tickers from one API call
2. **SMA cache:** `refresh_sma_cache()` populates Redis key `sector:sma_cache` with 20-day/50-day SMAs
3. **15-second loop:** Railway logs show sector scan entries every ~15 seconds during market hours
4. **No yfinance during market hours:** Polygon is the only source called. yfinance only fires if Polygon returns <6 tickers
5. **SMA seeded on startup:** `sector:sma_cache` exists immediately after deploy
6. **Startup logs:** "✅ Sector refresh loop started (15s interval, market hours)"
7. **Frontend sector data updates:** Dashboard sector display refreshes noticeably faster than before
8. **Log throttling:** Detailed sector log (Leading/Lagging) only appears once per minute, not every 15s

## Definition of Done
- [ ] `backend/integrations/sector_snapshot.py` created
- [ ] `scan_sector_strength()` uses Polygon via new module (yfinance fallback only)
- [ ] 15-second asyncio loop running during market hours
- [ ] SMA cache refreshed daily at 4:05 PM ET via APScheduler
- [ ] SMA cache seeded on startup
- [ ] Old 4x/day calls from `run_scheduled_refreshes()` removed
- [ ] Redis TTLs reduced for real-time data
- [ ] No yfinance calls during normal operation
- [ ] All existing tests pass
