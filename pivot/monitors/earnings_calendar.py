"""
Earnings proximity monitor.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

import yfinance as yf

from collectors.base_collector import get_json

logger = logging.getLogger(__name__)


def _get_next_earnings_date(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is not None and not cal.empty:
            if "Earnings Date" in cal.index:
                date_val = cal.loc["Earnings Date"][0]
                if isinstance(date_val, datetime):
                    return date_val.date()
                return date_val
    except Exception:
        return None
    return None


async def check_earnings(days_ahead: int = 2) -> List[Dict[str, Any]]:
    try:
        watchlist = await get_json("/watchlist")
    except Exception as exc:
        logger.warning(f"Earnings check failed: {exc}")
        return []

    tickers = watchlist.get("tickers", []) if isinstance(watchlist, dict) else []
    upcoming: List[Dict[str, Any]] = []

    today = datetime.utcnow().date()
    cutoff = today + timedelta(days=days_ahead)

    for symbol in tickers:
        try:
            date_val = _get_next_earnings_date(symbol)
            if not date_val:
                continue
            if isinstance(date_val, datetime):
                date_val = date_val.date()
            if today <= date_val <= cutoff:
                upcoming.append({
                    "ticker": symbol,
                    "earnings_date": date_val.isoformat(),
                    "days_until": (date_val - today).days,
                })
        except Exception:
            continue

    return upcoming
