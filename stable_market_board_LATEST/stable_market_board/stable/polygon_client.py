"""Minimal Polygon.io client for daily aggregate bars.

Uses the v2 aggregates endpoint:
  GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}

Docs: https://polygon.io/docs/rest/stocks/aggregates/custom-bars
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import config


BASE_URL = "https://api.polygon.io"
SESSION = requests.Session()


class PolygonError(Exception):
    """Raised when Polygon returns a non-OK response."""


class PolygonRateLimit(Exception):
    """Raised on 429. Retry with backoff."""


@retry(
    retry=retry_if_exception_type((PolygonRateLimit, requests.ConnectionError, requests.Timeout)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _get(path: str, params: dict) -> dict:
    """GET a Polygon endpoint with retry on transient errors."""
    params = {**params, "apiKey": config.polygon_api_key()}
    resp = SESSION.get(f"{BASE_URL}{path}", params=params, timeout=30)

    if resp.status_code == 429:
        raise PolygonRateLimit("rate limited")
    if resp.status_code >= 500:
        raise requests.ConnectionError(f"server error {resp.status_code}")
    if resp.status_code != 200:
        raise PolygonError(
            f"GET {path} -> {resp.status_code}: {resp.text[:300]}"
        )

    return resp.json()


def fetch_daily_bars(
    ticker: str,
    start: date,
    end: date,
    adjusted: bool = True,
) -> pd.DataFrame:
    """Fetch daily OHLCV bars for `ticker` between `start` and `end` (inclusive).

    Returns a DataFrame with columns: ticker, date, open, high, low, close, volume.
    Returns an empty DataFrame if Polygon returns no results.
    """
    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}"
    params = {
        "adjusted": "true" if adjusted else "false",
        "sort": "asc",
        "limit": 50000,
    }

    data = _get(path, params)

    # Polygon returns status="OK" with no `results` field when there's no data
    results = data.get("results") or []
    if not results:
        return pd.DataFrame(
            columns=["ticker", "date", "open", "high", "low", "close", "volume"]
        )

    df = pd.DataFrame(results)
    # Polygon column names: t (ms timestamp), o, h, l, c, v
    df = df.rename(columns={
        "t": "ts_ms",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "volume",
    })
    df["date"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.tz_convert("America/New_York").dt.date
    df["ticker"] = ticker
    df["volume"] = df["volume"].astype("int64")
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]


def fetch_full_market_snapshot() -> pd.DataFrame:
    """Fetch a snapshot of the entire US stock market in a single API call.

    Uses the snapshot endpoint:
      GET /v2/snapshot/locale/us/markets/stocks/tickers

    On the Stocks Starter plan this data is 15-minute delayed. Returns the most
    recent available trade price for every ticker, plus the current-day bar
    (open/high/low/close/volume so far) and the previous day's close.

    Returns a DataFrame with columns:
      ticker, last_price, day_open, day_high, day_low, day_volume,
      prev_close, change_pct, updated_ms

    `change_pct` is today's move versus the previous close, as a decimal
    (0.025 = +2.5%). Returns an empty DataFrame on failure.
    """
    path = "/v2/snapshot/locale/us/markets/stocks/tickers"
    try:
        data = _get(path, {})
    except Exception as e:
        print(f"snapshot fetch failed: {e}")
        return pd.DataFrame(columns=[
            "ticker", "last_price", "day_open", "day_high", "day_low",
            "day_volume", "prev_close", "change_pct", "updated_ms",
        ])

    tickers = data.get("tickers") or []
    rows = []
    for t in tickers:
        day = t.get("day") or {}
        prev = t.get("prevDay") or {}
        last_trade = t.get("lastTrade") or {}
        last_quote = t.get("lastQuote") or {}

        # Prefer last trade price; fall back to day close, then quote midpoint
        last_price = last_trade.get("p")
        if not last_price:
            last_price = day.get("c")
        if not last_price and last_quote.get("p") and last_quote.get("P"):
            last_price = (last_quote["p"] + last_quote["P"]) / 2

        prev_close = prev.get("c")
        # Polygon also provides todaysChangePerc directly
        change_pct = t.get("todaysChangePerc")
        if change_pct is not None:
            change_pct = change_pct / 100.0  # Polygon gives it as a percent
        elif last_price and prev_close:
            change_pct = (last_price / prev_close) - 1.0

        rows.append({
            "ticker": t.get("ticker"),
            "last_price": last_price,
            "day_open": day.get("o"),
            "day_high": day.get("h"),
            "day_low": day.get("l"),
            "day_volume": day.get("v"),
            "prev_close": prev_close,
            "change_pct": change_pct,
            "updated_ms": t.get("updated"),  # nanosecond timestamp
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.dropna(subset=["ticker"])
    return df


def health_check() -> bool:
    """Verify the API key works by pulling 5 days of SPY."""
    try:
        end = date.today()
        start = end - timedelta(days=10)
        df = fetch_daily_bars("SPY", start, end)
        return len(df) > 0
    except Exception as e:
        print(f"health check failed: {e}")
        return False
