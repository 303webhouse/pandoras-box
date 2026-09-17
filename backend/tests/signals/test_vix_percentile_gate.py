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
# 4. The percentile source: typed modes, newest trading days (R-IV.423 / R-IV.425(c))
#
# The test this replaces asserted `result is None` for short history. Its mock made
# `pool.acquire` return a COROUTINE, so `async with` raised, the old function caught that
# and returned None -- and the test passed through the ERROR path, never the warm-up one.
# It was an instance of the exact defect R-IV.425(c) names. The mock below is a real async
# context manager, and error and warm-up are asserted as DIFFERENT outcomes.
# ---------------------------------------------------------------------------

from datetime import date, timedelta  # noqa: E402


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, rows=None, raises=None):
        self._rows, self._raises = rows or [], raises
        self.sql = None

    def acquire(self):
        pool = self

        class _Conn:
            async def fetch(self, sql, *args):
                pool.sql = sql
                if pool._raises:
                    raise pool._raises
                return pool._rows

        return _Acquire(_Conn())


def _rows_newest_first(n_calendar_days, end=date(2026, 9, 16), vix_of=lambda d: 18.0):
    return [{"d": end - timedelta(days=i), "vix": vix_of(end - timedelta(days=i))}
            for i in range(n_calendar_days)]


def _run(pool):
    async def go():
        with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=pool)):
            return await _compute_vix_percentiles(VIX_REGIME_PERCENTILE_LOOKBACK)
    return asyncio.run(go())


def test_short_history_is_insufficient_history_not_error():
    r = _run(_Pool(rows=_rows_newest_first(50)))
    assert r["mode"] == "insufficient_history"
    assert r["needed"] == VIX_REGIME_PERCENTILE_LOOKBACK
    assert 0 < r["n_days"] < VIX_REGIME_PERCENTILE_LOOKBACK
    assert "error" not in r


def test_a_query_error_is_error_not_warmup():
    r = _run(_Pool(raises=RuntimeError("connection reset")))
    assert r["mode"] == "error"
    assert "connection reset" in r["error"]


def test_the_old_broken_mock_is_now_caught_as_an_error():
    """The differential: the mock that used to 'pass' the warm-up test now says error."""
    mock_ctx = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_ctx)   # the old, broken shape
    r = _run(mock_pool)
    assert r["mode"] == "error", "a broken pool must never be recorded as short history"


def test_keeps_the_NEWEST_trading_days_not_the_oldest():
    """Enough history for two windows; the kept one must end at the newest date."""
    rows = _rows_newest_first(700)
    r = _run(_Pool(rows=rows))
    assert r["mode"] == "percentile"
    assert r["n_days"] == VIX_REGIME_PERCENTILE_LOOKBACK
    assert r["window_end"] == "2026-09-16"
    assert r["window_start"] > "2025-08-01", r["window_start"]


def test_the_newest_values_are_the_ones_used():
    """Old readings are extreme, recent ones calm: a correct window sees only the calm."""
    end = date(2026, 9, 16)
    rows = _rows_newest_first(900, end=end,
                              vix_of=lambda d: 15.0 if (end - d).days < 380 else 80.0)
    r = _run(_Pool(rows=rows))
    assert r["mode"] == "percentile"
    assert r["p90_value"] == pytest.approx(15.0)


def test_weekends_and_holidays_are_not_trading_days():
    r = _run(_Pool(rows=_rows_newest_first(700)))
    start = date.fromisoformat(r["window_start"])
    # 252 trading days span far more than 252 calendar days
    assert (date(2026, 9, 16) - start).days > 330
    # 2026-09-07 is Labor Day and 2026-09-13 a Sunday: neither may count
    open_day = lambda d: d.weekday() < 5 and d != date(2026, 9, 7)
    with patch("stable_engine.market_calendar.is_trading_day_or_none") as cal:
        cal.side_effect = open_day
        r2 = _run(_Pool(rows=_rows_newest_first(20)))
    expected = sum(open_day(date(2026, 9, 16) - timedelta(days=i)) for i in range(20))
    assert expected == 13          # 14 weekdays in the span, minus Labor Day
    assert r2["n_days"] == expected


def test_calendar_gaps_are_counted_not_hidden():
    with patch("stable_engine.market_calendar.is_trading_day_or_none", return_value=None):
        r = _run(_Pool(rows=_rows_newest_first(10)))
    assert r["calendar_unknown"] == 10
    assert r["n_days"] == 8        # the weekday fallback, stated rather than silent


def test_market_dates_not_session_dates():
    pool = _Pool(rows=_rows_newest_first(5))
    _run(pool)
    assert "America/New_York" in pool.sql
    assert "ORDER BY d DESC" in pool.sql


def test_flag_is_named_for_what_it_does():
    import signals.pipeline as pl
    assert pl.VIX_REGIME_V2_SHADOW is True
    assert not hasattr(pl, "VIX_REGIME_USE_PERCENTILE")
    assert pl.VIX_REGIME_V2_GATE_VERSION


# ---------------------------------------------------------------------------
# 4b. The evidence lands on the row (R-IV.423(a)/(b))
# ---------------------------------------------------------------------------

class _RecConn:
    def __init__(self, raises=None):
        self.calls, self._raises = [], raises

    async def execute(self, sql, *args):
        if self._raises:
            raise self._raises
        self.calls.append((sql, args))


def _signal(**cd):
    return {"signal_id": "SIG-1", "committee_data": cd}


def test_evidence_is_written_to_its_own_columns():
    from database.postgres_client import _write_iv_regime_evidence
    conn = _RecConn()
    asyncio.run(_write_iv_regime_evidence(conn, _signal(
        iv_regime_legacy={"decision": "allow"}, iv_regime_v2={"decision": "suppress"},
        iv_regime_diverged=True)))
    sql, args = conn.calls[0]
    assert "iv_regime_legacy" in sql and "iv_regime_v2" in sql and "iv_regime_diverged" in sql
    assert "committee_data" not in sql     # the committee bridge replaces that column wholesale
    assert args[0] == "SIG-1" and args[3] is True


def test_no_evidence_no_write():
    from database.postgres_client import _write_iv_regime_evidence
    conn = _RecConn()
    asyncio.run(_write_iv_regime_evidence(conn, _signal()))
    assert conn.calls == []


def test_a_failed_evidence_write_never_raises_into_the_signal_path():
    from database.postgres_client import _write_iv_regime_evidence
    conn = _RecConn(raises=RuntimeError("column does not exist"))
    with patch("database.postgres_client.logger") as log:
        asyncio.run(_write_iv_regime_evidence(conn, _signal(iv_regime_diverged=False)))
    assert log.error.called, "evidence that does not land must be loud"


def test_log_signal_writes_evidence_only_after_a_real_insert():
    import inspect
    from database import postgres_client as pc
    src = inspect.getsource(pc.log_signal)
    i_ins, i_ev = src.index("inserted = "), src.index("_write_iv_regime_evidence")
    assert i_ins < i_ev
    assert "else:" in src[i_ins:i_ev], "a duplicate insert must not overwrite stored evidence"


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
