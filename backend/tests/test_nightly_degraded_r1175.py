"""R-IV.1175(b) — a nightly that came up short must SAY so, and must be retried.

THE FAILURE THIS FILE EXISTS FOR, exactly as it happened. On 2026-10-15 the nightly pass
downloaded 514 of 678 bars, wrote ZERO metrics rows for that session, recorded
`status = ok`, and the regime tool then served a 2026-10-14 reading for two days. Nothing
anywhere said anything was wrong. Three separate things had to be true for that:

  1. `check_nightly_output` tested `res["metrics_rows"]`, which is the count written across
     ALL HISTORY by a whole-history UPSERT -- 887,320 that night. A whole-history total cannot
     see a hole at the newest edge, and it is always large, so the test always passed.
  2. `res["degraded"]` (coverage below 90%) was only consulted when there was NO output at
     all, so a 75.8% download beside a big UPSERT never reached it.
  3. The regime payload served `metrics_date` alone. A stale date and a quiet market look
     identical from the outside; only the run's own verdict distinguishes them.

So the tests below are grouped by those three, and each asserts the property rather than the
wording. The one asymmetry worth stating out loud: `degraded` is RETRYABLE and
`completed_defective` is NOT, because the two describe different faults. A vendor gap heals on
repetition -- measured on 2026-10-16, when the request that returned 514 of 678 bars overnight
returned all 164 missing names that afternoon -- whereas a deterministic computation defect
returns the same nothing however many times it is run.
"""
from __future__ import annotations

import datetime as dt
import importlib

import pytest

jr = importlib.import_module("jobs.job_runs")
sj = importlib.import_module("jobs.stable_jobs")


def _ok(**over) -> dict:
    """A healthy nightly return: edge aligned, metrics written, coverage fine."""
    base = {"coverage": 99.1, "degraded": False,
            "newest_bar_date": "2026-10-16", "newest_metrics_date": "2026-10-16",
            "metrics_written": 678, "metrics_rows": 887320, "themes_stored": 24}
    base.update(over)
    return base


# ── 1. the status itself ─────────────────────────────────────────────────────

def test_degraded_is_its_own_status_string():
    assert jr.STATUS_DEGRADED == "degraded"


def test_degraded_is_NOT_a_completed_pass():
    """THE WHOLE POINT OF THE NEW STATUS. `PASS_COMPLETE_STATUSES` is what the retry reads to
    decide "this session is done"; a short vendor day is not done, so leaving it out is what
    makes the retry re-attempt instead of standing down."""
    assert jr.STATUS_DEGRADED not in jr.PASS_COMPLETE_STATUSES


def test_completed_defective_IS_a_completed_pass_and_the_two_differ():
    """The contrast is the design. `completed_defective` stays in, because repeating a
    deterministic defect produces the same nothing; `degraded` stays out, because a vendor gap
    heals. A change that collapsed them would silently stop one of the two behaviours."""
    assert jr.STATUS_COMPLETED_DEFECTIVE in jr.PASS_COMPLETE_STATUSES
    assert jr.STATUS_DEGRADED != jr.STATUS_COMPLETED_DEFECTIVE


def test_degraded_is_not_in_the_last_completed_set_either():
    """`last_completed` answers "when did a pass last RUN" for the staleness sentinel. A
    degraded night must not refresh that clock, or a week of short nights reads as current."""
    import inspect
    src = inspect.getsource(jr.last_completed)
    assert "STATUS_DEGRADED" not in src


# ── 2. the checker sees the newest edge ──────────────────────────────────────

def test_a_healthy_pass_still_passes():
    """Convention #30: the positive control. Without it, a checker that raised on everything
    would pass every test below."""
    assert sj.check_nightly_output(_ok()) is None


def test_bars_ahead_of_metrics_is_degraded():
    """2026-10-15 ITSELF: bars reached a session whose metrics never landed."""
    with pytest.raises(sj.NightlyDegraded) as e:
        sj.check_nightly_output(_ok(newest_metrics_date="2026-10-14",
                                    newest_bar_date="2026-10-15"))
    assert "2026-10-15" in str(e.value) and "2026-10-14" in str(e.value)


def test_zero_metrics_on_the_newest_bar_date_is_degraded():
    """The edge can be aligned and still empty -- MAX(date) over an empty session is the
    session before it. So the count on the newest BAR date is asked separately."""
    with pytest.raises(sj.NightlyDegraded):
        sj.check_nightly_output(_ok(metrics_written=0))


