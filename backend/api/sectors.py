"""
Sector Heatmap API — yfinance-powered sector data for all 11 S&P 500 sectors.
Fetches daily bars via yfinance batch download for SPY + 11 sector ETFs.
Computes Day/Week/Month changes and daily RS rankings vs SPY.

Uses yfinance as primary data source (near-real-time quotes, free).
Polygon Starter only provides 15-min delayed data, so yfinance is faster
for this use case with only 12 tickers.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytz
from fastapi import APIRouter

from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sectors", tags=["sectors"])

# Static SPY sector weights (update quarterly)
SECTOR_WEIGHTS = {
    "XLK": {"name": "Technology", "weight": 0.312},
    "XLF": {"name": "Financials", "weight": 0.139},
    "XLV": {"name": "Health Care", "weight": 0.117},
    "XLY": {"name": "Consumer Disc.", "weight": 0.105},
    "XLC": {"name": "Communication", "weight": 0.091},
    "XLI": {"name": "Industrials", "weight": 0.084},
    "XLP": {"name": "Consumer Staples", "weight": 0.058},
    "XLE": {"name": "Energy", "weight": 0.034},
    "XLRE": {"name": "Real Estate", "weight": 0.023},
    "XLU": {"name": "Utilities", "weight": 0.025},
    "XLB": {"name": "Materials", "weight": 0.019},
}

ALL_TICKERS = ["SPY"] + list(SECTOR_WEIGHTS.keys())
TICKER_STR = " ".join(ALL_TICKERS)

# Cache keys
HEATMAP_CACHE_KEY = "sector_heatmap:yf"
HEATMAP_LIVE_TTL = 10  # 10s during market hours for near-real-time
HEATMAP_STALE_KEY = "sector_heatmap:last_close"


def _is_market_hours() -> bool:
    """Check if we're in US market hours (9:30-16:00 ET weekdays)."""
    try:
        et = datetime.now(pytz.timezone("America/New_York"))
        if et.weekday() >= 5:
            return False
        # Include pre-market from 9:00 and post-market to 16:30
        if et.hour == 9 and et.minute >= 0:
            return True
        if 10 <= et.hour < 16:
            return True
        if et.hour == 16 and et.minute < 30:
            return True
        return False
    except Exception:
        return False


def _heatmap_cache_ttl() -> int:
    """Return 10s during market hours, 4 hours outside."""
    if _is_market_hours():
        return HEATMAP_LIVE_TTL
    return 14400


def _pct_change(closes: List[float], offset: int) -> Optional[float]:
    """Compute % change from closes[-offset-1] to closes[-1]. None if not enough data."""
    if len(closes) < offset + 1:
        return None
    old = closes[-(offset + 1)]
    if old == 0:
        return None
    return round((closes[-1] / old - 1) * 100, 2)


def _fetch_all_bars_sync() -> Dict[str, List[float]]:
    """
    Batch-fetch ~2 months of daily bars for SPY + 11 sector ETFs via yfinance.

    Uses a single yf.download() call for all 12 tickers — one HTTP request total.
    During market hours, today's partial bar is included with current price as 'Close'.
    """
    import yfinance as yf

    results: Dict[str, List[float]] = {}

    try:
        # Single batch call for all 12 tickers
        data = yf.download(
            TICKER_STR,
            period="2mo",
            interval="1d",
            progress=False,
            group_by="ticker",
            threads=True,
        )

        if data is None or data.empty:
            logger.warning("yfinance batch download returned empty data")
            return results

        for ticker in ALL_TICKERS:
            try:
                # yfinance batch download uses MultiIndex columns: (ticker, field)
                if isinstance(data.columns, __import__('pandas').MultiIndex):
                    ticker_data = data[ticker]
                else:
                    # Single ticker fallback (shouldn't happen with 12 tickers)
                    ticker_data = data

                if "Close" in ticker_data.columns:
                    closes = ticker_data["Close"].dropna().tolist()
                    closes = [float(c) for c in closes if c is not None]
                    if closes:
                        results[ticker] = closes
                else:
                    logger.warning("No Close column for %s", ticker)
            except (KeyError, TypeError) as e:
                logger.warning("Failed to extract %s from batch data: %s", ticker, e)

    except Exception as e:
        logger.error("yfinance batch download failed: %s", e)
        # Fall back to individual fetches
        for ticker in ALL_TICKERS:
            try:
                data = yf.download(ticker, period="2mo", interval="1d", progress=False)
                if data is not None and not data.empty and "Close" in data.columns:
                    closes = [float(c) for c in data["Close"].dropna().tolist()]
                    if closes:
                        results[ticker] = closes
            except Exception as inner_e:
                logger.warning("yfinance individual fetch for %s failed: %s", ticker, inner_e)

    return results


