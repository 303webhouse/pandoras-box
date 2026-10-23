"""The v2.1 cutover and the basis repair. R-IV.1288.

(b) THE CANONICAL BASIS IS THE SEED'S, and the two rows written under R-IV.1278(b)2 were on the
nightly's. Before rewriting them, (b)1 asked whether the VIX input changes either label.

    PROVED IMMATERIAL TWO WAYS, not sampled once:

    by construction  `vix.vix` / `vix.vix3m` are read by exactly ONE function, `_row_crash`.
                     That row needs `crash_families_required` = 3 of 5 families, and v2
                     populates 2 (structure and breadth; credit, vol and carry have no feed).
                     So crash_liquidation can never match, whatever the VIX does.
    by exhaustion    replaying with NO vix, with VIX 90 / VIX3M 20 (extreme backwardation) and
                     with VIX 12 / VIX3M 30 (extreme contango) gives identical labels on both
                     sessions. The control: with no vix the crash row is NOT EVALUABLE, with
                     the injection it IS -- so the injection genuinely reaches the row and the
                     test is not vacuous.

    before  2026-10-19 correction/correction  held 1    2026-10-20 correction/correction  held 2
    after   2026-10-19 range_chop/correction  held 4    2026-10-20 range_chop/correction  held 5

(c) THE CUTOVER INHERITS, AND VERIFIES RATHER THAN COPIES. Copying v2's counters across asserts
nothing -- it hands v2.1 a state it never computed, and a later divergence would be invisible
precisely because the numbers were copied. So v2.1 RECOMPUTES the anchor session from the same
stored series and the answers are compared; a mismatch REFUSES, which is registration §1 / R-IV.1277(b)'s own
instruction ("STOP and ask SPINE. Do not backfill").
"""
from __future__ import annotations

import ast
import io
import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from jobs import regime_job as rj                                   # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

JOB = _BACKEND / "jobs" / "regime_job.py"
SEED = _BACKEND / "jobs" / "regime_seed.py"
PG = _BACKEND / "database" / "postgres_client.py"
V21 = _BACKEND / "config" / "regime_rules.v2.1.json"
V2 = _BACKEND / "config" / "regime_rules.v2.json"


# ── (b)1 · the VIX is immaterial, by construction ───────────────────────────

def test_only_the_crash_row_reads_the_vix_inputs():
    """If a second row read them, "VIX is immaterial" would be a claim about this one case
    rather than about the classifier. Read from the PARSED tree so the docstrings that discuss
    VIX -- this module's does -- cannot satisfy it."""
    tree = ast.parse(read_source(str(_BACKEND / "models" / "regime_classifier.py")))
    readers = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.startswith("vix.")):
                readers.add(fn.name)
    assert readers == {"_row_crash"}, readers


def test_the_crash_row_needs_more_families_than_v2_can_populate():
    """3 of 5 required; v2 fills structure and breadth. Credit, vol and carry have no feed, so
    the row is unreachable -- which is what makes the VIX immaterial rather than merely
    unhelpful."""
    th = json.loads(io.open(V21, encoding="utf-8").read())["thresholds"]
    assert th["crash_families_required"] == 3
    assert th["crash_families_total"] == 5
    # The families v2 can populate, read off the BUILDER rather than from a list here -- and
    # not from a constant I guessed at: my first version of this line imported
    # `FAMILIES_WITH_A_FEED_IN_V1`, which exists nowhere. That is the fifth invented path of
    # this session's work, and the only reason it cost nothing is that an ImportError in a test
    # is loud where the same mistake in a handler is a silent 500.
    src = read_source(str(_BACKEND / "models" / "regime_inputs.py"))
    assert 'families["structure"]' in src
    assert 'families["breadth"]' in src
    for absent in ("credit", "vol", "carry"):
        assert 'families["%s"]' % absent not in src, absent


def test_the_crash_row_is_not_evaluable_without_a_vix_and_says_so():
    """"a crash check that never ran is not a crash check that passed" -- its own words."""
    src = read_source(str(_BACKEND / "models" / "regime_classifier.py"))
    i = src.index("def _row_crash")
    block = src[i:src.index("def _row_", i + 10)]
    assert "evaluable=False" in block
    assert "NOT read as 'not a crash'" in block


# ── (b)2 · the partial key, which is what let the correction be written ─────

def test_the_unique_key_is_partial_over_current_rows():
    """The unqualified index made the table's own supersession unusable for one
    (as_of, rules_version, close_source): a superseded row still occupied the key, so a
    corrected label could only be written by UPDATEing the row it corrected -- the one thing
    `_write_snapshot` exists not to do."""
    src = read_source(str(PG))
    assert "uq_regime_snapshots_current_asof_rules_source" in src
    i = src.index("uq_regime_snapshots_current_asof_rules_source")
    block = src[i:i + 300]
    assert "WHERE superseded = FALSE" in block
    assert "DROP INDEX IF EXISTS uq_regime_snapshots_asof_rules_source" in src


def test_the_conflict_target_matches_the_partial_index():
    """Postgres cannot infer a partial index from a bare `ON CONFLICT (cols)`; it raised
    `InvalidColumnReferenceError` the first time the index was made partial without this. The
    two must agree or every write fails."""
    src = read_source(str(SEED))
    assert "ON CONFLICT (as_of, rules_version, close_source) WHERE superseded = FALSE" in src


