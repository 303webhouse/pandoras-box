"""
Fetcher: /api/stock/{TICKER}/spot-exposures
No date param — returns current day's intraday GEX 1-minute ticks.
"""

import logging

import pandas as pd

from .base import uw_get

logger = logging.getLogger(__name__)


def fetch(ticker: str, api_key: str) -> pd.DataFrame:
    """
    Pull today's spot-exposure (intraday GEX) series for ticker.
    Returns DataFrame (possibly empty). Raises on unrecoverable HTTP error.
    """
    rows = uw_get(f"/api/stock/{ticker}/spot-exposures", api_key)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    logger.debug("spot_exposures %s: %d rows", ticker, len(df))
    return df
