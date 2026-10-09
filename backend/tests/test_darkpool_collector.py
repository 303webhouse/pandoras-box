"""The Triton dark-pool collector (R-IV.823(e), R-IV.826(c)).

The first test runs ONE real nightly cycle through `_record` -- the same wrapper the scheduler
uses -- with only the vendor, Redis and the database stubbed, and asserts that pages and window
rows are written. Nothing here inspects source text. The stubbed database answers by table, and
the writes are identified by the module's own statement constants, so a renamed table or a write
that never executes fails the test rather than agreeing with it.
"""

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, List

import pytest

import jobs.darkpool_collector as dc

UTC = timezone.utc
# Thu 2026-10-08 17:00 EDT -- after the close, before the 19:50 stop.
NIGHT = datetime(2026, 10, 8, 21, 0, tzinfo=UTC)


def _fire(rid, ticker, iso):
    return {"id": rid, "ticker": ticker, "fired_at": datetime.fromisoformat(iso)}


FIRES = [
    # tonight's session: 10:00 and 11:30 EDT. 30 RTH minutes before the first fire, so the
    # window reaches 210 minutes into Wed 10-07.
    _fire(400001, "aapl", "2026-10-08T14:00:00+00:00"),
    _fire(400002, "AAPL", "2026-10-08T15:30:00+00:00"),
    # a backlog session: 14:00 EDT, the window stays inside the session.
    _fire(390000, "MSFT", "2026-10-01T18:00:00+00:00"),
    # a SYNTHETIC row matching the seal's two predicates. The stub returns it whatever the SQL
    # says, so this proves the Python guard, not the WHERE clause.
    _fire(377000, "SEALD", "2026-09-16T15:00:00+00:00"),
]


class _Conn:
    def __init__(self, fires, probe_done=False):
        self.fires = fires
        self.probe_done = probe_done
        self.executed: List[tuple] = []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetch(self, sql, *args):
        if sql == dc.FIRES_SQL:
            return list(self.fires)
        return []

    async def fetchval(self, sql, *args):
        if sql == dc.PROBE_DONE_SQL:
            return self.probe_done
        return 1  # job_runs.start_run's RETURNING id

    async def fetchrow(self, sql, *args):
        return None

    def writes(self, stmt):
        return [a for s, a in self.executed if s == stmt]


class _Acq:
    def __init__(self, conn):
        self.conn = conn

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


def _pool(conn):
    class P:
        acquire = _Acq(conn)
    return P()


class _Redis:
    def __init__(self):
        self.setex_calls = []

    async def get(self, key):
        return None

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))


def _prints(older_than_ms, n, step_s=60):
    top = datetime.fromtimestamp(older_than_ms / 1000, tz=UTC)
    return [{"executed_at": (top - timedelta(seconds=step_s * (i + 1))).isoformat(),
             "price": "100.00", "premium": "1000.00", "size": 10, "canceled": False}
            for i in range(n)]


class _Vendor:
    """Short pages by default: every date is EXHAUSTED after one page."""

    def __init__(self, fail_first=0):
        self.calls = []
        self.fail_first = fail_first

    async def __call__(self, ticker, session, older_than_ms, limit):
        self.calls.append((ticker, session, older_than_ms))
        if len(self.calls) <= self.fail_first:
            return None
        return {"data": _prints(older_than_ms, 3)}


@pytest.fixture
def wired(monkeypatch):
    import database.postgres_client as pg
    import database.redis_client as rc
    import integrations.uw_api as uw
    import integrations.uw_api_cache as cache
    import stable_engine.job_status as js

    state = {"conn": _Conn(FIRES), "redis": _Redis(), "vendor": _Vendor(), "marked": {}}

    async def _get_pool():
        return _pool(state["conn"])

    async def _get_redis():
        return state["redis"]

    async def _fetch(*a):
        return await state["vendor"](*a)

    async def _count():
        return 1_000

    async def _ok(name):
        state["marked"]["success"] = name

    async def _fail(name, err):
        state["marked"]["failure"] = (name, err)
        return False

    monkeypatch.setattr(uw, "get_darkpool_ticker_page", _fetch)
    monkeypatch.setattr(cache, "get_daily_count", _count)
    monkeypatch.setattr(rc, "get_redis_client", _get_redis)
    monkeypatch.setattr(pg, "get_postgres_client", _get_pool)
    monkeypatch.setattr(js, "mark_success", _ok)
    monkeypatch.setattr(js, "mark_failure", _fail)
    return state


