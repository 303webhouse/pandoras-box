"""The IV snapshot (R-IV.866(b)).

The cycle test runs the REAL `snapshot_session` with only the vendor and the database stubbed and
asserts that a row per ticker is written with the nearest-expiry and 30-day ATM IV. The rest
pins the arithmetic, the budget and the retry semantics.
"""

import json
import math
from datetime import date, datetime

import pytest

from jobs import iv_snapshot as iv

SESSION = date(2026, 10, 12)


def _ts(rows):
    return {"data": [{"date": SESSION.isoformat(), "dte": d, "expiry": e, "volatility": v,
                      "implied_move": "1", "implied_move_perc": "0.01"} for d, e, v in rows]}


TERM = _ts([(0, "2026-10-12", "0.90"),          # expiring today: spent, never "nearest"
            (4, "2026-10-16", "0.30"),
            (25, "2026-11-06", "0.28"),
            (39, "2026-11-20", "0.26")])


def test_nearest_is_the_first_live_expiry_and_30d_interpolates_total_variance():
    s = iv.summarize(TERM["data"], SESSION)
    assert (s["near_dte"], s["near_expiry"], s["iv_near"]) == (4, date(2026, 10, 16), 0.30)
    t1, v1, t2, v2 = 25, 0.28, 39, 0.26
    var30 = v1 * v1 * t1 + (30 - t1) / (t2 - t1) * (v2 * v2 * t2 - v1 * v1 * t1)
    assert s["iv_30d_method"] == "interpolated"
    assert s["iv_30d"] == round(math.sqrt(var30 / 30), 6)


def test_30_days_not_bracketed_is_null_never_extrapolated():
    s = iv.summarize(_ts([(4, "2026-10-16", "0.30"), (11, "2026-10-23", "0.29")])["data"], SESSION)
    assert s["iv_30d"] is None and s["iv_30d_method"] == "not_bracketed"
    assert s["iv_near"] == 0.30


def test_another_sessions_rows_are_not_this_sessions():
    rows = [dict(r, date="2026-10-09") for r in TERM["data"]]
    s = iv.summarize(rows, SESSION)
    assert s["iv_near"] is None and s["iv_30d_method"] == "no_live_expiry"


def test_x4_reads_the_positions_own_expiry():
    assert iv.iv_for_expiry(json.dumps(TERM), date(2026, 11, 6)) == 0.28
    assert iv.iv_for_expiry(TERM, date(2026, 12, 18)) is None


class _Conn:
    def __init__(self, open_tickers):
        self.open, self.executed = open_tickers, []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetch(self, sql, *args):
        return [{"ticker": t} for t in self.open] if sql == iv.OPEN_UNDERLYINGS else []


@pytest.mark.asyncio
async def test_one_real_cycle_writes_a_row_per_ticker():
    from strategies.registered_shadow import UNIVERSE
    conn = _Conn(["aapl", "PDBC", "BTC-USD", "WEAT"])     # AAPL already in; a crypto pair filtered
    asked = []

    async def _fetch(ticker, session):
        asked.append(ticker)
        return TERM

    res = await iv.snapshot_session(conn, SESSION, _fetch)
    want = len(UNIVERSE) + 2                              # + PDBC, WEAT
    assert res["tickers"] == want == len(asked) and res["rows_touched"] == want
    assert "BTC-USD" not in asked and asked[-2:] == ["PDBC", "WEAT"]
    rows = [a for s, a in conn.executed if s == iv.UPSERT]
    assert len(rows) == want
    t, sess, near_exp, near_dte, iv_near, iv_30d, method, body, prov = rows[0]
    assert (sess, near_dte, iv_near, method, prov) == (SESSION, 4, 0.30, "interpolated", "uw")
    assert json.loads(body) == TERM                        # stored as received


@pytest.mark.asyncio
async def test_the_universe_never_exceeds_the_daily_cap():
    conn = _Conn(["AB%s" % chr(65 + i) for i in range(26)] + ["AC%s" % chr(65 + i) for i in range(26)]
                 + ["AD%s" % chr(65 + i) for i in range(26)])
    assert len(await iv.universe(conn)) == iv.DAILY_CAP


@pytest.mark.asyncio
async def test_a_governor_refusal_is_an_error_so_the_session_is_retried():
    from integrations.uw_governor import UWUnavailable

    async def _refused(ticker, session):
        return UWUnavailable("QUOTA_EXCEEDED")

    with pytest.raises(RuntimeError):
        await iv.snapshot_session(_Conn([]), SESSION, _refused)


def test_sessions_newest_first_and_never_before_the_registrations():
    tue_evening = datetime(2026, 10, 13, 17, 0, tzinfo=iv.ET)
    assert iv.sessions_to_run(tue_evening) == [date(2026, 10, 13), date(2026, 10, 12)]
    tue_morning = datetime(2026, 10, 13, 9, 0, tzinfo=iv.ET)
    assert iv.sessions_to_run(tue_morning) == [date(2026, 10, 12)]


@pytest.mark.asyncio
async def test_catch_up_stops_at_the_daily_cap(monkeypatch):
    """Two missed sessions cost ~392 calls: only the newest runs today."""
    import jobs.job_runs as jr
    import jobs.stable_jobs as sj

    async def _not_done(job, session):
        return False

    ran = []

    async def _record(name, fn, session_date=None):
        ran.append(session_date)
        return {"session": session_date.isoformat(), "tickers": 196, "rows_touched": 196}

    monkeypatch.setattr(jr, "has_completed", _not_done)
    monkeypatch.setattr(sj, "_record", _record)
    out = await iv.run(now=datetime(2026, 10, 13, 17, 0, tzinfo=iv.ET), fetch=lambda *a: None)
    assert ran == [date(2026, 10, 13)]
    assert out["sessions"][1] == {"session": "2026-10-12", "deferred": "daily cap"}


@pytest.mark.asyncio
async def test_a_session_with_no_live_iv_anywhere_is_retried(monkeypatch):
    """Vendor served another date's structure for every ticker: rows written, none usable."""
    import database.postgres_client as pg
    import jobs.job_runs as jr
    import jobs.stable_jobs as sj

    stale = {"data": [dict(r, date="2026-10-09") for r in TERM["data"]]}

    async def _fetch(ticker, session):
        return stale

    class _Acq:
        async def __aenter__(self):
            return _Conn([])

        async def __aexit__(self, *exc):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    async def _pool():
        return _Pool()

    async def _not_done(job, session):
        return False

    raised = []

    async def _record(name, fn, session_date=None):
        try:
            return await fn()
        except Exception as e:  # noqa: BLE001
            raised.append(type(e))
            return None

    monkeypatch.setattr(pg, "get_postgres_client", _pool)
    monkeypatch.setattr(jr, "has_completed", _not_done)
    monkeypatch.setattr(sj, "_record", _record)
    await iv.run(now=datetime(2026, 10, 12, 17, 0, tzinfo=iv.ET), fetch=_fetch)
    assert raised == [RuntimeError]
