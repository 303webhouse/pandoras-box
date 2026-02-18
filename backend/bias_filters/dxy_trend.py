"""
DXY trend macro confirmation factor.

Strong dollar is typically risk-off for equities.
"""

from __future__ import annotations

from datetime import datetime

try:
    from bias_engine.factor_utils import score_to_signal, get_price_history, neutral_reading
except Exception:  # pragma: no cover
    from backend.bias_engine.factor_utils import score_to_signal, get_price_history, neutral_reading

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

    # Integer vote mapping from brief:
    # -2 -> -1.0, -1 -> -0.5, 0 -> 0.0, +1 -> +0.5, +2 -> +1.0
    if pct_change_5d > 0.5 and above_sma:
        score = -1.0
    elif pct_change_5d > 0.5 and not above_sma:
        score = -0.5
    elif pct_change_5d < -0.5 and not above_sma:
        score = 1.0
    elif pct_change_5d < -0.5 and above_sma:
        score = 0.5
    else:
        score = 0.0

    trend = "rising" if pct_change_5d > 0.5 else "falling" if pct_change_5d < -0.5 else "flat"
    return FactorReading(
        factor_id="dxy_trend",
        score=score,
        signal=score_to_signal(score),
        detail=f"DXY {current:.2f} vs SMA20 {sma_20:.2f} ({'above' if above_sma else 'below'}), 5d {pct_change_5d:+.2f}% ({trend})",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "current": round(current, 4),
            "sma_20": round(sma_20, 4),
            "above_sma": above_sma,
            "pct_change_5d": round(pct_change_5d, 4),
            "trend": trend,
        },
    )

