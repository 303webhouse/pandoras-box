"""
Savita / BofA Sell Side Indicator (manual entry).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from .base_collector import post_factor, _clamp

logger = logging.getLogger(__name__)


def _get_savita_reading():
    raw = os.getenv("SAVITA_READING")
    if not raw:
        return None
    try:
        reading = float(raw)
    except ValueError:
        return None

    date_str = os.getenv("SAVITA_DATE")
    if date_str:
        try:
            ts = datetime.fromisoformat(date_str)
        except Exception:
            ts = datetime.utcnow()
    else:
        ts = datetime.utcnow()

    return reading, ts


async def compute_score():
    result = _get_savita_reading()
    if not result:
        return None

    reading, ts = result

    if reading >= 65:
        score = -0.8
    elif reading >= 60:
        score = -0.4
    elif reading >= 55:
        score = -0.1
    elif reading >= 50:
        score = 0.1
    elif reading >= 45:
        score = 0.4
    else:
        score = 0.8

    score = _clamp(score)

    detail = f"BofA Sell Side Indicator {reading:.1f}"
    data = {"value": reading, "date": ts.isoformat()}
    return score, detail, data, ts


async def collect_and_post():
    result = await compute_score()
    if not result:
        logger.warning("Savita reading not configured")
        return None

    score, detail, data, ts = result
    return await post_factor(
        "savita",
        score=score,
        detail=detail,
        data=data,
        collected_at=ts,
        stale_after_hours=1080,
        source="manual",
    )
