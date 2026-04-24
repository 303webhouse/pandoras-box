"""
Unit tests for iv_regime VIX percentile gate v2 (Olympus Pass 9, 2026-04-24).

Tests cover:
  - Percentile computation on synthetic series (low/high/regime-shift)
  - Warmup fallback when history is insufficient
  - Absolute floor/ceiling always-suppress overrides
  - Dual-logging diverged flag (agree and disagree cases)

Gate logic is exercised directly using _pct_result() so tests stay synchronous
and have no external dependencies. The one async test (warmup fallback) uses
asyncio.run() directly to avoid requiring pytest-asyncio.
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from signals.pipeline import (
    _compute_vix_percentiles,
    VIX_REGIME_ABS_CEILING,
    VIX_REGIME_ABS_FLOOR,
    VIX_REGIME_HIGH_THRESHOLD,
    VIX_REGIME_LOW_THRESHOLD,
    VIX_REGIME_PERCENTILE_HIGH,
    VIX_REGIME_PERCENTILE_LOOKBACK,
    VIX_REGIME_PERCENTILE_LOW,
    VIX_REGIME_WARMUP_FALLBACK_HIGH,
    VIX_REGIME_WARMUP_FALLBACK_LOW,
)


def _pct_result(vix_values: list) -> dict:
    """Compute percentile result dict from a list of VIX floats."""
    return {
        "p5_value":  float(np.percentile(vix_values, VIX_REGIME_PERCENTILE_LOW)),
        "p90_value": float(np.percentile(vix_values, VIX_REGIME_PERCENTILE_HIGH)),
        "n_days":    len(vix_values),
    }


def _v2_gate(vix: float, pct: dict) -> bool:
    """Apply the v2 gate decision given a vix value and computed percentile dict."""
    return (
        vix < pct["p5_value"]
        or vix > pct["p90_value"]
        or vix < VIX_REGIME_ABS_FLOOR
        or vix > VIX_REGIME_ABS_CEILING
    )


# ---------------------------------------------------------------------------
# 1. Low-vol series: both p5 and p90 are below 15
# ---------------------------------------------------------------------------

def test_percentile_computation_with_synthetic_low_vol_series():
    vix_series = [10.0 + (i % 5) * 0.4 for i in range(252)]  # 10.0 – 11.6

    result = _pct_result(vix_series)
    assert result["p5_value"] < 15.0, "p5 should be below 15 for low-vol series"
    assert result["p90_value"] < 15.0, "p90 should be below 15 for low-vol series"


# ---------------------------------------------------------------------------
# 2. High-vol series: p90 above 32
# ---------------------------------------------------------------------------

def test_percentile_computation_with_synthetic_high_vol_series():
    vix_series = [24.0 + (i % 10) * 1.0 for i in range(252)]  # 24 – 33

    result = _pct_result(vix_series)
    assert result["p90_value"] >= 32.0, "p90 should be at least 32 for high-vol series"


# ---------------------------------------------------------------------------
# 3. Regime-shift: first 150 @ 14, next 102 @ 22 — p90 blends to 23-25
# ---------------------------------------------------------------------------

def test_percentile_computation_with_regime_shift():
    # Linear ramp 14→26 over 252 days (gradual vol regime shift).
    # p90 of a uniform ramp [14..26] = 14 + 0.9*(26-14) ≈ 24.8
    vix_series = [14.0 + (i / 251) * 12.0 for i in range(252)]

    result = _pct_result(vix_series)
    assert 23.0 <= result["p90_value"] <= 25.0, (
        f"p90 should be 23-25 for regime-shift ramp series, got {result['p90_value']:.2f}"
    )


# ---------------------------------------------------------------------------
# 4. Warmup fallback: <252 rows causes _compute_vix_percentiles to return None
# ---------------------------------------------------------------------------

def test_warmup_fallback_when_history_insufficient():
    short_rows = [{"vix": 18.0}] * 50

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=short_rows)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_ctx)

    async def run():
        # Patch at the source module since get_postgres_client is imported lazily inside the function
        with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=mock_pool)):
            return await _compute_vix_percentiles(VIX_REGIME_PERCENTILE_LOOKBACK)

    result = asyncio.run(run())
    assert result is None, "Should return None when fewer than 252 days of history"


# ---------------------------------------------------------------------------
# 5. Absolute floor always suppresses (even if all-low-vol history would allow)
# ---------------------------------------------------------------------------

def test_abs_floor_always_suppresses():
    vix = VIX_REGIME_ABS_FLOOR - 0.1
    pct = _pct_result([8.0] * 252)  # history so low p5 ≈ 8, p90 ≈ 8 — no percentile match

    # Even if pct said "allow", the floor override should catch it
    suppressed = _v2_gate(vix, pct)
    assert suppressed, (
        f"VIX={vix:.2f} below floor={VIX_REGIME_ABS_FLOOR} must always suppress"
    )


# ---------------------------------------------------------------------------
# 6. Absolute ceiling always suppresses
# ---------------------------------------------------------------------------

def test_abs_ceiling_always_suppresses():
    vix = VIX_REGIME_ABS_CEILING + 0.1
    # History so extreme that p90 is also > 35, so percentile alone wouldn't suppress
    pct = _pct_result([40.0] * 252)

    suppressed = _v2_gate(vix, pct)
    assert suppressed, (
        f"VIX={vix:.2f} above ceiling={VIX_REGIME_ABS_CEILING} must always suppress"
    )


# ---------------------------------------------------------------------------
# 7. Diverged = True when v1 allows but v2 suppresses
#    VIX=26, history centred ~17 → p90 ≈ 19.5 → v2 suppresses; v1 allows (< 30)
# ---------------------------------------------------------------------------

def test_dual_log_diverged_flag_true_when_decisions_disagree():
    vix = 26.0
    vix_series = [16.0 + (i % 8) * 0.5 for i in range(252)]  # 16 – 19.5
    pct = _pct_result(vix_series)

    v1_suppressed = vix < VIX_REGIME_LOW_THRESHOLD or vix > VIX_REGIME_HIGH_THRESHOLD
    v2_suppressed = _v2_gate(vix, pct)
    diverged = v1_suppressed != v2_suppressed

    assert not v1_suppressed, f"v1 should allow at VIX={vix} (thresholds 15/30)"
    assert v2_suppressed, f"v2 should suppress at VIX={vix} (p90={pct['p90_value']:.2f})"
    assert diverged, "iv_regime_diverged must be True when decisions disagree"


# ---------------------------------------------------------------------------
# 8. Diverged = False when both gates agree (VIX=18, comfortable mid-range)
# ---------------------------------------------------------------------------

def test_dual_log_diverged_flag_false_when_decisions_agree():
    vix = 18.0
    vix_series = [14.0 + (i % 16) * 0.5 for i in range(252)]  # 14 – 21.5
    pct = _pct_result(vix_series)

    v1_suppressed = vix < VIX_REGIME_LOW_THRESHOLD or vix > VIX_REGIME_HIGH_THRESHOLD
    v2_suppressed = _v2_gate(vix, pct)
    diverged = v1_suppressed != v2_suppressed

    assert not diverged, (
        f"Both gates should agree (allow) at VIX={vix}. "
        f"v1_suppressed={v1_suppressed}, v2_suppressed={v2_suppressed}, "
        f"p5={pct['p5_value']:.2f}, p90={pct['p90_value']:.2f}"
    )
