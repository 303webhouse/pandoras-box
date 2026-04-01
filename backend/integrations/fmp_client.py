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

FMP_BASE_URL = "https://financialmodelingprep.com/stable"
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

    url = f"{FMP_BASE_URL}/earnings-calendar"
    params = {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "apikey": FMP_API_KEY
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    # Stable API does not include 'time' field (BMO/AMC)
    # Default to None — timing can be enriched later from other sources
    for entry in data:
        entry["_timing"] = None

    return data


async def fetch_etf_holdings(symbol: str, limit: int = 10) -> List[Dict]:
    """
    Fetch top holdings for an ETF from FMP.
    Returns list of dicts with keys: asset, name, weight, etc.
    """
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping ETF holdings fetch")
        return []

    url = f"{FMP_BASE_URL}/etf/holdings"
    params = {"symbol": symbol, "apikey": FMP_API_KEY}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        if resp.status_code in (402, 403):
            logger.info("FMP ETF holdings endpoint is paid-only (status %d)", resp.status_code)
            return []
        resp.raise_for_status()
        data = resp.json()

    return data[:limit] if data else []
