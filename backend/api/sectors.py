"""
Sector Heatmap API — serves weighted treemap data for S&P 500 sectors.
Reuses enrichment pipeline cache to avoid duplicate Polygon/yfinance calls.
"""

import json
import logging
from datetime import datetime, timezone
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

# Map enrichment sector names → ETF tickers
_SECTOR_NAME_TO_ETF = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Consumer Discretionary": "XLY",
    "Consumer Disc.": "XLY",
    "Communication Services": "XLC",
    "Communication": "XLC",
    "Industrials": "XLI",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Materials": "XLB",
}

HEATMAP_CACHE_KEY = "sector_heatmap"
HEATMAP_LIVE_TTL = 300  # 5 min during market hours
HEATMAP_STALE_KEY = "sector_heatmap:last_close"  # persists overnight


def _heatmap_cache_ttl() -> int:
    """Return 5 min during market hours, or seconds-until-next-open outside."""
    try:
        et = datetime.now(pytz.timezone("America/New_York"))
        # Weekday 9:30 AM - 4:00 PM ET = market hours
        if et.weekday() < 5 and 9 <= et.hour < 16:
            return HEATMAP_LIVE_TTL
        if et.weekday() < 5 and et.hour == 16 and et.minute < 30:
            return HEATMAP_LIVE_TTL
    except Exception:
        pass
    # Outside market hours: cache until 9:30 AM ET next trading day
    return 14400  # 4 hours — good enough, enrichment refresh will update it


@router.get("/heatmap")
async def get_sector_heatmap():
    """Return sector data for treemap rendering."""
    redis = await get_redis_client()

    # Check live cache first
    if redis:
        try:
            cached = await redis.get(HEATMAP_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # Build from enrichment cache
    sectors_data = []
    spy_change_1d = 0.0

    if redis:
        try:
            enriched_raw = await redis.get("watchlist:enriched")
            if enriched_raw:
                enriched = json.loads(enriched_raw)
                spy_change_1d = (enriched.get("benchmark", {}).get("change_1d")) or 0.0

                for sector in enriched.get("sectors", []):
                    etf = sector.get("etf") or _SECTOR_NAME_TO_ETF.get(sector.get("name"))
                    if not etf or etf not in SECTOR_WEIGHTS:
                        continue
                    weight_info = SECTOR_WEIGHTS[etf]
                    change_1w = sector.get("etf_change_1w") or 0.0
                    trend = sector.get("trend") or ("up" if change_1w > 0.3 else "down" if change_1w < -0.3 else "flat")
                    sectors_data.append({
                        "etf": etf,
                        "name": weight_info["name"],
                        "weight": weight_info["weight"],
                        "change_1d": sector.get("etf_change_1d") or 0.0,
                        "change_1w": change_1w,
                        "trend": trend,
                        "price": sector.get("etf_price"),
                        "strength_rank": sector.get("strength_rank", 99),
                    })
        except Exception as e:
            logger.warning("Sector heatmap enrichment read failed: %s", e)

    # Fill missing sectors with static weights (no price data)
    seen_etfs = {s["etf"] for s in sectors_data}
    for etf, info in SECTOR_WEIGHTS.items():
        if etf not in seen_etfs:
            sectors_data.append({
                "etf": etf,
                "name": info["name"],
                "weight": info["weight"],
                "change_1d": 0.0,
                "change_1w": 0.0,
                "trend": "flat",
                "price": None,
                "strength_rank": 99,
            })

    result = {
        "sectors": sorted(sectors_data, key=lambda s: s["weight"], reverse=True),
        "spy_change_1d": spy_change_1d,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    has_real_data = any(s.get("price") for s in sectors_data)

    # No enrichment data available — try stale fallback (last close)
    if not has_real_data and redis:
        try:
            stale = await redis.get(HEATMAP_STALE_KEY)
            if stale:
                return json.loads(stale)
        except Exception:
            pass

    # Cache the result
    if redis:
        try:
            result_json = json.dumps(result)
            await redis.set(HEATMAP_CACHE_KEY, result_json, ex=_heatmap_cache_ttl())
            if has_real_data:
                # Persist a stale copy that survives overnight (24h TTL)
                await redis.set(HEATMAP_STALE_KEY, result_json, ex=86400)
        except Exception:
            pass

    return result
