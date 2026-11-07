"""R-IV.1493(b): the forward dark-pool walk's three repairs, plus the positions tool's line.

1. Option 4: quota 250 -> 400 (ceiling 384), from the reserve, claimed 5,455 -> 5,605.
2. Option 3: a night with no session of its own walks the backlog only, never above the ceiling,
   and opens nothing when there is no backlog.
3. The label: a walk cut by its own budget RECORDS that, and it is told apart from the vendor
   having no more pages. Run 29 (2026-11-05) read "stop: unknown".
4. R-IV.1486(c): EXPIRED is separate from CLOSED, and status=ALL returns both.

The label and replay tests drive the REAL `collect_one` against a fake vendor and a fake pool.
A mocked `collect_one` would only test the mock's idea of where a budget runs out.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest

from jobs import darkpool_backfill as census
from jobs import darkpool_forward as fwd
from integrations import uw_governor as gov

ET = census._ET_ZONE()
NAMES = fwd.census_names()
THU = date(2026, 11, 5)
SAT_NIGHT = datetime(2026, 11, 7, 20, 30, tzinfo=ET)
THU_NIGHT = datetime(2026, 11, 5, 20, 30, tzinfo=ET)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fwd.reset_for_tests()

    async def _no_account(self):
        return None

    monkeypatch.setattr(census.Budget, "check_account", _no_account)
    yield
    fwd.reset_for_tests()


# ── a fake vendor and a fake store, so the REAL collect_one runs ─────────────

class _Store:
    """Pages per (ticker, session), the runs opened, and the job_runs rows written."""

    def __init__(self, done=()):
        self.pages = {}            # (ticker, session) -> [row_count, ...]
        self.done = list(done)     # rows DONE_SQL returns
        self.runs_opened = 0
        self.job_runs = []         # (sql, args)
        self.ended = []            # _end_run args


class _Conn:
    def __init__(self, store):
        self.s = store

    async def execute(self, sql, *a):
        if sql is census.INSERT_PAGE:
            ticker, session, _page_no, _cursor, n = a[:5]
            self.s.pages.setdefault((ticker, session), []).append(n)
        elif "job_runs" in sql:
            self.s.job_runs.append((sql, a))
        elif "UPDATE darkpool_backfill_runs" in sql:
            self.s.ended.append(a)
        return None

    async def fetch(self, sql, *a):
        return self.s.done if sql is census.DONE_SQL else []

    async def fetchval(self, sql, *a):
        if "darkpool_backfill_runs" in sql:
            self.s.runs_opened += 1
            return 900 + self.s.runs_opened
        if "job_runs" in sql:
            self.s.job_runs.append((sql, a))
            return 77
        return None

    async def fetchrow(self, sql, *a):
        if "count(*) AS pages" in sql:
            got = self.s.pages.get((a[0], a[1]), [])
            return {"pages": len(got), "prints": sum(got)}
        return None                # RESUME_SQL: nothing stored, start at page 1


class _Acq:
    def __init__(self, store):
        self.s = store

    async def __aenter__(self):
        return _Conn(self.s)

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, store):
        self.s = store

    def acquire(self):
        return _Acq(self.s)


def _vendor(pages_needed: dict):
    """fetch_page that serves `pages_needed[ticker]` pages, the last one short.

    Stamps fall back from 20:00Z a tenth of a second a print, so even a 400-page walk stays
    hours clear of its 04:00 ET floor: the walk ends on the vendor's short page.
    """
    served = {}

    async def _fetch(ticker, session, cursor, budget, caller=None):
        budget.spend()
        k = served.get((ticker, session), 0) + 1
        served[(ticker, session)] = k
        n = 100 if k >= pages_needed[ticker] else census.PAGE_LIMIT
        base = datetime(session.year, session.month, session.day, 20, 0, tzinfo=timezone.utc)
        start = (k - 1) * census.PAGE_LIMIT
        rows = [{"executed_at": (base - timedelta(milliseconds=100 * (start + i))).isoformat()}
                for i in range(n)]
        return {"data": rows}, None

    return _fetch


@pytest.fixture
def wired(monkeypatch):
    """Both gates open, the store faked, the vendor faked. Returns a setter for both."""
    import database.postgres_client as pg

    os.environ[fwd.ENV_FLAG] = "true"
    state = {}

    def _wire(pages_needed, done=(), quota=None):
        store = _Store(done)

        async def _pool():
            return _Pool(store)

        async def _noop(*a, **k):
            return {}

        monkeypatch.setattr(pg, "get_postgres_client", _pool)
        monkeypatch.setattr(census, "fetch_page", _vendor(pages_needed))
        monkeypatch.setattr(census, "refresh_completeness", _noop)
        if quota is not None:
            monkeypatch.setitem(gov.FOREIGN_RESERVE_QUOTAS, fwd.CALLER_TAG,
                                (quota, gov.TIER_STANDARD))
        state["store"] = store
        return store

    yield _wire
    del os.environ[fwd.ENV_FLAG]


def _done_except(sessions, missing):
    return [{"ticker": t, "session_date": d} for d in sessions for t in NAMES
            if (t, d) not in missing]


def _job_finish(store):
    """The (status, skip_reason) finish_run wrote."""
    for sql, a in store.job_runs:
        if sql.lstrip().upper().startswith("UPDATE"):
            return a
    raise AssertionError("finish_run never wrote: %r" % store.job_runs)


#: 11-05, ESTIMATED: R-IV.1491(c)'s ~345 calls split over the eight names (QQQ and SPY took about
#: 70-75 pages that night). The point is the total against the two ceilings.
HEAVY = {"SPY": 70, "QQQ": 75, "IWM": 25, "SMH": 15, "NVDA": 45, "AAPL": 40, "MSFT": 35,
         "TSLA": 40}

#: Every session before Thursday already written, so a Thursday replay measures Thursday alone
#: and the catch-up has nothing to take the remainder for.
_PRIOR_DONE = [{"ticker": t, "session_date": d}
               for d in fwd.catchup_sessions(THU, set(), NAMES) for t in NAMES]


# ── 1. option 4: the quota ───────────────────────────────────────────────────

def test_the_quota_is_400_from_the_reserve_and_the_ceiling_384():
    from integrations.uw_api_cache import UW_FOREIGN_RESERVE

    assert gov.FOREIGN_RESERVE_QUOTAS[fwd.CALLER_TAG] == (400, gov.TIER_STANDARD)
    assert fwd.CALLER_TAG not in gov.QUOTAS, "drawn from the reserve, not the hub table"
    assert fwd.night_ceiling() == 384
    assert sum(q for q, _ in gov.FOREIGN_RESERVE_QUOTAS.values()) == 5605
    assert 5605 <= UW_FOREIGN_RESERVE == 12000
    # Still STANDARD and still off-hours exempt: shed first under account pressure.
    assert gov.OFF_HOURS_FACTOR_BY_CALLER[fwd.CALLER_TAG] == 1.0
    assert sum(HEAVY.values()) == 345


@pytest.mark.asyncio
async def test_REPLAY_the_heavy_thursday_COMPLETES_at_384(wired):
    store = wired(HEAVY, done=_PRIOR_DONE)
    out = await fwd.walk_night(now=THU_NIGHT)
    assert out["session"] == "2026-11-05"
    assert out["status"] == "ok", out["status_reason"]
    assert out["exhausted"] == 8 and out["calls_spent"] == 345 <= 384
    assert store.runs_opened == 1


@pytest.mark.asyncio
async def test_REPLAY_the_same_night_at_the_old_240_is_cut_and_SAYS_WHY(wired):
    """What run 29 did, with the label fixed: no "unknown"."""
    wired(HEAVY, done=_PRIOR_DONE, quota=250)
    out = await fwd.walk_night(now=THU_NIGHT)
    assert out["status"] == "partial"
    why = out["status_reason"]
    assert "unknown" not in why
    assert "cut mid-walk: AAPL" in why and "never reached: MSFT,TSLA" in why
    assert "stop: call budget exhausted: 240 of 240 calls spent" in why
    assert out["calls_spent"] == 240


# ── 3. the label ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_REAL_collect_one_records_a_budget_stop_on_the_budget(wired):
    store = wired({"TSLA": 30})
    budget = census.Budget(5)
    r = await census.collect_one(_Pool(store), "TSLA", THU, budget, fwd.CALLER_TAG)
    assert r["exhausted"] is False
    assert r["stop"] == census.BUDGET_RAN_OUT == "call budget exhausted"
    assert budget.stop_reason == "call budget exhausted: 5 of 5 calls spent"


@pytest.mark.asyncio
async def test_the_vendor_running_out_of_pages_is_NOT_a_budget_stop(wired):
    """QUERY needs this difference: same walk, enough budget, the vendor ends it."""
    store = wired({"TSLA": 3})
    budget = census.Budget(50)
    r = await census.collect_one(_Pool(store), "TSLA", THU, budget, fwd.CALLER_TAG)
    assert r["exhausted"] is True
    assert r["stop"] == "short page - session complete"
    assert not r["stop"].startswith(census.BUDGET_RAN_OUT)
    assert budget.stop_reason is None


@pytest.mark.asyncio
async def test_a_budget_that_runs_out_BETWEEN_names_is_recorded(wired):
    """The loop broke on `remaining <= 0` before `collect_one` ran for the next name, so no
    session row said anything and the budget said nothing either. Exactly the ceiling on SPY."""
    wired(dict(HEAVY, SPY=384), done=_PRIOR_DONE)
    out = await fwd.walk_night(now=THU_NIGHT)
    why = out["status_reason"]
    assert "unknown" not in why
    assert "never reached: QQQ,IWM,SMH,NVDA,AAPL,MSFT,TSLA" in why, why
    assert "stop: call budget exhausted: 384 of 384 calls spent" in why


@pytest.mark.asyncio
async def test_a_night_that_finishes_on_its_last_call_is_NOT_labelled_cut(wired):
    """`_out_of_budget` is asked only when a name is still to walk."""
    store = wired(dict(HEAVY, SPY=109), done=_PRIOR_DONE)   # 345 - 70 + 109 = 384 exactly
    out = await fwd.walk_night(now=THU_NIGHT)
    assert out["calls_spent"] == 384 and out["status"] == "ok", out
    assert store.ended[-1][1] == fwd.WALKED_TO_THE_END
    assert not fwd.WALKED_TO_THE_END.startswith(census.BUDGET_RAN_OUT)


def test_the_verdict_never_says_unknown_even_without_a_night_reason():
    """A name cut by a vendor error leaves the budget unstopped: its own stop is used."""
    results = [{"ticker": "SPY", "exhausted": False, "stop": "error: HTTP 503"}]
    status, why = fwd.session_verdict(("SPY",), THU, set(), results, None)
    assert status == "partial"
    assert "unknown" not in why and "SPY: error: HTTP 503" in why


# ── 2. option 3: non-trading nights catch up ──────────────────────────────────

def _lookback(night):
    return fwd.catchup_sessions(night, set(), NAMES)


@pytest.mark.asyncio
async def test_SATURDAY_walks_ONLY_the_backlog_and_finishes_TSLA_1105(wired):
    """Tonight's case: everything written except TSLA 11-05."""
    sat = SAT_NIGHT.date()
    span = _lookback(sat)
    assert THU in span and date(2026, 11, 6) in span, "Friday and Thursday are candidates"
    store = wired({"TSLA": 30}, done=_done_except(span, {("TSLA", THU)}))
    out = await fwd.walk_night(now=SAT_NIGHT)

    assert out["session"] is None and out["catchup_only"] is True and out["fired"] is True
    assert out["catchup_pending"] == ["2026-11-05"]
    assert out["catchup_sessions"] == ["2026-11-05"]
    assert set(store.pages) == {("TSLA", THU)}, "it walked something other than the backlog"
    assert out["calls_spent"] == 30 <= fwd.night_ceiling()
    assert out["status"] == "ok"
    assert store.runs_opened == 1
    # The job_runs row: opened for the night's own date, closed ok, and saying what it was.
    starts = [a for sql, a in store.job_runs if "INSERT" in sql.upper()]
    assert starts and starts[0][0] == fwd.JOB_NAME and starts[0][1] == sat
    fin = _job_finish(store)
    assert "ok" in fin and any(isinstance(v, str) and "catch-up only" in v and "2026-11-05" in v
                               for v in fin), fin


