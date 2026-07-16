"""S-3 Phase 2 — Cycle Extremes engine tests (§4.8/§4.9).

Structural tests that run WITHOUT live API calls or database access.
All vendor client I/O is bypassed by testing internal helpers directly.

Key invariants:
- D3: _DIAL_WRITES_TO_FEED is False (never True)
- §4.2 staleness contract: every cell has value/state/as_of/stale/source
- state ∈ {LIVE, STALE, NA, DEGRADED}
- Canonical copy strings are immutable constants
- §4.6: signal #10 always has state=NA and reason=DEFERRED_S5_BUDGET_SIZING
- Composite: clips to [-100, +100]; None when zero LIVE cells
- Coverage note: symbol+tier-dependent (BTC/ETH full, SOL partial, others partial)
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Import guards
# ---------------------------------------------------------------------------

def test_module_importable():
    """Engine module loads without errors."""
    from bias_filters.crypto_cycle_engine import (
        FROTH_CONTEXT_COPY,
        CAPITULATION_CONTEXT_COPY,
        _DIAL_WRITES_TO_FEED,
        _S10_DEFERRED_CELL,
    )
    assert FROTH_CONTEXT_COPY is not None
    assert CAPITULATION_CONTEXT_COPY is not None


# ---------------------------------------------------------------------------
# D3 invariant: the feed-write flag is ALWAYS False
# ---------------------------------------------------------------------------

def test_d3_dial_never_writes_to_feed():
    """_DIAL_WRITES_TO_FEED must be False at import time and cannot change."""
    from bias_filters.crypto_cycle_engine import _DIAL_WRITES_TO_FEED
    assert _DIAL_WRITES_TO_FEED is False, (
        "D3 violated: _DIAL_WRITES_TO_FEED must always be False — "
        "the Cycle Extremes dial must NEVER write to the signals table."
    )


def test_assert_no_feed_writes_passes():
    """_assert_no_feed_writes() does not raise when D3 is intact."""
    from bias_filters.crypto_cycle_engine import _assert_no_feed_writes
    _assert_no_feed_writes()  # Must not raise


def test_assert_no_feed_writes_raises_on_violation(monkeypatch):
    """_assert_no_feed_writes() raises AssertionError if the flag is tampered with."""
    import bias_filters.crypto_cycle_engine as engine
    monkeypatch.setattr(engine, "_DIAL_WRITES_TO_FEED", True)
    with pytest.raises(AssertionError, match="D3 rule"):
        engine._assert_no_feed_writes()


# ---------------------------------------------------------------------------
# Canonical copy strings (§4.7, Titans carry-forward — must never change)
# ---------------------------------------------------------------------------

def test_froth_copy_string():
    """FROTH copy must say 'reduce new risk', never 'sell'."""
    from bias_filters.crypto_cycle_engine import FROTH_CONTEXT_COPY
    assert FROTH_CONTEXT_COPY == "reduce new risk"
    assert "sell" not in FROTH_CONTEXT_COPY.lower()


def test_capitulation_copy_string():
    """CAPITULATION copy must reference B1 accumulation-timing context."""
    from bias_filters.crypto_cycle_engine import CAPITULATION_CONTEXT_COPY
    assert CAPITULATION_CONTEXT_COPY == "B1 accumulation-timing context"


# ---------------------------------------------------------------------------
# §4.2 cell contract — _make_cell
# ---------------------------------------------------------------------------

def test_make_cell_required_fields():
    """Every cell must carry all §4.2 required fields."""
    from bias_filters.crypto_cycle_engine import _make_cell
    cell = _make_cell(
        signal_id="test_signal",
        column="CAPITULATION",
        value=42.0,
        state="LIVE",
        source="test_source",
        as_of="2026-07-16T12:00:00+00:00",
        stale=False,
    )
    required = {"signal_id", "column", "value", "state", "source", "as_of", "stale"}
    assert required.issubset(cell.keys()), f"Missing fields: {required - cell.keys()}"


def test_make_cell_state_values():
    """State must be one of the four contract values."""
    from bias_filters.crypto_cycle_engine import _make_cell
    valid_states = {"LIVE", "STALE", "NA", "DEGRADED"}
    for state in valid_states:
        cell = _make_cell("sig", "FROTH", None, state, "src", None, False)
        assert cell["state"] == state


def test_make_cell_reason_optional():
    """reason field is only present when provided."""
    from bias_filters.crypto_cycle_engine import _make_cell
    without = _make_cell("sig", "FROTH", 1.0, "LIVE", "src", "2026-07-16T00:00:00Z", False)
    assert "reason" not in without

    with_reason = _make_cell("sig", "FROTH", None, "NA", "src", None, False, reason="TEST_REASON")
    assert with_reason["reason"] == "TEST_REASON"


# ---------------------------------------------------------------------------
# §4.6 signal #10 deferred placeholder
# ---------------------------------------------------------------------------

def test_s10_deferred_cell_contract():
    """Signal #10 must always be NA with correct deferred reason."""
    from bias_filters.crypto_cycle_engine import _S10_DEFERRED_CELL
    assert _S10_DEFERRED_CELL["state"] == "NA"
    assert _S10_DEFERRED_CELL["reason"] == "DEFERRED_S5_BUDGET_SIZING"
    assert _S10_DEFERRED_CELL["signal_id"] == "s10_etf_flow_exhaustion"
    assert _S10_DEFERRED_CELL["column"] == "CAPITULATION"
    assert _S10_DEFERRED_CELL["value"] is None


