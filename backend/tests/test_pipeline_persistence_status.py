"""DEF-SIGNAL-PERSISTENCE-COLLAPSE -- cases 9 and 10.

A3 re-scoped the deployed ❌-probe onto CI, which makes THIS FILE the sole
verification anywhere that a failed persist is reported as a failure. Without it
the re-scope has no premise.

Two layers:
  * behavioural -- completion_status(), the pure mapping, driven through all three
    outcomes including a forced INSERT failure.
  * structural  -- AST assertions that the call site actually uses that mapping and
    that record_attempt() sits AFTER the try/except, so `issued` still increments
    when log_signal raises. Placing it inside the try would make the counter blind
    to the very defect it exists to catch.
"""
from __future__ import annotations

import ast
import pathlib
import sys

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from signals.pipeline import completion_status  # noqa: E402

PIPELINE = pathlib.Path(__file__).resolve().parents[1] / "signals" / "pipeline.py"


# --- CASE 9: forced INSERT failure -> failure, at ERROR ---------------------
def test_case9_forced_insert_failure_reports_failure_at_error():
    text, level = completion_status(False, RuntimeError("invalid input syntax for type json"))
    assert "FAILED" in text and "NOT persisted" in text
    assert "❌" in text, "failure must be visually distinct"
    assert level == "error", "a lost row must not be logged at info"
    assert "✅" not in text, "a failed persist must never render the success marker"


def test_case9b_the_exact_incident_exception_shape():
    """The real one: asyncpg rejecting a bare NaN token."""
    exc = ValueError('invalid input syntax for type json\nDETAIL:  Token "NaN" is invalid.')
    text, level = completion_status(False, exc)
    assert level == "error" and "FAILED" in text


# --- CASE 10: duplicate signal_id -> dedupe, distinct from failure ----------
def test_case10_dedupe_is_distinct_from_failure():
    text, level = completion_status(False, None)
    assert "DEDUPE" in text
    assert "FAILED" not in text, "a dedupe is a correct no-op, not data loss"
    assert level == "warning", "dedupe is neither success nor failure"


def test_case10b_three_states_are_mutually_distinguishable():
    ok = completion_status(True, None)
    dedupe = completion_status(False, None)
    fail = completion_status(False, RuntimeError("boom"))
    assert len({ok, dedupe, fail}) == 3, "states must not collapse into each other"
    assert {ok[1], dedupe[1], fail[1]} == {"info", "warning", "error"}


# --- success path: ✅ only when a row actually landed -----------------------
def test_success_marker_requires_persisted_true():
    text, level = completion_status(True, None)
    assert "✅" in text and level == "info"
    for persisted, err in ((False, None), (False, RuntimeError("x"))):
        t, _ = completion_status(persisted, err)
        assert "✅" not in t, "success marker leaked onto a non-landed row"


# --- structural: the wiring, not a copy of it ------------------------------
def _pipeline_tree() -> ast.Module:
    return ast.parse(PIPELINE.read_text(encoding="utf-8"))


def test_call_site_uses_the_mapping():
    src = PIPELINE.read_text(encoding="utf-8")
    assert "completion_status(persisted, persist_error)" in src, \
        "completion log must derive from the persistence outcome"


def test_log_signal_return_value_is_captured():
    src = PIPELINE.read_text(encoding="utf-8")
    assert "persisted = bool(await log_signal(signal_data))" in src, \
        "log_signal's boolean must be captured, not discarded"


def test_record_attempt_is_outside_the_try():
    """issued must increment even when log_signal raises."""
    tree = _pipeline_tree()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
        if "log_signal" not in body:
            continue
        assert "record_attempt" not in body, (
            "record_attempt sits inside the try that wraps log_signal -- a raising "
            "INSERT would skip it, leaving issued un-incremented and the gap blind "
            "to the exact defect it exists to detect")
        return
    raise AssertionError("no try block wrapping log_signal found")
