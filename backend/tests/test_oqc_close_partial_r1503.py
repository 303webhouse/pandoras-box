"""R-IV.1503(b) — a capture that saves fewer tickers than it should never logs "ok", and the
close starts early enough to finish before 16:00.

11-13's 15:59 slot started at 15:59:59.948 ET (job_runs 17473). The first call, AAPL, went out
inside the session; every call after 16:00:00 met the governor's off-hours quota for this tag
(320 x 0.25 = 80, 193 already spent) and came back empty. It saved AAPL only -- 22 rows,
15 of 16 pairs unavailable -- and logged `ok`, because `ok` meant "some rows".

THE PARTIAL TEST replays that slot through the REAL `capture_slot`: same instant, same 16
pairs, the vendor answering only the first call. Only the edges are fakes (the vendor call, the
pool, the job_runs writer). THE TIMING TEST walks the REAL `seconds_to_next_wake` from every
start phase and asks when the first wake-up inside the close lands.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from jobs import job_runs
from jobs import option_quote_capture as oqc

ET = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc
FRI = date(2026, 11, 13)
#: job_runs 17473's started_at, to the millisecond.
FRIDAY_START = datetime(2026, 11, 13, 20, 59, 59, 948000, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean():
    oqc.reset_for_tests()
    yield
    oqc.reset_for_tests()


def _raw_chain(ticker, expiry, spot=100.0, width=8):
    out = []
    for i in range(-width, width + 1):
        k = spot + i
        for kind, delta in (("C", 0.5 if i == 0 else 0.3), ("P", -0.5 if i == 0 else -0.3)):
            out.append({"option_symbol": "%s%s%s%08d" % (ticker, expiry.strftime("%y%m%d"),
                                                         kind, int(round(k * 1000))),
                        "nbbo_bid": 1.0, "nbbo_ask": 1.1, "delta": delta,
                        "implied_volatility": 0.2, "volume": 1, "open_interest": 1})
    return out


class _Conn:
    async def execute(self, sql, *args):
        return None

    async def fetch(self, sql, *args):
        return []


class _Acq:
    async def __aenter__(self):
        return _Conn()

    async def __aexit__(self, *a):
        return False


class _Pool:
    def acquire(self):
        return _Acq()


def _run_slot(answer, now=FRIDAY_START):
    """The REAL capture_slot. `answer(i, ticker, expiry)` -> raw chain or None (the vendor /
    governor). Returns (summary, [(status, rows_touched, error)])."""
    import database.postgres_client as pg

    finished, calls = [], []

    async def fake_fetch(ticker, expiry):
        calls.append((ticker, expiry))
        raw = answer(len(calls) - 1, ticker, expiry)
        return (raw, len(raw)) if raw is not None else (None, 0)

    async def fake_pool():
        return _Pool()

    async def fake_start(job, session):
        return 1

    async def fake_finish(run_id, status, **kw):
        finished.append((status, kw.get("rows_touched"), kw.get("error") or ""))

    saved = (oqc.fetch_expiry, pg.get_postgres_client, job_runs.start_run, job_runs.finish_run)
    oqc.fetch_expiry, pg.get_postgres_client = fake_fetch, fake_pool
    job_runs.start_run, job_runs.finish_run = fake_start, fake_finish
    try:
        out = asyncio.run(oqc.capture_slot(now=now))
    finally:
        (oqc.fetch_expiry, pg.get_postgres_client,
         job_runs.start_run, job_runs.finish_run) = saved
    return out, finished, calls


# ── 1. a partial capture is not "ok" ────────────────────────────────────────

def test_fridays_close_replayed_is_NOT_ok():
    """Only the first call answered, as on 11-13. Before this fix: status ok, 22 rows."""
    out, finished, calls = _run_slot(lambda i, t, e: _raw_chain(t, e) if i == 0 else None)
    assert out["slot"] == "15:59"
    assert len(calls) == 16, "the replay must plan 11-13's 16 pairs (8 tickers x 0 and 3 DTE)"
    assert out["tickers_saved"] == ["AAPL"]
    assert out["tickers_missing"] == ["IWM", "MSFT", "NVDA", "QQQ", "SMH", "SPY", "TSLA"]
    assert len(finished) == 1
    status, rows, error = finished[0]
    assert status != job_runs.STATUS_OK, "a capture that saved 1 of 8 tickers logged ok"
    assert status == job_runs.STATUS_COMPLETED_DEFECTIVE
    assert rows > 0
    assert "saved 1 of 8 tickers" in error and "QQQ" in error


def test_a_full_capture_is_still_ok():
    out, finished, _calls = _run_slot(lambda i, t, e: _raw_chain(t, e))
    assert out["tickers_missing"] == [] and len(out["tickers_saved"]) == 8
    assert finished[0][0] == job_runs.STATUS_OK


def test_a_ticker_the_vendor_has_no_expiry_for_is_not_missing():
    """Absent is a vendor fact, not a loss: a ticker with nothing to save is not counted."""
    out, finished, _calls = _run_slot(
        lambda i, t, e: [] if t == "SMH" else _raw_chain(t, e))
    assert "SMH" not in out["tickers_saved"] and out["tickers_missing"] == []
    assert finished[0][0] == job_runs.STATUS_OK


def test_one_ticker_lost_mid_session_is_defective_and_named():
    later = datetime.combine(FRI, time(11, 30, 1), tzinfo=ET).astimezone(UTC)
    out, finished, _calls = _run_slot(
        lambda i, t, e: None if t == "TSLA" else _raw_chain(t, e), now=later)
    assert out["tickers_missing"] == ["TSLA"]
    assert finished[0][0] == job_runs.STATUS_COMPLETED_DEFECTIVE
    assert "saved 7 of 8 tickers; missing TSLA" in finished[0][2]


def test_a_dropped_far_expiry_alone_does_not_make_a_ticker_missing():
    """The 3-DTE pair is the one the budget is designed to drop; the ticker was still saved."""
    out, finished, _calls = _run_slot(lambda i, t, e: None if e.day == 16 else _raw_chain(t, e))
    assert out["tickers_missing"] == [] and len(out["tickers_saved"]) == 8
    assert finished[0][0] == job_runs.STATUS_OK


# ── 2. the close starts early enough to finish before 16:00 ─────────────────

def _first_close_wake(phase_s, step):
    """Walk the loop from 15:57 + phase with `step(now)` as its sleep (capture time 0); return
    the first wake-up at which the 15:59 slot is due."""
    now = datetime.combine(FRI, time(15, 57), tzinfo=ET) + timedelta(seconds=phase_s)
    for _ in range(10):
        if oqc.due_slot(now) == oqc.CLOSE_SLOT:
            return now
        now = now + timedelta(seconds=step(now))
    raise AssertionError("never woke inside the close")


@pytest.mark.parametrize("phase_s", [0.0, 0.5, 1.0, 13.7, 30.0, 45.2, 59.0, 59.95])
def test_the_close_wakes_one_second_after_15_59_from_every_phase(phase_s):
    wake = _first_close_wake(phase_s, oqc.seconds_to_next_wake)
    latest = datetime.combine(FRI, time(15, 59, 1), tzinfo=ET) + timedelta(milliseconds=1)
    assert wake <= latest, "first close wake-up at %s" % wake.time()
    # 7.9 s is the longest close of the ten sessions before 11-13; it ends before 16:00.
    assert wake + timedelta(seconds=7.9) < datetime.combine(FRI, time(16, 0), tzinfo=ET)


def test_negative_control_the_old_60s_sleep_reproduces_fridays_start():
    """The old loop: from 11-13's phase the first close wake-up is 15:59:59.948."""
    wake = _first_close_wake(59.948, lambda now: oqc.POLL_SECONDS)
    assert wake.time() == time(15, 59, 59, 948000)
    assert wake + timedelta(seconds=2.6) > datetime.combine(FRI, time(16, 0), tzinfo=ET)


def test_the_loop_uses_the_slot_aware_sleep():
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) >= 3:
            raise asyncio.CancelledError

    async def fake_capture():
        return {}

    real_sleep, real_cap, real_wake = asyncio.sleep, oqc.capture_slot, oqc.seconds_to_next_wake
    asyncio.sleep, oqc.capture_slot = fake_sleep, fake_capture
    oqc.seconds_to_next_wake = lambda now: 12.5
    try:
        with pytest.raises(asyncio.CancelledError):
            real_run = oqc.run_forever()
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(real_run)
            finally:
                loop.close()
    finally:
        asyncio.sleep, oqc.capture_slot, oqc.seconds_to_next_wake = \
            real_sleep, real_cap, real_wake
    assert sleeps[0] == 75 and sleeps[1:] == [12.5, 12.5]


def test_away_from_a_slot_the_loop_still_sleeps_a_minute():
    noon = datetime.combine(FRI, time(12, 10), tzinfo=ET)
    assert oqc.seconds_to_next_wake(noon) == oqc.POLL_SECONDS
