"""DEF-SIGNAL-PERSISTENCE-COLLAPSE -- non-finite injection matrix.

Case 1 is the DEPLOY GATE: it must FAIL on 2de26c6 (where dumps_jsonb does not
exist) and pass on the fix. A control that cannot fail proves nothing.

Covers both bind targets ($19 triggering_factors / $20 bias_at_signal), both
injection shapes (global field and per-field leaf), and all three invalid token
classes (NaN, Infinity, -Infinity), plus numpy, list-root (A1), and the
byte-identical finite regression.
"""
from __future__ import annotations

import json
import math
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from utils.json_sanitize import NONFINITE_MARKER, dumps_jsonb, sanitize_for_json  # noqa: E402

NAN, INF, NINF = float("nan"), float("inf"), float("-inf")
BAD_TOKENS = ("NaN", "Infinity", "-Infinity")


def _assert_bindable(raw: str):
    """The property that decides whether the row lands: valid JSON, no bare token."""
    for tok in BAD_TOKENS:
        assert tok not in raw, f"bare {tok} token present -- Postgres will reject: {raw[:200]}"
    json.loads(raw)  # raises if not valid JSON


# --- shapes reproducing the two real bind payloads -------------------------
def _triggering_factors(bad):
    """$19 -- per-signal dict of scored factors."""
    return {"squeeze": {"score": 0.4}, "flow": {"net_prem": bad}, "adx": 25.0}


def _bias_at_signal(bad, nested=False):
    """$20 -- global snapshot shared by every signal in the window."""
    inner = {"rsi": bad, "ema20": 1.5} if nested else {"rsi": 30.0, "ema20": 1.5}
    return {"scheduler_bias": inner, "composite": (bad if not nested else 0.2)}


# --- CASE 1 (DEPLOY GATE) --------------------------------------------------
def test_case1_gate_triggering_factors_global_nan():
    """DEPLOY GATE. Must fail on 2de26c6 (no dumps_jsonb) and pass on the fix."""
    raw = dumps_jsonb(_triggering_factors(NAN))
    _assert_bindable(raw)
    out = json.loads(raw)
    assert out["flow"]["net_prem"] is None, "non-finite must become null, never 0"
    assert "flow.net_prem" in out[NONFINITE_MARKER], "degraded path must be named"
    assert out["adx"] == 25.0, "sibling fields must survive"


# --- CASES 2-6: both targets x both shapes x all three tokens --------------
@pytest.mark.parametrize("bad,label", [(NAN, "NaN"), (INF, "Infinity"), (NINF, "-Infinity")])
@pytest.mark.parametrize("builder,path", [
    (lambda b: _triggering_factors(b), "flow.net_prem"),                 # $19 leaf
    (lambda b: {"composite": b}, "composite"),                           # $19/$20 global field
    (lambda b: _bias_at_signal(b, nested=True), "scheduler_bias.rsi"),   # $20 nested global
    (lambda b: _bias_at_signal(b, nested=False), "composite"),           # $20 top-level
])
def test_cases2to6_all_targets_shapes_tokens(builder, path, bad, label):
    raw = dumps_jsonb(builder(bad))
    _assert_bindable(raw)
    out = json.loads(raw)
    assert path in out[NONFINITE_MARKER], f"{label} at {path} not reported"
    cur = out
    for part in path.split("."):
        cur = cur[part]
    assert cur is None, f"{label} at {path} must be null, got {cur!r}"


# --- CASE 7: numpy, guarded AFTER float() conversion (A2) ------------------
def test_case7_numpy_nan():
    np = pytest.importorskip("numpy")
    raw = dumps_jsonb({"atr_14": np.float64("nan"), "rvol": np.float64(0.63)})
    _assert_bindable(raw)
    out = json.loads(raw)
    assert out["atr_14"] is None
    assert out["rvol"] == pytest.approx(0.63)
    assert "atr_14" in out[NONFINITE_MARKER]


def test_case7b_decimal_nan():
    from decimal import Decimal
    raw = dumps_jsonb({"d": Decimal("NaN")})
    _assert_bindable(raw)
    assert json.loads(raw)["d"] is None


# --- CASE 8: finite regression, byte-identical -----------------------------
def test_case8_finite_payload_byte_identical():
    payload = {"a": 1, "b": "x", "c": [1, 2, 3], "d": 1.5, "e": None, "f": True}
    assert dumps_jsonb(payload) == json.dumps(payload)
    assert NONFINITE_MARKER not in dumps_jsonb(payload)


# --- CASE 11: list-rooted payload (A1) -------------------------------------
def test_case11_list_root_lands_and_logs(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        raw = dumps_jsonb([1.0, NAN, 3.0])
    _assert_bindable(raw)
    assert json.loads(raw) == [1.0, None, 3.0]
    assert any("non-finite" in r.getMessage() for r in caplog.records),         "list-root degradation must still be logged"


# --- guardrails ------------------------------------------------------------
def test_allow_nan_false_is_belt_and_braces():
    """If the sanitizer ever regresses, dumps must raise loudly, not emit a token."""
    with pytest.raises(ValueError):
        json.dumps({"a": NAN}, allow_nan=False)


def test_sanitizer_one_arg_backward_compatible():
    assert sanitize_for_json({"a": NAN}) == {"a": None}
    assert sanitize_for_json({"t": 1.5}) == {"t": 1.5}


def test_nested_path_syntax():
    out = json.loads(dumps_jsonb({"x": {"y": [NAN]}}))
    assert out["x"]["y"] == [None]
    assert "x.y[0]" in out[NONFINITE_MARKER]


def test_no_finite_value_is_altered():
    for v in (0.0, -0.0, 1e308, -1e308, 1e-308):
        assert math.isfinite(v)
        assert json.loads(dumps_jsonb({"v": v}))["v"] == v
