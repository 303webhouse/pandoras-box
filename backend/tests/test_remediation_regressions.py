"""Regression tests for the R-IV.46/47/48 remediations.

Each test corresponds to a defect the adversarial review found in the first cut of
this fix. Every one FAILS against the pre-remediation behaviour -- see
scratchpad/fails_pre_fix_proof.py, which reconstructs each pre-fix implementation
and drives these same assertions against it.
"""
from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from stable_engine.signals_freshness import (  # noqa: E402
    DEFAULT_SOURCE, REGISTERED_CLASSES, _COUNTERS, _class_status, class_key,
    counters_snapshot, record_attempt,
)
from utils.json_sanitize import NONFINITE_MARKER, dumps_jsonb  # noqa: E402

NAN = float("nan")


# --- F1 / (d) kwargs passthrough, allow_nan LOCKED -------------------------
def test_f1_kwargs_pass_through():
    """dumps_jsonb(..., default=str) was a TypeError -- a 500 on every call."""
    from datetime import date
    out = dumps_jsonb({"d": date(2026, 8, 21)}, default=str)
    assert json.loads(out)["d"] == "2026-08-21"
    assert dumps_jsonb({"b": 1, "a": 2}, sort_keys=True) == '{"a": 2, "b": 1}'


def test_f1b_allow_nan_cannot_be_re_enabled():
    """A caller must not be able to switch the guard off."""
    raw = dumps_jsonb({"a": NAN}, allow_nan=True)
    assert "NaN" not in raw
    assert json.loads(raw)["a"] is None


# --- F8 non-finite dict KEYS ----------------------------------------------
def test_f8_nonfinite_key_is_sanitized_not_raised():
    raw = dumps_jsonb({NAN: 1.0})
    assert "NaN" not in raw
    out = json.loads(raw)
    assert out["nan"] == 1.0
    assert any("<key" in p for p in out[NONFINITE_MARKER])


# --- F7 marker opt-out for map-shaped payloads ----------------------------
def test_f7_marker_false_keeps_maps_clean():
    raw = dumps_jsonb({"tech": NAN, "fin": 0.2}, marker=False)
    out = json.loads(raw)
    assert out == {"tech": None, "fin": 0.2}
    assert NONFINITE_MARKER not in out, "phantom entity injected into a map-shaped payload"


def test_f7b_marker_default_still_on_for_records():
    out = json.loads(dumps_jsonb({"atr": NAN, "rvol": 0.6}))
    assert NONFINITE_MARKER in out


# --- F6 three-outcome counting --------------------------------------------
@pytest.fixture(autouse=True)
def _clear_counters():
    _COUNTERS.clear()
    yield
    _COUNTERS.clear()


def test_f6_dedupe_is_not_a_gap():
    """A dedupe is a correct no-op; counting it as a gap made the alarm contradict
    completion_status() about the same event, in the same commit."""
    record_attempt("cta_scanner", persisted=False, error=None)      # dedupe
    c = counters_snapshot()["cta_scanner"]
    assert c["deduped"] == 1
    assert c["rejected"] == 0
    assert _class_status("cta_scanner", age=0.0, rejected=c["rejected"]) == "ok"


def test_f6b_rejection_is_a_gap_and_escalates():
    record_attempt("cta_scanner", persisted=False, error="invalid input syntax for type json")
    c = counters_snapshot()["cta_scanner"]
    assert c["rejected"] == 1 and c["deduped"] == 0
    assert _class_status("cta_scanner", age=0.0, rejected=c["rejected"]) == "flatline"


def test_f6c_three_outcomes_are_distinct():
    record_attempt("tradingview", persisted=True)
    record_attempt("tradingview", persisted=False, error="boom")
    record_attempt("tradingview", persisted=False, error=None)
    c = counters_snapshot()["tradingview"]
    assert (c["persisted"], c["rejected"], c["deduped"]) == (1, 1, 1)


# --- F11 counter key == column value --------------------------------------
def test_f11_class_key_mirrors_column_default():
    """postgres_client.py:1707 writes `source or "tradingview"`; the counter must agree."""
    assert class_key(None) == DEFAULT_SOURCE == "tradingview"
    assert class_key("") == "tradingview"
    assert class_key("  ") == "tradingview"
    assert class_key("cta_scanner") == "cta_scanner"


def test_f11b_no_phantom_unknown_class():
    record_attempt(None, persisted=True)
    assert "unknown" not in counters_snapshot()
    assert counters_snapshot()["tradingview"]["persisted"] == 1


# --- F4 static registry ----------------------------------------------------
def test_f4_registry_is_static_and_frozen():
    assert isinstance(REGISTERED_CLASSES, frozenset)
    for expected in ("tradingview", "server_scanner", "cta_scanner",
                     "crypto_scanner", "crypto_engine", "crypto_cvd_engine", "footprint"):
        assert expected in REGISTERED_CLASSES


def test_f4b_silent_class_renders_no_data_never_absent():
    """A record-derived instrument is void exactly when the record dies."""
    assert _class_status("crypto_cvd_engine", age=None, rejected=0) == "no_data"


def test_f4c_rejection_beats_rth_gating_at_any_hour():
    """Rejections are EVIDENCE and alert at any hour; RTH gates expectations only."""
    assert _class_status("tradingview", age=None, rejected=1) == "flatline"
    assert _class_status("tradingview", age=0.0, rejected=1) == "flatline"
