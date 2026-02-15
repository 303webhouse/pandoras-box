"""
Get current price, change, volume, and day range for any ticker.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import yfinance as yf

from tools.helpers import _now_iso, _error_response
from tools import YF_LOCK

logger = logging.getLogger(__name__)


async def get_quote(ticker: str) -> dict:
    """Get quote data for a ticker (price, change, volume, ranges, moving averages)."""
    try:
        return await asyncio.to_thread(_get_quote_sync, ticker)
    except Exception as exc:
        logger.error(f"get_quote({ticker}) failed: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


def _get_quote_sync(ticker: str) -> dict:
    """Synchronous implementation of quote fetch."""
    try:
        t = yf.Ticker(ticker)

        # Try fast_info first (lighter weight), fall back to full info
        info: dict = {}
        try:
            fi = t.fast_info
            # fast_info is an object with attributes, convert to dict-like access
            info = {
                "currentPrice": getattr(fi, "last_price", None),
                "regularMarketPrice": getattr(fi, "last_price", None),
                "regularMarketChange": None,
                "regularMarketChangePercent": None,
                "regularMarketOpen": getattr(fi, "open", None),
                "regularMarketDayHigh": getattr(fi, "day_high", None),
                "regularMarketDayLow": getattr(fi, "day_low", None),
                "regularMarketPreviousClose": getattr(fi, "previous_close", None),
                "regularMarketVolume": getattr(fi, "three_month_average_volume", None),
                "averageVolume10days": getattr(fi, "three_month_average_volume", None),
                "fiftyDayAverage": getattr(fi, "fifty_day_average", None),
                "twoHundredDayAverage": getattr(fi, "two_hundred_day_average", None),
                "fiftyTwoWeekHigh": getattr(fi, "year_high", None),
                "fiftyTwoWeekLow": getattr(fi, "year_low", None),
                "marketCap": getattr(fi, "market_cap", None),
                "shortName": None,
            }
            # Compute change fields if possible
            price = info["currentPrice"]
            prev = info["regularMarketPreviousClose"]
            if price is not None and prev is not None and prev != 0:
                info["regularMarketChange"] = price - prev
                info["regularMarketChangePercent"] = ((price - prev) / prev) * 100
        except Exception:
            pass

        # Fill missing fields from full .info if needed
        key_fields = ["currentPrice", "regularMarketPrice", "regularMarketVolume", "shortName"]
        needs_full_info = any(info.get(f) is None for f in key_fields)
        if needs_full_info:
            try:
                full = t.info
                if full:
                    # Merge: only fill in missing fields
                    for k, v in full.items():
                        if info.get(k) is None:
                            info[k] = v
            except Exception as exc:
                logger.debug(f"Full .info fetch failed for {ticker}: {exc}")

        # Extract price with fallbacks
        price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )

        if price is None:
            return _error_response(ticker, "Ticker not found or no data available")

        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")

        # Compute change if not already set
        change_dollars = info.get("regularMarketChange")
        change_pct = info.get("regularMarketChangePercent")
        if change_dollars is None and price is not None and prev_close is not None:
            change_dollars = price - prev_close
        if change_pct is None and price is not None and prev_close is not None and prev_close != 0:
            change_pct = ((price - prev_close) / prev_close) * 100

        # Normalize percent: yfinance sometimes returns as decimal (0.006 = 0.6%)
        if change_pct is not None and abs(change_pct) < 1 and abs(change_pct) > 0:
            # Likely a decimal fraction; multiply by 100
            pass  # yfinance usually returns as percent already for regularMarketChangePercent

        name = (
            info.get("shortName")
            or info.get("longName")
            or ticker.upper()
        )

        return {
            "status": "ok",
            "ticker": ticker.upper(),
            "name": name,
            "price": _safe_float(price),
            "change_dollars": _safe_float(change_dollars),
            "change_percent": _safe_float(change_pct),
            "open": _safe_float(info.get("regularMarketOpen") or info.get("open")),
            "high": _safe_float(info.get("regularMarketDayHigh") or info.get("dayHigh")),
            "low": _safe_float(info.get("regularMarketDayLow") or info.get("dayLow")),
            "prev_close": _safe_float(prev_close),
            "volume": _safe_int(info.get("regularMarketVolume") or info.get("volume")),
            "avg_volume": _safe_int(
                info.get("averageVolume10days")
                or info.get("averageVolume")
                or info.get("averageDailyVolume10Day")
            ),
            "market_cap": _safe_float(info.get("marketCap")),
            "fifty_day_ma": _safe_float(info.get("fiftyDayAverage")),
            "two_hundred_day_ma": _safe_float(info.get("twoHundredDayAverage")),
            "fifty_two_week_high": _safe_float(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": _safe_float(info.get("fiftyTwoWeekLow")),
            "timestamp": _now_iso(),
        }
    except Exception as exc:
        logger.error(f"_get_quote_sync({ticker}) error: {exc}", exc_info=True)
        return _error_response(ticker, str(exc))


def _safe_float(value) -> Optional[float]:
    """Convert value to float, returning None for invalid/missing values."""
    if value is None:
        return None
    try:
        f = float(value)
        import math
        if not math.isfinite(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> Optional[int]:
    """Convert value to int, returning None for invalid/missing values."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
