"""R-IV.1513(c) — three data-feed repairs from Fri 11-20, each pinned by a test that fails
without it.

1. A 30-minute option-quote slot that STORED NOTHING stays due while it is inside its grace.
   11-20: one 429 at 12:20:11 ET shed this job until 12:30:12; the 12:30 slot fired at 12:30:01,
   stored nothing, and was marked done, so the 12:31 wake-up -- which would have been served --
   found it "already captured". A refusal that never left the process is no longer counted as
   a spent call, so re-asking it each minute cannot eat the later slots' budget.
2. A chain at the 500-contract cap is asked again as calls and as puts -- in both option jobs,
   out of SPARE budget only, never by shedding a ticker the slot has not reached.
3. A Stable Engine nightly still incomplete at midnight is carried until 09:00 ET the next
   morning. 11-19's bars were 1/540 through all twelve attempts (21:00-23:48 ET); the 23:59
   cut-off ended the retry and Friday 11-20 ran on 11-18's metrics.

Only the edges are fakes (the vendor call, the pool, the job_runs writer, the completion ledger);
the slot logic, the split and the carry are the real functions.
"""
from __future__ import annotations

import ast
import asyncio
import datetime as _dt
import os
import pathlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jobs import job_runs
from jobs import option_quote_capture as oqc
from jobs import option_quote_grid as oqg
from jobs import stable_jobs as sj

ET = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc
FRI = date(2026, 11, 20)
#: 11-20's 12:30 slot as it ran (job_runs: started 17:30:01Z, every ticker missing).
AT_1230 = datetime(2026, 11, 20, 12, 30, 1, tzinfo=ET).astimezone(UTC)
_BACKEND = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean():
    oqc.reset_for_tests()
    oqg.reset_for_tests()
    sj._nightly_attempted_at.clear()
    yield
    oqc.reset_for_tests()
    oqg.reset_for_tests()
    sj._nightly_attempted_at.clear()


def _sym(ticker, expiry, kind, strike):
    return "%s%s%s%08d" % (ticker, expiry.strftime("%y%m%d"), kind, int(round(strike * 1000)))


def _chain(ticker, expiry, n_strikes=17, kinds=("C", "P"), spot=100.0):
    """A clean chain: n_strikes strikes centred on spot, both types unless told otherwise."""
    out = []
    half = n_strikes // 2
    for i in range(-half, n_strikes - half):
        k = spot + i
        for kind in kinds:
            d = (0.5 if i == 0 else 0.3) * (1 if kind == "C" else -1)
            out.append({"option_symbol": _sym(ticker, expiry, kind, k), "nbbo_bid": 1.0,
                        "nbbo_ask": 1.1, "delta": d, "implied_volatility": 0.2,
                        "volume": 1, "open_interest": 1})
    return out


def _refused():
    from integrations.uw_governor import ACCOUNT_EXHAUSTED, UWUnavailable
    return UWUnavailable(ACCOUNT_EXHAUSTED, caller=oqc.CALLER_TAG, detail="shed:rate_limited")


class _Conn:
    def __init__(self, sink):
        self.sink = sink

    async def execute(self, sql, *args):
        self.sink.append(args)

    async def fetch(self, sql, *args):
        return []


class _Pool:
    def __init__(self, sink):
        self.sink = sink

    def acquire(self):
        sink = self.sink

        class _A:
            async def __aenter__(self):
                return _Conn(sink)

            async def __aexit__(self, *a):
                return False
        return _A()


def _run_oqc(answer, now, sink=None):
    """The REAL oqc.capture_slot. `answer(ticker, expiry, option_type)` -> what fetch_expiry
    returns as raw (a chain, None, or a governor sentinel). Returns (summary, finished, calls)."""
    import database.postgres_client as pg

    finished, calls = [], []
    sink = sink if sink is not None else []

    async def fake_fetch(ticker, expiry, option_type=None):
        calls.append((ticker, expiry, option_type))
        raw = answer(ticker, expiry, option_type)
        if raw is None or not isinstance(raw, list):
            return raw, 0
        return raw, len(raw)

    async def fake_pool():
        return _Pool(sink)

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


# ── 1. a slot that stored nothing stays due ─────────────────────────────────

