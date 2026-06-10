"""ADX indicator + regime classification tests (sub-brief 3 Chunk 3)."""

from indicators.adx import latest_adx, wilder_adx_series
from scoring.adx_regime import classify_adx_regime


def _trending_series(n=60):
    # Steady uptrend, small intrabar range → high directional movement → high ADX
    highs, lows, closes = [], [], []
    base = 100.0
    for i in range(n):
        c = base + i * 1.0
        highs.append(c + 0.4)
        lows.append(c - 0.4)
        closes.append(c)
    return highs, lows, closes


def _choppy_series(n=60):
    # Oscillating sideways → low directional movement → low ADX
    highs, lows, closes = [], [], []
    base = 100.0
    for i in range(n):
        c = base + (1.0 if i % 2 == 0 else -1.0)
        highs.append(c + 0.5)
        lows.append(c - 0.5)
        closes.append(c)
    return highs, lows, closes


def test_trending_series_high_adx():
    h, l, c = _trending_series()
    adx = latest_adx(h, l, c, 14)
    assert adx is not None
    assert adx > 25, f"steady uptrend should be trending, got ADX={adx}"


def test_choppy_series_low_adx():
    h, l, c = _choppy_series()
    adx = latest_adx(h, l, c, 14)
    assert adx is not None
    assert adx < 25, f"oscillating series should be choppy, got ADX={adx}"


def test_trend_exceeds_chop():
    th, tl, tc = _trending_series()
    ch, cl, cc = _choppy_series()
    assert latest_adx(th, tl, tc, 14) > latest_adx(ch, cl, cc, 14)


def test_insufficient_bars_returns_none():
    assert latest_adx([1, 2], [0, 1], [1, 2], 14) is None
    assert wilder_adx_series([1, 2], [0, 1], [1, 2], 14) == []


def test_classify_thresholds():
    assert classify_adx_regime(30.0)["label"] == "trending"
    assert classify_adx_regime(22.0)["label"] == "transitional"
    assert classify_adx_regime(15.0)["label"] == "choppy"


def test_classify_unknown_no_confident_default():
    # absent / stale → 'unknown' with no penalty and no trending bonus
    none_r = classify_adx_regime(None)
    assert none_r["label"] == "unknown"
    assert none_r["penalty"] == 0
    assert none_r["reason"] == "no_data"
    stale_r = classify_adx_regime(30.0, stale=True)
    assert stale_r["label"] == "unknown"
    assert stale_r["reason"] == "stale"
