"""
DXY trend macro confirmation factor (with VIX interaction).

Strong dollar is typically risk-off for equities. VIX context distinguishes
benign dollar strength (low VIX) from fear-driven strength (high VIX).

Absorbs the logic from the former dollar_smile factor per committee review.
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from bias_engine.factor_utils import score_to_signal, get_price_history, get_latest_price, neutral_reading
except Exception:  # pragma: no cover
    from backend.bias_engine.factor_utils import score_to_signal, get_price_history, get_latest_price, neutral_reading

from bias_engine.composite import FactorReading


async def compute_score() -> FactorReading:
    data = await get_price_history("DX-Y.NYB", days=30)
    if data is None or data.empty or "close" not in data.columns or len(data) < 20:
        return neutral_reading("dxy_trend", "DXY data unavailable", source="yfinance")

    close = data["close"].astype(float)
    current = float(close.iloc[-1])
    sma_20 = float(close.rolling(20).mean().iloc[-1])
    if len(close) < 6:
        return neutral_reading("dxy_trend", "Insufficient DXY lookback", source="yfinance")

    prior_5 = float(close.iloc[-6])
    pct_change_5d = ((current - prior_5) / prior_5) * 100 if prior_5 else 0.0
    above_sma = current > sma_20
    rising = pct_change_5d > 0.5
    falling = pct_change_5d < -0.5

    # Fetch VIX for interaction scoring (absorbed from dollar_smile)
    vix = await get_latest_price("^VIX")
    vix_elevated = vix is not None and vix > 20

    score = _score_dxy_vix(rising, falling, above_sma, vix_elevated)

    trend = "rising" if rising else "falling" if falling else "flat"
    vix_label = f"VIX {'elevated' if vix_elevated else 'calm'} at {vix:.1f}" if vix else "VIX unavailable"

    return FactorReading(
        factor_id="dxy_trend",
        score=score,
        signal=score_to_signal(score),
        detail=(
            f"DXY {current:.2f} vs SMA20 {sma_20:.2f} "
            f"({'above' if above_sma else 'below'}), "
            f"5d {pct_change_5d:+.2f}% ({trend}), {vix_label}"
        ),
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "current": round(current, 4),
            "sma_20": round(sma_20, 4),
            "above_sma": above_sma,
            "pct_change_5d": round(pct_change_5d, 4),
            "trend": trend,
            "vix": round(vix, 2) if vix else None,
            "vix_elevated": vix_elevated,
        },
    )


def _score_dxy_vix(rising: bool, falling: bool, above_sma: bool, vix_elevated: bool) -> float:
    """
    DXY + VIX interaction scoring (merged from dollar_smile).

    Rising DXY + VIX elevated = strong risk-off signal.
    Rising DXY + VIX calm = benign strength (much less bearish).
    Falling DXY + below SMA = risk-on (bullish).
    """
    if rising and above_sma and vix_elevated:
        return -1.0   # Strong risk-off: DXY surging + fear
    if rising and above_sma and not vix_elevated:
        return -0.3   # Benign strength: DXY rising but no fear (was -1.0 without VIX)
    if not rising and not falling and above_sma and vix_elevated:
        return -0.6   # Fear drag: DXY flat but elevated + VIX high
    if not rising and not falling and above_sma and not vix_elevated:
        return -0.2   # Mild drag: DXY flat-above-SMA, VIX calm
    if falling and not above_sma:
        return 1.0    # Risk-on: DXY falling below SMA
    if falling and above_sma:
        return 0.5    # Weakening strength
    if rising and not above_sma:
        return -0.5   # Rising from below: potential regime change
    return 0.0

