"""Unit tests for the hub_get_chart_indicators v1 pure indicator modules.
Small, hand-verifiable fixtures (no data fetch)."""

from indicators.rsi import latest_rsi
from indicators.atr import latest_atr
from indicators.macd import ema_series, latest_macd
from indicators.moving_averages import latest_moving_averages


# ── EMA ──────────────────────────────────────────────────────────────────────
def test_ema_series_hand_verified():
    # period=2, k=2/3, seed=mean(1,2)=1.5 at idx1, then EMA forward.
    assert ema_series([1, 2, 3, 4, 5], 2) == [None, 1.5, 2.5, 3.5, 4.5]


def test_ema_series_insufficient():
    assert ema_series([1, 2], 5) == [None, None]


# ── RSI ──────────────────────────────────────────────────────────────────────
def test_rsi_all_gains_is_100_overbought():
    r = latest_rsi(list(range(1, 30)), period=14)  # strictly rising → no losses
    assert r["value"] == 100.0 and r["state"] == "overbought"


def test_rsi_all_losses_is_0_oversold():
    r = latest_rsi(list(range(30, 1, -1)), period=14)  # strictly falling
    assert r["value"] == 0.0 and r["state"] == "oversold"


def test_rsi_insufficient_returns_none():
    assert latest_rsi([1, 2, 3], period=14) is None


# ── ATR ──────────────────────────────────────────────────────────────────────
def test_atr_constant_range_equals_range():
    highs = [11, 11, 11]
    lows = [9, 9, 9]
    closes = [10, 10, 10]
    # TR each bar = max(h-l=2, |h-prevC|=1, |l-prevC|=1) = 2 → ATR = 2.0
    assert latest_atr(highs, lows, closes, period=2) == 2.0


def test_atr_insufficient_returns_none():
    assert latest_atr([1], [1], [1], period=14) is None


# ── MACD ─────────────────────────────────────────────────────────────────────
def test_macd_uptrend_positive_rising():
    # Accelerating uptrend (convex) → macd strongly positive AND histogram still
    # rising-positive (a pure linear ramp converges to macd==signal, hist≈0 — a
    # degenerate fixture, not a real price path).
    m = latest_macd([float(i * i) for i in range(1, 80)], fast=12, slow=26, signal=9)
    assert set(m) == {"fast", "slow", "signal", "macd", "signal_line", "histogram", "hist_state"}
    assert m["macd"] > 0
    assert m["hist_state"] == "rising_positive"


def test_macd_insufficient_returns_none():
    assert latest_macd(list(range(1, 20))) is None  # < slow+signal


# ── Moving averages ──────────────────────────────────────────────────────────
def test_ma_short_history_nulls_long_mas():
    closes = list(range(1, 61))  # 60 rising bars, price=60
    out = latest_moving_averages(closes)
    sma = out["sma"]
    assert sma["20"] == round(sum(range(41, 61)) / 20, 4)  # mean of last 20
    assert sma["50"] is not None
    assert sma["120"] is None and sma["200"] is None       # insufficient → null
    assert out["ema"]["200"] is None
    assert sma["stack_state"] is None                      # can't determine w/ nulls
    assert sma["price_vs"]["20"] == "above" and sma["price_vs"]["200"] is None


def test_ma_bullish_stack():
    # rising series → short MAs above long MAs → bullish stack
    closes = list(range(1, 401))
    sma = latest_moving_averages(closes)["sma"]
    assert sma["stack_state"] == "bullish"
    assert all(sma["price_vs"][p] == "above" for p in ("20", "50", "120", "200"))
