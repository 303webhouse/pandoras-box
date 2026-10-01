"""An option must be EXPIRED the evening it expires — R-IV.629(b).

THE CORRECTION THIS IMPLEMENTS. 316 SLV expired 09-30 and still read OPEN, and the first
reading was that the sweep had skipped it. It had not: the sweep ran late, and late was its
normal behaviour. Every recorded run fires at 06:30 ET on a weekday, and it can only ever use
`expiry < CURRENT_DATE` — strictly before today — because at 06:30 an option expiring today is
still live. So the earliest a Friday expiry could end was the following Monday, and MEASURED it
trailed every expiry by 1 to 3 days.

The cost of the lag is not cosmetic: between the close and the sweep, an expired option reads
OPEN to the loss alert, the caps and the River.

An option expires at its session's close, so after that close the inclusive cutoff is sound.
This is what makes "the evening it expires" possible, and it is sound ONLY after the close —
which is why the inclusive form is gated on the calendar and refuses a future date on its own
account.
"""

import ast
import io
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from stable_engine.sessions import REGULAR_CLOSE

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


# ─────────────────────── the two cutoffs

class TestTheTwoCutoffs:

    def test_the_backstop_keeps_strictly_before_today(self):
        """Unchanged, and it must stay that way: it runs at 06:30, before the close, where
        today's expiry is still live. An inclusive cutoff there would end a live position
        nine and a half hours early."""
        code = _code("api/unified_positions.py")
        assert "expiry < CURRENT_DATE" in code

    def test_the_post_close_pass_is_inclusive(self):
        """`expiry <= $1::date`. Without this the post-close run catches nothing on the day
        it matters — CURRENT_DATE is still today at 16:05 ET, so a strict `<` excludes
        exactly the expiries the pass exists for."""
        code = _code("api/unified_positions.py")
        assert "expiry <= $1::date" in code

    def test_the_inclusive_form_is_only_reachable_with_a_cutoff(self):
        """The default must remain the safe one, so an existing caller cannot acquire the
        inclusive behaviour by saying nothing."""
        import inspect

        from api.unified_positions import _sweep_expired_positions

        p = inspect.signature(_sweep_expired_positions).parameters["through"]
        assert p.default is None


# ─────────────────────── it cannot end a position that is still live

class TestItRefusesAFutureDate:

    @pytest.mark.asyncio
    async def test_a_future_cutoff_sweeps_nothing(self):
        """THE SAFETY CASE. `through` in the future would expire positions that have not
        expired. It is refused outright rather than trusted to the caller."""
        from api.unified_positions import _sweep_expired_positions

        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=400)
        assert await _sweep_expired_positions(through=tomorrow) == []

    def test_the_refusal_is_loud(self):
        """A silent refusal here looks identical to "nothing had expired"."""
        code = _code("api/unified_positions.py")
        i = code.index("is after today in ET")
        assert "logger.error" in code[max(0, i - 300):i]


# ─────────────────────── when it runs

