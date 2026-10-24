"""R-IV.1423(h)2 — the regime nightly fix: dated verifier, form (b), STOP-never-SKIP, as-of labels.

THE TWO STRUCTURAL FAULTS (C:/lane-state/REGIME-FIX-PROPOSAL.md §0), and why both had to go together:

  F1  the slot: the 21:3x ET run targeted its OWN session, which Polygon withholds for more than
      6.1h after the close -- so the target was never served.
  F2  the verifier: `uw_chart_close` returned only the chart's NEWEST close, so every session but
      the newest failed verification by construction and the back-fill could never write.

They blocked each other, which is the only reason nothing was mis-labelled: no bar was ever
stored, so the SKIP labeller had nothing to skip across. Fixing the verifier REMOVES that
accidental protection, so STOP-never-SKIP must land with it. These tests pin all four parts.

THE CALENDAR IS REAL in the walk tests. Thanksgiving 2026-11-26 is a weekday market holiday in
`market_calendar.MARKET_HOLIDAYS`; a fixture spanning it and two weekends is exactly the case a
naive day-by-day STOP gets wrong (it would halt at the first Saturday).
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from jobs import regime_job                                          # noqa: E402
from models.regime_inputs import Bar                                 # noqa: E402
from stable_engine import bars_polygon as bp                         # noqa: E402

D = dt.date


def _async(fn):
    async def inner(*a, **k):
        return fn(*a, **k)
    return inner


# ── §3.1 STOP, NEVER SKIP — walked on the MARKET CALENDAR ──────────────────

# Fri 11-20 labelled; Mon-Wed 11-23..25; THANKSGIVING Thu 11-26; Fri 11-27; weekend; Mon 11-30.
THANKSGIVING_SPAN = [D(2026, 11, 23), D(2026, 11, 24), D(2026, 11, 25),
                     D(2026, 11, 27), D(2026, 11, 30)]


def test_a_span_across_TWO_WEEKENDS_AND_A_HOLIDAY_labels_STRAIGHT_THROUGH():
    """The proposal §3.1 condition. Saturday, Sunday and Thanksgiving have no session, so they
    are crossed -- not treated as gaps. A day-by-day walk would stop at 11-21."""
    run, stopped = regime_job.contiguous_run(D(2026, 11, 20), THANKSGIVING_SPAN, D(2026, 11, 30),
                                             settled=lambda d: True)
    assert run == THANKSGIVING_SPAN, run
    assert stopped is None


def test_the_walk_never_even_ASKS_about_a_weekend_or_a_holiday():
    """Proof the crossing is structural, not a lucky `settled()` answer: the walk steps with
    `next_trading_day`, so a closed day is never visited at all."""
    asked = []
    regime_job.contiguous_run(D(2026, 11, 20), THANKSGIVING_SPAN, D(2026, 11, 30),
                              settled=lambda d: asked.append(d) or True)
    closed = {D(2026, 11, 21), D(2026, 11, 22), D(2026, 11, 26), D(2026, 11, 28), D(2026, 11, 29)}
    assert not closed & set(asked), sorted(closed & set(asked))
    assert asked == THANKSGIVING_SPAN


def test_a_MISSING_SETTLED_SESSION_STOPS_the_run_and_nothing_after_it_is_labelled():
    """The required STOP. 11-25 is settled and has no bar: 11-23 and 11-24 are labelled, and
    11-27 and 11-30 are NOT -- even though their bars are stored. SKIP would have labelled 11-27
    against 11-24 as its previous session."""
    stored = [d for d in THANKSGIVING_SPAN if d != D(2026, 11, 25)]
    run, stopped = regime_job.contiguous_run(D(2026, 11, 20), stored, D(2026, 11, 30),
                                             settled=lambda d: True)
    assert run == [D(2026, 11, 23), D(2026, 11, 24)], run
    assert stopped["kind"] == "gap" and stopped["session"] == D(2026, 11, 25)
    assert "2026-11-25" in stopped["detail"] and "STOPPED" in stopped["detail"]


def test_a_gap_on_the_FIRST_session_labels_nothing():
    run, stopped = regime_job.contiguous_run(D(2026, 10, 20), [D(2026, 10, 22), D(2026, 10, 23)],
                                             D(2026, 10, 23), settled=lambda d: True)
    assert run == [] and stopped["kind"] == "gap" and stopped["session"] == D(2026, 10, 21)


def test_an_UNSETTLED_session_stops_the_walk_as_unsettled_not_as_a_gap():
    run, stopped = regime_job.contiguous_run(D(2026, 11, 20), THANKSGIVING_SPAN, D(2026, 11, 30),
                                             settled=lambda d: d < D(2026, 11, 30))
    assert run == THANKSGIVING_SPAN[:-1]
    assert stopped["kind"] == "unsettled" and stopped["session"] == D(2026, 11, 30)


def test_forward_only_survives_nothing_at_or_before_the_newest_label():
    run, _ = regime_job.contiguous_run(D(2026, 11, 24), [D(2026, 11, 20)] + THANKSGIVING_SPAN,
                                       D(2026, 11, 30), settled=lambda d: True)
    assert run == [D(2026, 11, 25), D(2026, 11, 27), D(2026, 11, 30)]


def test_nothing_labelled_yet_starts_at_the_first_stored_bar():
    run, stopped = regime_job.contiguous_run(None, THANKSGIVING_SPAN, D(2026, 11, 30),
                                             settled=lambda d: True)
    assert run == THANKSGIVING_SPAN and stopped is None


# ── the nightly, end to end through a fake connection ─────────────────────

class FakeConn:
    def __init__(self, *, newest_labelled, bar_dates):
        self.newest_labelled = newest_labelled
        self.bar_dates = sorted(bar_dates)

    async def fetchval(self, sql, *a):
        return self.newest_labelled if "MAX(as_of)" in sql else None

    async def fetch(self, sql, *a):
        if "FROM regime_daily_bars" in sql and "DISTINCT b.date" in sql:
            assert "b.date > $1::date" in sql, "forward-only predicate changed"
            after, through = a[0], a[1]
            return [{"date": d} for d in self.bar_dates
                    if (after is None or d > after) and d <= through]
        return []

    async def fetchrow(self, sql, *a):
        return None

    async def execute(self, sql, *a):
        pass


@pytest.fixture
def nightly(monkeypatch):
    """A run on MONDAY 2026-10-26 at 21:3x ET: last settled session 10-26, so form (b)
    targets 10-23. Records the capture's target, every build's inputs, writes and audits."""
    seen = {"capture_target": None, "builds": [], "written": [], "audits": []}
    sessions = [D(2026, 10, d) for d in (19, 20, 21, 22, 23, 26)]
    bars = [Bar(d, c=100.0) for d in sessions]

    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "last_settled_session", lambda: D(2026, 10, 26))
    monkeypatch.setattr(cal, "is_session_settled", lambda d, now=None: d <= D(2026, 10, 26)
                        and cal.is_trading_day(d))
    monkeypatch.setattr(regime_job, "today_et", lambda: D(2026, 10, 26))
    monkeypatch.setattr(regime_job, "load_rules", lambda *a, **k: {"version": "v2.1"})
    monkeypatch.setattr(regime_job, "load_designated_series",
                        _async(lambda conn: {"SPY": list(bars), "QQQ": list(bars),
                                             "IWM": list(bars)}))
    monkeypatch.setattr(regime_job, "cutover_state",
                        _async(lambda conn, v, rules=None: {"ok": True, "inherited": False}))
    vix_loads = []
    seen["vix_loads"] = vix_loads
    monkeypatch.setattr(regime_job, "load_vix_pair",
                        lambda rules: vix_loads.append(1) or ({"2026-10-21": {}}, {"paired_dates": 1}))

    async def _capture(conn, session, tickers):
        seen["capture_target"] = session
        return {"degraded": False, "written": 9, "backfilled": [], "candidates": []}
    monkeypatch.setattr(bp, "capture_session", _capture)

    async def _build(conn, series, rules=None, settled_through=None, vix=None):
        seen.setdefault("vix", []).append(vix)
        newest = max(b.date for b in series["SPY"])
        seen["builds"].append((settled_through, newest.isoformat()))
        ss = sorted({b.date for b in series["SPY"]})
        return [object()] * len(ss), {"v2_inputs": True, "vix": {"paired_dates": 1},
                                      "_dates": ss}
    monkeypatch.setattr(regime_job, "build_sessions", _build)

    def _replay(sessions_, rules):
        # one shown row per session in the build -- the build passed its dates through
        last = seen["builds"][-1][1]
        return {"shown": [{"as_of": d.isoformat(), "shown_regime": "uptrend",
                           "regime": "uptrend", "label": "UP", "tags": [], "basis": "x",
                           "change": None, "blocked": None}
                          for d in sessions if d.isoformat() <= last]}
    monkeypatch.setattr(regime_job, "replay", _replay)

    async def _write(conn, row, *, seeded, close_source):
        seen["written"].append(row["as_of"])
        return {"as_of": row["as_of"]}
    import jobs.regime_seed as _seed
    monkeypatch.setattr(_seed, "_write_snapshot", _write)

    async def _audit(conn, *, action, detail, as_of=None, rows_written=0, rules_version=None):
        seen["audits"].append((action, str(as_of), detail))
    monkeypatch.setattr(regime_job, "_audit", _audit)
    return seen


@pytest.mark.asyncio
async def test_FORM_B_the_monday_run_targets_FRIDAY_one_session_back(nightly):
    await regime_job.run_nightly(FakeConn(newest_labelled=D(2026, 10, 20),
                                          bar_dates=[D(2026, 10, 21), D(2026, 10, 22),
                                                     D(2026, 10, 23)]))
    assert nightly["capture_target"] == D(2026, 10, 23)


@pytest.mark.asyncio
async def test_THE_FIRST_FIXED_RUN_labels_21_22_23_oldest_first_and_marks_the_two_late(nightly):
    """SPINE's expected Monday 10-26: 10-21, 10-22 and 10-23 labelled oldest first. Under form (b)
    10-23's OWN night is 10-26 -- it is ON TIME; 10-21 and 10-22 are late by 2 and 1."""
    out = await regime_job.run_nightly(FakeConn(newest_labelled=D(2026, 10, 20),
                                                bar_dates=[D(2026, 10, 21), D(2026, 10, 22),
                                                           D(2026, 10, 23)]))
    assert nightly["written"] == ["2026-10-21", "2026-10-22", "2026-10-23"]
    assert out["labelled"] == ["2026-10-21", "2026-10-22", "2026-10-23"]
    assert out["late"] == ["2026-10-21", "2026-10-22"]
    rows = {as_of: detail for action, as_of, detail in nightly["audits"] if action == "nightly"}
    assert rows["2026-10-21"].startswith("LATE by 2 session(s)"), rows["2026-10-21"]
    assert rows["2026-10-22"].startswith("LATE by 1 session(s)"), rows["2026-10-22"]
    assert not rows["2026-10-23"].startswith("LATE"), rows["2026-10-23"]


