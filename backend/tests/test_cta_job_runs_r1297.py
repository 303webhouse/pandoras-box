"""The CTA scan records that it ran, and its cooldown reaches the counter. R-IV.1297(f)1 and (f)3.

THE FAULT THIS CLOSES, measured on 2026-10-21 rather than reasoned about. /health reported
`signals_freshness:flatline` for `cta_scanner` while the scanner was running perfectly: 19 scans
on its coded 15/30-minute cadence, 43 setups found, 36 suppressed by its own 24-hour per-ticker
cooldown, 7 persisted. The longest gap between PERSISTED signals was 4.59 h against a 4 h SLO,
and only six distinct ticker/setup pairs qualified all session -- ISRG re-detected 14 times and
ABT 13, each correctly collapsed to one emission.

Two separate blindnesses produced that:

  1. `cta_scanner` has no `AGE_SOURCES` entry, so it is judged on whether it EMITTED. Nothing
     recorded whether it RAN: `_scheduler_status["cta_scanner"]` is an in-memory dict, lost on
     every restart, and served by no route -- `/analytics/schema-status` exposes the price
     collector and the benchmark tracker but not this one.
  2. `deduped` -- the one field that could have said "the producer is working and its output is
     being held back" -- read 5 while 36 suppressions had happened, because the cooldown
     `continue` sits BEFORE `process_signal_unified`, which is where `record_attempt` is called.

THE ORDER OF THE FIX IS NOT OPTIONAL. R-IV.617(b), R-IV.800(b) and R-IV.1059(b) each moved a
conditional producer to `AGE_SOURCE_JOB_RUNS` and each insisted the producer be given its
`job_runs` write FIRST: re-pointing a class at a table nothing writes renders `no_data`, which
does NOT degrade, so /health goes green while the sentinel becomes incapable of firing -- and the
approval's own control ("/health clears") passes vacuously. This file is step 1. The last test
here asserts step 2 has NOT happened yet, and is meant to go red in the commit that does it.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from ._srcscan import read_source                                  # noqa: E402

SCHED = str(_BACKEND / "scheduler" / "bias_scheduler.py")
FRESH = str(_BACKEND / "stable_engine" / "signals_freshness.py")


def _cta_scan_block() -> str:
    """`run_cta_scan_scheduled`, bounded by the next top-level `async def`.

    STRUCTURAL rather than a character window: a fixed window missed its own handler earlier in
    this build, and a slice to a named comment broke when R-IV.1297(e) re-cited that comment.
    """
    src = read_source(SCHED)
    i = src.index("async def run_cta_scan_scheduled():")
    j = src.index("async def trigger_cta_scan_now", i)
    return src[i:j]


# ── (f)1 · one row per scan, closed on every exit ───────────────────────────

def test_the_scan_opens_a_job_runs_row_under_its_OWN_CLASS_NAME():
    """The name has to be exactly the freshness class, or step 2 will point at rows that do not
    exist and render `no_data` -- the silent-disarm failure the ruling's order exists to avoid."""
    block = _cta_scan_block()
    assert '_start_run("cta_scanner"' in block
    from stable_engine.signals_freshness import REGISTERED_CLASSES
    assert "cta_scanner" in REGISTERED_CLASSES


def test_EVERY_exit_from_the_scan_closes_the_row():
    """The property that makes the row trustworthy. A `return` that leaves the row `running`
    forever is worse than no row: the freshness check would read a run that never finished and
    could not tell that from one still in flight.

    Counted off the PARSED function, so a `return` inside a comment or a docstring cannot
    satisfy it and a new early return cannot be added without being noticed.
    """
    tree = ast.parse(_cta_scan_block())
    fn = tree.body[0]
    assert isinstance(fn, ast.AsyncFunctionDef) and fn.name == "run_cta_scan_scheduled"

    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    closers = [n for n in ast.walk(fn)
               if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_finish_cta_run"]
    # 3 early returns + the success fall-through + the except handler = 5 closers;
    # the 3 returns are each immediately preceded by one.
    assert len(returns) == 3, [n.lineno for n in returns]
    assert len(closers) == 5, [n.lineno for n in closers]
    handlers = [h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers]
    assert handlers, "the scan still has its guard"
    assert any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_finish_cta_run"
               for h in handlers for c in ast.walk(h)), "the except path must close the row too"


def test_a_scan_that_found_NOTHING_closes_as_OK_not_skipped():
    """THE ENTIRE POINT of judging the job rather than its output. If an empty scan recorded
    `skipped`, the new row would carry the same blindness the old signal-age check had: a quiet
    tape would still read as a job that did not do its work."""
    block = _cta_scan_block()
    i = block.index("no new signals found")
    nearby = block[i:i + 420]
    assert '_finish_cta_run(_run_id, "ok", 0)' in nearby, nearby[:200]
    assert "A SCAN THAT FOUND NOTHING IS A SUCCESSFUL SCAN" in nearby


@pytest.mark.parametrize("status,where", [
    ("skipped", "CTA_SCANNER_AVAILABLE is False"),
    ("error", 'error=str(result["error"])'),
])
def test_the_refusal_paths_record_WHY(status, where):
    """`skipped` and `error` are different facts and a reader of the row is entitled to both.
    A single `ok` on every exit would make the row useless for anything but liveness."""
    block = _cta_scan_block()
    assert where in block
    assert '"%s"' % status in block


