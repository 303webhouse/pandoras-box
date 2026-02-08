"""
Watchlist sector strength collector.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .base_collector import get_json, get_price_history, post_sector_strength

logger = logging.getLogger(__name__)

BENCHMARK = "SPY"


def _pct_change(series, periods: int) -> float:
    if series is None or len(series) <= periods:
        return 0.0
    return (series.iloc[-1] / series.iloc[-(periods + 1)] - 1) * 100


async def collect_and_post():
    try:
        watchlist = await get_json("/watchlist")
    except Exception as exc:
        logger.warning(f"Failed to load watchlist: {exc}")
        return None

    sectors = watchlist.get("sectors", {})
    etfs = {data.get("etf") for data in sectors.values() if data.get("etf")}
    etfs.add(BENCHMARK)

    price_data = {}
    for symbol in etfs:
        hist = await get_price_history(symbol, days=10)
        if hist is None or hist.empty:
            continue
        closes = hist["close"].dropna()
        price_data[symbol] = {
            "price": float(closes.iloc[-1]),
            "change_1d": _pct_change(closes, 1),
            "change_1w": _pct_change(closes, 5),
        }

    spy = price_data.get(BENCHMARK, {"change_1d": 0, "change_1w": 0})

    sector_strength = {}
    ranked = []

    for sector_name, sector_cfg in sectors.items():
        etf = sector_cfg.get("etf")
        if not etf or etf not in price_data:
            sector_strength[sector_name] = {
                "strength": None,
                "vs_spy_1d": None,
                "trend": "neutral",
                "rank": 999,
                "updated_at": datetime.utcnow().isoformat(),
            }
            continue

        etf_data = price_data[etf]
        vs_spy_1d = round((etf_data.get("change_1d", 0) - spy.get("change_1d", 0)), 2)
        vs_spy_1w = round((etf_data.get("change_1w", 0) - spy.get("change_1w", 0)), 2)

        if vs_spy_1d > 0.3 and vs_spy_1w > 0.5:
            trend = "strengthening"
        elif vs_spy_1d < -0.3 and vs_spy_1w < -0.5:
            trend = "weakening"
        else:
            trend = "neutral"

        sector_strength[sector_name] = {
            "strength": vs_spy_1w,
            "vs_spy_1d": vs_spy_1d,
            "trend": trend,
            "rank": 999,
            "updated_at": datetime.utcnow().isoformat(),
        }
        ranked.append((sector_name, vs_spy_1w))

    ranked.sort(key=lambda x: x[1], reverse=True)
    for rank, (sector_name, _) in enumerate(ranked, 1):
        sector_strength[sector_name]["rank"] = rank

    if not sector_strength:
        return None

    return await post_sector_strength(sector_strength)
