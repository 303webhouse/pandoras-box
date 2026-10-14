"""A killed run is RECORDED, and the export waits for the run — R-IV.997(b)/(c).

RUN 7 IS THE CASE. A deploy of mine cancelled it mid-walk and its row still read
`ended_at: null`, indistinguishable from a run still in progress. R-IV.997(b) gates the nightly
export on exactly that field, so the ambiguity had to go first -- and it genuinely blocked:
the gate, run live, refused to export because of run 7's stale null.

WHY `CancelledError` WAS INVISIBLE. It derives from BaseException, not Exception, so every
`except Exception` in the job was blind to it. That is not a style point: it is the reason a
killed run looked identical to a live one.

WHY THE IN-PROCESS WRITE IS NOT THE MECHANISM. A write issued while the task is being
cancelled may itself be cancelled. Startup reconciliation decides from durable state instead,
and is what actually guarantees the record.
"""
from __future__ import annotations

import ast
import inspect

from jobs import darkpool_backfill as dp


def _code_of(fn):
    """Source of `fn` with its docstring stripped by IDENTITY.

    Comparing text to `ast.get_docstring()` never matches -- that CLEANS indentation. These
    docstrings name `CancelledError` and `ended_at` while explaining them, so a substring
    scan of raw source would pass on prose alone.
    """
    tree = ast.parse(inspect.getsource(fn))
    f = tree.body[0]
    doc = f.body[0].value if f.body and isinstance(f.body[0], ast.Expr) else None
    body = [n for n in f.body if not (isinstance(n, ast.Expr) and n.value is doc)]
    return "\n".join(ast.unparse(n) for n in body)


# -- (c) the record -------------------------------------------------------------------

def test_the_stop_reason_is_named_not_spelled_at_each_site():
    assert dp.KILLED_BY_DEPLOY == "KILLED_BY_DEPLOY"


def test_reconciliation_closes_only_rows_whose_process_is_gone():
    sql = dp.RECONCILE_ORPHANED_RUNS_SQL
    assert "ended_at IS NULL" in sql, sql
    # It must EXCLUDE the current run, or a run would close its own row on startup.
    assert "id <> $1" in sql, sql
    # COALESCE, so a row that somehow already has a reason keeps it.
    assert "COALESCE(ended_at, NOW())" in sql, sql
    assert "COALESCE(stop_reason, $2)" in sql, sql


def test_run_catches_the_cancellation_that_exception_handlers_could_not_see():
    code = _code_of(dp.run)
    assert "asyncio.CancelledError" in code, (
        "run() still cannot see the cancellation a deploy sends")
    assert "_close_run_as_killed" in code
    # And it must RE-RAISE: swallowing a cancellation leaves the task half-dead.
    tree = ast.parse("async def f():\n" + "\n".join(
        "    " + l for l in code.splitlines()))
    handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)
                and isinstance(n.type, ast.Attribute) and n.type.attr == "CancelledError"]
    assert handlers, "no CancelledError handler found"
    assert any(isinstance(s, ast.Raise) for s in ast.walk(handlers[0])), (
        "the cancellation handler does not re-raise")


def test_reconciliation_runs_before_any_collecting():
    """Ordering matters: a null ended_at must stop meaning two things BEFORE the night's work
    is chosen, because the export gates on that field while the run is still going."""
    code = _code_of(dp.run)
    assert "reconcile_orphaned_runs" in code
    assert code.index("reconcile_orphaned_runs") < code.index("collect_one"), code[:200]


def test_the_best_effort_write_is_shielded_and_bounded():
    """It is best-effort by construction, so it must not be able to hang the teardown."""
    code = _code_of(dp._close_run_as_killed)
    assert "shield" in code, code
    assert "timeout" in code, code
    # It only stamps a row that is still open, so it can never overwrite a real ending.
    assert "ended_at IS NULL" in code, code


# -- (b) the gate ---------------------------------------------------------------------

def _gate_src():
    import os
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "scripts", "f_export_gate.py")
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def test_the_gate_distinguishes_its_three_failures():
    """One non-zero code would make "the drive is unplugged" look like "still running", and
    those want opposite responses: one is waiting, the other is a person plugging something in.
    """
    src = _gate_src()
    tree = ast.parse(src)
    # Tuple targets too: the gate declares all four on one line, and a collector that only
    # handled single names reported "the gate does not define EXIT_OK" about a gate that does.
    names = set()
    for n in tree.body:
        if not isinstance(n, ast.Assign):
            continue
        for t in n.targets:
            for leaf in ast.walk(t):
                if isinstance(leaf, ast.Name):
                    names.add(leaf.id)
    for n in ("EXIT_OK", "EXIT_RUN_IN_PROGRESS", "EXIT_F_NOT_MOUNTED", "EXIT_GATE_ERROR"):
        assert n in names, "the gate does not define %s" % n
    assert "RUN_IN_PROGRESS" in src and "F_NOT_MOUNTED" in src


def test_a_gate_that_cannot_check_does_NOT_report_clear():
    """"I could not check" must never read as "nothing is running" -- the fake-healthy
    reading this register keeps finding."""
    src = _gate_src()
    assert "EXIT_GATE_ERROR" in src
    assert "GATE_ERROR, EXIT_OK" not in src
    # The DB-failure branch must return GATE_ERROR, not OK.
    i = src.index("could not read the run ledger")
    assert "EXIT_GATE_ERROR" in src[i:i + 400], src[i:i + 400]


def test_both_scripts_treat_a_superseded_null_run_as_orphaned_not_active():
    """Without this the pair DEADLOCKS: run 7's stale null blocks the very deploy that ships
    the reconciliation which clears it. Found by running the guard, not by reading it."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for name in ("f_export_gate.py", "deploy_guard.py"):
        with open(os.path.join(root, "scripts", name), encoding="utf-8") as fh:
            s = fh.read()
        assert "l.id > r.id" in s, "%s has no orphan discriminator" % name
        assert "l.ended_at IS NOT NULL" in s, name