# ---------------------------------------------------------------------------
# Staleness check helper
# ---------------------------------------------------------------------------

def test_stale_check_old_timestamp():
    """Timestamps older than threshold return stale=True."""
    from bias_filters.crypto_cycle_engine import _stale_check
    # 1970-01-01 is definitely stale
    assert _stale_check("1970-01-01T00:00:00Z", 360) is True


def test_stale_check_none_timestamp():
    """None timestamp returns stale=True."""
    from bias_filters.crypto_cycle_engine import _stale_check
    assert _stale_check(None, 360) is True


def test_stale_check_future_timestamp():
    """Future timestamp returns stale=False."""
    from bias_filters.crypto_cycle_engine import _stale_check
    assert _stale_check("2099-01-01T00:00:00Z", 360) is False


def test_stale_check_z_suffix_handled():
    """Z suffix in ISO string is handled without ValueError."""
    from bias_filters.crypto_cycle_engine import _stale_check
    result = _stale_check("2026-07-16T12:00:00Z", 360)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Composite score computation
# ---------------------------------------------------------------------------

def test_composite_clips_to_bounds():
    """Composite score is always within [-100, +100]."""
    from bias_filters.crypto_cycle_engine import _score_cap
    assert _score_cap(200.0) == 100.0
    assert _score_cap(-200.0) == -100.0
    assert _score_cap(0.0) == 0.0
    assert _score_cap(99.9) == 99.9


def test_compute_composite_no_live_cells():
    """Zero LIVE cells → None composite, degraded=True."""
    from bias_filters.crypto_cycle_engine import _compute_composite
    cap = [{"state": "DEGRADED", "signal_id": "x", "column": "CAPITULATION", "signal": "UNKNOWN"}]
    froth = [{"state": "NA", "signal_id": "y", "column": "FROTH", "firing": False}]
    score, method, degraded, reason, count = _compute_composite(cap, froth, {
        "min_live_cells_btc_eth": 3,
        "min_live_cells_others": 2,
    }, "BTC")
    assert score is None
    assert degraded is True
    assert count == 0


