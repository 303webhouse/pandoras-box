"""
Sector-ETF 3-10 Oscillator readings with in-process caching.

Computes 3-10 on the 11 SPDR sector ETFs every bar close, caches readings,
and exposes a lookup function for the signal enrichment pipeline.

Data source: UW API primary, yfinance fallback (per April 2026 data hierarchy).

NOTE: uw_api.get_candles does not yet exist — falling back to yfinance for
bar fetching. TODO: Add uw_api.get_candles for sector-ETF bar fetching —
scope a separate Titans-reviewed ticket.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd

from indicators.three_ten_oscillator import OSC_FAST, OSC_SLOW, OSC_CROSS, compute_3_10

logger = logging.getLogger(__name__)

# 11 SPDR sector ETFs
SECTOR_ETFS = [
    "XLK",  # Technology
    "XLF",  # Financials
    "XLE",  # Energy
    "XLY",  # Consumer Discretionary
    "XLV",  # Health Care
    "XLP",  # Consumer Staples
    "XLU",  # Utilities
    "XLI",  # Industrials
    "XLB",  # Materials
    "XLRE", # Real Estate
    "XLC",  # Communication Services
]

# Ticker-to-sector ETF map (partial — extend via sector_rs module lookup at runtime).
# This is a best-effort shortcut for the most common watchlist tickers.
# sector_rs.py has no get_ticker_sector_etf(ticker) function as of 2026-04-22;
# expand this map manually until that function exists.
_DEFAULT_SECTOR_MAP = {
    # Tech
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "GOOGL": "XLK", "META": "XLK",
    "AMZN": "XLY", "TSLA": "XLY",
    # Financials
    "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "GS": "XLF", "MS": "XLF",
    # Energy
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE",
    # Health
    "UNH": "XLV", "JNJ": "XLV", "LLY": "XLV", "PFE": "XLV",
    # etc. Extend as needed.
}

# In-process cache: sector_etf -> latest 3-10 reading dict
_sector_cache: Dict[str, Dict] = {}
_last_refresh: Optional[datetime] = None
_REFRESH_INTERVAL = timedelta(minutes=15)  # Refresh every 15 min at most


async def get_sector_3_10_for_ticker(ticker: str) -> Optional[Dict]:
    """
    Return the latest 3-10 reading for a ticker's sector ETF.

    Returns None if we can't resolve the sector or the cache is empty.
    Shape: {"sector_etf": "XLK", "osc_fast": 0.12, "osc_slow": 0.08, "osc_cross": 0}
    """
    sector_etf = _DEFAULT_SECTOR_MAP.get(ticker.upper())
    if not sector_etf:
        # Try the sector_rs module for a broader lookup
        try:
            from scanners.sector_rs import get_ticker_sector_etf
            sector_etf = await get_ticker_sector_etf(ticker)
        except Exception:
            pass
    if not sector_etf:
        return None

    # Refresh cache if stale
    await _refresh_if_stale()

    return _sector_cache.get(sector_etf)


async def refresh_sector_cache() -> None:
    """
    Force-refresh all sector ETF 3-10 readings. Safe to call on a schedule.
    """
    global _last_refresh
    tasks = [_compute_single_sector(etf) for etf in SECTOR_ETFS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for etf, result in zip(SECTOR_ETFS, results):
        if isinstance(result, Exception):
            logger.warning("Sector 3-10 compute failed for %s: %s", etf, result)
            continue
        _sector_cache[etf] = result
    _last_refresh = datetime.utcnow()
    logger.info("Sector 3-10 cache refreshed: %d ETFs", len(_sector_cache))


async def _refresh_if_stale() -> None:
    global _last_refresh
    if _last_refresh is None or (datetime.utcnow() - _last_refresh) > _REFRESH_INTERVAL:
        await refresh_sector_cache()


async def _compute_single_sector(sector_etf: str) -> Dict:
    """
    Fetch daily bars for a sector ETF and compute the latest 3-10 reading.
    yfinance fallback (UW get_candles not yet available — see module docstring).
    """
    df = await _fetch_daily_bars(sector_etf, days=60)
    if df is None or df.empty or len(df) < 20:
        return {"sector_etf": sector_etf, "osc_fast": None, "osc_slow": None, "osc_cross": 0}

    df = compute_3_10(df)
    latest = df.iloc[-1]
    return {
        "sector_etf": sector_etf,
        "osc_fast": float(latest[OSC_FAST]) if not pd.isna(latest[OSC_FAST]) else None,
        "osc_slow": float(latest[OSC_SLOW]) if not pd.isna(latest[OSC_SLOW]) else None,
        "osc_cross": int(latest[OSC_CROSS]) if not pd.isna(latest[OSC_CROSS]) else 0,
    }


async def _fetch_daily_bars(ticker: str, days: int = 60) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLC bars for a sector ETF.

    UW primary block commented out — uw_api.get_candles does not yet exist.
    TODO: Add uw_api.get_candles for sector-ETF bar fetching — scope a
    separate Titans-reviewed ticket before enabling the block below.

    # 1. Try UW API (re-enable when get_candles is implemented)
    # try:
    #     from integrations.uw_api import get_candles
    #     df = await get_candles(ticker, timeframe="1d", days=days)
    #     if df is not None and not df.empty:
    #         return df
    # except ImportError:
    #     logger.debug("uw_api.get_candles not available, falling back to yfinance")
    # except Exception as e:
    #     logger.debug("UW candles fetch failed for %s: %s", ticker, e)
    """
    # yfinance fallback (sole source until get_candles ticket is completed)
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        df = stock.history(period=f"{days}d", interval="1d")
        if df is not None and not df.empty:
            # Normalize column names to lowercase for compute_3_10
            df = df.rename(columns={"High": "high", "Low": "low", "Close": "close"})
            return df
    except Exception as e:
        logger.warning("yfinance fallback failed for %s: %s", ticker, e)

    return None
