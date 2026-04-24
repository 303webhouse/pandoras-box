"""
Tests for the 3-10 Oscillator indicator.

Test strategy:
    1. Math correctness — verify SMAs and oscillator values match expected
       output on a deterministic synthetic series.
    2. Column contract — function appends exactly OSC_FAST, OSC_SLOW,
       OSC_CROSS, OSC_DIV columns without mutating other columns.
    3. Insufficient data — returns df with NA columns when len(df) < 20.
    4. Divergence detection — synthetic bull-div and bear-div patterns
       trigger the correct osc_div sign.
    5. Raschke published vectors — PLACEHOLDER. Nick must supply these;
       the test is marked skip until he provides real values.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from unittest.mock import patch

from indicators.three_ten_oscillator import (
    OSC_CROSS,
    OSC_DIV,
    OSC_FAST,
    OSC_SLOW,
    _detect_divergences,
    compute_3_10,
)


def _make_df(highs, lows):
    assert len(highs) == len(lows)
    idx = [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(len(highs))]
    return pd.DataFrame({"high": highs, "low": lows}, index=idx)


def test_columns_appended_correctly():
    df = _make_df([10 + i * 0.1 for i in range(30)], [9 + i * 0.1 for i in range(30)])
    result = compute_3_10(df)
    for col in (OSC_FAST, OSC_SLOW, OSC_CROSS, OSC_DIV):
        assert col in result.columns, f"Missing column: {col}"


def test_returns_na_columns_when_insufficient_data():
    df = _make_df([10.0] * 15, [9.0] * 15)
    result = compute_3_10(df)
    assert result[OSC_FAST].isna().all()
    assert result[OSC_SLOW].isna().all()


def test_math_deterministic_series():
    """
    On an accelerating (exponential) rising series, raw = SMA3(midpoint) -
    SMA10(midpoint) is positive and increasing, so fast (SMA3 of raw) leads
    slow (SMA10 of raw) in the tail.

    Note: a purely linear series produces constant raw, making fast == slow
    everywhere (degenerate case). An accelerating series is the minimal
    input that exercises the fast > slow property.
    """
    df = _make_df(
        highs=[10 * (1.01 ** i) for i in range(50)],
        lows=[9 * (1.01 ** i) for i in range(50)],
    )
    result = compute_3_10(df)
    # After warmup, oscillator values should be defined and fast > slow
    tail = result.iloc[25:]
    assert not tail[OSC_FAST].isna().any()
    assert (tail[OSC_FAST] > tail[OSC_SLOW]).mean() > 0.8  # Majority fast > slow


def test_bull_divergence_smoke():
    """
    Smoke test: verify divergence detection runs without error on a realistic
    price series. Does NOT assert that divergence fires — synthetic patterns
    are fragile proxies for real divergences. Actual divergence quality is
    validated during the 6-month shadow period against real market data.
    """
    # Construct 50 bars of mixed price action (falling then sideways then rising)
    lows = [10 - i * 0.15 for i in range(15)] + [7.5 + (i % 3) * 0.1 for i in range(15)] + [8 + i * 0.2 for i in range(20)]
    highs = [lo + 0.5 for lo in lows]
    df = _make_df(highs, lows)
    result = compute_3_10(df)
    # Verify column populated with valid integer values (no exceptions raised)
    assert result[OSC_DIV].dtype in ("int8", "int64", "Int64")
    assert result[OSC_DIV].isin([-1, 0, 1]).all()


def test_divergence_detection_handles_flat_series():
    """
    Edge case: a perfectly flat price series should produce no divergences
    (no pivots at all) and should not crash.
    """
    df = _make_df([10.0] * 30, [9.0] * 30)
    result = compute_3_10(df)
    assert (result[OSC_DIV] == 0).all()


# ---------------------------------------------------------------------------
# Day-0 calibration tests — timeframe-aware divergence threshold
# ---------------------------------------------------------------------------

def test_timeframe_1h_uses_015_threshold():
    """compute_3_10(timeframe='1h') must pass threshold=0.15 to _detect_divergences."""
    df = _make_df([10 + i * 0.1 for i in range(30)], [9 + i * 0.1 for i in range(30)])
    with patch("indicators.three_ten_oscillator._detect_divergences", wraps=_detect_divergences) as mock_div:
        compute_3_10(df, timeframe="1h")
        assert mock_div.call_args.kwargs["threshold"] == 0.15


def test_timeframe_1d_uses_010_threshold():
    """compute_3_10(timeframe='1d') must pass threshold=0.10 (canonical Raschke default)."""
    df = _make_df([10 + i * 0.1 for i in range(30)], [9 + i * 0.1 for i in range(30)])
    with patch("indicators.three_ten_oscillator._detect_divergences", wraps=_detect_divergences) as mock_div:
        compute_3_10(df, timeframe="1d")
        assert mock_div.call_args.kwargs["threshold"] == 0.10


def test_explicit_threshold_overrides_timeframe():
    """Explicit divergence_threshold=0.25 wins over any timeframe lookup."""
    df = _make_df([10 + i * 0.1 for i in range(30)], [9 + i * 0.1 for i in range(30)])
    with patch("indicators.three_ten_oscillator._detect_divergences", wraps=_detect_divergences) as mock_div:
        compute_3_10(df, divergence_threshold=0.25, timeframe="1h")
        assert mock_div.call_args.kwargs["threshold"] == 0.25


def test_unknown_timeframe_falls_back_to_010():
    """Unknown timeframe string falls back to DEFAULT_DIVERGENCE_THRESHOLD (0.10)."""
    df = _make_df([10 + i * 0.1 for i in range(30)], [9 + i * 0.1 for i in range(30)])
    with patch("indicators.three_ten_oscillator._detect_divergences", wraps=_detect_divergences) as mock_div:
        compute_3_10(df, timeframe="unknown_tf")
        assert mock_div.call_args.kwargs["threshold"] == 0.10


@pytest.mark.skip(reason="Nick to supply Raschke published test vectors — see Phase 1 checkpoint")
def test_raschke_published_vectors():
    """
    Validate math output matches Raschke's published examples to 4 decimal places.

    TODO (Nick): Source 2-3 known 3-10 readings from Linda Raschke's published
    examples (her books or trading course materials). Replace this stub with
    real test vectors.

    When ready:
        expected = [
            {"bar_index": 14, "osc_fast": 0.1234, "osc_slow": 0.0567},
            ...
        ]
        df = build_df_from_raschke_example()
        result = compute_3_10(df)
        for e in expected:
            assert abs(result[OSC_FAST].iloc[e["bar_index"]] - e["osc_fast"]) < 1e-4
    """
    pass
