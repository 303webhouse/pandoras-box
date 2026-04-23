"""
Divergence event persistence.

Writes 3-10 Oscillator divergence firings from a DataFrame's osc_div column
to the divergence_events table for later analysis and frequency-cap monitoring.
"""

import logging
from typing import Optional

import pandas as pd

from indicators.three_ten_oscillator import OSC_DIV, OSC_FAST

logger = logging.getLogger(__name__)


async def persist_divergences(
    df: pd.DataFrame,
    ticker: str,
    timeframe: str,
    threshold_used: float = 0.10,
    lookback_used: int = 5,
) -> int:
    """
    Write all divergence events in df to divergence_events table.

    Uses ON CONFLICT DO NOTHING via the UNIQUE constraint on
    (ticker, timeframe, bar_timestamp, div_type) so re-scans of overlapping
    bar windows are idempotent.

    Args:
        df: DataFrame with OSC_DIV column populated by compute_3_10.
            DatetimeIndex required.
        ticker: symbol to tag events with.
        timeframe: e.g. "1h", "1d", "15m".
        threshold_used: divergence threshold used in detection (for audit).
        lookback_used: lookback window used in detection (for audit).

    Returns:
        Count of rows inserted (excluding duplicates rejected by UNIQUE).
    """
    if df is None or df.empty or OSC_DIV not in df.columns:
        return 0

    # Filter to rows where divergence fired (+1 bull, -1 bear)
    div_rows = df[df[OSC_DIV] != 0]
    if div_rows.empty:
        return 0

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
    except Exception as e:
        logger.warning("Cannot get DB pool for divergence persistence: %s", e)
        return 0

    inserted = 0
    async with pool.acquire() as conn:
        for idx, row in div_rows.iterrows():
            div_type = "bull" if row[OSC_DIV] == 1 else "bear"
            # We don't surface pivot values from the detection function in MVP
            # — passing NULL for pivot columns is acceptable per schema.
            try:
                result = await conn.execute(
                    """
                    INSERT INTO divergence_events (
                        ticker, timeframe, bar_timestamp, div_type,
                        fast_pivot_prev, fast_pivot_curr,
                        price_pivot_prev, price_pivot_curr,
                        threshold_used, lookback_used
                    ) VALUES ($1, $2, $3, $4, NULL, NULL, NULL, NULL, $5, $6)
                    ON CONFLICT (ticker, timeframe, bar_timestamp, div_type)
                    DO NOTHING
                    """,
                    ticker,
                    timeframe,
                    idx if isinstance(idx, pd.Timestamp) else pd.Timestamp(idx),
                    div_type,
                    threshold_used,
                    lookback_used,
                )
                if str(result).strip().endswith("1"):
                    inserted += 1
            except Exception as e:
                logger.debug("Divergence insert failed for %s @ %s: %s", ticker, idx, e)

    if inserted > 0:
        logger.info("Persisted %d divergence events for %s (%s)", inserted, ticker, timeframe)
        # Frequency cap sanity check (URSA — Olympus 2026-04-22)
        await check_divergence_frequency(ticker, timeframe)
    return inserted


async def check_divergence_frequency(ticker: str, timeframe: str) -> None:
    """
    Log a warning if divergence events for a ticker on a given timeframe
    exceed 3 per month on daily bars. URSA frequency-cap sanity check
    (Olympus-locked 2026-04-22).

    Only applies to 1d timeframe — intraday divergences fire more frequently
    by design and are not subject to this cap.
    """
    if timeframe != "1d":
        return

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
    except Exception as e:
        logger.warning("Cannot get DB pool for frequency check: %s", e)
        return

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM divergence_events
            WHERE ticker = $1
              AND timeframe = '1d'
              AND bar_timestamp > NOW() - INTERVAL '30 days'
            """,
            ticker,
        )
    if count and count > 3:
        logger.warning(
            "FREQ_CAP_BREACH: ticker=%s divergences=%d/30d on daily — "
            "rule may be detecting noise. Review threshold/lookback.",
            ticker, count,
        )
