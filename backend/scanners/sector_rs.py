"""
Sector Relative Strength — Daily pre-market computation.

Compares rolling 10-day and 20-day returns of 11 sector ETFs vs SPY
to detect institutional rotation patterns. Results cached in Redis
with 18h TTL. Used by sell_the_rip_scanner for early detection mode
and scoring modifiers.

Schedule: 8:00 AM ET daily (pre-market).
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLY": "Consumer Discretionary",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
    "XLB": "Materials",
}

RS_TTL = 60  # 60 seconds (4x the 15-second refresh interval)

# Classification thresholds (percentage points vs SPY)
ACTIVE_DISTRIBUTION_THRESHOLD = -1.0   # Both windows below -1%
POTENTIAL_ROTATION_THRESHOLD = -0.5    # Either window below -0.5%
SECTOR_STRENGTH_THRESHOLD = 1.0        # Both windows above +1%


def _fetch_sector_prices() -> Optional[Dict]:
    """Fetch 25 trading days of daily closes for SPY + sector ETFs (blocking)."""
    import yfinance as yf

    tickers = ["SPY"] + list(SECTOR_ETFS.keys())
    data = yf.download(tickers, period="2mo", interval="1d", progress=False)

    if data.empty:
        return None

    # yfinance returns MultiIndex columns for multi-ticker downloads
    closes = data["Close"] if "Close" in data.columns.get_level_values(0) else data
    # Keep last 25 trading days
    closes = closes.tail(25)

    if len(closes) < 20:
        logger.warning("Sector RS: only %d trading days available (need 20+)", len(closes))
        return None

    return closes


def _classify(rs_10d: float, rs_20d: float) -> str:
    """Classify sector RS into rotation buckets."""
    if rs_10d < ACTIVE_DISTRIBUTION_THRESHOLD and rs_20d < ACTIVE_DISTRIBUTION_THRESHOLD:
        return "ACTIVE_DISTRIBUTION"
    if rs_10d > SECTOR_STRENGTH_THRESHOLD and rs_20d > SECTOR_STRENGTH_THRESHOLD:
        return "SECTOR_STRENGTH"
    if rs_10d < POTENTIAL_ROTATION_THRESHOLD or rs_20d < POTENTIAL_ROTATION_THRESHOLD:
        return "POTENTIAL_ROTATION"
    return "NEUTRAL"


async def compute_sector_rs() -> Dict[str, Dict]:
    """
    Compute sector relative strength vs SPY and cache in Redis.
    Returns dict of {ETF: {rs_10d, rs_20d, classification}}.
    """
    try:
        closes = await asyncio.to_thread(_fetch_sector_prices)
    except Exception as e:
        logger.error("Sector RS: yfinance fetch failed: %s", e)
        return {}

    if closes is None:
        logger.error("Sector RS: no price data returned")
        return {}

    # SPY returns
    spy = closes.get("SPY")
    if spy is None or spy.dropna().empty:
        logger.error("Sector RS: no SPY data")
        return {}

    spy_return_10d = (spy.iloc[-1] / spy.iloc[-11] - 1) * 100 if len(spy) >= 11 else 0
    spy_return_20d = (spy.iloc[-1] / spy.iloc[-21] - 1) * 100 if len(spy) >= 21 else 0

    results = {}
    for etf in SECTOR_ETFS:
        series = closes.get(etf)
        if series is None or series.dropna().empty:
            logger.warning("Sector RS: no data for %s, skipping", etf)
            continue

        etf_return_10d = (series.iloc[-1] / series.iloc[-11] - 1) * 100 if len(series) >= 11 else 0
        etf_return_20d = (series.iloc[-1] / series.iloc[-21] - 1) * 100 if len(series) >= 21 else 0

        rs_10d = round(etf_return_10d - spy_return_10d, 2)
        rs_20d = round(etf_return_20d - spy_return_20d, 2)

        results[etf] = {
            "rs_10d": rs_10d,
            "rs_20d": rs_20d,
            "classification": _classify(rs_10d, rs_20d),
            "sector_name": SECTOR_ETFS[etf],
        }

    # Cache to Redis
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        for etf, data in results.items():
            await client.setex(f"sector_rs:{etf}", RS_TTL, json.dumps(data))
        await client.setex("sector_rs:updated_at", RS_TTL, datetime.now(timezone.utc).isoformat())
        logger.info("Sector RS: cached %d sectors to Redis", len(results))
    except Exception as e:
        logger.error("Sector RS: Redis cache failed: %s", e)

    return results


async def get_sector_rs(etf: str) -> Optional[Dict]:
    """Retrieve cached sector RS for a single ETF."""
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        data = await client.get(f"sector_rs:{etf}")
        return json.loads(data) if data else None
    except Exception:
        return None


async def get_all_sector_rs() -> Dict[str, Dict]:
    """Retrieve all cached sector RS data."""
    results = {}
    for etf in SECTOR_ETFS:
        data = await get_sector_rs(etf)
        if data:
            results[etf] = data
    return results


async def is_sector_rs_stale() -> bool:
    """Check if sector RS data is older than 18h."""
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        updated_at = await client.get("sector_rs:updated_at")
        if not updated_at:
            return True
        ts = datetime.fromisoformat(updated_at)
        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return age_hours > 18
    except Exception:
        return True