@pytest.mark.asyncio
async def test_EACH_LABEL_IS_BUILT_AS_OF_ITS_OWN_SESSION(nightly):
    """§5. Three builds, one per session, and each saw NO bar after its own session -- although
    the loaded series runs to 10-26."""
    await regime_job.run_nightly(FakeConn(newest_labelled=D(2026, 10, 20),
                                          bar_dates=[D(2026, 10, 21), D(2026, 10, 22),
                                                     D(2026, 10, 23)]))
    assert nightly["builds"] == [("2026-10-21", "2026-10-21"), ("2026-10-22", "2026-10-22"),
                                 ("2026-10-23", "2026-10-23")], nightly["builds"]


@pytest.mark.asyncio
async def test_the_VIX_pair_is_loaded_ONCE_per_run_and_shared_by_every_build(nightly):
    """Two FRED calls per build would multiply on a catch-up and let one run's sessions see
    different VIX data."""
    await regime_job.run_nightly(FakeConn(newest_labelled=D(2026, 10, 20),
                                          bar_dates=[D(2026, 10, 21), D(2026, 10, 22),
                                                     D(2026, 10, 23)]))
    assert nightly["vix_loads"] == [1], nightly["vix_loads"]
    assert len(nightly["vix"]) == 3 and all(v is nightly["vix"][0] for v in nightly["vix"])
    assert nightly["vix"][0] is not None


