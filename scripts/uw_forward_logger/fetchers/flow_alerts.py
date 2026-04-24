"""
Fetcher: /api/stock/{TICKER}/flow-alerts
No date param — returns current day's flow stream (limit=500).
"""

import logging

import pandas as pd

from .base import uw_get

logger = logging.getLogger(__name__)


def fetch(ticker: str, api_key: str) -> pd.DataFrame:
    """
    Pull today's flow alerts for ticker.
    Returns DataFrame (possibly empty). Raises on unrecoverable HTTP error.
    """
    rows = uw_get(
        f"/api/stock/{ticker}/flow-alerts",
        api_key,
        params={"limit": 500},
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    logger.debug("flow_alerts %s: %d rows", ticker, len(df))
    return df
