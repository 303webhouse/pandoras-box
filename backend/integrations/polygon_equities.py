"""
Polygon.io Equities Integration

Fetches OHLCV bars and snapshots for equity/ETF tickers.
Uses /v2/aggs/ticker/{ticker}/range/ for bars and /v2/snapshot/ for latest data.
Polygon Stocks Starter plan ($29/mo): 15-min delayed, unlimited calls.

This client mirrors the structure of polygon_options.py.
"""

import os
import logging
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY") or ""
POLYGON_BASE = "https://api.polygon.io"

# In-memory cache: {cache_key: (timestamp, data)}
_bars_cache: Dict[str, tuple] = {}
_snapshot_cache: Dict[str, tuple] = {}
_CACHE_TTL = 300  # 5 minutes


async def get_bars(
    ticker: str,
    multiplier: int = 1,
    timespan: str = "day",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch OHLCV bars from Polygon aggregates endpoint.

    Args:
        ticker: Stock/ETF ticker (e.g., "SPY", "XLK")
        multiplier: Bar size multiplier (default 1)
        timespan: Bar timespan — "day", "hour", "minute" (default "day")
        from_date: Start date YYYY-MM-DD (default: 60 days ago)
        to_date: End date YYYY-MM-DD (default: today)

    Returns:
        List of bar dicts with keys: o, h, l, c, v, vw, t, n
        or None on failure.
    """
    if not POLYGON_API_KEY:
        logger.debug("POLYGON_API_KEY not set — skipping equities bars")
        return None

    today = date.today()
    if not from_date:
        from_date = (today - timedelta(days=60)).isoformat()
    if not to_date:
        to_date = today.isoformat()

    cache_key = f"{ticker.upper()}|{multiplier}|{timespan}|{from_date}|{to_date}"
    cached = _bars_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    url = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker.upper()}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
    params: Dict[str, Any] = {
        "apiKey": POLYGON_API_KEY,
        "adjusted": "true",
        "sort": "asc",
        "limit": 5000,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.error(
                    "Polygon bars %s: HTTP %s — %s",
                    ticker, resp.status_code, resp.text[:200],
                )
                return None

            data = resp.json()
            results = data.get("results")
            if not results:
                logger.warning("Polygon bars %s: empty results", ticker)
                return None

    except Exception as e:
        logger.error("Polygon bars %s failed: %s", ticker, e)
        return None

    logger.info("Fetched %d bars for %s (%s %s)", len(results), ticker, multiplier, timespan)
    _bars_cache[cache_key] = (time.time(), results)
    return results


async def get_bars_as_dataframe(ticker: str, days: int = 30) -> Optional[pd.DataFrame]:
    """
    Convenience wrapper: fetch daily bars and return as a pandas DataFrame
    matching the format expected by factor_utils (columns: open, high, low, close, volume).
    """
    today = date.today()
    # Request extra days to account for weekends/holidays
    from_date = (today - timedelta(days=int(days * 1.6) + 5)).isoformat()
    to_date = today.isoformat()

    bars = await get_bars(ticker, 1, "day", from_date, to_date)
    if not bars:
        return None

    rows = []
    for bar in bars:
        ts = bar.get("t")
        if ts is None:
            continue
        # Polygon timestamps are in milliseconds
        dt = pd.Timestamp(ts, unit="ms")
        rows.append({
            "open": bar.get("o"),
            "high": bar.get("h"),
            "low": bar.get("l"),
            "close": bar.get("c"),
            "volume": bar.get("v"),
        })

    if not rows:
        return None

    # Build DataFrame with DatetimeIndex
    timestamps = [pd.Timestamp(bar["t"], unit="ms") for bar in bars if bar.get("t") is not None]
    df = pd.DataFrame(rows, index=timestamps[:len(rows)])
    df.index.name = "Date"

    # Trim to requested number of trading days
    if len(df) > days:
        df = df.iloc[-days:]

    return df


async def get_snapshot(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get latest snapshot for a ticker (current price, volume, prev day).
    Uses /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}.
    """
    if not POLYGON_API_KEY:
        return None

    cache_key = f"snapshot|{ticker.upper()}"
    cached = _snapshot_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}"
    params = {"apiKey": POLYGON_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.error(
                    "Polygon snapshot %s: HTTP %s — %s",
                    ticker, resp.status_code, resp.text[:200],
                )
                return None

            data = resp.json()
            result = data.get("ticker")
            if not result:
                logger.warning("Polygon snapshot %s: no ticker data", ticker)
                return None

    except Exception as e:
        logger.error("Polygon snapshot %s failed: %s", ticker, e)
        return None

    _snapshot_cache[cache_key] = (time.time(), result)
    return result


async def get_previous_close(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get previous trading day's OHLCV for a ticker.
    Uses /v2/aggs/ticker/{ticker}/prev.
    """
    if not POLYGON_API_KEY:
        return None

    url = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker.upper()}/prev"
    params = {"apiKey": POLYGON_API_KEY, "adjusted": "true"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.error(
                    "Polygon prev close %s: HTTP %s — %s",
                    ticker, resp.status_code, resp.text[:200],
                )
                return None

            data = resp.json()
            results = data.get("results")
            if not results:
                return None
            return results[0] if isinstance(results, list) else results

    except Exception as e:
        logger.error("Polygon prev close %s failed: %s", ticker, e)
        return None


def clear_cache():
    """Clear all in-memory caches."""
    _bars_cache.clear()
    _snapshot_cache.clear()
