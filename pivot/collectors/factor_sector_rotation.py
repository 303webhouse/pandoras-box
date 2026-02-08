"""
Sector rotation factor (offensive vs defensive).
"""

from __future__ import annotations

import logging
from datetime import datetime

from .base_collector import get_price_history, post_factor, _clamp

logger = logging.getLogger(__name__)


async def compute_score():
    xlk = await get_price_history("XLK", days=30)
    xly = await get_price_history("XLY", days=30)
    xlp = await get_price_history("XLP", days=30)
    xlu = await get_price_history("XLU", days=30)

    if any(df is None or df.empty for df in (xlk, xly, xlp, xlu)):
        return None

    offensive = xlk["close"] + xly["close"]
    defensive = xlp["close"] + xlu["close"]
    ratio = offensive / defensive

    if ratio.empty:
        return None

    current = float(ratio.iloc[-1])
    sma_20 = float(ratio.rolling(20).mean().iloc[-1])
    if sma_20 == 0:
        return None

    pct_dev = (current - sma_20) / sma_20 * 100
    roc_5d = (ratio.iloc[-1] - ratio.iloc[-5]) / ratio.iloc[-5] * 100 if len(ratio) >= 5 else 0

    if pct_dev >= 2.0:
        base = 0.7
    elif pct_dev >= 1.0:
        base = 0.3
    elif pct_dev >= -1.0:
        base = 0.0
    elif pct_dev >= -2.0:
        base = -0.4
    else:
        base = -0.8

    roc_modifier = max(-0.3, min(0.3, roc_5d * 0.2))
    score = _clamp(base + roc_modifier)

    detail = f"Off/Def pct_dev {pct_dev:+.1f}%, 5d ROC {roc_5d:+.2f}%"

    data = {
        "xlk": float(xlk["close"].iloc[-1]),
        "xly": float(xly["close"].iloc[-1]),
        "xlp": float(xlp["close"].iloc[-1]),
        "xlu": float(xlu["close"].iloc[-1]),
        "ratio": current,
        "sma20": sma_20,
        "pct_dev": float(pct_dev),
        "roc_5d": float(roc_5d),
    }

    return score, detail, data


async def collect_and_post():
    result = await compute_score()
    if not result:
        logger.warning("Sector rotation data unavailable")
        return None

    score, detail, data = result
    return await post_factor(
        "sector_rotation",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=48,
        source="yfinance",
    )
