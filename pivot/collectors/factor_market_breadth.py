"""
Market breadth factor (RSP/SPY).
"""

from __future__ import annotations

import logging
from datetime import datetime

from .base_collector import get_price_history, post_factor, _clamp

logger = logging.getLogger(__name__)


async def compute_score():
    rsp = await get_price_history("RSP", days=30)
    spy = await get_price_history("SPY", days=30)

    if rsp is None or spy is None or rsp.empty or spy.empty:
        return None

    ratio = rsp["close"] / spy["close"]
    if ratio.empty:
        return None

    current = float(ratio.iloc[-1])
    sma_20 = float(ratio.rolling(20).mean().iloc[-1])
    if sma_20 == 0:
        return None

    pct_dev = (current - sma_20) / sma_20 * 100
    roc_5d = (ratio.iloc[-1] - ratio.iloc[-5]) / ratio.iloc[-5] * 100 if len(ratio) >= 5 else 0

    if pct_dev >= 1.5:
        base = 0.8
    elif pct_dev >= 0.5:
        base = 0.4
    elif pct_dev >= -0.5:
        base = 0.0
    elif pct_dev >= -1.5:
        base = -0.4
    else:
        base = -0.8

    roc_modifier = max(-0.2, min(0.2, roc_5d * 0.15))
    score = _clamp(base + roc_modifier)

    detail = (
        f"RSP/SPY {current:.4f} vs SMA20 {sma_20:.4f} "
        f"({pct_dev:+.1f}%), 5d ROC {roc_5d:+.2f}%"
    )

    data = {
        "rsp": float(rsp["close"].iloc[-1]),
        "spy": float(spy["close"].iloc[-1]),
        "ratio": current,
        "sma20": sma_20,
        "pct_dev": float(pct_dev),
        "roc_5d": float(roc_5d),
    }

    return score, detail, data


async def collect_and_post():
    result = await compute_score()
    if not result:
        logger.warning("Market breadth data unavailable")
        return None

    score, detail, data = result
    return await post_factor(
        "market_breadth",
        score=score,
        detail=detail,
        data=data,
        collected_at=datetime.utcnow(),
        stale_after_hours=48,
        source="yfinance",
    )
