"""
VIX Regime Factor — absolute VIX level scoring for the composite bias engine.

Different from vix_term (which measures VIX/VIX3M ratio). This scores the
absolute VIX level, which indicates overall market fear/complacency.

Source: yfinance ^VIX
Timeframe: Intraday (staleness: 4h)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal, get_latest_price
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal, get_latest_price


async def compute_score() -> Optional[FactorReading]:
    """Score based on absolute VIX level."""
    vix = await get_latest_price("^VIX")
    if vix is None:
        logger.warning("VIX regime: could not fetch VIX price")
        return None

    score = _score_vix_level(vix)

    return FactorReading(
        factor_id="vix_regime",
        score=score,
        signal=score_to_signal(score),
        detail=f"VIX at {vix:.1f} ({'panic' if vix > 30 else 'fear' if vix > 25 else 'elevated' if vix > 20 else 'cautious' if vix > 18 else 'normal' if vix > 14 else 'complacent'})",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={"vix": float(vix)},
    )


def _score_vix_level(vix: float) -> float:
    """
    Score absolute VIX level.
    Low VIX = complacency = bullish (but contrarian warning at extremes).
    High VIX = fear = bearish.
    """
    if vix > 35:
        return -0.9
    elif vix > 30:
        return -0.7
    elif vix > 25:
        return -0.5
    elif vix > 20:
        return -0.3
    elif vix > 18:
        return -0.1   # Elevated — lean slightly bearish (was 0.0)
    elif vix > 14:
        return 0.2
    elif vix > 12:
        return 0.4
    else:
        # Extreme complacency — still bullish but stretched
        return 0.3
