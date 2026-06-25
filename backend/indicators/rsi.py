"""Wilder RSI — pure indicator math (hub_get_chart_indicators v1).

Mirrors adx.py: takes a chronological close array (oldest→newest), returns the
latest RSI value + state. No data fetch inside. None on insufficient bars
(never fabricates).
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence


def latest_rsi(closes: Sequence[float], period: int = 14) -> Optional[Dict]:
    """Wilder RSI(period) on the latest bar → {period, value, state} or None.

    state: 'overbought' (>70) / 'oversold' (<30) / 'neutral'. Needs >= period+1
    closes (one extra for the first delta).
    """
    n = len(closes)
    if n < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, n):
        ch = closes[i] - closes[i - 1]
        gains.append(ch if ch > 0 else 0.0)
        losses.append(-ch if ch < 0 else 0.0)

    # Wilder seed: simple average of the first `period` deltas, then smooth.
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100.0
    elif avg_gain == 0:
        rsi = 0.0
    else:
        rsi = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    state = "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral"
    return {"period": period, "value": round(rsi, 2), "state": state}