@pytest.mark.asyncio
async def test_a_catch_up_night_NEVER_spends_past_the_ceiling(wired):
    """Ten whole sessions pending at 345 each is 3,450 calls. It stops at 384 and says so."""
    sat = SAT_NIGHT.date()
    store = wired(HEAVY, done=[])
    out = await fwd.walk_night(now=SAT_NIGHT)
    assert out["calls_spent"] == fwd.night_ceiling() == 384
    assert sum(len(v) for v in store.pages.values()) == 384, "pages != calls"
    assert out["status"] == "partial"
    why = out["status_reason"]
    assert why.startswith("backlog left: ") and "unknown" not in why
    assert "stop: call budget exhausted: 384 of 384 calls spent" in why
    # Oldest first.
    assert out["catchup_sessions"][0] == _lookback(sat)[0].isoformat()


@pytest.mark.asyncio
async def test_a_catch_up_night_with_NO_backlog_opens_nothing_and_spends_nothing(wired):
    sat = SAT_NIGHT.date()
    store = wired(HEAVY, done=_done_except(_lookback(sat), set()))
    out = await fwd.walk_night(now=SAT_NIGHT)
    assert out["reason"] == "not a trading session; no backlog"
    assert out["calls_spent"] == 0 and out["fired"] is True
    assert store.runs_opened == 0 and store.job_runs == [] and store.pages == {}