def test_a_degraded_download_is_degraded_even_with_output():
    """FAULT 2 ABOVE. Coverage below the downloader's own floor used to be consulted only when
    there was no output at all, so 75.8% alongside a large UPSERT passed."""
    with pytest.raises(sj.NightlyDegraded) as e:
        sj.check_nightly_output(_ok(degraded=True, coverage=75.8))
    assert "75.8" in str(e.value)


def test_a_whole_history_metrics_total_can_no_longer_carry_the_pass():
    """FAULT 1, stated as the property: a huge `metrics_rows` must NOT rescue a session that
    got nothing. This is the exact shape of the 10-15 return value."""
    with pytest.raises(sj.NightlyDegraded):
        sj.check_nightly_output(_ok(metrics_rows=887320, metrics_written=0,
                                    newest_metrics_date="2026-10-14",
                                    newest_bar_date="2026-10-15",
                                    degraded=True, coverage=75.8))


@pytest.mark.parametrize("missing", ["newest_bar_date", "newest_metrics_date",
                                     "metrics_written"])
def test_an_unreadable_edge_FAILS_CLOSED(missing):
    """An earlier draft of this checker returned None from the edge read and then skipped every
    test, because `None == 0` is False and `None is not None` is False -- so an unreadable edge
    PASSED the run. "I could not tell" is not "fine"."""
    with pytest.raises(sj.NightlyDegraded) as e:
        sj.check_nightly_output(_ok(**{missing: None}))
    assert "cannot be verified" in str(e.value)


def test_the_defective_path_is_untouched():
    """The old OutputCheckFailed behaviour must survive the new branch: download fine, no
    output at all, still a non-retried defect rather than a degraded day."""
    with pytest.raises(sj.OutputCheckFailed):
        sj.check_nightly_output(_ok(metrics_rows=0, themes_stored=0))


def test_the_degraded_branch_runs_BEFORE_the_old_tests():
    """Ordering is load-bearing: the 10-15 return had a healthy `metrics_rows`, so if the old
    tests ran first they would return early and the edge would never be examined."""
    with pytest.raises(sj.NightlyDegraded):
        sj.check_nightly_output(_ok(metrics_rows=887320, themes_stored=24,
                                    metrics_written=0))


def test_degraded_is_its_own_exception_type():
    """`_record` picks the recorded status by exception class. Without a distinct type this
    lands in the generic handler and is recorded as `error` and alerted as a crash -- a
    different claim about a different fault."""
    assert issubclass(sj.NightlyDegraded, RuntimeError)
    assert not issubclass(sj.NightlyDegraded, sj.OutputCheckFailed)
    assert not issubclass(sj.OutputCheckFailed, sj.NightlyDegraded)


# ── the edge read normalises both dates the same way ─────────────────────────

def test_the_edge_read_slices_both_dates_identically(monkeypatch):
    """`"2026-10-15 00:00:00" < "2026-10-15"` is TRUE lexicographically. The driver may hand
    back `date` or pandas `Timestamp` depending on the query shape, so a mixed pair would
    report a healthy session as behind. Both are sliced, or neither."""
    import pandas as pd

    from stable_engine import db

    monkeypatch.setattr(db, "read_df", lambda sql, params=None: pd.DataFrame(
        [{"b": pd.Timestamp("2026-10-16"), "m": dt.date(2026, 10, 16), "n": 678}]))
    assert sj._newest_edge() == ("2026-10-16", "2026-10-16", 678)


def test_the_edge_read_returns_None_on_a_failed_read(monkeypatch):
    from stable_engine import db

    def _boom(sql, params=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "read_df", _boom)
    assert sj._newest_edge() == (None, None, None)


def test_the_edge_read_returns_None_on_an_empty_result(monkeypatch):
    """Empty is not zero. An empty frame means the question was not answered."""
    import pandas as pd

    from stable_engine import db

    monkeypatch.setattr(db, "read_df", lambda sql, params=None: pd.DataFrame())
    assert sj._newest_edge() == (None, None, None)


def test_the_nightly_return_carries_the_edge_fields():
    """The checker reads these three keys, so `_nightly_work` has to produce them -- a checker
    reading keys nobody sets is a check that never runs."""
    from tests._srcscan import code_of_file

    code = code_of_file(sj.__file__)
    for key in ("newest_bar_date", "newest_metrics_date", "metrics_written"):
        assert '"%s"' % key in code or "'%s'" % key in code, key
    assert "_newest_edge()" in code


# ── 3. a reader can tell a failed run from a healthy one ─────────────────────

def _no_run():
    async def _lr(job_name):
        return None
    return _lr