def test_the_invariant_the_partial_key_still_enforces_is_stated():
    src = read_source(str(PG))
    assert "AT MOST ONE CURRENT" in src.upper()


# ── (c) · the cutover ───────────────────────────────────────────────────────

def test_the_predecessor_is_declared_and_not_guessed():
    """"the previous version" is a judgement, and a wrong guess silently inherits the wrong
    hysteresis."""
    assert rj.CUTOVER_PREDECESSOR == {"v2.1": "v2"}


@pytest.mark.asyncio
async def test_a_version_with_rows_already_needs_no_cutover():
    class _Conn:
        async def fetchval(self, *a):
            return 304
    got = await rj.cutover_state(_Conn(), "v2")
    assert got["ok"] is True and got["inherited"] is False
    assert "no cutover needed" in got["reason"]


@pytest.mark.asyncio
async def test_an_undeclared_version_refuses_instead_of_guessing():
    class _Conn:
        async def fetchval(self, *a):
            return 0
    got = await rj.cutover_state(_Conn(), "v9")
    assert got["ok"] is False and got["needs_ruling"] is True
    assert "no predecessor is declared" in got["reason"]
    assert "forbids" in got["reason"]


@pytest.mark.asyncio
async def test_a_predecessor_with_no_settled_row_stops_and_asks():
    class _Conn:
        async def fetchval(self, *a):
            return 0

        async def fetchrow(self, *a):
            return None
    got = await rj.cutover_state(_Conn(), "v2.1")
    assert got["ok"] is False and got["needs_ruling"] is True
    assert "cannot start without" in got["reason"] and "registration §1 / R-IV.1277(b)" in got["reason"]


def test_the_inheritance_is_verified_rather_than_copied():
    """The whole design. Copying asserts nothing; recomputing and comparing CATCHES a
    divergence that a copy would hide."""
    src = read_source(str(JOB))
    i = src.index("async def cutover_state")
    block = src[i:src.index("async def unmatched_run", i)]
    assert "VERIFIED, NOT COPIED" in block
    assert "replay(" in block
    assert "diffs" in block and "needs_ruling=True" in block
    for field in ("shown_regime", "held_sessions", "pending", "pending_closes"):
        assert field in block, field


def test_a_disputed_state_refuses_and_names_what_differs():
    src = read_source(str(JOB))
    i = src.index("async def cutover_state")
    block = src[i:src.index("async def unmatched_run", i)]
    assert "STOPPING and asking" in block
    assert "stored=%r computed=%r" in block


def test_nothing_is_written_and_no_era_is_replayed_onto_disk():
    """registration §1 / R-IV.1277(b): "no replay or re-seed of any era: no backfill run of v2.1 over any date." The
    walk is in memory, which is what every nightly already does to rebuild its counters."""
    src = read_source(str(JOB))
    i = src.index("async def cutover_state")
    block = src[i:src.index("async def unmatched_run", i)]
    assert "NOTHING IS WRITTEN HERE" in block
    assert "_write_snapshot" not in block
    assert "INSERT" not in block.upper()


NL_ = chr(10)


def test_the_gate_runs_before_any_label_is_computed():
    """A run that cannot legitimately start must not write a label first and ask afterwards."""
    src = read_source(str(JOB))
    i = src.index("async def run_nightly")
    # BOUNDED BY THE FUNCTION, not by a character count. This read `src[i:i + 9000]`,
    # and R-IV.1357(a)2 made `run_nightly` longer, so `build_sessions` fell outside the
    # window and the test failed while the ORDER IT CHECKS still held. A fixed-width
    # window is a locator that breaks when its neighbours change.
    j = src.find(NL_ + "async def ", i + 10)
    block = src[i:j if j > 0 else len(src)]
    assert block.index("cutover_state(conn") < block.index("build_sessions(conn")
    assert "cutover_blocked" in block


def test_expecting_agreement_is_sound_because_NO_ARITHMETIC_DIFFERS():
    """The reason a mismatch is a REFUSAL rather than a surprise: there is nothing in v2.1 that
    could legitimately produce a different hysteresis state.

    RESTATED AS A PREDICATE (R-IV.1297(c)). This asserted "exactly two keys differ", and the
    stamped artifact differs in seven -- every one of them provenance. A count would have gone
    red while the property it protects was untouched, and the natural fix for a red count is to
    edit the number, which is how a guard quietly stops guarding. Measured on the stamped file:
    thresholds, order, confirmed_break, gating, families_v1, tags and every hysteresis RULE are
    identical, and `stated_cost` is now identical to v2's as well.
    """
    a = json.loads(io.open(V2, encoding="utf-8").read())
    b = json.loads(io.open(V21, encoding="utf-8").read())
    assert a["thresholds"] == b["thresholds"]
    assert list(a["order"]) == list(b["order"])
    assert a.get("confirmed_break") == b.get("confirmed_break")
    assert a.get("gating") == b.get("gating")
    assert a.get("families_v1") == b.get("families_v1")
    for k in a["hysteresis"]:
        if k != "stated_cost":
            assert a["hysteresis"][k] == b["hysteresis"][k], k


def test_v21_builds_the_v2_inputs_at_the_cutover():
    """If it did not, the state it recomputed would differ from v2's for the wrong reason and
    the gate would refuse a cutover that is actually fine."""
    assert rj.uses_v2_inputs("v2.1") is True