@pytest.mark.asyncio
async def test_a_HOLIDAY_is_a_catch_up_night_too(wired):
    """Thanksgiving 2026-11-26: no session, so the backlog gets the night."""
    hol = datetime(2026, 11, 26, 20, 30, tzinfo=ET)
    assert fwd.target_session(hol) is None
    span = _lookback(hol.date())
    store = wired({"MSFT": 4}, done=_done_except(span, {("MSFT", span[-1])}))
    out = await fwd.walk_night(now=hol)
    assert out["catchup_only"] is True and out["catchup_sessions"] == [span[-1].isoformat()]
    assert out["status"] == "ok"


@pytest.mark.asyncio
async def test_the_loop_counts_a_catch_up_night_as_FIRED(monkeypatch):
    """Otherwise it would re-read the backlog every minute until 23:59 ET."""
    import ast
    import inspect
    src = ast.unparse(ast.parse(inspect.getsource(fwd.run_forever)))
    assert "out.get('fired')" in src


# ── 4. R-IV.1486(c) ───────────────────────────────────────────────────────────

def test_the_positions_tool_says_EXPIRED_is_separate_and_ALL_returns_both():
    from hub_mcp.tools.positions import DESCRIPTION
    assert "EXPIRED rows are separate from CLOSED rows; `status=ALL` returns both." in DESCRIPTION
