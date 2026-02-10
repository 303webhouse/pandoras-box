"""
TICK breadth factor (from Pandora API).
"""

from __future__ import annotations

import logging
from datetime import datetime

from .base_collector import get_json, post_factor, _clamp

logger = logging.getLogger(__name__)


def _score_from_tick(tick_avg: float, tick_high: float, tick_low: float) -> float:
    if tick_avg > 400:
        base = 0.8
    elif tick_avg > 200:
        base = 0.4
    elif tick_avg > -200:
        base = 0.0
    elif tick_avg > -400:
        base = -0.4
    else:
        base = -0.8

    extreme_mod = 0.0
    if tick_low < -1000:
        extreme_mod = -0.2
    elif tick_high > 1000:
        extreme_mod = 0.2

    return _clamp(base + extreme_mod)


async def collect_and_post():
    try:
        tick = await get_json("/bias/tick")
    except Exception as exc:
        logger.error(f"Failed to fetch TICK data from /bias/tick: {exc}", exc_info=True)
        return None

    if not tick:
        logger.warning("TICK data: /bias/tick returned empty response — no TV webhook data in Redis?")
        return None

    status = tick.get("status")
    if status not in ("ok", "success"):
        logger.warning(f"TICK data not ready: status={status}, response={tick}")
        return None

    tick_high = float(tick.get("tick_high", 0) or 0)
    tick_low = float(tick.get("tick_low", 0) or 0)

    if tick_high == 0 and tick_low == 0:
        logger.warning("TICK data has zero high/low — likely no TV alert received yet today")
        return None

    # If average not provided, approximate from range.
    tick_avg = float(tick.get("tick_avg") or (tick_high + tick_low) / 2)
    tick_close = float(tick.get("tick_close") or tick_avg)

    score = _score_from_tick(tick_avg, tick_high, tick_low)

    detail = (
        f"TICK avg {tick_avg:+.0f}, range [{tick_low:.0f}, {tick_high:.0f}], "
        f"close {tick_close:+.0f}"
    )

    data = {
        "tick_high": tick_high,
        "tick_low": tick_low,
        "tick_avg": tick_avg,
        "tick_close": tick_close,
        "source": "pandora_api",
    }

    logger.info(f"TICK breadth posting: score={score:+.2f}, {detail}")

    return await post_factor(
        "tick_breadth",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=4,
        source="tradingview",
    )
