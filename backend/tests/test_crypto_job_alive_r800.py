"""R-IV.800(b) — the three conditional crypto producers are judged on RUNNING, not on emitting.

THE DEFECT. `crypto_engine` tripped `flatline` on 2026-10-08 after 12.6 quiet hours with its
producing loop demonstrably alive: logs showed `Crypto scan complete - 1 signals found` and the
loop cycling on its 5-minute schedule. It emits a signal only when a funding/session/liquidation
setup fires, so judged on SIGNAL age a quiet regime is indistinguishable from a dead engine.

R-IV.617(b) HAD ALREADY DIAGNOSED AND FIXED THIS — for `crypto_scanner`, in this same dict, with
the measurement in its own comment: median gap between signals 0.5h, yet eleven gaps past the 12h
SLO and nine past 24h, the longest 131.9h, "eleven false flatlines". The other two classes that
needed the same treatment were left out.

THE ORDER MATTERED, AND GETTING IT WRONG WOULD HAVE BEEN WORSE THAN THE BUG. The declared age
source is the ONLY source -- `ages.pop(cls)` discards the signal age. With no `job_runs` row
these classes render `no_data`, and `no_data` does NOT degrade. Switching the mapping alone would
have turned /health green while the sentinel became incapable of ever firing, and R-IV.800(b)'s
own control ("/health clears signals_freshness for both") would have passed VACUOUSLY. Before the
switch, `grep start_run` returned exactly one crypto producer: `crypto_scanner`. So the producers
were made to record their runs first, which is also what R-IV.617(b) actually did.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from stable_engine import signals_freshness as sf  # noqa: E402

CONDITIONAL_CRYPTO = ("crypto_scanner", "crypto_engine", "crypto_cvd_engine")


class TestAllThreeAreJudgedOnTheRun:
    """The control R-IV.800(b) asks for: a quiet regime cannot read as dead."""

    @pytest.mark.parametrize("cls", CONDITIONAL_CRYPTO)
    def test_the_age_comes_from_job_runs(self, cls):
        assert sf.AGE_SOURCES.get(cls) == sf.AGE_SOURCE_JOB_RUNS, cls

    @pytest.mark.parametrize("cls", CONDITIONAL_CRYPTO)
    def test_each_is_judged_on_being_ALIVE_not_on_a_completed_pass(self, cls):
        """`last_completed` is blind to failure and returns None for an errored run, which would
        render `no_data` instead of the flatline it is. For a class whose question is "is it
        alive", that is backwards."""
        assert cls in sf.JOB_ALIVE_CLASSES, cls

    @pytest.mark.parametrize("cls", CONDITIONAL_CRYPTO)
    def test_none_of_them_is_treated_as_a_once_per_session_job(self, cls):
        """Crypto trades round the clock, so there is no session to excuse a quiet hour."""
        assert cls not in sf.SESSION_JOB_CLASSES, cls

    def test_the_registry_still_carries_all_three(self):
        """POSITIVE CONTROL. Every test above passes trivially if a class were deregistered —
        which would remove the monitoring rather than fix it."""
        for cls in CONDITIONAL_CRYPTO:
            assert cls in sf.REGISTERED_CLASSES, cls


class TestTheProducersRecordTheirRuns:
    """Without this the switch is a sentinel that cannot fail."""

    def test_the_crypto_engine_loop_opens_and_closes_a_run(self):
        import inspect

        import main

        src = inspect.getsource(main)
        assert 'start_run("crypto_engine"' in src
        assert "_close_crypto_engine_run(run_id, \"ok\"" in src
        assert "_close_crypto_engine_run(run_id, \"error\"" in src, \
            "an errored run must be RECORDED as errored, or it reads no_data"

    def test_the_tape_health_job_opens_and_closes_a_run(self):
        import inspect

        from scheduler import bias_scheduler as bs

        src = inspect.getsource(bs.run_crypto_tape_health_job_scheduled)
        assert '_start_run("crypto_tape_health"' in src
        assert '_finish_crypto_run(_run_id, "ok"' in src
        assert '_finish_crypto_run(_run_id, "error"' in src

    def test_the_cvd_engine_reads_the_tape_health_jobs_row(self):
        """It has no job of its own — it emits from inside compute_all_tape_health()."""
        assert sf.AGE_SOURCE_JOB_NAME["crypto_cvd_engine"] == "crypto_tape_health"

    def test_the_scanner_still_records_its_own(self):
        """Untouched by this change, and the precedent being followed."""
        import inspect

        from scheduler import bias_scheduler as bs

        assert 'start_run("crypto_scanner"' in inspect.getsource(bs.run_crypto_scan_scheduled)
        assert sf.AGE_SOURCE_JOB_NAME.get("crypto_engine", "crypto_engine") == "crypto_engine"

    def test_recording_a_run_never_raises_into_the_producer(self):
        """A failure to record must not fail the scan — but must be logged loudly, because the
        check reads this row and a silent write failure leaves a live engine looking dead."""
        import inspect

        import main
        from scheduler import bias_scheduler as bs

        # Both closers swallow their own failure and log it. Scanned at module level for
        # main.py because the helper is a closure inside the lifespan, not a top-level def.
        assert "could not close its job_runs record" in inspect.getsource(main)
        assert "could not close its job_runs record" in inspect.getsource(bs._finish_crypto_run)
        # And the OPEN side too: a start_run failure leaves run_id None and the scan proceeds.
        assert "could not open a job_runs record" in inspect.getsource(main)
        assert "could not open a job_runs record" in inspect.getsource(bs)


class TestAQuietRegimeIsNotDeath:
    """The semantics, exercised against `_class_status` rather than asserted about it."""

    def test_a_long_signal_gap_no_longer_decides_anything(self):
        """The 12.6-hour gap that tripped tonight. The SLO is unchanged; what changed is which
        clock it is measured against."""
        assert sf.SLO_SECONDS["crypto_engine"] == 12 * 3600
        # Judged on a FRESH run row, the same quiet period is ok.
        assert sf._class_status("crypto_engine", age=300, rejected=0) == "ok"

    def test_a_genuinely_dead_job_still_flatlines(self):
        """CONTROL (#30). The fix must not make the class unable to report an outage — that
        would be removing the alarm, not repairing it."""
        assert sf._class_status("crypto_engine", age=13 * 3600, rejected=0) == "flatline"
        assert sf._class_status("crypto_cvd_engine", age=13 * 3600, rejected=0) == "flatline"

    def test_an_absent_run_row_reads_no_data_which_is_why_the_order_mattered(self):
        """Documents the trap rather than relying on memory of it: with no run row the age is
        absent, the status is `no_data`, and `no_data` does not degrade. That is the vacuous
        green the switch alone would have produced."""
        assert sf._class_status("crypto_engine", age=None, rejected=0) == "no_data"
