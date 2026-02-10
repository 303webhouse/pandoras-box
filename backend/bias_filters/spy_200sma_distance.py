"""
SPY 200 SMA Distance Factor — percent distance from 200-day SMA.

Classic trend strength gauge with contrarian twist at extremes.
Far above 200 SMA = strong trend but stretched (mean reversion risk).
Far below 200 SMA = bearish but oversold (contrarian bounce potential).

Source: yfinance SPY
Timeframe: Swing (staleness: 24h)
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
    """Score SPY percent distance from 200-day SMA."""
    data = await get_price_history("SPY", days=250)
    if data is None or data.empty or "close" not in data.columns or len(data) < 200:
        logger.warning("SPY 200 SMA: insufficient data (need 200+ days)")
        return None

    close = data["close"]
    sma200 = close.rolling(window=200).mean()

    current_price = float(close.iloc[-1])
    current_sma = float(sma200.iloc[-1])

    if current_sma == 0 or current_sma != current_sma:  # NaN check
        return None

    pct_distance = ((current_price - current_sma) / current_sma) * 100
    score = _score_200sma_distance(pct_distance)

    return FactorReading(
        factor_id="spy_200sma_distance",
        score=score,
        signal=score_to_signal(score),
        detail=f"SPY {current_price:.2f}, 200 SMA {current_sma:.2f} ({pct_distance:+.1f}%)",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "price": current_price,
            "sma200": round(current_sma, 2),
            "pct_distance": round(pct_distance, 2),
        },
    )


def _score_200sma_distance(pct: float) -> float:
    """
    Score based on % distance from 200 SMA.
    Bullish when above, bearish when below.
    Slight contrarian pullback at extreme distances.
    """
    if pct > 15:
        return 0.4   # Very stretched — still bullish but less so
    elif pct > 10:
        return 0.5
    elif pct > 5:
        return 0.6
    elif pct > 3:
        return 0.4
    elif pct > 0:
        return 0.15
    elif pct > -3:
        return -0.15
    elif pct > -5:
        return -0.4
    elif pct > -10:
        return -0.6
    elif pct > -15:
        return -0.5
    else:
        return -0.4  # Very oversold — still bearish but less so
