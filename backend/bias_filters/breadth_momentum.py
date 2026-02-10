"""
Breadth Momentum Factor — rate of change of RSP/SPY ratio.

Measures whether market breadth is improving or deteriorating.
RSP (equal-weight S&P 500) outperforming SPY = broadening participation.
RSP underperforming SPY = narrowing leadership.

Source: yfinance RSP, SPY
Timeframe: Intraday (staleness: 24h)
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
    """Score RSP/SPY ratio rate of change over 5 days."""
    rsp_data = await get_price_history("RSP", days=15)
    spy_data = await get_price_history("SPY", days=15)

    if rsp_data is None or spy_data is None:
        return None
    if rsp_data.empty or spy_data.empty:
        return None
    if "close" not in rsp_data.columns or "close" not in spy_data.columns:
        return None
    if len(rsp_data) < 6 or len(spy_data) < 6:
        return None

    # Align indices
    rsp_close = rsp_data["close"].iloc[-6:]
    spy_close = spy_data["close"].iloc[-6:]

    if len(rsp_close) < 6 or len(spy_close) < 6:
        return None

    # Ratio now vs 5 days ago
    ratio_now = float(rsp_close.iloc[-1]) / float(spy_close.iloc[-1])
    ratio_5d = float(rsp_close.iloc[0]) / float(spy_close.iloc[0])

    if ratio_5d == 0:
        return None

    roc = ((ratio_now / ratio_5d) - 1) * 100  # percentage change
    score = _score_breadth_roc(roc)

    return FactorReading(
        factor_id="breadth_momentum",
        score=score,
        signal=score_to_signal(score),
        detail=f"RSP/SPY ratio 5d ROC: {roc:+.2f}% ({'improving' if roc > 0.2 else 'deteriorating' if roc < -0.2 else 'stable'})",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "ratio_now": round(ratio_now, 4),
            "ratio_5d": round(ratio_5d, 4),
            "roc_pct": round(roc, 3),
        },
    )


def _score_breadth_roc(roc: float) -> float:
    """Score based on 5-day rate of change of breadth ratio."""
    if roc > 1.0:
        return 0.7
    elif roc > 0.5:
        return 0.4
    elif roc > 0.2:
        return 0.2
    elif roc > -0.2:
        return 0.0
    elif roc > -0.5:
        return -0.2
    elif roc > -1.0:
        return -0.4
    else:
        return -0.7
