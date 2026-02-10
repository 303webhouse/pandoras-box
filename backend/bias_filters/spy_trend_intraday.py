"""
SPY Trend Intraday Factor — SPY price vs 9-period EMA.

Measures short-term momentum: is SPY above or below its fast EMA?
A simple but effective intraday directional indicator.

Source: yfinance SPY
Timeframe: Intraday (staleness: 4h)
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
    """Score SPY price vs 9 EMA."""
    data = await get_price_history("SPY", days=20)
    if data is None or data.empty or "close" not in data.columns or len(data) < 10:
        logger.warning("SPY trend intraday: insufficient data")
        return None

    close = data["close"]
    ema9 = close.ewm(span=9, adjust=False).mean()

    current_price = float(close.iloc[-1])
    current_ema = float(ema9.iloc[-1])

    if current_ema == 0:
        return None

    pct_from_ema = ((current_price - current_ema) / current_ema) * 100
    score = _score_ema_distance(pct_from_ema)

    return FactorReading(
        factor_id="spy_trend_intraday",
        score=score,
        signal=score_to_signal(score),
        detail=f"SPY {current_price:.2f} vs 9 EMA {current_ema:.2f} ({pct_from_ema:+.2f}%)",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "price": current_price,
            "ema9": round(current_ema, 2),
            "pct_from_ema": round(pct_from_ema, 2),
        },
    )


def _score_ema_distance(pct: float) -> float:
    """Score based on % distance from 9 EMA."""
    if pct > 2.0:
        return 0.7
    elif pct > 1.0:
        return 0.5
    elif pct > 0.3:
        return 0.2
    elif pct > -0.3:
        return 0.0
    elif pct > -1.0:
        return -0.2
    elif pct > -2.0:
        return -0.5
    else:
        return -0.7