@pytest.mark.asyncio
async def test_the_status_reads_the_shared_job_name_constant(monkeypatch):
    """Not the literal. `JOB_NIGHTLY` is the string R-IV.360(1) rules, and a hand-written
    name here would read an empty ledger and report "no run on record" forever."""
    import services.read_only.stable as ro

    seen = {}

    async def _lr(job_name):
        seen["name"] = job_name
        return None

    monkeypatch.setattr(jr, "last_run", _lr)
    await ro._nightly_run_status()
    assert seen["name"] == jr.JOB_NIGHTLY


@pytest.mark.asyncio
async def test_a_healthy_run_reads_healthy(monkeypatch):
    import services.read_only.stable as ro

    async def _lr(job_name):
        return {"status": "ok", "session_date": dt.date(2026, 10, 16),
                "started_at": None, "finished_at": dt.datetime(2026, 10, 17, 2, 14),
                "rows_touched": 678, "skip_reason": None, "error": None}

    monkeypatch.setattr(jr, "last_run", _lr)
    out = await ro._nightly_run_status()
    assert out["status"] == "ok"
    assert out["healthy"] is True
    assert out["session_date"] == "2026-10-16"
    assert out["finished_at"].startswith("2026-10-17T02:14")


@pytest.mark.asyncio
async def test_a_degraded_run_reads_NOT_healthy_and_carries_its_reason(monkeypatch):
    import services.read_only.stable as ro

    async def _lr(job_name):
        return {"status": "degraded", "session_date": dt.date(2026, 10, 15),
                "started_at": None, "finished_at": dt.datetime(2026, 10, 16, 2, 11),
                "rows_touched": None, "skip_reason": None,
                "error": "bars reach 2026-10-15 but metrics stop at 2026-10-14"}

    monkeypatch.setattr(jr, "last_run", _lr)
    out = await ro._nightly_run_status()
    assert out["status"] == "degraded"
    assert out["healthy"] is False
    assert "metrics stop at" in out["detail"]


@pytest.mark.asyncio
async def test_an_unreadable_ledger_is_NOT_healthy_and_NOT_False(monkeypatch):
    """UNKNOWN IS NOT HEALTHY, and it is not an outright failure either. This field was added
    because a short run reported itself healthy; a failure to read it must not be able to say
    the one thing the field exists to catch."""
    import services.read_only.stable as ro

    monkeypatch.setattr(jr, "last_run", _no_run())
    out = await ro._nightly_run_status()
    assert out["status"] is None
    assert out["healthy"] is None
    assert out["healthy"] is not False


@pytest.mark.asyncio
async def test_a_raising_ledger_is_caught_and_still_not_healthy(monkeypatch):
    import services.read_only.stable as ro

    async def _boom(job_name):
        raise RuntimeError("db down")

    monkeypatch.setattr(jr, "last_run", _boom)
    out = await ro._nightly_run_status()
    assert out["status"] is None
    assert out["healthy"] is None
    assert "unreadable" in out["detail"]


@pytest.mark.asyncio
async def test_BOTH_regime_return_paths_serve_the_field(monkeypatch):
    """THE LESSON FROM `_feed_health`: its except branch returned a DIFFERENT SHAPE, so the
    new fields disappeared exactly when they mattered. Here the error path is the one a reader
    needs most, so the failing read is what is tested."""
    import database.postgres_client as pc
    import services.read_only.stable as ro

    async def _lr(job_name):
        return {"status": "degraded", "session_date": dt.date(2026, 10, 15),
                "started_at": None, "finished_at": None, "rows_touched": None,
                "skip_reason": None, "error": "short"}

    async def _dead():
        raise RuntimeError("db down")

    monkeypatch.setattr(jr, "last_run", _lr)
    monkeypatch.setattr(pc, "get_postgres_client", _dead)
    monkeypatch.setattr(ro, "get_postgres_client", _dead, raising=False)
    out = await ro.get_regime()
    assert out["nightly_run_status"]["status"] == "degraded"
    assert out["nightly_run_status"]["healthy"] is False


def test_the_status_is_read_before_the_pool_is_acquired():
    """Why it is positioned where it is: `last_run` takes its own connection, and the error
    envelope has to be able to serve the field after the regime read has already failed. Both
    follow from reading it before, and outside, the try."""
    import services.read_only.stable as ro
    from tests._srcscan import function_code

    code = function_code(ro.__file__, "get_regime")
    i = code.index("_nightly_run_status()")
    assert "get_postgres_client" not in code[:i], (
        "the run status must be read before the pool acquire")