class TestWhenItRuns:

    def test_the_time_derives_from_the_session_calendar(self):
        """One author for the close. A second hard-coded 16:00 is a second thing to change
        the day the calendar moves."""
        from jobs.stable_jobs import _postclose_time_et

        h, m = _postclose_time_et()
        assert (h, m) > (REGULAR_CLOSE.hour, REGULAR_CLOSE.minute)
        assert h == REGULAR_CLOSE.hour  # a few minutes' grace, not a different hour

    def test_it_runs_after_the_close_never_before(self):
        from jobs.stable_jobs import _postclose_time_et

        assert _postclose_time_et() == (16, 5)

    def test_a_half_day_is_safe_in_this_direction_only(self):
        """sessions.py deliberately does not model early closes. On a 13:00 ET half day this
        pass runs three hours AFTER the real close — late, never early. Late is correctable;
        early ends a live position."""
        from jobs.stable_jobs import _postclose_time_et

        half_day_close = (13, 0)
        assert _postclose_time_et() > half_day_close

    def test_the_two_passes_are_separate_job_records(self):
        """Sharing one job name would make either pass's completion suppress the other for
        the day, which is how a backstop stops being one."""
        from jobs.stable_jobs import EXPIRY_SWEEP_JOB, EXPIRY_SWEEP_POSTCLOSE_JOB

        assert EXPIRY_SWEEP_JOB != EXPIRY_SWEEP_POSTCLOSE_JOB

    def test_the_backstop_is_kept(self):
        """R-IV.629(b) keeps it explicitly. It catches what a restart or an outage lost."""
        code = _code("jobs/stable_jobs.py")
        assert "await _maybe_run_expiry_sweep(et)" in code
        assert "await _maybe_run_expiry_sweep_postclose(et)" in code

    def test_an_unanswerable_calendar_day_runs_no_inclusive_sweep(self):
        """UNKNOWN is not YES. A date the calendar cannot answer for is not a session, so
        the inclusive pass must not run on it — the backstop covers it next weekday."""
        code = _code("jobs/stable_jobs.py")
        # Anchored on the AWAIT, not the name: `_maybe_run_expiry_sweep_postclose(et)` also
        # matches its own `async def` four hundred lines earlier, and a window on the wrong
        # occurrence passes or fails for the wrong reason. Pinned unique so it cannot drift.
        anchor = "await _maybe_run_expiry_sweep_postclose(et)"
        assert code.count(anchor) == 1, code.count(anchor)
        window = code[max(0, code.index(anchor) - 400):code.index(anchor)]
        assert "_traded_day(et.date())" in window
        assert "is True" in window

    def test_the_post_close_block_imports_its_own_name(self):
        """It previously would have relied on the CIRCE block above having imported
        is_trading_day_or_none. A name bound by another section's import is a NameError
        waiting for the day that section is reordered, and py_compile cannot see it."""
        code = _code("jobs/stable_jobs.py")
        i = code.index("pch, pcm = _postclose_time_et()")
        assert "as _traded_day" in code[max(0, i - 400):i]


# ─────────────────────── the run record can report what the pass did

class TestTheRunRecordsItsCount:

    def test_finish_run_passes_rows_touched_through(self):
        """`job_runs.finish_run` has always accepted `rows_touched`, and the wrapper never
        passed it — so EVERY run of EVERY job routed through _record recorded NULL. Measured
        on the expiry sweep: eight consecutive `ok` runs, rows_touched NULL on all eight. The
        new pass is judged on what it ends, and that was unrecordable."""
        import inspect

        from jobs import stable_jobs

        src = inspect.getsource(stable_jobs._finish_run)
        assert "rows_touched=rows_touched" in src
        assert "rows_touched" in inspect.signature(stable_jobs._finish_run).parameters

    def test_record_reads_only_the_declared_key(self):
        """One key, by convention. A per-job mapping here would be a second place to keep
        every job's return shape, which is how the two drift apart."""
        import inspect

        from jobs import stable_jobs

        src = inspect.getsource(stable_jobs._record)
        assert 'res.get("rows_touched")' in src
        assert "isinstance(res, dict)" in src

    def test_a_job_that_reports_nothing_records_null_not_zero(self):
        """POSITIVE CONTROL and the important half: a job that returns a non-dict must leave
        the column NULL. A fabricated 0 would read as "ran and touched nothing", which is a
        different claim from "did not say"."""
        import inspect

        from jobs import stable_jobs

        src = inspect.getsource(stable_jobs._record)
        assert "else None" in src

    def test_both_sweeps_report_their_count(self):
        import inspect

        from jobs import stable_jobs

        for fn in (stable_jobs._maybe_run_expiry_sweep,
                   stable_jobs._maybe_run_expiry_sweep_postclose):
            src = inspect.getsource(fn)
            assert '"rows_touched": len(ended)' in src, fn.__name__


# ─────────────────────── the lag this closes

def test_the_window_in_which_an_expired_option_read_open():
    """Arithmetic, not behaviour: the point of the change. A Friday expiry under the old
    single pass waited until Monday 06:30 ET — about 62 hours of reading OPEN. Under the
    post-close pass it is 5 minutes."""
    friday_close = datetime(2026, 10, 2, 16, 0)
    monday_backstop = datetime(2026, 10, 5, 6, 30)
    old_lag_h = (monday_backstop - friday_close).total_seconds() / 3600
    assert 60 < old_lag_h < 65

    new_lag_min = 5
    assert new_lag_min < old_lag_h * 60
