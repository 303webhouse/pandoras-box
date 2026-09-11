"""
Fetcher: /api/stock/{TICKER}/greek-exposure
No date param — returns the rolling 1-year daily GEX series.
Cache pattern: single overwriting file per ticker (not monthly-partitioned).

Canary check (§12.8 of Phase 0 findings):
If fewer than 200 rows are returned, UW may have tightened the no-date
carve-out. Warns once per week per ticker via a flag file.
"""

import logging
import os
from datetime import datetime, timezone

import pandas as pd

from .base import uw_get

logger = logging.getLogger(__name__)

_CANARY_THRESHOLD = 200
_CANARY_FLAG_DIR = "/opt/openclaw/workspace/data/cache/uw/.canary_flags"


def fetch(ticker: str, api_key: str) -> pd.DataFrame:
    """
    Pull the rolling 1-year greek-exposure series for ticker.
    Returns DataFrame (possibly empty). Raises on unrecoverable HTTP error.
    Runs carve-out canary check per §12.8.
    """
    rows = uw_get(f"/api/stock/{ticker}/greek-exposure", api_key)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    logger.debug("greek_exposure %s: %d rows", ticker, len(df))

    # Carve-out canary check
    _run_canary(ticker, len(df))

    return df


def _run_canary(ticker: str, row_count: int) -> None:
    """
    Warn if greek-exposure returned fewer than 200 rows — possible sign that
    UW tightened the no-date 1-year carve-out. Alerts once per week per ticker.
    """
    if row_count >= _CANARY_THRESHOLD:
        return

    flag_file = os.path.join(_CANARY_FLAG_DIR, f"canary_{ticker}.txt")
    os.makedirs(_CANARY_FLAG_DIR, exist_ok=True)

    # Check if we already alerted this week
    today = datetime.now(timezone.utc)
    if os.path.exists(flag_file):
        try:
            with open(flag_file) as f:
                last_alerted = datetime.fromisoformat(f.read().strip())
            days_since = (today - last_alerted).days
            if days_since < 7:
                # Already alerted this week — log only, don't re-alert
                logger.warning(
                    "CARVE_OUT_CANARY: %s greek-exposure only %d rows "
                    "(last alert %d days ago — suppressed this week)",
                    ticker, row_count, days_since,
                )
                return
        except Exception:
            pass

    # Alert — write flag and log
    logger.warning(
        "CARVE_OUT_CANARY: %s greek-exposure returned only %d rows. "
        "UW may have tightened the no-date carve-out. Check with ATHENA.",
        ticker, row_count,
    )
    try:
        with open(flag_file, "w") as f:
            f.write(today.isoformat())
    except Exception as e:
        logger.debug("Failed to write canary flag for %s: %s", ticker, e)

    # Return the alert for the main loop to dispatch
    raise CarveOutCanaryTriggered(ticker, row_count)


class CarveOutCanaryTriggered(Exception):
    """Raised when the greek-exposure canary fires. Caller catches + alerts."""
    def __init__(self, ticker: str, row_count: int):
        self.ticker = ticker
        self.row_count = row_count
        super().__init__(f"CARVE_OUT_CANARY: {ticker} returned only {row_count} rows")
