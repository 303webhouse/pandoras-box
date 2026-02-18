"""
Calendar and event context helpers for signal instrumentation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MARKET_EVENTS_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "market_events.json",
)

_events_cache: Dict[str, Any] = {"mtime": None, "mapping": {}}
_earnings_cache: Dict[str, Dict[str, Any]] = {}
_earnings_ttl = timedelta(hours=6)

_LIKELY_CRYPTO_TICKERS = {
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "ADA",
    "AVAX",
    "DOGE",
    "DOT",
    "LINK",
    "LTC",
    "BCH",
    "XLM",
}


def _third_friday(year: int, month: int) -> date:
    first_day = date(year, month, 1)
    # Monday=0 ... Friday=4
    days_to_first_friday = (4 - first_day.weekday()) % 7
    return first_day + timedelta(days=days_to_first_friday + 14)


def check_opex_week(ts: datetime) -> bool:
    d = ts.date()
    third_friday = _third_friday(d.year, d.month)
    week_start = third_friday - timedelta(days=4)  # Monday
    return week_start <= d <= third_friday


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime()
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _normalize_ticker_for_earnings(ticker: str) -> Optional[str]:
    if not ticker:
        return None
    symbol = ticker.upper().strip()
    if (
        symbol in _LIKELY_CRYPTO_TICKERS
        or symbol.endswith("USDT")
        or symbol.endswith("USDTPERP")
        or symbol.endswith("PERP")
        or symbol.endswith("-USD")
        or symbol.endswith("USD")
    ):
        return None
    return symbol


def _extract_earnings_date(calendar: Any) -> Optional[datetime]:
    # yfinance may return DataFrame, Series, dict-like, or None.
    if calendar is None:
        return None

    try:
        if hasattr(calendar, "empty") and calendar.empty:
            return None
    except Exception:
        pass

    if isinstance(calendar, dict):
        candidates = (
            calendar.get("Earnings Date"),
            calendar.get("earningsDate"),
            calendar.get("EarningsDate"),
        )
        for candidate in candidates:
            if isinstance(candidate, (list, tuple)) and candidate:
                dt_value = _coerce_datetime(candidate[0])
                if dt_value:
                    return dt_value
            dt_value = _coerce_datetime(candidate)
            if dt_value:
                return dt_value
        return None

    # DataFrame/Series path
    try:
        if "Earnings Date" in calendar.index:
            candidate = calendar.loc["Earnings Date"]
            if hasattr(candidate, "iloc"):
                for idx in range(len(candidate)):
                    dt_value = _coerce_datetime(candidate.iloc[idx])
                    if dt_value:
                        return dt_value
            dt_value = _coerce_datetime(candidate)
            if dt_value:
                return dt_value
    except Exception:
        pass

    return None


def _fetch_days_to_earnings_sync(ticker: str, as_of: datetime) -> Optional[int]:
    symbol = _normalize_ticker_for_earnings(ticker)
    if not symbol:
        return None

    try:
        import yfinance as yf

        stock = yf.Ticker(symbol)
        earnings_date = _extract_earnings_date(stock.calendar)
        if not earnings_date:
            return None
        days = (earnings_date.date() - as_of.date()).days
        if 0 <= days <= 30:
            return int(days)
        return None
    except Exception as exc:
        logger.debug("Earnings lookup failed for %s: %s", symbol, exc)
        return None


async def get_days_to_earnings(ticker: str, as_of: datetime) -> Optional[int]:
    symbol = _normalize_ticker_for_earnings(ticker)
    if not symbol:
        return None

    cached = _earnings_cache.get(symbol)
    now = datetime.utcnow()
    if cached and cached.get("expires_at") and cached["expires_at"] > now:
        return cached.get("value")

    value = await asyncio.to_thread(_fetch_days_to_earnings_sync, symbol, as_of)
    _earnings_cache[symbol] = {
        "value": value,
        "expires_at": now + _earnings_ttl,
    }
    return value


def _load_market_events_mapping() -> Dict[str, str]:
    try:
        mtime = os.path.getmtime(MARKET_EVENTS_FILE)
    except OSError:
        return {}

    if _events_cache.get("mtime") == mtime:
        return _events_cache.get("mapping", {})

    try:
        with open(MARKET_EVENTS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        logger.debug("Failed to load market events file: %s", exc)
        return {}

    mapping: Dict[str, str] = {}
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            d = str(item.get("date") or "").strip()
            event = str(item.get("event") or "").strip()
            if d and event:
                mapping[d] = event
    elif isinstance(payload, dict):
        # Accept {"YYYY-MM-DD": "EVENT"} shorthand.
        for d, event in payload.items():
            if d and event:
                mapping[str(d)] = str(event)

    _events_cache["mtime"] = mtime
    _events_cache["mapping"] = mapping
    return mapping


def check_market_event(ts: datetime) -> Optional[str]:
    mapping = _load_market_events_mapping()
    if not mapping:
        return None
    return mapping.get(ts.date().isoformat())


async def get_signal_calendar_fields(timestamp: datetime, ticker: str) -> Dict[str, Any]:
    ts = timestamp if isinstance(timestamp, datetime) else datetime.utcnow()
    day_of_week = ts.weekday()
    hour_of_day = ts.hour
    is_opex_week = check_opex_week(ts)
    days_to_earnings = await get_days_to_earnings(ticker or "", ts)
    market_event = check_market_event(ts)

    return {
        "day_of_week": day_of_week,
        "hour_of_day": hour_of_day,
        "is_opex_week": is_opex_week,
        "days_to_earnings": days_to_earnings,
        "market_event": market_event,
    }

