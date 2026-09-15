"""/health must not be able to 500 (R-IV.381).

On 2026-09-14 it returned HTTP 500 for hours with
    ValueError: Out of range float values are not JSON compliant: nan

Every block in the payload is wrapped in its own try/except, and every one of
them SUCCEEDED. The failure was at SERIALISATION — after the last guard had
already passed — so no per-block guard could have caught it.

The endpoint is the single surface the four-step deploy verification, the
freshness SLOs and the alarm reads all go through. While it was down, all of
them were blind.
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_SRC = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
_NS = {"logger": type("L", (), {"error": staticmethod(lambda *a, **k: None)})()}
exec(_SRC[_SRC.index("def _json_safe"):_SRC.index('@app.get("/health")')], _NS)
_sanitise = _NS["_sanitise_health"]


def test_nan_becomes_null_and_is_reported():
    out = _sanitise({"x": float("nan")})
    assert out["x"] is None
    assert "x" in out["_nonfinite"]


def test_infinity_both_signs():
    out = _sanitise({"p": float("inf"), "n": float("-inf")})
    assert out["p"] is None and out["n"] is None


def test_nested_paths_are_named():
    out = _sanitise({"a": {"b": {"c": float("nan")}}})
    assert out["a"]["b"]["c"] is None
    assert "a.b.c" in out["_nonfinite"]


def test_inside_lists():
    out = _sanitise({"xs": [1.0, float("nan"), 3.0]})
    assert out["xs"] == [1.0, None, 3.0]
    assert "xs[1]" in out["_nonfinite"]


def test_good_values_are_untouched():
    payload = {"i": 5, "f": 1.5, "s": "ok", "b": True, "n": None, "l": [1, 2]}
    out = _sanitise(dict(payload))
    for k, v in payload.items():
        assert out[k] == v
    assert "_nonfinite" not in out, "a clean payload gained a noise key"


def test_the_result_actually_serialises():
    """The whole point. A payload that cannot be encoded is a 500."""
    payload = {"a": float("nan"), "b": [float("inf"), {"c": float("-inf")}]}
    json.dumps(_sanitise(payload))          # must not raise


def test_nan_is_replaced_not_dropped():
    """A silently-omitted key makes a broken computation look like a missing
    feature — the absent-vs-real collapse this register keeps filing."""
    out = _sanitise({"pct": float("nan")})
    assert "pct" in out, "the key was dropped instead of nulled"
    assert out["pct"] is None


def test_clean_payload_is_not_rewritten_into_noise():
    out = _sanitise({"status": "healthy", "n": 3})
    assert out == {"status": "healthy", "n": 3}