async def _fetch_all_bars() -> Dict[str, List[float]]:
    """Async wrapper around synchronous yfinance batch download."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_all_bars_sync)


@router.get("/heatmap")
async def get_sector_heatmap():
    """Return sector data for treemap: all 11 sectors with Day/Week/Month changes and daily RS."""
    redis = await get_redis_client()

    # Check cache first
    if redis:
        try:
            cached = await redis.get(HEATMAP_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # Fetch bars from yfinance (single batch call)
    all_closes = await _fetch_all_bars()

    # Compute SPY changes
    spy_closes = all_closes.get("SPY", [])
    spy_change_1d = _pct_change(spy_closes, 1) or 0.0
    spy_change_1w = _pct_change(spy_closes, 5)
    spy_change_1m = _pct_change(spy_closes, 21)

    # Build sector data
    sectors_data = []
    for etf, info in SECTOR_WEIGHTS.items():
        closes = all_closes.get(etf, [])
        price = closes[-1] if closes else None
        change_1d = _pct_change(closes, 1)
        change_1w = _pct_change(closes, 5)
        change_1m = _pct_change(closes, 21)

        # Daily RS = sector daily change minus SPY daily change
        rs_daily = round(change_1d - spy_change_1d, 2) if change_1d is not None else None

        # Trend from weekly change
        if change_1w is not None:
            trend = "up" if change_1w > 0.3 else "down" if change_1w < -0.3 else "flat"
        else:
            trend = "flat"

        sectors_data.append({
            "etf": etf,
            "name": info["name"],
            "weight": info["weight"],
            "price": round(price, 2) if price is not None else None,
            "change_1d": change_1d if change_1d is not None else 0.0,
            "change_1w": change_1w if change_1w is not None else 0.0,
            "change_1m": change_1m if change_1m is not None else 0.0,
            "rs_daily": rs_daily if rs_daily is not None else 0.0,
            "trend": trend,
            "strength_rank": 99,  # placeholder, computed below
        })

    # Rank by rs_daily descending (rank 1 = strongest daily outperformer)
    ranked = sorted(sectors_data, key=lambda s: s["rs_daily"], reverse=True)
    for i, sector in enumerate(ranked):
        sector["strength_rank"] = i + 1

    result = {
        "sectors": sorted(sectors_data, key=lambda s: s["weight"], reverse=True),
        "spy_change_1d": spy_change_1d,
        "spy_change_1w": spy_change_1w,
        "spy_change_1m": spy_change_1m,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    has_real_data = any(s.get("price") for s in sectors_data)

    # No data at all — try stale fallback
    if not has_real_data and redis:
        try:
            stale = await redis.get(HEATMAP_STALE_KEY)
            if stale:
                return json.loads(stale)
        except Exception:
            pass

    # Cache result
    if redis:
        try:
            result_json = json.dumps(result)
            await redis.set(HEATMAP_CACHE_KEY, result_json, ex=_heatmap_cache_ttl())
            if has_real_data:
                await redis.set(HEATMAP_STALE_KEY, result_json, ex=86400)
        except Exception:
            pass

    return result
