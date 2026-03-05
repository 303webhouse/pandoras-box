"""
SPY 50 SMA Distance Factor — percent distance from 50-day SMA.

Intermediate trend indicator for swing timeframe. The 50 SMA captures
multi-week momentum — it flips within days of a real trend change,
unlike the 200 SMA which takes weeks.

Far above 50 SMA = strong intermediate trend but getting stretched.
Below 50 SMA = intermediate trend broken, bearish for swing trades.

Source: yfinance SPY (Polygon primary, yfinance fallback)
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
    """Score SPY percent distance from 50-day SMA."""
    data = await get_price_history("SPY", days=80)
    if data is None or data.empty or "close" not in data.columns or len(data) < 50:
        logger.warning("SPY 50 SMA: insufficient data (need 50+ days)")
        return None

    close = data["close"]
    sma50 = close.rolling(window=50).mean()

    current_price = float(close.iloc[-1])
    current_sma = float(sma50.iloc[-1])

    if current_sma == 0 or current_sma != current_sma:  # NaN check
        return None

    pct_distance = ((current_price - current_sma) / current_sma) * 100
    score = _score_50sma_distance(pct_distance)

    return FactorReading(
        factor_id="spy_50sma_distance",
        score=score,
        signal=score_to_signal(score),
        detail=f"SPY {current_price:.2f}, 50 SMA {current_sma:.2f} ({pct_distance:+.1f}%)",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "price": current_price,
            "sma50": round(current_sma, 2),
            "pct_distance": round(pct_distance, 2),
        },
    )


def _score_50sma_distance(pct: float) -> float:
    """
    Score based on % distance from 50 SMA.

    Tighter bands than 200 SMA — the 50 SMA is closer to price so
    even small deviations are significant for swing positioning.

    Bullish when above, bearish when below.
    Contrarian pullback at extremes (stretched = mean reversion risk).
    """
    if pct > 8:
        return 0.3    # Very stretched above — still bullish but fading
    elif pct > 5:
        return 0.5    # Strong intermediate uptrend
    elif pct > 3:
        return 0.6    # Healthy distance above
    elif pct > 1:
        return 0.4    # Mildly above — bullish
    elif pct > 0:
        return 0.1    # Right at the line — barely bullish
    elif pct > -1:
        return -0.1   # Just below — early warning
    elif pct > -3:
        return -0.4   # Clearly below — intermediate trend broken
    elif pct > -5:
        return -0.6   # Accelerating below
    elif pct > -8:
        return -0.5   # Oversold but still bearish
    else:
        return -0.3   # Very oversold — contrarian bounce zone
