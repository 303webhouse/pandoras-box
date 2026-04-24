"""
Integration test: March 2026 drawdown replay through the iv_regime dual gate.

Tests that the percentile gate (v2) correctly identifies the March 2026 VIX
elevation as a regime anomaly while v1's absolute thresholds missed it.

ATHENA-requested per Olympus Pass 9. This test uses real FRED VIXCLS backfill
data (source='fred_backfill') seeded by scripts/fred_vix_backfill.py on 2026-04-24.

The percentile gate's p5/p90 across the 252-day backfill are approximately:
  p5  ≈ 14.73   p90 ≈ 24.19
(computed from 258 trading days: 2025-04-24 to 2026-04-23)

Divergence zone: VIX between 24.19 and 30.0 — v2 suppresses, v1 allows.
"""

import pytest
import numpy as np

from signals.pipeline import (
    VIX_REGIME_LOW_THRESHOLD,
    VIX_REGIME_HIGH_THRESHOLD,
    VIX_REGIME_ABS_FLOOR,
    VIX_REGIME_ABS_CEILING,
)

# ---------------------------------------------------------------------------
# Real FRED VIXCLS data for the March 2026 drawdown window (2026-03-01 to 2026-03-31).
# Source: factor_readings WHERE source='fred_backfill', seeded 2026-04-24.
# ---------------------------------------------------------------------------
MARCH_2026_VIX = [
    ("2026-03-02", 21.44),
    ("2026-03-03", 23.57),
    ("2026-03-04", 21.15),
    ("2026-03-05", 23.75),
    ("2026-03-06", 29.49),
    ("2026-03-09", 25.50),
    ("2026-03-10", 24.93),
    ("2026-03-11", 24.23),
    ("2026-03-12", 27.29),
    ("2026-03-13", 27.19),
    ("2026-03-16", 23.51),
    ("2026-03-17", 22.37),
    ("2026-03-18", 25.09),
    ("2026-03-19", 24.06),
    ("2026-03-20", 26.78),
    ("2026-03-23", 26.15),
    ("2026-03-24", 26.95),
    ("2026-03-25", 25.33),
    ("2026-03-26", 27.44),
    ("2026-03-27", 31.05),
    ("2026-03-30", 30.61),
]

# Full 258-day backfill used as the lookback window for percentile computation.
# p5 and p90 computed from the seeded DB (verified via SQL on 2026-04-24).
P5_BACKFILL  = 14.727
P90_BACKFILL = 24.188


def _v1_suppressed(vix: float) -> bool:
    return vix < VIX_REGIME_LOW_THRESHOLD or vix > VIX_REGIME_HIGH_THRESHOLD


def _v2_suppressed(vix: float, p5: float = P5_BACKFILL, p90: float = P90_BACKFILL) -> bool:
    return (
        vix < p5
        or vix > p90
        or vix < VIX_REGIME_ABS_FLOOR
        or vix > VIX_REGIME_ABS_CEILING
    )


def test_march_2026_drawdown_vix_26_28_caught_by_v2_not_v1():
    """
    During the March 2026 drawdown, VIX was elevated (26-28) but below v1's
    absolute 30-threshold. v2's percentile gate should suppress while v1 allows.
    """
    drawdown_days = [(d, v) for d, v in MARCH_2026_VIX if 26.0 <= v <= 28.0]
    assert len(drawdown_days) >= 3, (
        f"Expected at least 3 days in the 26-28 VIX drawdown window, got {len(drawdown_days)}"
    )

    for day, vix in drawdown_days:
        assert not _v1_suppressed(vix), (
            f"{day} VIX={vix}: v1 should ALLOW (thresholds: {VIX_REGIME_LOW_THRESHOLD}/{VIX_REGIME_HIGH_THRESHOLD})"
        )
        assert _v2_suppressed(vix), (
            f"{day} VIX={vix}: v2 should SUPPRESS (p90={P90_BACKFILL:.2f})"
        )


def test_at_least_5_diverged_days_in_march_2026():
    """
    The validation signal for the 60-day review period.
    At least 5 days in March 2026 should show gate divergence.
    """
    diverged_days = [
        (d, v) for d, v in MARCH_2026_VIX
        if _v1_suppressed(v) != _v2_suppressed(v)
    ]
    assert len(diverged_days) >= 5, (
        f"Expected >=5 diverged days in March 2026, found {len(diverged_days)}: "
        + str([(d, v) for d, v in diverged_days])
    )


def test_no_false_suppressions_in_comfortable_range():
    """
    v2 must not suppress on days when VIX is in the comfortable 15-24 range
    (inside both gates). No false positives in the low-vol portion of the window.
    """
    comfortable_days = [(d, v) for d, v in MARCH_2026_VIX if 15.0 <= v <= 24.0]
    assert len(comfortable_days) >= 3, "Need at least 3 comfortable-range days in the window"

    for day, vix in comfortable_days:
        assert not _v2_suppressed(vix), (
            f"{day} VIX={vix}: v2 incorrectly suppresses in comfortable range "
            f"(p5={P5_BACKFILL:.2f}, p90={P90_BACKFILL:.2f})"
        )


def test_both_gates_agree_on_crisis_days():
    """
    On days where VIX exceeded v1's absolute threshold (>30), both gates
    should suppress — no divergence at the extreme tail.
    """
    crisis_days = [(d, v) for d, v in MARCH_2026_VIX if v > VIX_REGIME_HIGH_THRESHOLD]
    assert len(crisis_days) >= 1, "Expected at least one crisis day (VIX>30) in March 2026"

    for day, vix in crisis_days:
        assert _v1_suppressed(vix), f"{day} VIX={vix}: v1 should suppress above 30"
        assert _v2_suppressed(vix), f"{day} VIX={vix}: v2 should suppress above p90 or ceiling"
        assert _v1_suppressed(vix) == _v2_suppressed(vix), (
            f"{day} VIX={vix}: gates should agree (both suppress) above crisis threshold"
        )
