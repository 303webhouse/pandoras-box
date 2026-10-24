"""R-IV.1408(b)5 — the bars export de-coupled, and the R-IV.1378(c) hold guard.

TWO THINGS ARE PINNED HERE, and the second one is the reason the first could ship tonight.

  THE DE-COUPLING. `export_bars1m()` ran inside `f_export.py`, which only runs when
  `f_export_gate.py` opens, and that gate's identity is `(latest_ended_run_id,
  eligible_count)` from the DARK-POOL backfill tables. So the yfinance bars were gated on a
  dark-pool run counter. On 2026-10-23 the counter had not moved, the gate printed
  ALREADY_DONE and exited 0 on all seven ticks, and session 10-23 was never written.

  THE HOLD. `export_bars1m()`'s window is `today - 29 days`, which on 2026-10-24 is
  2026-09-25 -- the first day of R-IV.1378(c)'s held range -- so every run rewrites
  09-25..10-15, and will until 2026-11-13. The dark-pool gate being shut had been accidentally
  protecting that hold; enabling `darkpool_forward` under R-IV.1408(b)1 moves the counter,
  opens the gate, and the full export would have rewritten the held window on its first run.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from datetime import date, datetime, timedelta

import pytest

from jobs import job_runs

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)
BARS_JOB = os.path.join(REPO, "scripts", "f_export_bars.py")
F_EXPORT = os.path.join(REPO, "scripts", "f_export.py")


def _src(path):
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _f_export():
    spec = importlib.util.spec_from_file_location("_f_export_under_test", F_EXPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bars_job():
    spec = importlib.util.spec_from_file_location("_f_export_bars_under_test", BARS_JOB)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. the hold guard ───────────────────────────────────────────────────────

@pytest.mark.parametrize("d,held", [
    ("2026-09-24", False),   # the day before
    ("2026-09-25", True),    # the ruling's first named day -- INCLUSIVE
    ("2026-10-01", True),
    ("2026-10-15", True),    # the ruling's last named day -- INCLUSIVE
    ("2026-10-16", False),
    ("2026-10-23", False),   # the session SPINE asked about: writable
])
def test_the_held_range_is_INCLUSIVE_at_both_ends(d, held):
    """R-IV.1378(c) names "09-25 to 10-15". A half-open reading would leave 10-15 writable --
    and this register already has one withdrawn finding from reading a ruling's date range as
    half-open when it was not."""
    assert _f_export().session_is_held(date.fromisoformat(d)) is held


def test_the_export_window_REALLY_DOES_overlap_the_held_range():
    """THE PREMISE, asserted rather than asserted-about. If the window did not reach back into
    the hold, the guard would be dead code and this whole precaution pointless -- so the
    arithmetic that makes it necessary is checked here."""
    today = date(2026, 10, 24)
    start = today - timedelta(days=29)
    assert start == date(2026, 9, 25)
    m = _f_export()
    assert m.R1378C_HELD_FROM <= start <= m.R1378C_HELD_TO, (
        "the 29-day window no longer reaches the held range: if that is because the hold was "
        "lifted, R1378C_HOLD_ACTIVE should be False rather than the range being stale")
    # And it stops overlapping on a date that can be computed, so nobody has to guess when the
    # guard stops mattering.
    assert m.R1378C_HELD_TO + timedelta(days=29) == date(2026, 11, 13)


def test_the_flag_and_the_dates_MOVE_TOGETHER():
    """A flag cleared while the range stayed, or a range emptied while the flag stood, would
    each read as "the hold is honoured" while doing the opposite."""
    m = _f_export()
    if m.R1378C_HOLD_ACTIVE:
        assert m.R1378C_HELD_FROM == date(2026, 9, 25)
        assert m.R1378C_HELD_TO == date(2026, 10, 15)
        assert m.R1378C_HELD_FROM <= m.R1378C_HELD_TO
    else:
        # The hold is lifted. Then nothing may be held, whatever the dates say.
        for d in ("2026-09-25", "2026-10-01", "2026-10-15"):
            assert m.session_is_held(date.fromisoformat(d)) is False


def test_the_guard_sits_at_the_ONE_write_site_so_it_protects_the_FULL_export_too():
    """The guard is in `f_export.py` beside `write_parquet`, not in the new job. That matters
    because enabling `darkpool_forward` opens the dark-pool gate, and the FULL export would
    then rewrite the held window on its first run -- the gate having been shut was the only
    thing preventing it."""
    src = _src(F_EXPORT)
    i = src.index("def export_bars1m")
    j = src.index("def export_bars1d")
    body = src[i:j]
    assert "session_is_held" in body, "the guard is not inside export_bars1m"
    k = body.index("session_is_held")
    w = body.index("write_parquet", k)
    between = body[k:w]
    assert "continue" in between, (
        "the held check does not SKIP the write: it must `continue` before write_parquet, or "
        "the file is rewritten anyway")


def test_what_the_export_WRITES_is_unchanged():
    """R-IV.1408(b)5: do not change paths, format or window -- TRITON-R and R2 both read these
    files. So the path template, the 29-day window and the parquet writer all stay."""
    src = _src(F_EXPORT)
    assert 'os.path.join(ROOT, "bars1m", d.isoformat(), "%s.parquet" % ticker)' in src
    assert "timedelta(days=29)" in src
    assert 'interval="1m"' in src and "prepost=True" in src
    assert 'all_df["source"] = "yfinance"' in src


def test_a_held_session_is_REPORTED_not_silent():
    """A run that wrote 9 of 30 sessions and said only "9" is indistinguishable from a vendor
    that returned a third of the data."""
    src = _src(F_EXPORT)
    assert "HELD by R-IV.1378(c)" in src
    assert "sessions_held" in src


# ── 2. the de-coupling ──────────────────────────────────────────────────────

def test_the_bars_job_does_NOT_read_the_dark_pool_gate_or_its_tables():
    """THE WHOLE POINT. Any of these names appearing in executable code means the bars are
    still gated on something that has nothing to do with them."""
    tree = ast.parse(_src(BARS_JOB))
    # Strip docstrings by identity -- this file's own prose names every one of these tables to
    # explain why it does not touch them, and a raw-text scan would fail on the explanation.
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            docs.add(id(body[0]))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            node.body = [n for n in body if id(n) not in docs] or [ast.Pass()]
    code = ast.unparse(tree)

    for forbidden in ("darkpool_backfill_runs", "darkpool_backfill_sessions",
                      "darkpool_backfill_pages", "latest_ended", "f_export_last_run",
                      "_last_exported", "eligible"):
        assert forbidden not in code, (
            "the de-coupled bars job references %r: it is still coupled to the dark-pool "
            "gate, which is the fault R-IV.1408(b)5 removes" % forbidden)
    # And SM7's collector, untouched as always (R-IV.912(c)2).
    assert "darkpool_collector" not in code
    assert "darkpool_pages" not in code


def test_it_calls_the_exports_and_nothing_else_that_writes():
    code = _src(BARS_JOB)
    assert "export_bars1m()" in code and "export_bars1d()" in code
    assert "write_manifest" not in code, (
        "the manifest is f_export.py's to author: writing it from here would mean reading the "
        "dark-pool completeness map to avoid dropping a section of it, which is the exact "
        "coupling this job removes")
    assert "export_darkpool" not in code and "export_option_quotes" not in code


def test_every_exit_writes_a_job_runs_row():
    """"ran and wrote nothing", "never fired" and "failed" must stop being the same thing seen
    from outside -- which for this job they have been since it was written."""
    tree = ast.parse(_src(BARS_JOB))
    main = next(n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "main")
    found = []

    def walk(stmts):
        seen = False
        for st in stmts:
            if (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call)
                    and getattr(st.value.func, "id", None) == "_record"):
                seen = True
            if isinstance(st, ast.Return):
                found.append((st.lineno, seen))
            for attr in ("body", "orelse", "finalbody"):
                inner = getattr(st, attr, None)
                if isinstance(inner, list) and inner:
                    walk(inner)
            if isinstance(st, ast.Try):
                for h in st.handlers:
                    walk(h.body)

    walk(main.body)
    assert len(found) >= 5, found
    unrecorded = [ln for ln, ok in found if not ok]
    assert not unrecorded, (
        "these `return` lines leave no job_runs row, so the run they end is indistinguishable "
        "from one that never fired: %r" % unrecorded)


def test_ZERO_files_written_is_recorded_as_a_FAULT_not_a_success():
    """The original fault, one job along: `f_export_gate` exited 0 while exporting nothing, so
    every monitor saw green. Zero session files here is `completed_defective` -- the existing
    vocabulary for "the pass ran to the end and its own output check failed" (R-IV.426(b)),
    and no new label (R-IV.925(b))."""
    code = _src(BARS_JOB)
    i = code.index("if written == 0:")
    j = code.index("return", i)
    assert "STATUS_COMPLETED_DEFECTIVE" in code[i:j], code[i:j]


def test_no_status_LABEL_is_INVENTED():
    known = {job_runs.STATUS_RUNNING, job_runs.STATUS_OK, job_runs.STATUS_ERROR,
             job_runs.STATUS_TIMEOUT, job_runs.STATUS_SKIPPED,
             job_runs.STATUS_COMPLETED_DEFECTIVE, job_runs.STATUS_DEGRADED}
    mod = _bars_job()
    used = []
    for node in ast.walk(ast.parse(_src(BARS_JOB))):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_record"
                and node.args):
            a = node.args[0]
            assert isinstance(a, ast.Name), ast.dump(a)
            used.append(getattr(mod, a.id))
    assert used and set(used) <= known, set(used) - known


def test_the_job_name_literal_fallback_cannot_DRIFT():
    assert _bars_job().JOB_F_EXPORT_BARS == job_runs.JOB_F_EXPORT_BARS == "f_export_bars"
    src = _src(BARS_JOB)
    assert 'JOB_F_EXPORT_BARS = "f_export_bars"' in src
    assert "from jobs.job_runs import" in src


def test_it_has_its_OWN_job_name_not_the_gates():
    """Sharing `f_export` would make the two runs unseparable in the record, which is the
    `flow_per_expiry` / `hermes_session_poll` fault the quota table records twice."""
    assert job_runs.JOB_F_EXPORT_BARS != job_runs.JOB_F_EXPORT


def test_the_recorder_never_prints_the_dsn():
    for node in ast.walk(ast.parse(_src(BARS_JOB))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("_say", "print"):
            assert "_pg_dsn" not in ast.dump(node), ast.unparse(node)


@pytest.mark.parametrize("hour,shift", [(19, 0), (23, 0), (0, -1), (5, -1), (6, 0)])
def test_a_nights_run_lands_on_ONE_session_date(hour, shift):
    """Same 06:00 boundary as the gate's, and for the same reason: a task that can fire either
    side of midnight must file both sides under one session."""
    got = _bars_job().session_date_for(datetime(2026, 10, 23, hour, 0).astimezone())
    assert got == date(2026, 10, 23) + timedelta(days=shift)


def test_the_scheduled_task_runs_BEFORE_the_dark_pool_window():
    """The whole de-coupling is undone if the bars task is scheduled to depend on the
    dark-pool run having happened. 18:45 MT is after the close and before the gate's 19:00."""
    cmd = _src(os.path.join("C:\\", "lane-state", "f_export_bars_nightly.cmd"))
    assert "f_export_bars.py" in cmd
    assert "/ST 18:45" in cmd
    assert "f_export_gate.py" not in cmd.replace("f_export_gate.py`", "")