def test_1120s_1230_slot_replayed_is_captured_on_the_next_wake():
    """12:30:01 the governor refuses every call (never sent); 12:31:01 it serves them."""
    out1, fin1, _c1 = _run_oqc(lambda t, e, k: _refused(), AT_1230)
    assert out1["slot"] == "12:30" and out1["rows"] == 0
    assert out1["tickers_missing"] and out1["refused"] == out1["planned"]
    assert fin1[0][0] == job_runs.STATUS_COMPLETED_DEFECTIVE
    assert "stays due until 12:55 ET" in fin1[0][2], fin1

    out2, fin2, calls2 = _run_oqc(lambda t, e, k: _chain(t, e), AT_1230 + timedelta(minutes=1))
    assert out2.get("reason") != "already captured", "the 12:31 wake-up found it done"
    assert out2["slot"] == "12:30"
    assert len(out2["tickers_saved"]) == 8 and out2["tickers_missing"] == []
    assert fin2[0][0] == job_runs.STATUS_OK
    assert calls2, "the second wake-up made no calls"


def test_a_slot_the_vendor_answered_with_nothing_also_stays_due():
    """None (a 429, a 500) is a SPENT call -- and the slot still stored nothing."""
    out1, _f, _c = _run_oqc(lambda t, e, k: None, AT_1230)
    assert out1["rows"] == 0 and out1["calls"] > 0 and out1["refused"] == 0
    out2, _f2, _c2 = _run_oqc(lambda t, e, k: _chain(t, e), AT_1230 + timedelta(minutes=1))
    assert out2.get("reason") != "already captured"
    assert out2["rows"] > 0


def test_re_asks_spend_only_the_slots_first_share():
    """A vendor answering empty (a 500, every minute) for the whole grace. Uncapped, each re-ask
    took a fresh `remaining // remaining_slots`, and 25 of them leave the close ~4% of its due."""
    first, _f, _c = _run_oqc(lambda t, e, k: None, AT_1230)
    share = first["allowance"]
    assert first["calls"] == min(share, first["planned"])
    total = first["calls"]
    for m in range(1, 25):
        out, _f, _c = _run_oqc(lambda t, e, k: None, AT_1230 + timedelta(minutes=m))
        assert out["slot"] == "12:30", m
        total += out["calls"]
    assert total <= share, (total, share)
    assert oqc._calls_used <= share
    # ...and the close is still owed its full share of what the session had.
    ceiling = oqc.session_ceiling()
    remaining_slots = sum(1 for s in oqc.SLOT_TIMES_ET if s > _dt.time(12, 30))
    assert oqc.slot_allowance(oqc._calls_used, remaining_slots, ceiling) >= share


def test_a_refused_call_is_not_a_spent_call():
    out, _f, _c = _run_oqc(lambda t, e, k: _refused(), AT_1230)
    assert out["calls"] == 0
    assert oqc._calls_used == 0, "refused re-asks would eat the later slots' budget"


def test_the_retry_is_still_bounded_by_the_grace():
    _run_oqc(lambda t, e, k: _refused(), AT_1230)
    late = datetime(2026, 11, 20, 12, 55, 30, tzinfo=ET).astimezone(UTC)
    out, _f, calls = _run_oqc(lambda t, e, k: _chain(t, e), late)
    assert out["slot"] is None and out["reason"] == "no slot due"
    assert calls == []


CLOSE_1120 = datetime(2026, 11, 20, 15, 59, 1, tzinfo=ET).astimezone(UTC)


@pytest.mark.parametrize("answer", [lambda t, e, k: _refused(), lambda t, e, k: None],
                         ids=["refused", "vendor-empty"])
def test_the_close_never_re_asks_after_1600(answer):
    """The 15:59 grace runs to 16:01; a re-ask at 16:00:01 would store post-close quotes as
    15:59's. A close that stored nothing is done once tried, and says nothing about staying due."""
    first, fin, _c = _run_oqc(answer, CLOSE_1120)
    assert first["slot"] == "15:59" and first["rows"] == 0
    assert "stays_due_until" not in first and "stays due" not in fin[0][2]
    out, _f, calls = _run_oqc(lambda t, e, k: _chain(t, e), CLOSE_1120 + timedelta(minutes=1))
    assert out.get("reason") == "already captured" and calls == []


def test_a_slot_that_saved_one_ticker_is_done():
    """Re-asking it would overwrite AAPL's rows with later quotes."""
    _run_oqc(lambda t, e, k: _chain(t, e) if t == "AAPL" else None, AT_1230)
    out, _f, calls = _run_oqc(lambda t, e, k: _chain(t, e), AT_1230 + timedelta(minutes=1))
    assert out["reason"] == "already captured" and calls == []


def test_a_slot_whose_every_pair_is_absent_is_done():
    _run_oqc(lambda t, e, k: [], AT_1230)
    out, _f, calls = _run_oqc(lambda t, e, k: _chain(t, e), AT_1230 + timedelta(minutes=1))
    assert out["reason"] == "already captured" and calls == []


