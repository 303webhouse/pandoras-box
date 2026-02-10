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

    if vix is None:
        logger.error("VIX data unavailable from yfinance — cannot compute vix_term")
        return None

    # VIX3M unavailable: post a degraded VIX-only reading instead of nothing
    if vix3m is None or vix3m == 0:
        logger.warning(f"VIX3M unavailable — using VIX-only fallback (VIX={vix:.1f})")
        return _vix_only_fallback(vix)

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


def _vix_only_fallback(vix: float):
    """
    Degraded scoring using absolute VIX level only.
    Less precise than the full VIX/VIX3M ratio, but better than posting nothing.
    """
    if vix >= 35:
        score = -0.8
    elif vix >= 30:
        score = -0.5
    elif vix >= 25:
        score = -0.3
    elif vix >= 20:
        score = -0.1
    elif vix >= 15:
        score = 0.1
    elif vix >= 12:
        score = 0.3
    else:
        score = 0.5

    detail = f"VIX {vix:.1f} (VIX3M unavailable — VIX-only fallback)"
    data = {
        "vix": float(vix),
        "vix3m": None,
        "ratio": None,
        "degraded": True,
        "source_note": "VIX-only fallback, VIX3M unavailable from yfinance",
    }

    return _clamp(score), detail, data


async def collect_and_post():
    try:
        result = await compute_score()
    except Exception as exc:
        logger.error(f"VIX term compute_score() raised: {exc}", exc_info=True)
        return None

    if not result:
        logger.error("VIX term: compute_score() returned None — no data posted, factor will go stale")
        return None

    score, detail, data = result
    degraded = data.get("degraded", False)
    if degraded:
        logger.warning(f"VIX term posting DEGRADED reading: score={score:+.2f}, {detail}")
    else:
        logger.info(f"VIX term posting: score={score:+.2f}, {detail}")

    return await post_factor(
        "vix_term",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=4,
        source="yfinance",
    )
