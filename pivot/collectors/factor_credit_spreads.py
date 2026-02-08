"""
Credit spreads factor (HYG/TLT).
"""

from __future__ import annotations

import logging
from datetime import datetime

from .base_collector import get_price_history, post_factor, _clamp

logger = logging.getLogger(__name__)


async def compute_score():
    hyg = await get_price_history("HYG", days=30)
    tlt = await get_price_history("TLT", days=30)

    if hyg is None or tlt is None or hyg.empty or tlt.empty:
        return None

    ratio = hyg["close"] / tlt["close"]
    if ratio.empty:
        return None

    current_ratio = float(ratio.iloc[-1])
    sma_20 = float(ratio.rolling(20).mean().iloc[-1])
    if sma_20 == 0:
        return None

    pct_dev = (current_ratio - sma_20) / sma_20 * 100
    roc_5d = (ratio.iloc[-1] - ratio.iloc[-5]) / ratio.iloc[-5] * 100 if len(ratio) >= 5 else 0

    if pct_dev >= 2.0:
        base = 0.8
    elif pct_dev >= 1.0:
        base = 0.4
    elif pct_dev >= -1.0:
        base = 0.0
    elif pct_dev >= -2.0:
        base = -0.4
    else:
        base = -0.8

    roc_modifier = max(-0.2, min(0.2, roc_5d * 0.1))
    score = _clamp(base + roc_modifier)

    detail = (
        f"HYG/TLT {current_ratio:.3f} vs SMA20 {sma_20:.3f} "
        f"({pct_dev:+.1f}%), 5d ROC {roc_5d:+.2f}%"
    )

    data = {
        "hyg": float(hyg["close"].iloc[-1]),
        "tlt": float(tlt["close"].iloc[-1]),
        "ratio": current_ratio,
        "sma20": sma_20,
        "pct_dev": float(pct_dev),
        "roc_5d": float(roc_5d),
    }

    return score, detail, data


async def collect_and_post():
    result = await compute_score()
    if not result:
        logger.warning("Credit spreads data unavailable")
        return None

    score, detail, data = result
    return await post_factor(
        "credit_spreads",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=48,
        source="yfinance",
    )
