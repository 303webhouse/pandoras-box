"""
Fetcher: /api/darkpool/{TICKER}
Cursor-paginated via older_than= (ISO timestamp). Date param = yesterday.
Full day for a liquid name can be thousands of prints.
"""

import logging

import pandas as pd

from .base import uw_get

logger = logging.getLogger(__name__)

_PAGE_LIMIT = 500
_MAX_ROWS = 25_000  # Safety cap per brief §B.6


def fetch(ticker: str, api_key: str, date: str | None = None) -> pd.DataFrame:
    """
    Pull full-day dark pool prints for ticker.
    date: YYYY-MM-DD string (yesterday). If None, uses API default.
    Returns DataFrame (possibly empty). Raises on unrecoverable HTTP error.
    """
    all_rows: list = []
    cursor: str | None = None
    page = 0

    while True:
        params: dict = {"limit": _PAGE_LIMIT}
        if date:
            params["date"] = date
        if cursor:
            params["older_than"] = cursor

        rows = uw_get(f"/api/darkpool/{ticker}", api_key, params=params)

        if not rows:
            break

        all_rows.extend(rows)
        page += 1

        if len(rows) < _PAGE_LIMIT:
            break  # final page

        if len(all_rows) >= _MAX_ROWS:
            logger.warning(
                "darkpool %s on %s exceeded %d rows — truncating (page %d)",
                ticker, date, _MAX_ROWS, page,
            )
            break

        # Next cursor = oldest timestamp in batch (newest-first response)
        cursor = rows[-1].get("executed_at") or rows[-1].get("timestamp")
        if not cursor:
            logger.warning("darkpool %s: no cursor field in row — stopping pagination", ticker)
            break

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    logger.debug("darkpool %s (date=%s): %d rows across %d pages", ticker, date, len(df), page)
    return df
