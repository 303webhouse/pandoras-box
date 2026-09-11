"""R-IV.360(1) — the nightly retries, and a failure it cannot record is not lost.

THE DEFECT BEING CLOSED (measured 2026-09-10): Postgres entered recovery mid-run.
The nightly failed, `mark_failure` could not write because it needed that same
database, and the pass was not retried until the next day's 21:00 slot. A few
minutes of outage cost a full day of `stable_daily_bars`.

The load-bearing assertions are:
  * a FAILED pass is retried (the old code marked it fired BEFORE running);
  * the retry survives a restart, because completion is asked of job_runs and not
    of an in-process set;
  * `has_completed` returning None (unreadable DB) does NOT read as "done";
  * a failure Postgres cannot record reaches a channel that does not need Postgres.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import stable_jobs as sj


ET_NOW = datetime(2026, 9, 11, 21, 0, 0)
KEY = "2026-09-11"


@pytest.fixture(autouse=True)
def _clear_state():
    sj._nightly_attempted_at.clear()
    yield
    sj._nightly_attempted_at.clear()


@pytest.fixture
def harness(monkeypatch):
    calls = {"runs": 0, "completed_q": 0}
    state = {"completed": False}

    async def fake_has_completed(job, session_date):
        calls["completed_q"] += 1
        return state["completed"]

    async def fake_record(job_name, coro_fn, session_date=None):
        calls["runs"] += 1
        return None

    import jobs.job_runs as jr
    monkeypatch.setattr(jr, "has_completed", fake_has_completed, raising=False)
    monkeypatch.setattr(sj, "_record", fake_record)
    return calls, state


# ------------------------------------------------------- the retry itself

@pytest.mark.asyncio
async def test_runs_when_the_session_pass_has_not_completed(harness):
    calls, state = harness
    await sj._maybe_run_nightly(ET_NOW, KEY)
    assert calls["runs"] == 1


@pytest.mark.asyncio
async def test_does_not_run_when_already_completed(harness):
    calls, state = harness
    state["completed"] = True
    await sj._maybe_run_nightly(ET_NOW, KEY)
    assert calls["runs"] == 0


@pytest.mark.asyncio
async def test_a_failed_pass_is_retried_after_the_interval(harness):
    """THE DEFECT. The old code marked it fired BEFORE running, so this never happened."""
    calls, state = harness
    await sj._maybe_run_nightly(ET_NOW, KEY)               # 21:00, fails (still incomplete)
    later = ET_NOW + timedelta(seconds=sj.NIGHTLY_RETRY_EVERY_S + 1)
    await sj._maybe_run_nightly(later, KEY)
    assert calls["runs"] == 2, "a failed pass was not retried"


@pytest.mark.asyncio
async def test_retry_is_rate_limited_inside_the_interval(harness):
    """Without this an unreadable database re-fires the nightly every 45 seconds."""
    calls, state = harness
    await sj._maybe_run_nightly(ET_NOW, KEY)
    await sj._maybe_run_nightly(ET_NOW + timedelta(seconds=45), KEY)
    await sj._maybe_run_nightly(ET_NOW + timedelta(seconds=90), KEY)
    assert calls["runs"] == 1


@pytest.mark.asyncio
async def test_stops_retrying_once_a_pass_completes(harness):
    calls, state = harness
    await sj._maybe_run_nightly(ET_NOW, KEY)
    state["completed"] = True
    await sj._maybe_run_nightly(ET_NOW + timedelta(seconds=sj.NIGHTLY_RETRY_EVERY_S + 1), KEY)
    assert calls["runs"] == 1


# ------------------------------------------------- the tri-state is load-bearing

@pytest.mark.asyncio
async def test_unknown_completion_runs_rather_than_skips(harness):
    """None means THE QUESTION COULD NOT BE ANSWERED — which is what a Postgres in
    recovery returns. Reading it as 'done' would reproduce the defect exactly."""
    calls, state = harness
    state["completed"] = None
    await sj._maybe_run_nightly(ET_NOW, KEY)
    assert calls["runs"] == 1, "an unreadable database was read as 'already done'"


@pytest.mark.asyncio
async def test_completion_check_raising_still_runs(harness, monkeypatch):
    calls, state = harness

    async def boom(job, session_date):
        raise RuntimeError("connection already closed")

    import jobs.job_runs as jr
    monkeypatch.setattr(jr, "has_completed", boom, raising=False)
    await sj._maybe_run_nightly(ET_NOW, KEY)
    assert calls["runs"] == 1, "an exception on the check silently skipped the pass"


@pytest.mark.asyncio
async def test_completion_is_asked_of_job_runs_not_an_in_process_set(harness):
    """Durability: the question must reach job_runs every attempt."""
    calls, state = harness
    await sj._maybe_run_nightly(ET_NOW, KEY)
    await sj._maybe_run_nightly(ET_NOW + timedelta(seconds=sj.NIGHTLY_RETRY_EVERY_S + 1), KEY)
    assert calls["completed_q"] == 2


@pytest.mark.asyncio
async def test_a_restart_does_not_lose_or_double_fire_the_session(harness):
    """Clearing in-process state models a restart. job_runs still answers."""
    calls, state = harness
    state["completed"] = True
    sj._nightly_attempted_at.clear()          # the restart
    await sj._maybe_run_nightly(ET_NOW, KEY)
    assert calls["runs"] == 0, "a restart re-fired a completed session"


def test_retry_window_constants_are_sane():
    assert sj.NIGHTLY_RETRY_EVERY_S >= 60
    assert 21 <= sj.NIGHTLY_RETRY_UNTIL_HOUR_ET <= 23
    # ~12 attempts available between 21:00 and the cut-off
    span = (sj.NIGHTLY_RETRY_UNTIL_HOUR_ET + 1 - 21) * 3600
    assert span // sj.NIGHTLY_RETRY_EVERY_S >= 4


# ------------------------------------- the failure channel that survives the DB

@pytest.mark.asyncio
async def test_failure_postgres_cannot_record_goes_out_of_band(monkeypatch):
    """conventions #15: an error channel must not share the failing dependency."""
    from stable_engine import job_status as jst

    written = {}

    class FakeRedis:
        async def setex(self, k, ttl, v):
            written["key"], written["ttl"], written["val"] = k, ttl, v

        async def delete(self, k):
            written["deleted"] = k

    async def fake_redis():
        return FakeRedis()

    async def dead_pool():
        raise RuntimeError("the database system is in recovery mode")

    import database.redis_client as rc
    import database.postgres_client as pc
    monkeypatch.setattr(rc, "get_redis_client", fake_redis, raising=False)
    monkeypatch.setattr(pc, "get_postgres_client", dead_pool, raising=False)

    await jst.mark_failure("nightly", "connection already closed")
    assert written.get("key") == jst.REDIS_FAILURE_KEY.format(job_name="nightly")
    assert "connection already closed" in written["val"]
    assert written["ttl"] == jst.REDIS_FAILURE_TTL_S