@pytest.mark.asyncio
async def test_THE_OLD_SKIP_IS_GONE_a_gap_at_10_22_stops_the_run_and_is_AUDITED(nightly):
    """The exact hazard R-IV.1419(b) cited: with 10-22 missing, the old labeller would label 10-23
    computed against 10-21 as its previous session. Now 10-21 is labelled, 10-23 is not, and the
    stop is a regime_audit row."""
    out = await regime_job.run_nightly(FakeConn(newest_labelled=D(2026, 10, 20),
                                                bar_dates=[D(2026, 10, 21), D(2026, 10, 23)]))
    assert nightly["written"] == ["2026-10-21"]
    assert "2026-10-23" not in nightly["written"]
    stops = [(as_of, d) for a, as_of, d in nightly["audits"] if a == "stopped_at_gap"]
    assert stops and stops[0][0] == "2026-10-22", nightly["audits"]
    assert out["stopped"]["kind"] == "gap"


@pytest.mark.asyncio
async def test_a_gap_on_the_first_session_is_a_recorded_noop_and_a_recorded_stop(nightly):
    out = await regime_job.run_nightly(FakeConn(newest_labelled=D(2026, 10, 20),
                                                bar_dates=[D(2026, 10, 22), D(2026, 10, 23)]))
    actions = [a for a, _s, _d in nightly["audits"]]
    assert nightly["written"] == [] and "noop" in out
    assert "stopped_at_gap" in actions and "noop" in actions


