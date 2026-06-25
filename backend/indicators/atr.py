"""Wilder ATR — pure indicator math (hub_get_chart_indicators v1).

Takes chronological high/low/close arrays (oldest→newest), returns the latest
RAW ATR value (the aggregator computes atr_pct against spot). None on
insufficient bars. Mirrors adx.py.
"""

from __future__ import annotations

from typing import Optional, Sequence


def latest_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Optional[float]:
    """Wilder ATR(period) raw value (price units), rounded 4dp. None if too few bars."""
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None

    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    # Wilder seed: mean of the first `period` true ranges, then smooth.
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return round(atr, 4)
