"""
Sector Rotation Bonus for Signal Scoring

Awards bonus points when a signal's ticker is in a sector experiencing
sharp rotation momentum:
- LONG signal in a SURGING sector: +8 bonus
- SHORT signal in a DUMPING sector: +8 bonus
- Opposite alignment: -5 penalty (long in dumping, short in surging)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

BONUS_ALIGNED = 8       # Signal direction matches sector momentum
PENALTY_MISALIGNED = -5  # Signal direction opposes sector momentum


async def get_sector_bonus(signal: Dict[str, Any]) -> int:
    """
    Calculate sector rotation bonus/penalty for a signal.

    Returns bonus points (positive or negative) to add to the raw score.
    """
    ticker = (signal.get("ticker") or "").upper()
    direction = (signal.get("direction") or "").upper()
    is_long = direction in ("LONG", "BUY")

    if not ticker or not direction:
        return 0

    # Detect sector for this ticker
    try:
        from config.sectors import detect_sector
    except ImportError:
        try:
            from backend.config.sectors import detect_sector
        except ImportError:
            return 0

    sector = detect_sector(ticker)
    if sector == "Uncategorized":
        return 0

    # Get cached sector rotation data
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return 0

        raw = await redis.get("sector:rotation:current")
        if not raw:
            return 0

        rotation_data = json.loads(raw)
    except Exception:
        return 0

    sector_info = rotation_data.get(sector)
    if not sector_info:
        return 0

    status = sector_info.get("status", "STEADY")

    if status == "STEADY":
        return 0

    if status == "SURGING":
        if is_long:
            logger.info(f"📈 Sector rotation bonus: {ticker} LONG in {sector} (SURGING) +{BONUS_ALIGNED}")
            return BONUS_ALIGNED
        else:
            return PENALTY_MISALIGNED

    if status == "DUMPING":
        if not is_long:
            logger.info(f"📉 Sector rotation bonus: {ticker} SHORT in {sector} (DUMPING) +{BONUS_ALIGNED}")
            return BONUS_ALIGNED
        else:
            return PENALTY_MISALIGNED

    return 0