def test_FORM_B_on_a_weekday_holiday_targets_the_session_before_the_last_settled_one(monkeypatch):
    """Thanksgiving: the loop still runs (the weekday gate is calendar-only), last settled is
    Wed 11-25, so the target is Tue 11-24 -- ordinary catch-up, and the holiday is never a
    label target (proposal §4)."""
    import stable_engine.market_calendar as cal
    now = dt.datetime(2026, 11, 26, 21, 34, tzinfo=cal.MARKET_TZ)
    lss = cal.last_settled_session(now)
    assert lss == D(2026, 11, 25)
    assert cal.previous_trading_day(lss) == D(2026, 11, 24)


# ── §5 the LATE marker and the as-of truncation, directly ─────────────────

def test_lateness_is_counted_in_scheduled_NIGHTS_on_the_market_calendar():
    run_day = D(2026, 10, 26)                       # Monday
    assert regime_job.lateness(D(2026, 10, 23), run_day) is None          # its own night
    assert regime_job.lateness(D(2026, 10, 22), run_day).startswith("LATE by 1 session(s)")
    assert regime_job.lateness(D(2026, 10, 21), run_day).startswith("LATE by 2 session(s)")
    # across Thanksgiving: 11-25's own night is 11-27 (11-26 is closed), so 11-27 is on time
    assert regime_job.lateness(D(2026, 11, 25), D(2026, 11, 27)) is None


def test_series_through_drops_every_later_bar_and_REFUSES_an_undated_one():
    s = {"SPY": [Bar(D(2026, 10, d)) for d in (21, 22, 23)]}
    cut = regime_job.series_through(s, D(2026, 10, 22))
    assert [b.date for b in cut["SPY"]] == [D(2026, 10, 21), D(2026, 10, 22)]
    with pytest.raises(TypeError):
        regime_job.series_through({"SPY": [Bar(None)]}, D(2026, 10, 22))


