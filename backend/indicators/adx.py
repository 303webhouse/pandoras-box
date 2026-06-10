"""Wilder ADX(14) — pure indicator math (sub-brief 3 Chunk 3).

Reusable by design: takes OHLC arrays (chronological, oldest→newest) and returns
the ADX series / latest value. No data fetch, no SPY hard-coding — the PYTHAGORAS
feed Phase 0 reuses this module directly for its own trend-strength math.
"""

from __future__ import annotations

from typing import List, Optional, Sequence


def wilder_adx_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> List[float]:
    """Wilder-smoothed ADX series.

    Returns [] if there are too few bars for a stable read (need >= 2*period+1).
    The returned list is the ADX values from the first computable bar onward
    (oldest→newest); the last element is the most recent ADX.
    """
    n = len(closes)
    if n < period * 2 + 1 or len(highs) != n or len(lows) != n:
        return []

    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    # Wilder smoothing seeded with the sum over the first `period` deltas (idx 1..period)
    smoothed_tr = sum(tr[1 : period + 1])
    smoothed_p = sum(plus_dm[1 : period + 1])
    smoothed_m = sum(minus_dm[1 : period + 1])

    dxs: List[float] = []
    for i in range(period, n):
        if i > period:
            smoothed_tr = smoothed_tr - smoothed_tr / period + tr[i]
            smoothed_p = smoothed_p - smoothed_p / period + plus_dm[i]
            smoothed_m = smoothed_m - smoothed_m / period + minus_dm[i]
        if smoothed_tr == 0:
            dxs.append(0.0)
            continue
        plus_di = 100.0 * smoothed_p / smoothed_tr
        minus_di = 100.0 * smoothed_m / smoothed_tr
        denom = plus_di + minus_di
        dxs.append(0.0 if denom == 0 else 100.0 * abs(plus_di - minus_di) / denom)

    if len(dxs) < period:
        return []

    # ADX = Wilder smoothing of DX; seed = mean of the first `period` DX values
    adx = sum(dxs[:period]) / period
    out = [adx]
    for k in range(period, len(dxs)):
        adx = (adx * (period - 1) + dxs[k]) / period
        out.append(adx)
    return out


def latest_adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Optional[float]:
    """Most recent ADX value, rounded to 2dp. None if insufficient bars."""
    series = wilder_adx_series(highs, lows, closes, period)
    return round(series[-1], 2) if series else None