def test_recording_the_run_can_never_fail_the_run():
    """A failure to write bookkeeping must not break the scan -- but it must not look like
    success either, which is why the closer logs at ERROR."""
    block = _cta_scan_block()
    i = block.index("_start_run(")
    assert "except Exception as _jr" in block[i - 400:i + 400]
    closer = read_source(SCHED)
    j = closer.index("async def _finish_cta_run")
    body = closer[j:closer.index("async def run_cta_scan_scheduled", j)]
    assert "if run_id is None:" in body and "return" in body
    assert "logger.error(" in body
    # FROM THE PARSED TREE. `"raise" not in body` fails on the docstring's own
    # "Never raises into the scan" -- the tenth time a negative substring scan has been
    # defeated by the prose explaining the thing it scans for.
    fn = ast.parse(body.rstrip()).body[0]
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Raise)], "it must swallow, not raise"


def test_it_is_a_SEPARATE_closer_from_the_crypto_one_and_says_why():
    """Not an oversight. Two four-line functions that cannot affect each other beat one that
    both scans depend on while one of them is being changed -- and the reason is written down
    so the next reader does not "tidy" it without knowing."""
    src = read_source(SCHED)
    assert "async def _finish_crypto_run" in src and "async def _finish_cta_run" in src
    j = src.index("async def _finish_cta_run")
    assert "deliberately not shared" in src[j:j + 900]


# ── (f)3 · the cooldown reaches the counter ─────────────────────────────────

def test_the_cooldown_path_records_an_ATTEMPT():
    block = _cta_scan_block()
    i = block.index("Skipping CTA signal for")
    nearby = block[i:i + 1400]
    assert 'record_attempt("cta_scanner", persisted=False)' in nearby
    assert "from stable_engine.signals_freshness import record_attempt" in nearby


def test_it_is_counted_as_DEDUPED_and_not_as_REJECTED():
    """`record_attempt(persisted=False, error=None)` is the deduped branch; passing an error
    would make every cooldown skip look like a write failure and `rejected` would climb into
    the thousands. Asserted against the writer, not assumed from the call."""
    src = read_source(FRESH)
    i = src.index("def record_attempt")
    body = src[i:src.index("def ", i + 10)]
    assert 'elif error is not None:' in body and 'c["rejected"] += 1' in body
    assert 'c["deduped"] += 1' in body


def test_the_counter_actually_moves(monkeypatch):
    """Behavioural, not a source scan: the call has to reach the right bucket. Measured as a
    DELTA, because the counters are process-wide and other tests in the same run also emit."""
    from stable_engine import signals_freshness as sf
    before = dict(sf._COUNTERS["cta_scanner"])
    sf.record_attempt("cta_scanner", persisted=False)
    after = dict(sf._COUNTERS["cta_scanner"])
    assert after["deduped"] == before["deduped"] + 1
    assert after["persisted"] == before["persisted"]
    assert after["rejected"] == before["rejected"]


def test_the_metrics_call_cannot_break_the_scan():
    """"metrics must never break the pipeline" is the writer's own rule, and this call site is
    inside the hot loop of a scan that pushes real signals."""
    block = _cta_scan_block()
    # BOUNDED BY THE COMMENT BLOCK, not by a character count. My first version used +/-260
    # characters and missed the phrase by a few lines -- the same window-locator fault that has
    # now failed five times in this build.
    i = block.index("R-IV.1297(f)3")
    j = block.index("                    continue", i)
    window = block[i:j]
    assert "try:" in window and "except Exception" in window
    assert "TELEMETRY ONLY" in window, "the call must say it changes no signal's fate"
    assert 'record_attempt("cta_scanner", persisted=False)' in window


def test_the_suppression_still_SUPPRESSES():
    """The telemetry must not have become a behaviour change. The `continue` has to survive,
    and it has to come after the counter so a skip is counted exactly once."""
    tree = ast.parse(_cta_scan_block())
    fn = tree.body[0]
    conts = [n for n in ast.walk(fn) if isinstance(n, ast.Continue)]
    assert conts, "the cooldown `continue` must still be there"
    block = _cta_scan_block()
    assert block.index('record_attempt("cta_scanner"') < block.index("                    continue")


# ── the order the earlier rulings require ──────────────────────────────────

def test_STEP_2_HAS_NOT_HAPPENED_YET_and_this_is_deliberate():
    """R-IV.1297(f)2 waits for step 1 to be LIVE, and Railway's builds are paused.

    THIS TEST IS MEANT TO GO RED in the commit that does step 2 -- that is what makes the flip
    deliberate rather than incidental, and it is the same device as
    `test_RULES_VERSION_IS_NOW_v21_BECAUSE_THIS_IS_THE_CUTOVER` (which has since fired and flipped). Until then it pins the ordering
    that R-IV.617(b), R-IV.800(b) and R-IV.1059(b) all insisted on: a class re-pointed at
    `job_runs` before anything writes the row renders `no_data`, which does not degrade, so the
    sentinel switches off while /health goes green.
    """
    from stable_engine.signals_freshness import AGE_SOURCE_JOB_RUNS, AGE_SOURCES, SLO_SECONDS
    assert "cta_scanner" not in AGE_SOURCES, (
        "if this is intentional, this is the step-2 commit: set the 60-minute RTH SLO "
        "R-IV.1297(f)2 specifies and update this test in the same commit")
    assert AGE_SOURCES.get("crypto_scanner") == AGE_SOURCE_JOB_RUNS, (
        "the precedent this ordering comes from must still be in place")
    assert SLO_SECONDS["cta_scanner"] == 4 * 3600, "the threshold is unchanged until step 2"


def test_the_live_verification_step_is_written_down():
    """(f)1 says "Deploy it and verify the rows appear." Railway's builds are paused, so the
    verification cannot run in this commit -- and an unrecorded owed step is one nobody does."""
    block = _cta_scan_block()
    assert "STEP 1 OF TWO" in block
    assert "verified live" in block
