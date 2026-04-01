"""
Financial Modeling Prep (FMP) API Client
Free tier: 250 calls/day
Used for: earnings calendar, ETF holdings
"""
import os
import logging
import httpx
from datetime import date
from typing import List, Dict

logger = logging.getLogger("fmp_client")

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
FMP_API_KEY = os.getenv("FMP_API_KEY") or ""


async def fetch_earnings_calendar(date_from: date, date_to: date) -> List[Dict]:
    """
    Fetch earnings calendar from FMP for a date range.
    Max range: 3 months per call.
    Returns list of dicts with keys: symbol, date, eps, epsEstimated,
    revenue, revenueEstimated, fiscalDateEnding, time, etc.
    """
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping earnings fetch")
        return []

    url = f"{FMP_BASE_URL}/earning_calendar"
    params = {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "apikey": FMP_API_KEY
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    # FMP returns a flat list of earnings entries
    # Normalize the 'time' field: "bmo" → "BMO", "amc" → "AMC", else "TNS"
    for entry in data:
        raw_time = (entry.get("time") or "").lower()
        if "bmo" in raw_time or "before" in raw_time:
            entry["_timing"] = "BMO"
        elif "amc" in raw_time or "after" in raw_time:
            entry["_timing"] = "AMC"
        else:
            entry["_timing"] = "TNS"

    return data


async def fetch_etf_holdings(symbol: str, limit: int = 10) -> List[Dict]:
    """
    Fetch top holdings for an ETF from FMP.
    Returns list of dicts with keys: asset, name, weight, etc.
    """
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping ETF holdings fetch")
        return []

    url = f"{FMP_BASE_URL}/etf-holder/{symbol}"
    params = {"apikey": FMP_API_KEY}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    # FMP returns holdings sorted by weight descending
    return data[:limit] if data else []
