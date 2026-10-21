"""The seed and the nightly built DIFFERENT INPUTS for the same classifier. R-IV.1284(c).

FOUND WHILE WIRING v2.1's CUTOVER, which is what R-IV.1284(c) asks for: "it inherits v2's last
shown label and hysteresis state ... nightly from there." Inheriting a state means the thing
that continues it must compute the way the thing that produced it did. These did not.

    the seed     sessions_from_series(..., vix_by_date=vix, v2=True)
    the nightly  sessions_from_series(..., settled_through=...)       <- v2 defaults to False
    measured     95 OF 304 SESSIONS take a different label depending on which build ran

For 2026-10-19 and 10-20 they disagree outright: the nightly's build says
`correction / correction`, the seed's `range_chop / correction`. So the 302 seeded rows and
every nightly row written after them were produced by one classifier reading two different
input sets -- two instruments measuring one thing, and here the disagreement reached the label
on the screen.

AND `== "v2"` WOULD HAVE BROKEN THE CUTOVER SILENTLY. Both the seed's VIX gate and its session
build tested the version with a literal `== "v2"`, which is False for `"v2.1"` -- so tagging the
rules file v2.1 would have stopped building the v2 inputs and stopped reading the VIX pair,
with nothing to say so. That is the same shape as the bug it sits next to.

ONE BUILDER, THREE CALLERS now: the seed, the nightly and the evening repair script.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from jobs import regime_job as rj                                   # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

JOB = _BACKEND / "jobs" / "regime_job.py"
REPAIR = _BACKEND.parent / "scripts" / "regime_bars_repair.py"


# ── the version test ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("version,expected", [
    ("v2", True), ("v2.1", True),
    ("v1", False), ("v3", False), ("", False), (None, False),
])
def test_which_versions_build_the_v2_inputs(version, expected):
    assert rj.uses_v2_inputs(version) is expected


def test_v21_builds_them_which_a_literal_comparison_would_not_have():
    """The cutover's silent failure, as arithmetic."""
    assert ("v2.1" == "v2") is False
    assert rj.uses_v2_inputs("v2.1") is True


def test_it_is_a_set_so_a_new_version_has_to_opt_in():
    """A `startswith("v2")` would have swept in a future v2.9 nobody had reviewed."""
    assert rj.V2_INPUT_VERSIONS == frozenset({"v2", "v2.1"})
    assert rj.uses_v2_inputs("v2.9") is False


def test_no_literal_version_comparison_survives_in_the_build_path():
    """Read from the PARSED tree, so the comments that quote the old comparison -- this file's
    docstring does, and so does the module's -- cannot satisfy or trip it."""
    tree = ast.parse(read_source(str(JOB)))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not isinstance(node.ops[0], ast.Eq):
            continue
        for comp in node.comparators:
            if isinstance(comp, ast.Constant) and comp.value == "v2":
                bad.append(ast.dump(node)[:120])
    assert not bad, bad


# ── one builder, three callers ───────────────────────────────────────────────

def test_the_builder_exists_and_passes_both_arguments():
    src = read_source(str(JOB))
    i = src.index("async def build_sessions")
    block = src[i:src.index("#: TA-208", i)]
    assert "vix_by_date=vix_by_date" in block
    assert "v2=uses_v2_inputs(version)" in block


def test_the_nightly_uses_it():
    tree = ast.parse(read_source(str(JOB)))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_nightly")
    calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)]
    assert any(getattr(c.func, "id", "") == "build_sessions" for c in calls), (
        "the nightly must build its sessions the way the seed does")
    assert not any(getattr(c.func, "id", "") == "sessions_from_series" for c in calls), (
        "a direct call here is what defaulted v2 to False")


def test_the_seed_uses_the_shared_version_test():
    src = read_source(str(JOB))
    i = src.index("async def run_seed")
    block = src[i:i + 7000]
    assert "uses_v2_inputs(rules.get(\"version\"))" in block
    assert "v2=uses_v2_inputs" in block


def test_the_repair_script_uses_it_too():
    """It is the third writer, authorised by R-IV.1284(b) while builds are paused, and its first
    version called `sessions_from_series` directly -- which is how the two rows it wrote for
    10-19 and 10-20 came to be on the nightly's basis."""
    src = read_source(str(REPAIR))
    assert "build_sessions" in src
    tree = ast.parse(src)
    assert not [c for c in ast.walk(tree) if isinstance(c, ast.Call)
                and getattr(c.func, "id", "") == "sessions_from_series"]


def test_the_builder_reports_the_basis_rather_than_leaving_it_implicit():
    """Whether the v2 inputs were built, and how many VIX dates paired, decide which rows are
    evaluable. A label whose basis is not recorded is one a later reader has to assume about."""
    src = read_source(str(JOB))
    i = src.index("async def build_sessions")
    block = src[i:src.index("#: TA-208", i)]
    assert '"v2_inputs": uses_v2_inputs(version)' in block
    assert '"vix": vix_report' in block


def test_the_nightlys_audit_row_carries_the_basis():
    src = read_source(str(JOB))
    assert "[v2_inputs=%s vix=%s]" in src
    assert "THE BASIS GOES ON THE RECORD WITH THE LABEL" in src


def test_the_seeds_audit_row_cannot_disagree_with_its_own_run():
    """It printed "v2 inputs: %s" from a literal `== "v2"` beside a build that used the helper.
    An audit row that disagrees with the run it describes is worse than none."""
    src = read_source(str(JOB))
    i = src.index('action="sessions_built"')
    block = src[i - 200:i + 800]
    assert "uses_v2_inputs(rules.get(\"version\"))" in block


# ── the absent VIX is reported, never substituted ───────────────────────────

def test_a_vix_read_that_fails_is_recorded_as_an_error_not_an_empty_pair():
    """FRED was in SITE MAINTENANCE on 2026-10-21 and answered HTTP 200 with an HTML page, so
    `fredapi` raised a ParseError. A 200 that is not data is the worst shape of outage, and the
    only defence is that the caller records what happened instead of carrying on with {}."""
    src = read_source(str(JOB))
    i = src.index("async def build_sessions")
    block = src[i:src.index("#: TA-208", i)]
    assert 'except Exception as exc:' in block
    assert '{"error": type(exc).__name__}' in block


def test_the_skip_reason_names_the_version_rather_than_saying_v1():
    """It said `{"skipped": "v1"}` on every non-v2 version, which would have read as "this is
    v1" on a v3 run."""
    src = read_source(str(JOB))
    assert 'does not read the VIX pair' in src
    assert '{"skipped": "v1"}' not in src