# ── 2. a capped chain is re-asked by contract type ──────────────────────────

#: QQQ's same-day chain on 11-20: more than one response holds. 300 strikes = 600 contracts; a
#: whole-chain ask returns the first 500 (the cap), each typed ask returns its 300.
def _qqq_answer(t, e, k):
    if t == "QQQ" and e == FRI:
        full = _chain(t, e, n_strikes=300, spot=500.0)
        if k is None:
            return full[:oqc.UW_CONTRACT_CAP]
        letter = "C" if k == "call" else "P"
        return [c for c in full if c["option_symbol"][len(t) + 6] == letter]
    return _chain(t, e)


def _qqq_rows(sink):
    return [a for a in sink if a[3] == "QQQ" and a[4] == FRI]


def test_oqc_a_capped_chain_is_split_and_stored_untruncated():
    sink = []
    out, fin, calls = _run_oqc(_qqq_answer, AT_1230, sink)
    key = "QQQ:%s" % FRI.isoformat()
    assert out["split"] == {key: oqc.SPLIT_OK}, out["split"]
    assert key not in out["truncated"]
    typed = [k for t, e, k in calls if t == "QQQ" and e == FRI]
    assert typed == [None, "call", "put"]
    assert out["calls"] == out["planned"] + 2
    rows = _qqq_rows(sink)
    assert rows and all(r[17] == 300 and r[18] is False for r in rows), \
        {(r[17], r[18]) for r in rows}
    assert fin[0][0] == job_runs.STATUS_OK


def test_oqc_the_split_never_sheds_a_later_ticker(monkeypatch):
    """No spare budget: the capped chain is kept and marked, and nobody is shed for it."""
    # 8 slots remain from 12:30; 16 pairs x 8 = an allowance of exactly 16, so no spare.
    monkeypatch.setattr(oqc, "session_ceiling", lambda: 16 * 8)
    out, _f, calls = _run_oqc(_qqq_answer, AT_1230)
    key = "QQQ:%s" % FRI.isoformat()
    assert out["planned"] == 16, out["planned"]
    assert out["split"] == {key: oqc.SPLIT_NO_BUDGET}
    assert key in out["truncated"]
    assert out["shed"] == 0 and len(out["tickers_saved"]) == 8
    assert [k for _t, _e, k in calls if k] == []


def test_a_split_whose_filter_is_not_honoured_is_a_failure_not_a_merge():
    async def ignores_filter(ticker, expiry, option_type=None):
        full = _chain(ticker, expiry, n_strikes=300, spot=500.0)[:oqc.UW_CONTRACT_CAP]
        return full, len(full)

    raw, n, spent, outcome = asyncio.run(oqc.split_by_type(ignores_filter, "QQQ", FRI))
    assert (raw, outcome, spent) == (None, oqc.SPLIT_FAILED, 1)


def test_a_half_still_at_the_cap_stays_truncated():
    async def huge(ticker, expiry, option_type=None):
        letter = "C" if option_type == "call" else "P"
        half = _chain(ticker, expiry, n_strikes=600, kinds=(letter,), spot=500.0)
        return half, len(half)

    raw, n, spent, outcome = asyncio.run(oqc.split_by_type(huge, "QQQ", FRI))
    assert outcome == oqc.SPLIT_CAPPED and n == 600 and spent == 2 and len(raw) == 1200


def test_split_spare_reserves_every_pair_not_yet_reached():
    assert oqc.split_spare(allowance=8, used_here=2, pairs_after=6) == 0
    assert oqc.split_spare(allowance=10, used_here=2, pairs_after=6) == 2


def test_grid_a_capped_chain_is_split_from_spare_budget():
    import database.postgres_client as pg
    from integrations import uw_governor as gov

    calls, sink = [], []

    async def fake_fetch(ticker, expiry, option_type=None):
        calls.append((ticker, option_type))
        if ticker == "QQQ":
            full = _chain(ticker, expiry, n_strikes=300, spot=100.0)
            if option_type is None:
                raw = full[:oqg.UW_CONTRACT_CAP]
            else:
                letter = "C" if option_type == "call" else "P"
                raw = [c for c in full if c["option_symbol"][len(ticker) + 6] == letter]
        else:
            raw = _chain(ticker, expiry)
        return raw, len(raw)

    async def fake_pool():
        return _Pool(sink)

    gov.QUOTAS[oqg.CALLER_TAG] = (1000, gov.TIER_STANDARD)
    os.environ[oqg.ENV_FLAG] = "true"
    real_fetch, real_pool = oqg._fetch, pg.get_postgres_client
    oqg._fetch, pg.get_postgres_client = fake_fetch, fake_pool
    try:
        out = asyncio.run(oqg.capture_slot(
            now=datetime(2026, 10, 26, 11, 0, tzinfo=ET).astimezone(UTC)))
    finally:
        oqg._fetch, pg.get_postgres_client = real_fetch, real_pool
        del os.environ[oqg.ENV_FLAG]
        gov.QUOTAS[oqg.CALLER_TAG] = (640, gov.TIER_STANDARD)   # the RULED figure

    keys = [k for k in out["split"]]
    assert len(keys) == 1 and keys[0].startswith("QQQ:"), out["split"]
    assert out["split"][keys[0]] == oqc.SPLIT_OK
    assert not any(t.startswith("QQQ:") for t in out["truncated"])
    assert [k for t, k in calls if t == "QQQ"] == [None, "call", "put"]
    assert out["calls"] == 10 and out["shed"] == 0 and out["captured"] == 8


