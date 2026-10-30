"""R-IV.1451(b): the forward dark-pool walk gets its full 250 off-hours, and a walk that stops
before finishing the session that just closed records PARTIAL in job_runs, never ok."""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from integrations import uw_governor as gov
from jobs import darkpool_forward as fwd
from jobs.job_runs import STATUS_OK, STATUS_PARTIAL, PASS_COMPLETE_STATUSES

ET = ZoneInfo("America/New_York")
NIGHT = datetime(2026, 10, 30, 20, 30, tzinfo=ET)     # Friday's walk window


def test_the_walk_is_exempt_from_the_off_hours_cut():
    assert gov.OFF_HOURS_FACTOR_BY_CALLER.get(fwd.CALLER_TAG) == 1.0


def test_the_governor_grants_the_full_250_off_hours():
    quota, tier = gov.quota_for(fwd.CALLER_TAG)
    assert (quota, tier) == (250, gov.TIER_STANDARD), "the ruled allowance itself moved"
    assert gov.effective_quota(fwd.CALLER_TAG, NIGHT) == (250, gov.TIER_STANDARD)
    # The exemption is this caller's alone: an unlisted STANDARD caller still gets a quarter.
    assert gov.effective_quota("darkpool_ticker", NIGHT)[0] == int(gov.quota_for(
        "darkpool_ticker")[0] * 0.25)


@pytest.mark.asyncio
@pytest.mark.parametrize("count,blocked", [(62, False), (249, False), (250, True)])
async def test_the_REAL_gate_lets_the_63rd_call_through_after_hours(monkeypatch, count, blocked):
    """Through `precheck`, the function that actually blocked: 62 used is no longer the end."""
    async def _count(caller):
        return count

    async def _no_shed(tier, now=None):
        return None

    monkeypatch.setattr(gov, "_is_rth", lambda now_et=None: False)
    monkeypatch.setattr(gov, "get_caller_count_or_none", _count)
    monkeypatch.setattr(gov, "account_shed", _no_shed)
    monkeypatch.setattr(gov, "breaker_is_tripped", lambda: False)
    monkeypatch.setattr(gov, "_mode", lambda: "enforce")
    out = await gov.precheck(fwd.CALLER_TAG)
    if blocked:
        assert out is not None and "250/250" in str(out.detail)
    else:
        assert out is None, out


# ── PARTIAL ───────────────────────────────────────────────────────────────────────────────

NAMES = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")
S = date(2026, 10, 29)


def _r(t, exhausted=True):
    return {"ticker": t, "exhausted": exhausted}


def test_the_night_that_hid_for_four_nights_is_PARTIAL():
    """Run 23 exactly: four complete, NVDA cut by the governor, three never reached."""
    results = [_r("SPY"), _r("QQQ"), _r("IWM"), _r("SMH"), _r("NVDA", exhausted=False)]
    status, why = fwd.session_verdict(
        NAMES, S, set(), results,
        "governor blocked: UWUnavailable(reason=QUOTA_EXCEEDED, detail=62/62)")
    assert status == STATUS_PARTIAL != STATUS_OK
    assert "cut mid-walk: NVDA" in why
    assert "never reached: AAPL,MSFT,TSLA" in why
    assert "QUOTA_EXCEEDED" in why


def test_a_finished_session_is_ok_even_with_backlog_left():
    status, why = fwd.session_verdict(NAMES, S, set(), [_r(t) for t in NAMES], None)
    assert (status, why) == (STATUS_OK, None)


def test_names_done_by_an_earlier_attempt_count_as_done():
    done = {(t, S) for t in NAMES[:6]}
    status, _ = fwd.session_verdict(NAMES, S, done, [_r("MSFT"), _r("TSLA")], None)
    assert status == STATUS_OK
    status, why = fwd.session_verdict(NAMES, S, done, [_r("MSFT")], "ceiling")
    assert status == STATUS_PARTIAL and why.startswith("never reached: TSLA")


def test_partial_is_not_a_completed_pass():
    assert STATUS_PARTIAL not in PASS_COMPLETE_STATUSES


class _Conn:
    async def execute(self, *a, **k):
        return None

    async def fetch(self, *a, **k):
        return []

    async def fetchval(self, *a, **k):
        return 20


class _Acq:
    async def __aenter__(self):
        return _Conn()

    async def __aexit__(self, *a):
        return False


class _Pool:
    def acquire(self):
        return _Acq()


@pytest.mark.asyncio
async def test_END_TO_END_a_starved_night_writes_partial_to_job_runs(monkeypatch):
    """A walk whose budget runs out mid-session closes its job_runs row as PARTIAL."""
    import database.postgres_client as pg
    from jobs import darkpool_backfill as census
    from jobs import job_runs

    rows = {}

    async def _start(job, session):
        rows["start"] = (job, session)
        return 7

    async def _finish(run_id, status, rows_touched=None, skip_reason=None, error=None):
        rows["finish"] = (run_id, status, skip_reason)

    async def _collect(pool, ticker, session, budget, caller=None):
        for _ in range(40):          # 40 calls per name: the 62-call cut lands in the second
            budget.spend()
        return {"ticker": ticker, "session": session.isoformat(), "pages": 1, "prints": 1,
                "exhausted": True, "reached_floor": True}

    async def _pool():
        return _Pool()

    async def _noop(*a, **k):
        return {}

    monkeypatch.setattr(job_runs, "start_run", _start)
    monkeypatch.setattr(job_runs, "finish_run", _finish)
    monkeypatch.setattr(census, "collect_one", _collect)
    monkeypatch.setattr(census, "refresh_completeness", _noop)
    monkeypatch.setattr(pg, "get_postgres_client", _pool)
    monkeypatch.setattr(fwd, "night_ceiling", lambda: 62)
    monkeypatch.setitem(gov.FOREIGN_RESERVE_QUOTAS, fwd.CALLER_TAG, (250, gov.TIER_STANDARD))
    monkeypatch.setenv(fwd.ENV_FLAG, "true")
    out = await fwd.walk_night(now=datetime(2026, 10, 29, 21, 0, tzinfo=ET))
    assert rows["start"] == ("darkpool_forward", date(2026, 10, 29))
    run_id, status, why = rows["finish"]
    assert (run_id, status) == (7, STATUS_PARTIAL), rows
    assert "never reached" in why
    assert out["status"] == STATUS_PARTIAL
