"""T2 — durable job bookkeeping (R-IV.289).

These call the REAL module. The point under test is the TRI-STATE: has_completed
must be able to return None, and None must not be False. A test that only checks
True/False would pass against a module that collapsed unknown into "already ran" —
which is the failure that silently stops grading.
"""

import importlib

import pytest

jr = importlib.import_module("jobs.job_runs")


class _Boom:
    async def __aenter__(self): raise RuntimeError("db down")
    async def __aexit__(self, *a): return False


def _pool_raising():
    class P:
        def acquire(self): return _Boom()
    async def _get():
        return P()
    return _get


def test_terminal_statuses_are_enumerated():
    """An acceptance predicate enumerates its pass states — so does a status set."""
    assert jr.STATUS_OK == "ok"
    assert {jr.STATUS_RUNNING, jr.STATUS_OK, jr.STATUS_ERROR,
            jr.STATUS_TIMEOUT, jr.STATUS_SKIPPED} == {
        "running", "ok", "error", "timeout", "skipped"}


def test_job_name_constant_is_shared():
    """The loop and the reader must not drift apart on the key — AND the value
    must be the string R-IV.295(a) rules, because a hand-written query will use
    the ruled name. One constant, one spelling, matching the ruling."""
    assert jr.JOB_TRITON_GRADER == "triton_grader"


@pytest.mark.asyncio
async def test_has_completed_returns_None_when_unreadable(monkeypatch):
    """UNKNOWN IS NOT FALSE. This is the whole test."""
    import database.postgres_client as pc
    monkeypatch.setattr(pc, "get_postgres_client", _pool_raising())
    out = await jr.has_completed("anything", __import__("datetime").date(2026, 9, 8))
    assert out is None
    assert out is not False


@pytest.mark.asyncio
async def test_finish_run_is_a_noop_without_an_id():
    """start_run returning None must not make finish_run explode."""
    await jr.finish_run(None, jr.STATUS_OK)


@pytest.mark.asyncio
async def test_write_failures_never_raise(monkeypatch):
    """Bookkeeping must not kill the job it records."""
    import database.postgres_client as pc
    monkeypatch.setattr(pc, "get_postgres_client", _pool_raising())
    d = __import__("datetime").date(2026, 9, 8)
    assert await jr.start_run("j", d) is None
    await jr.finish_run(1, jr.STATUS_ERROR, error="x")   # must not raise
    assert await jr.last_run("j") is None


def test_timeout_is_derived_not_chosen():
    """T1: >=10x the ~20s measured pass. 300s is 15x."""
    import main
    assert main.TRITON_GRADER_TIMEOUT_S >= 10 * 20
    assert main.TRITON_GRADER_TIMEOUT_S == 300


def test_timeout_metric_exists_and_starts_at_zero():
    """A timeout with no metric is indistinguishable from one that never fires."""
    import main
    assert main.TRITON_GRADER_TIMEOUTS["count"] == 0
    assert "last_session" in main.TRITON_GRADER_TIMEOUTS