def test_compute_composite_froth_dominant():
    """All LIVE froth signals firing → positive composite."""
    from bias_filters.crypto_cycle_engine import _compute_composite
    cap = [{"state": "LIVE", "signal_id": "c1", "column": "CAPITULATION", "signal": "NEUTRAL"}]
    froth = [
        {"state": "LIVE", "signal_id": "f1", "column": "FROTH", "firing": True},
        {"state": "LIVE", "signal_id": "f2", "column": "FROTH", "firing": True},
    ]
    score, method, degraded, reason, count = _compute_composite(cap, froth, {
        "min_live_cells_btc_eth": 2,
        "min_live_cells_others": 1,
    }, "ETH")
    assert score is not None
    assert score > 0, f"Expected positive score, got {score}"
    assert method == "froth_dominant"


def test_compute_composite_cap_dominant():
    """All LIVE cap signals firing → negative composite."""
    from bias_filters.crypto_cycle_engine import _compute_composite
    cap = [
        {"state": "LIVE", "signal_id": "c1", "column": "CAPITULATION", "signal": "FIRING"},
        {"state": "LIVE", "signal_id": "c2", "column": "CAPITULATION", "signal": "FIRING"},
    ]
    froth = [{"state": "LIVE", "signal_id": "f1", "column": "FROTH", "firing": False}]
    score, method, degraded, reason, count = _compute_composite(cap, froth, {
        "min_live_cells_btc_eth": 2,
        "min_live_cells_others": 1,
    }, "BTC")
    assert score is not None
    assert score < 0, f"Expected negative score, got {score}"
    assert method == "cap_dominant"


def test_compute_composite_degraded_below_min():
    """Fewer than min_live_cells → degraded=True even with a composite."""
    from bias_filters.crypto_cycle_engine import _compute_composite
    cap = [{"state": "LIVE", "signal_id": "c1", "column": "CAPITULATION", "signal": "NEUTRAL"}]
    froth = []
    # min is 3 for BTC/ETH but only 1 LIVE cell
    _, _, degraded, reason, count = _compute_composite(cap, froth, {
        "min_live_cells_btc_eth": 3,
        "min_live_cells_others": 2,
    }, "BTC")
    assert degraded is True
    assert reason is not None
    assert count == 1


# ---------------------------------------------------------------------------
# Coverage note builder
# ---------------------------------------------------------------------------

def test_coverage_note_btc():
    """BTC (tier 1) with LIVE Deribit skew gets full-coverage note."""
    from bias_filters.crypto_cycle_engine import _build_coverage_note
    note = _build_coverage_note("BTC", 1, {"state": "LIVE"})
    assert "full two-column" in note
    assert "BTC" in note


def test_coverage_note_sol():
    """SOL (tier 2) mentions Deribit NA."""
    from bias_filters.crypto_cycle_engine import _build_coverage_note
    note = _build_coverage_note("SOL", 2, None)
    assert "SOL" in note
    assert "Tier-2" in note


def test_coverage_note_tier3():
    """Tier-3 symbols (HYPE, ZEC, FARTCOIN) mention constraints."""
    from bias_filters.crypto_cycle_engine import _build_coverage_note
    note = _build_coverage_note("HYPE", 3, None)
    assert "Tier-3" in note
    assert "HYPE" in note


# ---------------------------------------------------------------------------
# Scheduler registration sanity
# ---------------------------------------------------------------------------

def test_scheduler_status_has_crypto_cycle_key():
    """_scheduler_status contains a 'crypto_cycle' key with expected fields."""
    from scheduler.bias_scheduler import _scheduler_status
    assert "crypto_cycle" in _scheduler_status
    assert "last_run" in _scheduler_status["crypto_cycle"]
    assert "rows_written" in _scheduler_status["crypto_cycle"]
    assert "status" in _scheduler_status["crypto_cycle"]


def test_enable_crypto_cycle_job_default_true():
    """ENABLE_CRYPTO_CYCLE_JOB defaults to True (dial is shadow-enabled at deploy)."""
    from scheduler.bias_scheduler import ENABLE_CRYPTO_CYCLE_JOB
    assert ENABLE_CRYPTO_CYCLE_JOB is True