# ── 3. a held-back session's nightly is carried past midnight ───────────────

@pytest.mark.parametrize("et, expected", [
    (datetime(2026, 11, 20, 2, 0), date(2026, 11, 19)),    # Fri small hours: Thu carried
    (datetime(2026, 11, 21, 3, 0), date(2026, 11, 20)),    # Sat small hours: Fri carried
    (datetime(2026, 11, 20, 8, 59), date(2026, 11, 19)),   # last minute of the carry
    (datetime(2026, 11, 20, 9, 0), None),                  # 09:00: the carry is over
    (datetime(2026, 11, 23, 3, 0), None),                  # Mon: Sunday was no session
    (datetime(2026, 11, 27, 3, 0), None),                  # Thanksgiving was no session
    (datetime(2026, 11, 26, 3, 0), date(2026, 11, 25)),    # Wed carried into the holiday
])
def test_which_session_is_carried(et, expected):
    assert sj.carried_nightly_session(et) == expected


@pytest.fixture
def ledger(monkeypatch):
    asked, ran = [], []
    state = {"completed": False}

    async def fake_has_completed(job, session_date):
        asked.append(session_date)
        return state["completed"]

    async def fake_record(job_name, coro_fn, session_date=None):
        ran.append((job_name, session_date))

    import jobs.job_runs as jr
    monkeypatch.setattr(jr, "has_completed", fake_has_completed, raising=False)
    monkeypatch.setattr(sj, "_record", fake_record)
    return asked, ran, state


def test_1119s_nightly_is_retried_after_midnight_for_1119(ledger):
    asked, ran, _state = ledger
    asyncio.run(sj._carry_tick(datetime(2026, 11, 20, 2, 0)))
    assert asked == [date(2026, 11, 19)]
    assert ran == [("nightly", date(2026, 11, 19))]


def test_the_carry_stops_once_the_pass_completes(ledger):
    asked, ran, state = ledger
    state["completed"] = True
    asyncio.run(sj._carry_tick(datetime(2026, 11, 20, 2, 0)))
    assert ran == []


def test_the_carry_keeps_the_evenings_15_minute_spacing_through_midnight(ledger):
    _asked, ran, _state = ledger
    asyncio.run(sj._maybe_run_nightly(datetime(2026, 11, 19, 23, 48), "2026-11-19"))
    asyncio.run(sj._carry_tick(datetime(2026, 11, 20, 0, 1)))       # 13 min later: waits
    assert len(ran) == 1
    asyncio.run(sj._carry_tick(datetime(2026, 11, 20, 0, 4)))       # 16 min later: runs
    assert ran == [("nightly", date(2026, 11, 19)), ("nightly", date(2026, 11, 19))]


def test_nothing_is_carried_after_0900(ledger):
    _asked, ran, _state = ledger
    asyncio.run(sj._carry_tick(datetime(2026, 11, 20, 9, 0)))
    assert ran == []


def _calls_and_gates(fn_name):
    """(call names, set of call names nested under an `if is_weekday(...)`) in fn_name."""
    tree = ast.parse((_BACKEND / "jobs" / "stable_jobs.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == fn_name)
    gated = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and "is_weekday" in ast.unparse(node.test):
            for sub in node.body:
                for c in ast.walk(sub):
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Name):
                        gated.add(c.func.id)
    called = {c.func.id for c in ast.walk(fn)
              if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    return called, gated


def test_the_loop_runs_the_carry_outside_the_weekday_gate():
    """Friday's session is carried into SATURDAY's small hours, when the gate is shut."""
    called, gated = _calls_and_gates("stable_engine_loop")
    assert "_carry_tick" in called
    assert "_carry_tick" not in gated
