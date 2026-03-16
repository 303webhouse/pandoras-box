"""
Sector Heatmap API — Polygon-powered sector data for all 11 S&P 500 sectors.
Fetches daily bars directly from Polygon for SPY + 11 sector ETFs.
Computes Day/Week/Month changes and daily RS rankings vs SPY.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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

HEATMAP_CACHE_KEY = "sector_heatmap:polygon"
HEATMAP_LIVE_TTL = 300  # 5 min during market hours
HEATMAP_STALE_KEY = "sector_heatmap:last_close"


def _heatmap_cache_ttl() -> int:
    """Return 5 min during market hours, 4 hours outside."""
    try:
        et = datetime.now(pytz.timezone("America/New_York"))
        if et.weekday() < 5 and 9 <= et.hour < 16:
            return HEATMAP_LIVE_TTL
        if et.weekday() < 5 and et.hour == 16 and et.minute < 30:
            return HEATMAP_LIVE_TTL
    except Exception:
        pass
    return 14400


def _pct_change(closes: List[float], offset: int) -> Optional[float]:
    """Compute % change from closes[-offset-1] to closes[-1]. None if not enough data."""
    if len(closes) < offset + 1:
        return None
    old = closes[-(offset + 1)]
    if old == 0:
        return None
    return round((closes[-1] / old - 1) * 100, 2)


async def _fetch_all_bars() -> Dict[str, List[float]]:
    """Fetch ~25 daily closing prices for SPY + all 11 sector ETFs via Polygon."""
    from integrations.polygon_equities import get_bars

    tickers = ["SPY"] + list(SECTOR_WEIGHTS.keys())
    results: Dict[str, List[float]] = {}

    for ticker in tickers:
        bars = await get_bars(ticker, 1, "day")
        if bars:
            closes = [b["c"] for b in bars if b.get("c") is not None]
            if closes:
                results[ticker] = closes
                continue

        # Polygon failed — try yfinance fallback
        try:
            await _yf_fallback(ticker, results)
        except Exception as e:
            logger.warning("yfinance fallback for %s failed: %s", ticker, e)

    return results


async def _yf_fallback(ticker: str, results: Dict[str, List[float]]) -> None:
    """Best-effort yfinance fallback for a single ticker."""
    import yfinance as yf
    import asyncio

    def _fetch():
        data = yf.download(ticker, period="2mo", interval="1d", progress=False)
        if data is not None and len(data) > 0 and "Close" in data.columns:
            return [float(c) for c in data["Close"].dropna().tolist()]
        return None

    closes = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    if closes:
        results[ticker] = closes


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

    # Fetch bars from Polygon
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
