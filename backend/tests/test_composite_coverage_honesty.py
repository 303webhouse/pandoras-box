"""R-IV.99 item 2 — factor-render coverage honesty.

The composite renormalises over whatever factors survived staleness:

    active_weight_sum = sum(FACTOR_CONFIG[f]["weight"] for f in active)
    normalized_weights = {f: FACTOR_CONFIG[f]["weight"] / active_weight_sum ...}
    raw_score = sum(active[f].score * normalized_weights[f] for f in active)

so a score built on 3 of 20 factors renders numerically identical to one built on
all 20. `active_weight_sum` IS the coverage fraction (weights sum to 1.00); it was
computed as a divisor and thrown away.

`confidence` cannot substitute for it: it is COUNT-based, so six active factors
report "HIGH" whether they carry 19% or 40% of the intended weight. That gap is
what test_coverage_discriminates_what_confidence_conflates pins.

FAIL-FIRST: every test here fails against pre-fix composite.py — the schema tests
because the fields do not exist, the structural tests because the compute path
never assigned them. See scratchpad/coverage_fails_pre_fix_proof.py.
"""
from __future__ import annotations

import ast
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from bias_engine.composite import FACTOR_CONFIG, CompositeResult  # noqa: E402

COMPOSITE = pathlib.Path(__file__).resolve().parents[1] / "bias_engine" / "composite.py"


def _result(**kw):
    base = dict(
        composite_score=50.0,
        bias_level="NEUTRAL",
        bias_numeric=0,
        factors={},
        active_factors=[],
        stale_factors=[],
        velocity_multiplier=1.0,
        timestamp=datetime.utcnow(),
        confidence="HIGH",
    )
    base.update(kw)
    return CompositeResult(**base)


# --- the premise the fix rests on --------------------------------------------
def test_weights_sum_to_one_so_active_sum_is_a_coverage_fraction():
    total = sum(c["weight"] for c in FACTOR_CONFIG.values())
    assert abs(total - 1.0) < 1e-6, (
        "coverage_ratio is only a fraction because the full weights sum to 1.00; "
        f"they sum to {total}")


# --- the defect, pinned -------------------------------------------------------
def test_coverage_discriminates_what_confidence_conflates():
    """Six factors is 'HIGH' confidence whether they carry 19% or 40% of the book."""
    w = sorted((c["weight"] for c in FACTOR_CONFIG.values()), reverse=True)
    heavy = round(sum(w[:6]), 4)
    light = round(sum(w[-6:]), 4)
    assert heavy > light, "expected a spread between heaviest and lightest six"

    a = _result(confidence="HIGH", coverage_ratio=heavy)
    b = _result(confidence="HIGH", coverage_ratio=light)

    assert a.confidence == b.confidence, "count-based confidence conflates these"
    assert a.coverage_ratio != b.coverage_ratio, "coverage must separate them"
    assert b.coverage_ratio < 0.5, (
        "a 'HIGH' confidence score can rest on under half the intended evidence — "
        "that is the fact the field exists to surface")


def test_coverage_absent_renders_none_never_zero():
    """GREEKS-ZERO precedent: an absent measurement must not render as a real 0.0.

    A cached pre-fix payload deserialises without the field; it must come back None
    so a consumer can tell 'unknown' from 'no factors active'.
    """
    assert _result().coverage_ratio is None
    assert _result(coverage_ratio=0.0).coverage_ratio == 0.0


def test_excluded_factors_field_exists_and_defaults_empty():
    assert _result().excluded_factors == []
    r = _result(excluded_factors=["gex", "vix_term"])
    assert r.excluded_factors == ["gex", "vix_term"]


# --- structural: the compute path actually populates them ---------------------
def _tree() -> ast.Module:
    return ast.parse(COMPOSITE.read_text(encoding="utf-8"))


def test_compute_path_assigns_coverage_from_active_weight_sum():
    src = COMPOSITE.read_text(encoding="utf-8")
    assert "coverage_ratio = round(active_weight_sum, 4)" in src, (
        "coverage_ratio must derive from active_weight_sum itself, not be "
        "recomputed — a second derivation can drift from the divisor actually used")


def test_result_construction_passes_both_fields():
    """Fields on the model that the constructor never sets are invisible in prod."""
    tree = _tree()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "CompositeResult"):
            continue
        kws = {k.arg for k in node.keywords}
        assert "coverage_ratio" in kws, "CompositeResult built without coverage_ratio"
        assert "excluded_factors" in kws, "CompositeResult built without excluded_factors"
        return
    raise AssertionError("no CompositeResult(...) construction found")


def test_excluded_is_complement_of_active_in_source():
    src = COMPOSITE.read_text(encoding="utf-8")
    assert "excluded_factors = [f for f in FACTOR_CONFIG if f not in active]" in src, (
        "excluded_factors must be the complement of `active` over FACTOR_CONFIG, so a "
        "factor that silently never reported is named rather than merely missing")
