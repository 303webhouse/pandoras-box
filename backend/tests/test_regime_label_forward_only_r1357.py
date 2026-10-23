"""The nightly labels forward only, and the capture stores every bar it fetched. R-IV.1357(a).

THE FAULT THIS CLOSES, measured on production and not reasoned about.

On 2026-10-23 at 02:08:40Z Polygon served SPY/QQQ/IWM daily bars for 10-15, 10-16, 10-19, 10-20
and 10-21, and withheld 10-22. The regime nightly had run at 01:3xZ that morning and labelled
**2026-10-20** -- two sessions behind, while 10-21 was sitting in the vendor's own response.

Two separate mechanisms produced that, and fixing either alone leaves the system broken:

  1. `capture_session` fetched a SEVEN-DAY RANGE (`RANGE_LOOKBACK_DAYS = 7`) and used exactly
     one bar from it -- the target session's. Every other bar was discarded. Since that function
     is the ONLY writer of `regime_daily_bars` and is called once a night with that night's own
     target, a session withheld on the night it was the target was never asked for again. 10-21
     was refused at +5.6h after its close on the night of 10-21, and from then on it was
     unreachable forever.

  2. The withheld-target fallback (R-IV.1278(b)3) chose "the newest settled session that HAS a
     bar and HAS NO LABEL". That reads like catching up and is the opposite: it consults the BAR
     TABLE, not the vendor, so a session with no stored bar is invisible to it. **And it walked
     BACKWARDS.** Once 10-20 held a label, the newest unlabelled session with a bar became
     10-19, then 10-16 -- each night writing a row OLDER than the night before while the real
     lag grew. A pipeline that reports progress by moving backwards through history is worse
     than one that stops, because it looks alive. R-IV.1357(a)2 removes it.

WHY THE ORDER IS LOAD-BEARING, and the reason the required fixture checks it. `held_sessions`
and the pending-label counters are carried session to session by the replay, and a row's
`change` text describes a transition from the row before it. Writing newest-first would store
each row correctly while leaving a reader who follows `created_at` watching the series run
backwards.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from jobs import regime_job                                          # noqa: E402
from stable_engine import bars_polygon as bp                         # noqa: E402

TRADING = {dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 21),
           dt.date(2026, 10, 22), dt.date(2026, 10, 23)}


class FakeConn:
    """Only the four methods this path uses, each answering from explicit fixture state."""

    def __init__(self, *, newest_labelled, bar_dates):
        self.newest_labelled = newest_labelled
        self.bar_dates = sorted(bar_dates)
        self.executed = []

    async def fetchval(self, sql, *a):
        if "MAX(as_of)" in sql:
            return self.newest_labelled
        return None

    async def fetch(self, sql, *a):
        if "FROM regime_daily_bars" in sql and "DISTINCT b.date" in sql:
            after, through = a[0], a[1]
            # THE FAKE READS THE PREDICATE OUT OF THE SQL rather than restating it.
            # First draft hardcoded `d > after`, so flipping the real query to `>=`
            # left every behavioural test GREEN -- they were testing the fake. A fake
            # that repeats the rule it is meant to check cannot fail when the rule
            # changes.
            strict = "b.date > $1::date" in sql
            assert strict or "b.date >= $1::date" in sql, "unrecognised predicate"
            return [{"date": d} for d in self.bar_dates
                    if (after is None or (d > after if strict else d >= after))
                    and d <= through]
        if "COUNT(DISTINCT ticker)" in sql:
            return [{"date": d, "n": 3} for d in self.bar_dates]
        return []

    async def fetchrow(self, sql, *a):
        return None

    async def execute(self, sql, *a):
        self.executed.append(a)


@pytest.fixture
def harness(monkeypatch):
    """The target is WITHHELD and two earlier sessions have bars but no label."""
    written, audits = [], []

    monkeypatch.setattr(regime_job, "load_designated_series",
                        _async(lambda conn: {"SPY": [object()] * 300,
                                             "QQQ": [object()] * 300,
                                             "IWM": [object()] * 300}))
    monkeypatch.setattr(regime_job, "cutover_state",
                        _async(lambda conn, v, rules=None: {"ok": True, "inherited": False}))
    monkeypatch.setattr(regime_job, "build_sessions",
                        _async(lambda conn, series, rules=None, settled_through=None:
                               ([object()] * len(TRADING),
                                 {"v2_inputs": True, "vix": {"paired_dates": 300}})))
    monkeypatch.setattr(regime_job, "replay", lambda sessions, rules: {"shown": [
        {"as_of": d.isoformat(), "shown_regime": "range_chop", "regime": "range_chop",
         "label": "CORRECTION", "tags": [], "basis": "x", "change": None, "blocked": None,
         "rules_version": "v2.1"}
        for d in sorted(TRADING)]})

    async def _write(conn, row, *, seeded, close_source):
        written.append(row["as_of"])
        return {"as_of": row["as_of"]}

    async def _audit(conn, *, action, detail, as_of=None, rows_written=0, rules_version=None):
        audits.append((action, detail))

    # PATCHED ON regime_seed, NOT regime_job: run_nightly imports _write_snapshot from
    # jobs.regime_seed INSIDE the function (regime_seed imports from regime_job, so a
    # module-level import would be circular). Patching the name on regime_job would be
    # silently ignored -- the function re-imports the real one on every call.
    import jobs.regime_seed as _seed
    monkeypatch.setattr(_seed, "_write_snapshot", _write)
    monkeypatch.setattr(regime_job, "_audit", _audit)
    monkeypatch.setattr(regime_job, "load_rules", lambda *a, **k: {"version": "v2.1"})

    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "is_session_settled", lambda d: d in TRADING)
    monkeypatch.setattr(cal, "last_settled_session", lambda: dt.date(2026, 10, 23))
    monkeypatch.setattr(cal, "settlement_reason", lambda d: "fixture")

    # the target (10-23) is WITHHELD by the vendor; the capture backfilled 10-21 and 10-22
    monkeypatch.setattr(bp, "capture_session",
                        _async(lambda conn, session, tickers: {
                            "degraded": True, "written": 6,
                            "backfilled": ["2026-10-21", "2026-10-22"],
                            "candidates": ["2026-10-21", "2026-10-22", "2026-10-23"],
                            "reason": "SPY: polygon has no bar for 2026-10-23 yet"}))
    return written, audits


def _async(fn):
    async def inner(*a, **k):
        return fn(*a, **k)
    return inner


# ── R-IV.1357(a)3: the required fixture ─────────────────────────────────────

@pytest.mark.asyncio
async def test_BOTH_unlabelled_sessions_are_labelled_IN_ORDER(harness):
    """The ruling's test. Newest labelled is 10-20; 10-21 and 10-22 have bars and no label; the
    target 10-23 is withheld. Both must be labelled, oldest first."""
    written, audits = harness
    conn = FakeConn(newest_labelled=dt.date(2026, 10, 20),
                    bar_dates=[dt.date(2026, 10, 19), dt.date(2026, 10, 20),
                               dt.date(2026, 10, 21), dt.date(2026, 10, 22)])

    out = await regime_job.run_nightly(conn)

    assert written == ["2026-10-21", "2026-10-22"], written
    assert out["written"] == 2
    assert out["labelled"] == ["2026-10-21", "2026-10-22"]


@pytest.mark.asyncio
async def test_NOTHING_at_or_before_the_newest_labelled_session_is_touched(harness):
    """The other half, and the half the old fallback got wrong: 10-19 has a bar and no v2.1
    label, and it must NOT be labelled, because it is older than the newest labelled session."""
    written, _ = harness
    conn = FakeConn(newest_labelled=dt.date(2026, 10, 20),
                    bar_dates=[dt.date(2026, 10, 19), dt.date(2026, 10, 20),
                               dt.date(2026, 10, 21), dt.date(2026, 10, 22)])
    await regime_job.run_nightly(conn)

    assert "2026-10-19" not in written, "the backward walk is back"
    assert "2026-10-20" not in written, "the newest labelled session must not be revisited"


@pytest.mark.asyncio
async def test_the_WITHHELD_TARGET_is_not_labelled_because_it_has_no_bar(harness):
    written, _ = harness
    conn = FakeConn(newest_labelled=dt.date(2026, 10, 20),
                    bar_dates=[dt.date(2026, 10, 21), dt.date(2026, 10, 22)])
    await regime_job.run_nightly(conn)
    assert "2026-10-23" not in written


@pytest.mark.asyncio
async def test_a_withheld_target_is_audited_as_PENDING_not_as_a_failure(harness):
    _, audits = harness
    conn = FakeConn(newest_labelled=dt.date(2026, 10, 20),
                    bar_dates=[dt.date(2026, 10, 21), dt.date(2026, 10, 22)])
    await regime_job.run_nightly(conn)
    actions = [a for a, _d in audits]
    assert "pending_source" in actions
    assert "degraded" not in actions


@pytest.mark.asyncio
async def test_the_BACKFILL_is_audited_with_the_sessions_it_stored(harness):
    _, audits = harness
    conn = FakeConn(newest_labelled=dt.date(2026, 10, 20),
                    bar_dates=[dt.date(2026, 10, 21), dt.date(2026, 10, 22)])
    await regime_job.run_nightly(conn)
    rows = [d for a, d in audits if a == "backfill"]
    assert rows and "2026-10-21" in rows[0] and "2026-10-22" in rows[0]


@pytest.mark.asyncio
async def test_NOTHING_NEW_is_a_recorded_NOOP_and_not_a_silent_return(harness):
    """When every session with a bar is already labelled the run must SAY so. A nightly that
    skipped a session silently is the R-IV.1175 fault."""
    written, audits = harness
    conn = FakeConn(newest_labelled=dt.date(2026, 10, 22),
                    bar_dates=[dt.date(2026, 10, 21), dt.date(2026, 10, 22)])
    out = await regime_job.run_nightly(conn)
    assert written == []
    assert out["written"] == 0
    assert "noop" in out
    assert "noop" in [a for a, _d in audits]


@pytest.mark.asyncio
async def test_an_EMPTY_snapshot_table_labels_everything_it_can(harness):
    """`newest_labelled_session` returning None means nothing is labelled yet -- not "stop"."""
    written, _ = harness
    conn = FakeConn(newest_labelled=None,
                    bar_dates=[dt.date(2026, 10, 21), dt.date(2026, 10, 22)])
    await regime_job.run_nightly(conn)
    assert written == ["2026-10-21", "2026-10-22"]


@pytest.mark.asyncio
async def test_a_bar_for_an_UNSETTLED_session_is_not_labelled_early(harness):
    """`sessions_after` is bounded at the target AND filtered by the calendar."""
    written, _ = harness
    conn = FakeConn(newest_labelled=dt.date(2026, 10, 20),
                    bar_dates=[dt.date(2026, 10, 21), dt.date(2026, 10, 24)])
    await regime_job.run_nightly(conn)
    assert written == ["2026-10-21"], written


# ── (a)1: the capture stores the whole range, all-or-nothing per session ────

@pytest.mark.asyncio
async def test_the_capture_BACKFILLS_a_session_that_has_no_stored_bar(monkeypatch):
    """The target is withheld and an earlier session has no stored bar: that one is verified and
    written, and the target is reported degraded without stopping the rest."""
    stored_writes = []

    class _Conn:
        async def execute(self, sql, *a):
            stored_writes.append((a[0], a[1]))

        async def fetch(self, sql, *a):
            return [{"date": dt.date(2026, 10, 20), "n": 3}]        # only 10-20 is stored

    served = [dt.date(2026, 10, 20), dt.date(2026, 10, 21)]          # 10-22 withheld

    async def _fetch(t, s, e):
        return [{"date": d, "o": 1.0, "h": 2.0, "l": 0.5, "c": 100.0, "v": 1} for d in served]

    async def _verify(t, session, close):
        return True, "agrees"

    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "is_session_settled", lambda d: True)
    monkeypatch.setattr(cal, "settlement_reason", lambda d: "fixture")
    monkeypatch.setattr(bp, "fetch_daily", _fetch)
    monkeypatch.setattr(bp, "verify_close", _verify)
    monkeypatch.setattr(bp, "CALL_GAP_S", 0.0)

    out = await bp.capture_session(_Conn(), dt.date(2026, 10, 22), ("SPY", "QQQ", "IWM"))

    assert out["degraded"] is True, "the target itself was withheld"
    assert out["backfilled"] == ["2026-10-21"], out
    assert {d for _t, d in stored_writes} == {dt.date(2026, 10, 21)}, (
        "only the session that had no stored bar is written")


@pytest.mark.asyncio
async def test_a_backfill_session_is_ALL_OR_NOTHING_across_tickers(monkeypatch):
    """One ticker failing verification drops that SESSION whole -- and leaves its neighbours."""
    stored_writes = []

    class _Conn:
        async def execute(self, sql, *a):
            stored_writes.append((a[0], a[1]))

        async def fetch(self, sql, *a):
            return []

    served = [dt.date(2026, 10, 20), dt.date(2026, 10, 21)]

    async def _fetch(t, s, e):
        return [{"date": d, "o": 1.0, "h": 2.0, "l": 0.5, "c": 100.0, "v": 1} for d in served]

    async def _verify(t, session, close):
        if t == "IWM" and session == dt.date(2026, 10, 20):
            return False, "IWM: 2026-10-20 close disagrees"
        return True, "agrees"

    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "is_session_settled", lambda d: True)
    monkeypatch.setattr(cal, "settlement_reason", lambda d: "fixture")
    monkeypatch.setattr(bp, "fetch_daily", _fetch)
    monkeypatch.setattr(bp, "verify_close", _verify)
    monkeypatch.setattr(bp, "CALL_GAP_S", 0.0)

    out = await bp.capture_session(_Conn(), dt.date(2026, 10, 21), ("SPY", "QQQ", "IWM"))

    dates = {d for _t, d in stored_writes}
    assert dt.date(2026, 10, 20) not in dates, "a session with one bad ticker must not be written"
    assert dt.date(2026, 10, 21) in dates, "and its neighbour must still go in"
    assert out["degraded"] is False, "the TARGET verified, so the target is not degraded"


@pytest.mark.asyncio
async def test_an_UNREADABLE_bar_table_falls_back_to_the_TARGET_ONLY_and_says_so(monkeypatch):
    """The third answer. None is not an empty set: an empty set would send the UW verifier over
    the whole range every night."""
    class _Conn:
        async def execute(self, sql, *a):
            pass

        async def fetch(self, sql, *a):
            raise RuntimeError("table unreadable")

    served = [dt.date(2026, 10, 20), dt.date(2026, 10, 21)]

    async def _fetch(t, s, e):
        return [{"date": d, "o": 1.0, "h": 2.0, "l": 0.5, "c": 100.0, "v": 1} for d in served]

    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "is_session_settled", lambda d: True)
    monkeypatch.setattr(cal, "settlement_reason", lambda d: "fixture")
    monkeypatch.setattr(bp, "fetch_daily", _fetch)
    monkeypatch.setattr(bp, "verify_close", _async(lambda t, s, c: (True, "agrees")))
    monkeypatch.setattr(bp, "CALL_GAP_S", 0.0)

    out = await bp.capture_session(_Conn(), dt.date(2026, 10, 21), ("SPY",))
    assert out["backfilled"] == []
    assert "backfill_blind" in out
    assert out["degraded"] is False


@pytest.mark.asyncio
async def test_sessions_with_stored_bars_needs_EVERY_ticker():
    """A date holding SPY but not IWM was never written by this path, so it counts as missing."""
    class _Conn:
        async def fetch(self, sql, *a):
            return [{"date": dt.date(2026, 10, 20), "n": 3},
                    {"date": dt.date(2026, 10, 21), "n": 2}]        # partial

    got = await bp.sessions_with_stored_bars(_Conn(), ["SPY", "QQQ", "IWM"],
                                             dt.date(2026, 10, 14))
    assert got == {dt.date(2026, 10, 20)}


@pytest.mark.asyncio
async def test_sessions_with_stored_bars_returns_NONE_on_failure():
    class _Conn:
        async def fetch(self, sql, *a):
            raise RuntimeError("nope")

    assert await bp.sessions_with_stored_bars(_Conn(), ["SPY"], dt.date(2026, 10, 14)) is None
