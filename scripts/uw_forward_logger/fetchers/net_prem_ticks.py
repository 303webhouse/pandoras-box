"""
Fetcher: /api/stock/{TICKER}/net-prem-ticks
No date param — returns current day's intraday net-premium ticks.
"""

import logging

import pandas as pd

from .base import uw_get

logger = logging.getLogger(__name__)


def fetch(ticker: str, api_key: str) -> pd.DataFrame:
    """
    Pull today's net-premium tick series for ticker.
    Returns DataFrame (possibly empty). Raises on unrecoverable HTTP error.
    """
    rows = uw_get(f"/api/stock/{ticker}/net-prem-ticks", api_key)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    logger.debug("net_prem_ticks %s: %d rows", ticker, len(df))
    return df
