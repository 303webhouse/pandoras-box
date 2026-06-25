"""MACD + EMA — pure indicator math (hub_get_chart_indicators v1).

No EMA helper existed in the indicators/ package (three_ten_oscillator is
SMA/pandas-based), so `ema_series` is implemented here pure-python and reused
by moving_averages.py for EMA-200. Mirrors adx.py: arrays in, latest out, no
fetch. None on insufficient bars.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence


def ema_series(values: Sequence[float], period: int) -> List[Optional[float]]:
    """EMA aligned to `values` (oldest→newest). Indices < period-1 are None;
    seeded with the SMA of the first `period` values (standard convention)."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n < period or period < 1:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def latest_macd(
    closes: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Optional[Dict]:
    """MACD(fast/slow/signal) on the latest bar.

    Returns {fast, slow, signal, macd, signal_line, histogram, hist_state} or
    None if too few bars for a stable signal line. hist_state =
    {rising|falling}_{positive|negative} (direction vs the prior bar's histogram).
    """
    if len(closes) < slow + signal:
        return None

    e_fast = ema_series(closes, fast)
    e_slow = ema_series(closes, slow)
    macd_line = [a - b for a, b in zip(e_fast, e_slow) if a is not None and b is not None]
    if len(macd_line) < signal + 1:
        return None

    sig = ema_series(macd_line, signal)
    if sig[-1] is None or sig[-2] is None:
        return None

    macd_v = macd_line[-1]
    sig_v = sig[-1]
    hist = macd_v - sig_v
    prev_hist = macd_line[-2] - sig[-2]

    direction = "rising" if hist >= prev_hist else "falling"
    sign = "positive" if hist >= 0 else "negative"

    return {
        "fast": fast,
        "slow": slow,
        "signal": signal,
        "macd": round(macd_v, 4),
        "signal_line": round(sig_v, 4),
        "histogram": round(hist, 4),
        "hist_state": f"{direction}_{sign}",
    }
