"""Moving-average stack — pure indicator math (hub_get_chart_indicators v1).

SMA(20,50,120,200) + EMA(200), stack_state (CTA zones), and price_vs map.
A given MA returns null when there are too few bars for it (never computed on a
short window — the fake-healthy P0 class). Mirrors adx.py; EMA reused from macd.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from .macd import ema_series

_SMA_PERIODS = (20, 50, 120, 200)


def _sma(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 4)


def latest_moving_averages(closes: Sequence[float]) -> Dict:
    """Return {sma:{20,50,120,200,stack_state,price_vs}, ema:{200}}.

    stack_state: 'bullish' (20>50>120>200), 'bearish' (inverse), 'transitioning'
    (neither) — or None if any of the four SMAs is null (can't be determined).
    price_vs[p]: 'above'/'below'/None per MA vs the latest close.
    """
    price = closes[-1] if closes else None
    smas = {p: _sma(closes, p) for p in _SMA_PERIODS}

    e200 = ema_series(closes, 200)
    ema200 = round(e200[-1], 4) if e200 and e200[-1] is not None else None

    vals = [smas[p] for p in _SMA_PERIODS]
    if all(v is not None for v in vals):
        if vals[0] > vals[1] > vals[2] > vals[3]:
            stack = "bullish"
        elif vals[0] < vals[1] < vals[2] < vals[3]:
            stack = "bearish"
        else:
            stack = "transitioning"
    else:
        stack = None  # insufficient bars for the full stack — honest null

    price_vs = {}
    for p in _SMA_PERIODS:
        if smas[p] is None or price is None:
            price_vs[str(p)] = None
        else:
            price_vs[str(p)] = "above" if price >= smas[p] else "below"

    return {
        "sma": {
            "20": smas[20], "50": smas[50], "120": smas[120], "200": smas[200],
            "stack_state": stack, "price_vs": price_vs,
        },
        "ema": {"200": ema200},
    }