async def _one_cycle():
    from jobs.stable_jobs import _record

    async def _run():
        return await dc.collect(now_utc=NIGHT)

    return await _record(dc.JOB_NAME, _run, session_date=date(2026, 10, 8))


@pytest.mark.asyncio
async def test_one_real_cycle_writes_pages_and_windows(wired):
    res = await _one_cycle()
    conn, vendor = wired["conn"], wired["vendor"]

    assert wired["marked"] == {"success": dc.JOB_NAME}
    pages = conn.writes(dc.INSERT_PAGE)
    windows = conn.writes(dc.UPSERT_WINDOW)
    # AAPL: two market dates (10-08, 10-07); MSFT: one.
    assert len(pages) == 3
    assert res["rows_touched"] == 3
    assert {(w[0], w[1], w[11]) for w in windows} == {
        ("AAPL", date(2026, 10, 8), dc.FORWARD), ("MSFT", date(2026, 10, 1), dc.BACKFILL)}
    for w in windows:
        assert w[8] is True and w[9] == dc.EXHAUSTED  # reached, by short pages
    # payloads are stored as received
    stored = json.loads(pages[0][6])
    assert len(stored["data"]) == 3 and stored["data"][0]["premium"] == "1000.00"
    # the probe ran first, three calls, and was recorded as OK
    probes = conn.writes(dc.INSERT_PROBE)
    assert len(probes) == 1 and probes[0][0] is True
    assert [c["label"] for c in json.loads(probes[0][1])["calls"]] == ["oldest", "mid", "recent"]
    # forward before backfill: after the 3 probe calls, AAPL's dates come before MSFT's
    assert [c[0] for c in vendor.calls[3:]] == ["AAPL", "AAPL", "MSFT"]
    # the summary reaches the last-run key for /health
    assert wired["redis"].setex_calls[0][0] == dc.LAST_RUN_KEY


@pytest.mark.asyncio
async def test_sealed_row_is_never_fetched(wired):
    await _one_cycle()
    assert all(c[0] != "SEALD" for c in wired["vendor"].calls)
    assert all(w[0] != "SEALD" for w in wired["conn"].writes(dc.UPSERT_WINDOW))


@pytest.mark.asyncio
async def test_failed_probe_means_forward_only(wired):
    wired["vendor"] = _Vendor(fail_first=3)
    await _one_cycle()
    probes = wired["conn"].writes(dc.INSERT_PROBE)
    assert probes[0][0] is False
    assert {w[0] for w in wired["conn"].writes(dc.UPSERT_WINDOW)} == {"AAPL"}
    assert all(c[0] != "MSFT" for c in wired["vendor"].calls[3:])