# ── §1.1 the DATED verifier ───────────────────────────────────────────────

SERIES = {D(2026, 10, 21): 671.30, D(2026, 10, 22): 668.12, D(2026, 10, 23): 672.05}


@pytest.mark.asyncio
async def test_the_verifier_checks_a_PAST_session_against_ITS_OWN_close(monkeypatch):
    monkeypatch.setattr(bp, "uw_dated_closes", _async(lambda t: dict(SERIES)))
    ok, why = await bp.verify_close("SPY", D(2026, 10, 21), 671.30)
    assert ok is True, why
    ok, why = await bp.verify_close("SPY", D(2026, 10, 22), 668.124)       # within 0.005
    assert ok is True, why


@pytest.mark.asyncio
async def test_a_DISAGREEING_past_close_is_a_MISMATCH(monkeypatch):
    monkeypatch.setattr(bp, "uw_dated_closes", _async(lambda t: dict(SERIES)))
    ok, why = await bp.verify_close("SPY", D(2026, 10, 22), 668.20)
    assert ok is False and "MISMATCH" in why


@pytest.mark.asyncio
async def test_it_FAILS_CLOSED_when_UW_has_no_row_for_the_session(monkeypatch):
    """The series is bounded by a row limit, not by date: a session inside its span may be absent,
    and absence is never agreement."""
    monkeypatch.setattr(bp, "uw_dated_closes", _async(lambda t: dict(SERIES)))
    ok, why = await bp.verify_close("SPY", D(2026, 10, 20), 665.00)
    assert ok is False and "no regular-session row" in why and "could not be verified" in why


@pytest.mark.asyncio
async def test_it_FAILS_CLOSED_when_UW_cannot_answer_at_all(monkeypatch):
    monkeypatch.setattr(bp, "uw_dated_closes", _async(lambda t: None))
    ok, why = await bp.verify_close("SPY", D(2026, 10, 21), 671.30)
    assert ok is False and "unavailable" in why


@pytest.mark.asyncio
async def test_uw_dated_closes_reads_REGULAR_session_rows_only_and_drops_unreadable_ones(monkeypatch):
    rows = [
        {"date": "2026-10-21", "market_time": "pr", "close": 1.0},
        {"date": "2026-10-21", "market_time": "r", "close": 671.30},
        {"date": "2026-10-21", "market_time": "po", "close": 2.0},
        {"date": "2026-10-22", "market_time": "r", "close": "668.12"},
        {"date": "2026-10-23", "market_time": "r", "close": None},          # unreadable: dropped
    ]
    import integrations.uw_api as uw
    import integrations.uw_governor as gov
    monkeypatch.setattr(uw, "get_ohlc", _async(lambda *a, **k: list(rows)))
    monkeypatch.setattr(gov, "is_unavailable", lambda x: False)
    got = await bp.uw_dated_closes("SPY")
    assert got == {D(2026, 10, 21): 671.30, D(2026, 10, 22): 668.12}, got


@pytest.mark.asyncio
async def test_the_dated_read_uses_THE_CARD_S_OWN_CALL_caller_tag_and_cache_key(monkeypatch):
    """No new UW spend: same caller tag ("chart_indicators") and same lookback (cache key)."""
    calls = []
    import integrations.uw_api as uw
    import integrations.uw_governor as gov
    from services.read_only import chart_indicators as ci

    async def _ohlc(sym, **k):
        calls.append(k)
        return []
    monkeypatch.setattr(uw, "get_ohlc", _ohlc)
    monkeypatch.setattr(gov, "is_unavailable", lambda x: False)
    await bp.uw_dated_closes("SPY")
    assert calls == [{"candle_size": "1d", "lookback_days": ci.LOOKBACK_DAYS,
                      "caller": "chart_indicators"}], calls


