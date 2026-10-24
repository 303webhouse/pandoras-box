"""R-IV.1398(b)4 / R-IV.1403(d) — the F: export gate records every tick.

THE FAULT THIS ANSWERS, measured on 2026-10-23: the gate fired six times on schedule, printed
`ALREADY_DONE: the archive is current for run 19`, and exited 0 each time. Any monitor reading
exit codes saw six clean runs. The bars for that session were never written -- `export_bars1m`
lives inside `f_export.py`, behind this gate, so the yfinance bars are gated on a DARK-POOL run
counter that had not moved.

"Ran and did nothing" was indistinguishable from "exported successfully", and from outside the
log it still would be. The tests here pin the three properties that make it distinguishable:

  1. EVERY exit records. An exit added later without a record is the fault coming back.
  2. The record uses the EXISTING status vocabulary (R-IV.925(b): do not invent labels).
  3. The record cannot break the gate, and the gate's DECISIONS are unchanged -- which matters
     because R-IV.1378(c) forbids rewriting anything on F: covering 09-25 to 10-15, and a gate
     that opened one tick earlier than before could do exactly that.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from datetime import datetime

import pytest

from jobs import job_runs

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)
GATE_FILE = os.path.join(REPO, "scripts", "f_export_gate.py")


def _tree():
    with open(GATE_FILE, encoding="utf-8-sig") as fh:
        return ast.parse(fh.read())


def _main_fn():
    for node in _tree().body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("main() not found in %s" % GATE_FILE)


def _gate_module():
    spec = importlib.util.spec_from_file_location("_f_export_gate_under_test", GATE_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. every exit records ───────────────────────────────────────────────────

def _returns_with_preceding_record(fn):
    """[(lineno, recorded?)] for every `return` in fn, scanning its own statement list.

    Structural rather than textual: a new exit added inside a new `if` is found, and a record
    that sits in a DIFFERENT branch does not count for it. That is the whole point -- the
    failure mode is an exit path added later whose author did not know about the record.
    """
    out = []

    def walk(stmts):
        seen_record = False
        for st in stmts:
            if (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call)
                    and getattr(st.value.func, "id", None) == "_record_job_run"):
                seen_record = True
            if isinstance(st, ast.Return):
                out.append((st.lineno, seen_record))
            for attr in ("body", "orelse", "finalbody"):
                inner = getattr(st, attr, None)
                if isinstance(inner, list) and inner:
                    walk(inner)
            if isinstance(st, ast.Try):
                for h in st.handlers:
                    walk(h.body)
        return out

    walk(fn.body)
    return out


def test_EVERY_exit_from_the_gate_writes_a_record():
    rets = _returns_with_preceding_record(_main_fn())
    assert len(rets) >= 7, "fewer exits than the gate has verdicts: %r" % (rets,)
    unrecorded = [ln for ln, ok in rets if not ok]
    assert not unrecorded, (
        "these `return` lines in f_export_gate.main() leave no job_runs row, so the tick they "
        "end is indistinguishable from a tick that never fired: %r" % unrecorded)


def test_the_gates_DECISION_ORDER_is_unchanged_by_this_build():
    """The record is observability only. If the sequence of exits moved, the gate might open
    on a tick it used to refuse -- and R-IV.1378(c) forbids rewriting 09-25..10-15 on F:.

    Pinned as the ORDERED list of what each exit returns, which changes if a condition is
    added, removed or reordered.
    """
    found = []
    for node in ast.walk(_main_fn()):
        if isinstance(node, ast.Return) and node.value is not None:
            if isinstance(node.value, ast.Name):
                found.append((node.lineno, node.value.id))
            elif isinstance(node.value, ast.Attribute):
                found.append((node.lineno, node.value.attr))
    # SORTED BY LINE. `ast.walk` is breadth-first, so it yields the deepest exit first and
    # "the order of the exits" read as the order of the TREE, not of the file -- which would
    # have made this test pass or fail on nesting rather than on sequence.
    names = [n for _ln, n in sorted(found)]
    assert names == [
        "EXIT_F_NOT_MOUNTED",     # F: absent
        "EXIT_F_NOT_MOUNTED",     # F: mounted, archive root absent
        "EXIT_GATE_ERROR",        # the run ledger could not be read
        "EXIT_RUN_IN_PROGRESS",   # a run has no ended_at
        "EXIT_GATE_ERROR",        # no completed run exists at all
        "EXIT_OK",                # ALREADY_DONE
        "EXIT_OK",                # EXPORTED and matched
        "returncode",             # EXPORTED, match disagreed
    ], names


# ── 2. the vocabulary ───────────────────────────────────────────────────────

def test_no_status_LABEL_is_INVENTED():
    """R-IV.925(b). Every status the gate records must already exist in jobs/job_runs.py --
    a row whose status nothing recognises is a row nothing queries."""
    known = {job_runs.STATUS_RUNNING, job_runs.STATUS_OK, job_runs.STATUS_ERROR,
             job_runs.STATUS_TIMEOUT, job_runs.STATUS_SKIPPED,
             job_runs.STATUS_COMPLETED_DEFECTIVE, job_runs.STATUS_DEGRADED}
    mod = _gate_module()
    used = []
    for node in ast.walk(_tree()):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "_record_job_run"
                and node.args):
            a = node.args[0]
            assert isinstance(a, ast.Name), (
                "the status must be a named constant, not a literal: %s" % ast.dump(a))
            used.append(getattr(mod, a.id))
    assert used, "no _record_job_run call passes a status"
    assert set(used) <= known, set(used) - known


def test_the_job_name_literal_fallback_cannot_DRIFT_from_the_constant():
    """The gate falls back to a literal if the import fails, because a scheduled task on
    Nick's machine must not stop exporting over an import error. A fallback to a DIFFERENT
    name would write rows nobody queries -- the same blindness, one level up."""
    assert _gate_module().JOB_F_EXPORT == job_runs.JOB_F_EXPORT == "f_export"
    src = open(GATE_FILE, encoding="utf-8-sig").read()
    assert 'JOB_F_EXPORT = "f_export"' in src, "the literal fallback is not the constant"
    assert "from jobs.job_runs import" in src, "the constant is not imported at all"


def test_the_three_states_the_ruling_NAMES_are_each_reachable():
    """"ran and did nothing", "late" and "failed" -- the first and third as statuses, the
    second as the ABSENCE of a row, which is why every tick must write one."""
    mod = _gate_module()
    assert mod.STATUS_SKIPPED == "skipped"
    assert mod.STATUS_ERROR == "error"
    assert mod.STATUS_OK == "ok"
    assert mod.STATUS_COMPLETED_DEFECTIVE == "completed_defective"

    src = open(GATE_FILE, encoding="utf-8-sig").read()
    # ALREADY_DONE -- the state that was invisible -- must carry its verdict in skip_reason,
    # because `skipped` alone cannot tell it from RUN_IN_PROGRESS or an unplugged drive.
    i = src.index("ALREADY_DONE: archive current for run")
    j = src.rindex("_record_job_run", 0, i)
    assert "skip_reason" in src[j:i + 60]
    assert "STATUS_SKIPPED" in src[j:i]


# ── 3. the recorder cannot break the gate ───────────────────────────────────

def test_the_recorder_swallows_everything_and_returns_None():
    """Bookkeeping must not break the job it records. Forced to fail by pointing the DSN
    reader at an exception -- the failure path a dead .mcp.json or a down database takes."""
    mod = _gate_module()
    said = []
    real_dsn, real_say = mod._pg_dsn, mod._say

    def _boom():
        raise RuntimeError("no dsn")

    mod._pg_dsn = _boom
    mod._say = lambda m: said.append(m)
    try:
        assert mod._record_job_run(mod.STATUS_SKIPPED, skip_reason="x") is None
    finally:
        mod._pg_dsn, mod._say = real_dsn, real_say
    assert any("job_runs record FAILED" in m for m in said), said
    assert not any("no dsn" in m for m in said), (
        "the exception's own text reached the log; only its TYPE should", said)


def test_the_recorder_never_prints_the_dsn():
    """`_pg_dsn` reads the write URL out of the gitignored .mcp.json. It must not reach a log
    line, an error message or a job_runs column."""
    src = open(GATE_FILE, encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("_say", "print"):
            dumped = ast.dump(node)
            assert "_pg_dsn" not in dumped, ast.unparse(node)


# ── 4. the session a tick belongs to ────────────────────────────────────────

@pytest.mark.parametrize("hour,expect_shift", [
    (19, 0),      # the first tick of the night
    (21, 0),
    (23, 0),
    (0, -1),      # past midnight: still LAST night's session
    (1, -1),
    (5, -1),      # the last tick of the night
    (6, 0),       # the boundary, chosen to sit inside the 05:00-19:00 gap
    (12, 0),
])
def test_a_nights_ticks_all_land_on_ONE_session_date(hour, expect_shift):
    """The scheduler fires 19:00 to 05:00 MT, so a night straddles midnight. `date.today()`
    would file the 01:00 tick under tomorrow, splitting one night across two session dates --
    and "no row for this session" would then fire every night at midnight, which is the
    false alarm that gets a surface ignored."""
    mod = _gate_module()
    from datetime import date, timedelta
    got = mod.session_date_for(datetime(2026, 10, 23, hour, 0).astimezone())
    assert got == date(2026, 10, 23) + timedelta(days=expect_shift), got


def test_the_boundary_is_not_midnight():
    """Stated as a property rather than left to the parametrised cases: the boundary has to be
    strictly inside the 05:00-19:00 gap, so a tick a few minutes late cannot cross it."""
    mod = _gate_module()
    from datetime import date
    assert mod.session_date_for(datetime(2026, 10, 24, 5, 59).astimezone()) == date(2026, 10, 23)
    assert mod.session_date_for(datetime(2026, 10, 24, 6, 0).astimezone()) == date(2026, 10, 24)
