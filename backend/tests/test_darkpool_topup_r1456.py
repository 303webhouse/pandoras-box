"""R-IV.1456(f): the one weekend top-up of the forward walk's backlog, up to 1,000 calls.

Oldest first (10-23, then 10-26 -> 10-29), its own reserve tag at the full 1,000 off-hours, one
run ever, never on a trading day, and one job_runs row that is `ok` only when every pending
ticker-session was walked to its end.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from integrations import uw_governor as gov
from jobs import darkpool_topup as top
from jobs.job_runs import JOB_DARKPOOL_TOPUP, STATUS_OK, STATUS_PARTIAL

ET = ZoneInfo("America/New_York")
SAT = datetime(2026, 10, 31, 10, 0, tzinfo=ET)
NAMES = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")


def _backlog_done():
    """Exhausted ticker-sessions as of Friday night: every name through 10-22, the four names
    the starved nights reached on 10-26..10-29, and 10-30 complete. 10-23 has nothing."""
    done = set()
    for d in (date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22),
              date(2026, 10, 30)):
        done |= {(t, d) for t in NAMES}
    for d in (date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29)):
        done |= {(t, d) for t in ("SPY", "QQQ", "IWM", "SMH")}
    return done


# ── the allowance ─────────────────────────────────────────────────────────────────────────

def test_the_top_up_has_its_own_reserve_tag_at_exactly_1000():
    assert top.CALLER_TAG == "darkpool_topup" and top.MAX_CALLS == 1000
    assert gov.FOREIGN_RESERVE_QUOTAS[top.CALLER_TAG] == (1000, gov.TIER_STANDARD)
    assert top.CALLER_TAG not in gov.QUOTAS, "the hub's own budget table is untouched"


def test_the_governor_grants_the_full_1000_on_a_weekend():
    assert gov.OFF_HOURS_FACTOR_BY_CALLER.get(top.CALLER_TAG) == 1.0
    assert gov.effective_quota(top.CALLER_TAG, SAT) == (1000, gov.TIER_STANDARD)


@pytest.mark.asyncio
@pytest.mark.parametrize("count,blocked", [(250, False), (999, False), (1000, True)])
async def test_the_REAL_gate_allows_999_and_blocks_the_1001st(monkeypatch, count, blocked):
    async def _count(caller):
        return count

    async def _no_shed(tier, now=None):
        return None
    monkeypatch.setattr(gov, "_is_rth", lambda now_et=None: False)
    monkeypatch.setattr(gov, "get_caller_count_or_none", _count)
    monkeypatch.setattr(gov, "account_shed", _no_shed)
    monkeypatch.setattr(gov, "breaker_is_tripped", lambda: False)
    monkeypatch.setattr(gov, "_mode", lambda: "enforce")
    out = await gov.precheck(top.CALLER_TAG)
    assert (out is not None) == blocked, out


# ── arming and the plan ───────────────────────────────────────────────────────────────────

def test_only_the_exact_arm_value_arms(monkeypatch):
    for v, expect in (("", False), ("1", False), ("true", False), ("r-iv.1456f", False),
                      ("R-IV.1456f", True), (" R-IV.1456f ", True)):
        monkeypatch.setenv(top.ARM_ENV, v)
        assert top.armed() is expect, repr(v)


def test_the_plan_is_oldest_first_and_starts_with_10_23():
    anchor = top.anchor_after(SAT.date())
    assert anchor == date(2026, 11, 2)
    plan = top.plan(anchor, _backlog_done(), NAMES)
    assert plan[:8] == [(date(2026, 10, 23), t) for t in NAMES]
    rest = plan[8:]
    assert [s for s, _ in rest] == sorted(s for s, _ in rest), "oldest session first"
    assert {s for s, _ in rest} == {date(2026, 10, 26), date(2026, 10, 27),
                                    date(2026, 10, 28), date(2026, 10, 29)}
    assert {t for _, t in rest} == {"NVDA", "AAPL", "MSFT", "TSLA"}
    assert len(plan) == 8 + 16


def test_the_verdict_is_ok_only_when_every_planned_ticker_session_is_exhausted():
    todo = [(date(2026, 10, 23), "SPY"), (date(2026, 10, 23), "QQQ")]
    full = [{"session": "2026-10-23", "ticker": "SPY", "exhausted": True},
            {"session": "2026-10-23", "ticker": "QQQ", "exhausted": True}]
    assert top.verdict(todo, full, None) == ("ok", None)
    status, why = top.verdict(todo, full[:1], "budget")
    assert status == "partial" and "2026-10-23 QQQ never reached" in why and "budget" in why
    cut = [full[0], dict(full[1], exhausted=False)]
    assert "2026-10-23 QQQ cut mid-walk" in top.verdict(todo, cut, None)[1]


# ── the run, end to end, against a fake database ──────────────────────────────────────────

class _Conn:
    def __init__(self, db):
        self.db = db

    async def fetchval(self, sql, *a):
        if "pg_try_advisory_lock" in sql:
            return self.db["lock_free"]
        if "count(*) FROM job_runs" in sql:
            return self.db["prior"]
        if "INSERT INTO darkpool_backfill_runs" in sql:
            return 77
        raise AssertionError(sql)

    async def fetch(self, sql, *a):
        return [{"ticker": t, "session_date": d} for t, d in self.db["done"]]

    async def execute(self, sql, *a):
        self.db["executed"].append(sql)


class _Acq:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return _Conn(self.db)

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, db):
        self.db = db

    def acquire(self):
        return _Acq(self.db)


@pytest.fixture
def fake(monkeypatch):
    from jobs import darkpool_backfill as bf, darkpool_forward as fwd
    import database.postgres_client as pc
    db = {"lock_free": True, "prior": 0, "done": _backlog_done(), "executed": [],
          "runs": [], "walked": [], "calls_each": 30}

    async def _pool():
        return _Pool(db)

    async def _start(job, session):
        db["runs"].append({"job": job, "session": session})
        return 501

    async def _finish(run_id, status, rows_touched=None, skip_reason=None, error=None):
        db["runs"][-1].update(status=status, rows=rows_touched, why=skip_reason, error=error)

    async def _collect(pool, ticker, session, budget, caller):
        assert caller == "darkpool_topup"
        db["walked"].append((session, ticker))
        n = min(db["calls_each"], budget.remaining)
        for _ in range(n):
            budget.spend()
        if budget.remaining <= 0:
            budget.stop("budget")
        return {"ticker": ticker, "session": session.isoformat(), "pages": n, "prints": 1,
                "exhausted": n == db["calls_each"]}

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(pc, "get_postgres_client", _pool)
    monkeypatch.setattr("jobs.job_runs.start_run", _start)
    monkeypatch.setattr("jobs.job_runs.finish_run", _finish)
    monkeypatch.setattr(bf, "collect_one", _collect)
    monkeypatch.setattr(bf, "refresh_completeness", _noop)
    monkeypatch.setattr(bf.Budget, "check_account", _noop)
    monkeypatch.setattr(fwd, "census_names", lambda: NAMES)
    monkeypatch.setattr("integrations.uw_spend_ledger.uw_day", lambda now: date(2026, 10, 31))
    return db


@pytest.mark.asyncio
async def test_END_TO_END_the_backlog_is_written_oldest_first_and_recorded_ok(fake):
    out = await top.run_once(now=SAT)
    assert out["status"] == "ok" and out["calls"] == 24 * 30 <= 1000
    assert fake["walked"][:8] == [(date(2026, 10, 23), t) for t in NAMES]
    run = fake["runs"][0]
    assert run["job"] == JOB_DARKPOOL_TOPUP and run["status"] == STATUS_OK
    assert run["session"] == date(2026, 10, 23)
    assert "calls 720/1000" in run["why"] and "2026-10-23 SPY" in run["why"]
    assert any("SET ended_at" in s for s in fake["executed"]), "the F: gate needs the run ended"


@pytest.mark.asyncio
async def test_END_TO_END_a_budget_cut_is_PARTIAL_and_names_what_is_left(fake):
    fake["calls_each"] = 60          # 24 x 60 = 1,440 > 1,000
    out = await top.run_once(now=SAT)
    assert out["calls"] == 1000
    run = fake["runs"][0]
    assert run["status"] == STATUS_PARTIAL
    assert "never reached" in run["why"] and "LEFT" in run["why"]


@pytest.mark.asyncio
async def test_a_SECOND_run_is_refused(fake):
    fake["prior"] = 1
    out = await top.run_once(now=SAT)
    assert out["status"] == "refused" and "one run only" in out["reason"]
    assert fake["walked"] == [] and fake["runs"] == []


@pytest.mark.asyncio
async def test_a_held_lock_is_refused(fake):
    fake["lock_free"] = False
    assert (await top.run_once(now=SAT))["status"] == "refused"
    assert fake["walked"] == []


@pytest.mark.asyncio
async def test_a_TRADING_DAY_is_refused(fake):
    out = await top.run_once(now=datetime(2026, 11, 2, 10, 0, tzinfo=ET))
    assert out["status"] == "refused" and "trading day" in out["reason"]
    assert fake["walked"] == []


@pytest.mark.asyncio
async def test_unarmed_does_nothing(monkeypatch, fake):
    monkeypatch.delenv(top.ARM_ENV, raising=False)
    await top.start_if_armed()
    assert fake["walked"] == [] and fake["runs"] == []
