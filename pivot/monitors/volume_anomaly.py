"""
Detect >2.5x average volume spikes.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any

from collectors.base_collector import get_json

logger = logging.getLogger(__name__)


async def check_volume_anomalies(multiplier: float = 2.5) -> List[Dict[str, Any]]:
    try:
        flat = await get_json("/watchlist/flat?limit=500")
    except Exception as exc:
        logger.warning(f"Volume anomaly check failed: {exc}")
        return []

    tickers = flat.get("tickers", []) if isinstance(flat, dict) else []
    anomalies: List[Dict[str, Any]] = []

    for ticker in tickers:
        symbol = ticker.get("symbol")
        volume = ticker.get("volume")
        avg = ticker.get("volume_avg")
        if not symbol or not volume or not avg:
            continue
        if avg > 0 and volume >= avg * multiplier:
            anomalies.append({
                "ticker": symbol,
                "volume": volume,
                "volume_avg": avg,
                "multiplier": round(volume / avg, 2),
            })

    return anomalies
