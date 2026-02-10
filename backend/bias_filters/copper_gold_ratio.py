"""
Copper/Gold Ratio Factor — economic activity vs safety.

Copper rising relative to gold signals economic optimism and risk appetite.
Gold outperforming copper signals risk aversion and flight to safety.

Source: yfinance COPX (copper miners ETF), GLD (gold ETF)
Timeframe: Macro (staleness: 48h)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal, get_price_history
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal, get_price_history


async def compute_score() -> Optional[FactorReading]:
    """Score based on 20-day COPX vs GLD relative performance."""
    copx_data = await get_price_history("COPX", days=30)
    gld_data = await get_price_history("GLD", days=30)

    if copx_data is None or gld_data is None:
        return None
    if copx_data.empty or gld_data.empty:
        return None
    if "close" not in copx_data.columns or "close" not in gld_data.columns:
        return None
    if len(copx_data) < 20 or len(gld_data) < 20:
        return None

    # 20-day performance
    copx_close = copx_data["close"]
    gld_close = gld_data["close"]

    copx_return = (float(copx_close.iloc[-1]) / float(copx_close.iloc[-20]) - 1) * 100
    gld_return = (float(gld_close.iloc[-1]) / float(gld_close.iloc[-20]) - 1) * 100

    spread = copx_return - gld_return  # Positive = copper outperforming = risk-on
    score = _score_copper_gold(spread)

    return FactorReading(
        factor_id="copper_gold_ratio",
        score=score,
        signal=score_to_signal(score),
        detail=f"COPX 20d: {copx_return:+.1f}%, GLD 20d: {gld_return:+.1f}%, spread: {spread:+.1f}%",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "copx_return_20d": round(copx_return, 2),
            "gld_return_20d": round(gld_return, 2),
            "spread": round(spread, 2),
        },
    )


def _score_copper_gold(spread: float) -> float:
    """
    Score based on copper-gold performance spread.
    Positive spread = copper outperforming = economic optimism.
    Negative spread = gold outperforming = risk aversion.
    """
    if spread > 5.0:
        return 0.7
    elif spread > 3.0:
        return 0.5
    elif spread > 1.0:
        return 0.2
    elif spread > -1.0:
        return 0.0
    elif spread > -3.0:
        return -0.2
    elif spread > -5.0:
        return -0.5
    else:
        return -0.7