@pytest.mark.asyncio
async def test_THE_MONDAY_CAPTURE_stores_10_21_10_22_and_the_target_10_23_verified(monkeypatch):
    """End to end at the capture: stored through 10-20, Polygon serves 10-19..10-23 for the 10-23
    target, UW's dated series agrees -- 10-21 and 10-22 are back-filled and 10-23 is the target."""
    writes = []

    class _Conn:
        async def execute(self, sql, *a):
            writes.append((a[0], a[1], a[-1]))

        async def fetch(self, sql, *a):
            return [{"date": D(2026, 10, 19), "n": 3}, {"date": D(2026, 10, 20), "n": 3}]

    served = [D(2026, 10, d) for d in (19, 20, 21, 22, 23)]
    closes = {d: 600.0 + d.day for d in served}

    async def _fetch(t, s, e):
        return [{"date": d, "o": 1.0, "h": 2.0, "l": 0.5, "c": closes[d], "v": 1}
                for d in served if s <= d <= e]

    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "is_session_settled", lambda d, now=None: cal.is_trading_day(d))
    monkeypatch.setattr(bp, "fetch_daily", _fetch)
    monkeypatch.setattr(bp, "uw_dated_closes", _async(lambda t: dict(closes)))
    monkeypatch.setattr(bp, "CALL_GAP_S", 0.0)

    out = await bp.capture_session(_Conn(), D(2026, 10, 23), ("SPY", "QQQ", "IWM"))
    assert out["degraded"] is False, out
    assert out["backfilled"] == ["2026-10-21", "2026-10-22"]
    assert {d for _t, d, _v in writes} == {D(2026, 10, 21), D(2026, 10, 22), D(2026, 10, 23)}
    assert all(v is True for _t, _d, v in writes), "every write is uw_verified TRUE"


@pytest.mark.asyncio
async def test_a_session_UW_lacks_is_NOT_stored_and_its_neighbours_still_are(monkeypatch):
    writes = []

    class _Conn:
        async def execute(self, sql, *a):
            writes.append(a[1])

        async def fetch(self, sql, *a):
            return [{"date": D(2026, 10, 20), "n": 3}]

    served = [D(2026, 10, d) for d in (20, 21, 22, 23)]
    closes = {d: 600.0 + d.day for d in served}

    async def _fetch(t, s, e):
        return [{"date": d, "o": 1.0, "h": 2.0, "l": 0.5, "c": closes[d], "v": 1} for d in served]

    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "is_session_settled", lambda d, now=None: cal.is_trading_day(d))
    monkeypatch.setattr(bp, "fetch_daily", _fetch)
    monkeypatch.setattr(bp, "uw_dated_closes",
                        _async(lambda t: {d: c for d, c in closes.items() if d != D(2026, 10, 22)}))
    monkeypatch.setattr(bp, "CALL_GAP_S", 0.0)

    await bp.capture_session(_Conn(), D(2026, 10, 23), ("SPY",))
    assert D(2026, 10, 22) not in writes and D(2026, 10, 21) in writes and D(2026, 10, 23) in writes


# ── health: one session behind is the DESIGN ──────────────────────────────

@pytest.mark.parametrize("as_of,state", [
    (D(2026, 10, 26), "current"),       # lag 0
    (D(2026, 10, 23), "current"),       # lag 1: form (b)'s steady state, all day
    (D(2026, 10, 22), "stale"),         # lag 2: tonight's run has not labelled yet
    (D(2026, 10, 21), "dead"),          # lag 3: missed
])
@pytest.mark.asyncio
async def test_health_treats_ONE_SESSION_BEHIND_as_current(monkeypatch, as_of, state):
    class _Conn:
        async def fetchrow(self, sql, *a):
            return {"as_of": as_of, "shown_regime": "uptrend", "settled": True,
                    "created_at": None}

    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "last_settled_session", lambda now=None: D(2026, 10, 26))
    out = await regime_job.health(_Conn(), rules_version="v2.1")
    assert out["state"] == state, out
    if state == "stale":
        assert "2026-10-23" in out["reason"], out["reason"]