@pytest.mark.asyncio
async def test_probe_runs_once(wired):
    wired["conn"] = _Conn(FIRES, probe_done=True)
    await _one_cycle()
    assert wired["conn"].writes(dc.INSERT_PROBE) == []
    assert [c[0] for c in wired["vendor"].calls] == ["AAPL", "AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_account_total_at_30000_stops_before_any_call(wired):
    async def _spent(now):
        return dc.ACCOUNT_STOP_AT

    budget = dc.Budget(deadline=NIGHT + timedelta(hours=2), now=lambda: NIGHT, total=_spent)
    res = await dc.collect(now_utc=NIGHT, budget=budget)
    assert wired["vendor"].calls == []
    assert res["rows_touched"] == 0 and res["stopped"].startswith("account total")


@pytest.mark.asyncio
async def test_vendor_gate_stops_the_night_and_window_is_retryable(wired):
    from integrations.uw_governor import UWUnavailable

    class _Gated(_Vendor):
        async def __call__(self, *a):
            self.calls.append(a)
            return UWUnavailable("RATE_LIMITED")

    wired["conn"] = _Conn(FIRES, probe_done=True)
    wired["vendor"] = _Gated()
    res = await dc.collect(now_utc=NIGHT)
    windows = wired["conn"].writes(dc.UPSERT_WINDOW)
    assert len(wired["vendor"].calls) == 1          # one refusal, then nothing
    assert [w[9] for w in windows] == [dc.INTERRUPTED]
    assert dc.INTERRUPTED not in dc.TERMINAL
    assert "RATE_LIMITED" in res["stopped"]


@pytest.mark.asyncio
async def test_paging_walks_back_until_the_window_start(wired):
    """Full pages move the cursor back; the page that passes the start ends the date."""
    calls = []

    async def _full(ticker, session, older_than_ms, limit):
        calls.append(older_than_ms)
        return {"data": _prints(older_than_ms, dc.PAGE_LIMIT, step_s=6)}  # 50 min a page

    g = dc.Group("NVDA", date(2026, 10, 8),
                 datetime(2026, 10, 8, 18, 0, tzinfo=UTC), datetime(2026, 10, 8, 19, 0, tzinfo=UTC))
    budget = dc.Budget(deadline=NIGHT + timedelta(hours=2), now=lambda: NIGHT,
                       total=lambda now: _zero())
    conn = _Conn([])
    res = await dc.collect_window(conn, _full, g, dc.FORWARD, budget)
    # window: 14:00 EDT - 240 min = 10:00 EDT, end 15:00 EDT -> 300 minutes at 50 a page
    assert res.segments[-1]["stop_reason"] == dc.REACHED_START
    assert res.pages == 6 == len(conn.writes(dc.INSERT_PAGE))
    assert calls == sorted(calls, reverse=True)


async def _zero():
    return 0


@pytest.mark.asyncio
async def test_a_stuck_cursor_is_recorded_not_looped(wired):
    async def _stuck(ticker, session, older_than_ms, limit):
        top = datetime(2026, 10, 8, 19, 0, tzinfo=UTC)
        return {"data": [{"executed_at": top.isoformat()}] * dc.PAGE_LIMIT}

    g = dc.Group("TSLA", date(2026, 10, 8),
                 datetime(2026, 10, 8, 18, 0, tzinfo=UTC), datetime(2026, 10, 8, 19, 0, tzinfo=UTC))
    budget = dc.Budget(deadline=NIGHT + timedelta(hours=2), now=lambda: NIGHT,
                       total=lambda now: _zero())
    res = await dc.collect_window(_Conn([]), _stuck, g, dc.FORWARD, budget)
    assert res.segments[-1]["stop_reason"] == dc.STALLED and res.pages == 1


# ── pure helpers ──────────────────────────────────────────────────────────────────────────
def test_seal_needs_both_predicates():
    after = datetime(2026, 8, 17, tzinfo=UTC)
    before = after - timedelta(seconds=1)
    assert dc.is_sealed(377783, after)
    assert not dc.is_sealed(377784, after)
    assert not dc.is_sealed(377783, before)


@pytest.mark.parametrize("fire_et, start_et", [
    ("2026-10-08T14:00", "2026-10-08T10:00"),   # enough session before the fire
    ("2026-10-08T13:00", "2026-10-07T15:30"),   # 210 min today, 30 from Wednesday's close
    ("2026-10-05T09:45", "2026-10-02T12:15"),   # Monday: 15 min today, 225 from Friday
    ("2026-10-08T08:00", "2026-10-07T12:00"),   # pre-market fire anchors at the open
])
def test_window_start_counts_regular_minutes(fire_et, start_et):
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    fire = datetime.fromisoformat(fire_et).replace(tzinfo=et)
    assert dc.window_start(fire) == datetime.fromisoformat(start_et).replace(tzinfo=et)


def test_segments_span_each_market_date_newest_first():
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    start = datetime(2026, 10, 2, 12, 15, tzinfo=et)
    end = datetime(2026, 10, 5, 11, 0, tzinfo=et)
    segs = dc.segments(start, end)
    assert [s[0] for s in segs] == [date(2026, 10, 5), date(2026, 10, 2)]
    assert segs[0][2] == end and segs[0][1] == datetime(2026, 10, 5, tzinfo=et)
    assert segs[1][1] == start and segs[1][2] == datetime(2026, 10, 3, tzinfo=et)


def test_deadline_is_1950_et_in_summer_and_the_reset_in_winter():
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    # EDT: 19:50 ET and 10 min before 00:00Z coincide.
    assert dc.deadline_for(NIGHT).astimezone(et).strftime("%H:%M") == "19:50"
    # EST (after 2026-11-01): 00:00Z is 19:00 ET, so the stop is 18:50 ET.
    winter = datetime(2026, 11, 4, 21, 30, tzinfo=UTC)
    assert dc.deadline_for(winter).astimezone(et).strftime("%H:%M") == "18:50"


def test_group_fires_one_window_per_ticker_session():
    groups = dc.group_fires(FIRES)
    keys = {(g.ticker, g.session) for g in groups}
    assert keys == {("AAPL", date(2026, 10, 8)), ("MSFT", date(2026, 10, 1))}
    aapl = next(g for g in groups if g.ticker == "AAPL")
    assert aapl.first_fire < aapl.last_fire
