"""
VIX term structure factor.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .base_collector import get_latest_price, post_factor, _clamp

logger = logging.getLogger(__name__)


async def compute_score():
    vix = await get_latest_price("^VIX")
    vix3m = await get_latest_price("^VIX3M")

    if vix is None or vix3m is None or vix3m == 0:
        return None

    ratio = vix / vix3m

    if ratio >= 1.10:
        term_score = -1.0
    elif ratio >= 1.0:
        term_score = -0.6
    elif ratio >= 0.95:
        term_score = -0.2
    elif ratio >= 0.85:
        term_score = 0.2
    else:
        term_score = 0.6

    if vix >= 30:
        level_mod = -0.3
    elif vix >= 25:
        level_mod = -0.2
    elif vix >= 20:
        level_mod = -0.1
    elif vix <= 12:
        level_mod = 0.1
    else:
        level_mod = 0.0

    score = _clamp(term_score + level_mod)

    detail = (
        f"VIX {vix:.1f} / VIX3M {vix3m:.1f} = {ratio:.3f}"
    )

    data = {
        "vix": float(vix),
        "vix3m": float(vix3m),
        "ratio": float(ratio),
        "term_score": term_score,
        "level_mod": level_mod,
    }

    return score, detail, data


async def collect_and_post():
    result = await compute_score()
    if not result:
        logger.warning("VIX term data unavailable")
        return None

    score, detail, data = result
    return await post_factor(
        "vix_term",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=4,
        source="yfinance",
    )