@pytest.mark.asyncio
async def test_both_channels_down_does_not_raise(monkeypatch):
    """If Redis is down too, the log is what is left — but nothing may throw."""
    from stable_engine import job_status as jst

    async def dead(*a, **k):
        raise RuntimeError("down")

    import database.redis_client as rc
    import database.postgres_client as pc
    monkeypatch.setattr(rc, "get_redis_client", dead, raising=False)
    monkeypatch.setattr(pc, "get_postgres_client", dead, raising=False)
    assert await jst.mark_failure("nightly", "boom") is False


@pytest.mark.asyncio
async def test_out_of_band_marker_reports_which_job_and_why(monkeypatch):
    from stable_engine import job_status as jst
    import json

    store = {}

    class FakeRedis:
        async def setex(self, k, ttl, v):
            store[k] = v

        async def get(self, k):
            return store.get(k)

    async def fake_redis():
        return FakeRedis()

    import database.redis_client as rc
    monkeypatch.setattr(rc, "get_redis_client", fake_redis, raising=False)
    await jst._mark_failure_out_of_band("nightly", "connection already closed")
    found = await jst.unrecorded_failures()
    assert len(found) == 1
    assert found[0]["job_name"] == "nightly"
    assert "conventions #15" in found[0]["note"]


def test_unrecorded_failures_scans_the_real_roster():
    """A scan over a name that does not exist returns [] forever — a null verifier
    inside the fix for a null verifier."""
    from stable_engine import job_status as jst
    assert "nightly" in jst.JOB_FEEDS
    src = Path(__file__).resolve().parents[1] / "stable_engine" / "job_status.py"
    assert "for job in JOB_FEEDS" in src.read_text(encoding="utf-8")
