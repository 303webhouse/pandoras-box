"""
Dollar smile factor (DXY + VIX context).
"""

from __future__ import annotations

import logging
from datetime import datetime

from .base_collector import get_price_history, get_latest_price, post_factor

logger = logging.getLogger(__name__)


async def compute_score():
    dxy = await get_price_history("DX-Y.NYB", days=60)
    vix = await get_latest_price("^VIX")

    if dxy is None or dxy.empty or vix is None:
        return None

    current_dxy = float(dxy["close"].iloc[-1])
    sma_20 = float(dxy["close"].rolling(20).mean().iloc[-1])
    if sma_20 == 0:
        return None

    dxy_above = current_dxy > sma_20
    vix_elevated = vix > 20

    if dxy_above and vix_elevated:
        score = -0.6
    elif dxy_above and not vix_elevated:
        score = 0.0
    elif (not dxy_above) and vix_elevated:
        score = -0.3
    else:
        score = 0.5

    detail = (
        f"DXY {current_dxy:.2f} {'above' if dxy_above else 'below'} SMA20 {sma_20:.2f}, "
        f"VIX {'elevated' if vix_elevated else 'calm'} at {vix:.1f}"
    )

    data = {
        "dxy": current_dxy,
        "sma20": sma_20,
        "vix": float(vix),
    }

    return score, detail, data


async def collect_and_post():
    result = await compute_score()
    if not result:
        logger.warning("Dollar smile data unavailable")
        return None

    score, detail, data = result
    return await post_factor(
        "dollar_smile",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=48,
        source="yfinance",
    )
