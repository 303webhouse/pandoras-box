"""The crypto alarm measures the wrong thing — R-IV.617(b).

It judged the scanner on the AGE OF THE NEWEST SIGNAL. Crypto trades round the clock, so there
is no session to excuse a quiet hour — but a scanner correctly declining to signal in a saturated
regime is not a dead job.

MEASURED over 60 days of Crypto Scanner emissions: median gap between signals **0.51 h**, and yet
**eleven gaps past the 12 h SLO**, nine past 24 h, the longest **131.9 h**. Eleven false flatlines.

Diagnosed 2026-10-01: the job runs (its own log says `Crypto scan complete - 0 signals found`),
every one of the twelve tickers returns a clean payload, and all twelve sit in `MAX_LONG`, whose
recommendation is `HOLD_OR_WAIT_PULLBACK` — so no entry signal exists to emit.

So: two signals, and only one of them degrades.
"""

import ast
import io
import os

import pytest

from stable_engine.signals_freshness import (AGE_SOURCE_JOB_RUNS, AGE_SOURCES,
                                             DEFAULT_SLO_SECONDS, JOB_ALIVE_CLASSES,
                                             SLO_SECONDS, _job_alive_status)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLS = "crypto_scanner"
SLO = SLO_SECONDS.get(CLS, DEFAULT_SLO_SECONDS)


def _code(rel):
    """Live code only: docstrings and comments both removed, spacing preserved."""
    import tokenize

    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    lines = src.splitlines(keepends=True)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
            lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
    except (tokenize.TokenError, IndentationError):
        pass
    return "".join(lines)


# ─────────────────── it is judged on its run record, not on its output

class TestItIsJudgedOnBeingAlive:

    def test_the_class_is_declared_and_sourced_from_job_runs(self):
        assert CLS in JOB_ALIVE_CLASSES
        assert AGE_SOURCES[CLS] == AGE_SOURCE_JOB_RUNS

    def test_a_scan_that_ran_and_emitted_nothing_is_ok(self):
        """THE DEFECT. Zero emissions used to read as a flatline once the age passed the SLO.
        "Nothing qualified" and "nothing ran" are opposite facts."""
        status, note = _job_alive_status(CLS, 600, {
            "status": "ok", "rows_touched": 0,
            "skip_reason": "quiet: all assets in no-signal zones (MAX_LONG)"})
        assert status == "ok"
        assert "quiet: all assets in no-signal zones" in note
        assert "MAX_LONG" in note

    def test_a_scan_that_emitted_is_also_ok(self):
        status, note = _job_alive_status(CLS, 600, {
            "status": "ok", "rows_touched": 7, "skip_reason": None})
        assert status == "ok"
        assert not note

    def test_zero_emissions_never_degrade_however_old_the_last_signal_is(self):
        """The 131.9-hour drought: the job ran throughout. Age of SIGNAL is not consulted at
        all for this class — only age of RUN."""
        for emitted in (0, None):
            status, _ = _job_alive_status(CLS, 60, {
                "status": "ok", "rows_touched": emitted, "skip_reason": None})
            assert status == "ok", emitted


class TestWhatDoesDegrade:

    def test_an_errored_run(self):
        status, note = _job_alive_status(CLS, 600, {
            "status": "error", "rows_touched": 0, "error": "CTA Scanner unavailable"})
        assert status == "flatline"
        assert "errored" in note
        assert "CTA Scanner unavailable" in note

    def test_a_run_that_is_overdue_means_the_scheduler_is_not_firing(self):
        status, note = _job_alive_status(CLS, SLO + 1, {
            "status": "ok", "rows_touched": 3, "skip_reason": None})
        assert status == "flatline"
        assert "scheduler is not firing" in note

    def test_no_run_record_is_unknown_and_unknown_escalates(self):
        """Claiming health on an absent record is the fault this split exists to remove."""
        status, note = _job_alive_status(CLS, None, None)
        assert status == "no_data"
        assert "no run record" in note

    def test_just_inside_the_slo_is_still_ok(self):
        """POSITIVE CONTROL for the overdue test: the boundary is the SLO, not any age."""
        status, _ = _job_alive_status(CLS, SLO - 1, {"status": "ok", "rows_touched": 0})
        assert status == "ok"

    @pytest.mark.parametrize("ok_word", ["ok", "success", "completed", "skipped", "OK"])
    def test_the_statuses_that_count_as_finished(self, ok_word):
        status, _ = _job_alive_status(CLS, 60, {"status": ok_word, "rows_touched": 0})
        assert status == "ok", ok_word


# ─────────────────── the scan records that it ran

class TestTheScanRecordsItsRun:

    def test_it_opens_and_closes_a_job_runs_row(self):
        """It kept its state only in `_scheduler_status`, an in-memory dict lost on every
        restart and unreadable by the check — so the only thing /health could measure was the
        age of the newest signal."""
        code = _code("scheduler/bias_scheduler.py")
        assert 'start_run("crypto_scanner"' in code
        assert "_finish_crypto_run(_run_id, \"ok\"" in code
        assert "_finish_crypto_run(_run_id, \"error\"" in code

    def test_it_records_why_it_was_quiet(self):
        code = _code("scheduler/bias_scheduler.py")
        assert "quiet: all assets in no-signal zones" in code
        assert "_zones_seen" in code

    def test_the_emitted_count_goes_in_rows_touched(self):
        code = _code("scheduler/bias_scheduler.py")
        assert '_finish_crypto_run(_run_id, "ok", signals_found' in code

    def test_an_unavailable_scanner_closes_the_run_as_an_error(self):
        """It used to `return` silently, leaving an open run row that would later read as
        overdue — a real fault reported as the wrong one."""
        code = _code("scheduler/bias_scheduler.py")
        i = code.index("CTA Scanner not available for crypto scan")
        assert "_finish_crypto_run" in code[i:i + 400]

    def test_a_failure_to_record_never_fails_the_scan_but_is_never_silent(self):
        import inspect

        from scheduler import bias_scheduler
        src = inspect.getsource(bias_scheduler._finish_crypto_run)
        assert "except Exception" in src
        assert "logger.error" in src


# ─────────────────── the two signals are reported apart

def test_the_block_says_which_signal_moved_the_status():
    """So a reader never has to work out why a zero did not degrade anything."""
    code = _code("stable_engine/signals_freshness.py")
    assert '"judged_on"' in code
    assert "job alive (its own run record)" in code
    assert '"signals_emitted"' in code
    assert '"emitted_degrades"' in code


def test_only_the_crypto_scanner_is_split_for_now():
    """The change is narrow: every other class keeps the status it had."""
    assert JOB_ALIVE_CLASSES == frozenset({"crypto_scanner"})
