"""R-IV.1398(b)1 — the 15:59 close slot, and the 5-minute ATM-vertical grid.

Two things ship here and each has one failure mode that would not look like a failure:

  THE CLOSE SLOT could store a POST-CLOSE book under the label `15:59`. The 25-minute grace
  that is correct for a 30-minute grid keeps a 15:59 slot due until 16:24, so a loop that woke
  late -- or a Railway deploy that restarted the process at 16:15, which happens on every
  push -- would fetch the wide, untradeable after-hours spreads and stamp them as the closing
  minute. Nothing downstream could tell. The guard is a per-slot grace, and the test below
  proves it is load-bearing by removing it and watching the fabrication appear.

  THE GRID could SPEND UNBUDGETED. R-IV.1398(b)1 requires the calls/day report and a funding
  ruling before it collects, and an unregistered caller tag does not stop a job -- the
  governor hands it DEFAULT_QUOTA 500 and it quietly spends them, which is the recorded
  `outcome_resolver` fault (2,764 calls in a session on a default meant for unknown code).
  So the gate is checked here against the thing that matters: whether a vendor call is made.
"""
from __future__ import annotations

import datetime as _dt
import math
import os
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from jobs import option_quote_capture as oqc
from jobs import option_quote_grid as oqg
from tests._srcscan import code_of_file, function_code, read_source

ET = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRID_FILE = os.path.join(BACKEND, "jobs", "option_quote_grid.py")
PG_FILE = os.path.join(BACKEND, "database", "postgres_client.py")

MON = date(2026, 10, 26)          # a Monday
TUE = date(2026, 10, 27)


@pytest.fixture(autouse=True)
def _clean():
    oqc.reset_for_tests()
    oqg.reset_for_tests()
    yield
    oqc.reset_for_tests()
    oqg.reset_for_tests()


# ── 1. the 15:59 close slot ─────────────────────────────────────────────────

@pytest.mark.parametrize("hh,mm,expect", [
    (15, 30, "15:30"),    # the 30-minute grid is untouched
    (15, 54, "15:30"),    # ... and keeps its own 25-minute grace
    (15, 56, None),       # the 15:30 grace has expired; 15:59 has not arrived
    (15, 58, None),
    (15, 59, "15:59"),
    (16, 0, "15:59"),     # one minute late: still the closing book
    (16, 1, "15:59"),
    (16, 2, None),        # past the 2-minute grace
    (16, 20, None),       # THE FABRICATION: a restart here must capture nothing
    (17, 0, None),
    (23, 59, None),
])
def test_the_close_slot_is_due_only_while_the_closing_book_is_the_closing_book(hh, mm, expect):
    got = oqc.due_slot(datetime(2026, 10, 26, hh, mm, tzinfo=ET))
    assert (got.strftime("%H:%M") if got else None) == expect


def test_WITHOUT_the_per_slot_grace_a_1620_restart_FABRICATES_the_close():
    """POSITIVE CONTROL (Convention #30), and the reason the override exists at all.

    A guard that is never shown to be load-bearing is indistinguishable from a guard that is
    dead code. So this removes it and asserts the defect appears: on the default 25-minute
    grace the 15:59 slot is still "due" at 16:20, and the job would store the after-hours
    book -- wide, untradeable -- labelled as the closing minute.
    """
    at_1620 = datetime(2026, 10, 26, 16, 20, tzinfo=ET)
    assert oqc.due_slot(at_1620) is None, "the guard is not holding"

    real = oqc.SLOT_GRACE_OVERRIDE_MINUTES
    oqc.SLOT_GRACE_OVERRIDE_MINUTES = {}
    try:
        fabricated = oqc.due_slot(at_1620)
    finally:
        oqc.SLOT_GRACE_OVERRIDE_MINUTES = real

    assert fabricated is not None and fabricated.strftime("%H:%M") == "15:59", (
        "removing the override did NOT reproduce the fault, so the override is not what "
        "prevents it and this test proves nothing: %r" % (fabricated,))


def test_the_override_is_SCOPED_to_the_close_and_does_not_tighten_the_grid():
    """The 25-minute grace is correct for the 30-minute slots and must survive. A single
    global constant would have been the easy fix and would have cost every late wake-up on
    the twelve slots that can afford one."""
    assert oqc.SLOT_GRACE_MINUTES == 25
    assert set(oqc.SLOT_GRACE_OVERRIDE_MINUTES) == {time(15, 59)}
    assert oqc.SLOT_GRACE_OVERRIDE_MINUTES[time(15, 59)] == 2
    # 10:00 + 25 minutes is still inside its slot.
    assert oqc.due_slot(datetime(2026, 10, 26, 10, 25, tzinfo=ET)) is not None


def test_the_grace_is_longer_than_one_poll_so_phase_cannot_lose_the_close():
    """A one-minute grace is missed outright whenever the loop's phase puts a wake-up at
    :59:05 and the next at 16:00:05 -- a coin flip on the one slot that cannot be recovered.
    The grace must exceed the poll interval."""
    assert oqc.SLOT_GRACE_OVERRIDE_MINUTES[time(15, 59)] * 60 > oqc.POLL_SECONDS


def test_the_close_is_the_LAST_slot_so_the_budget_reserves_it():
    """`remaining // slots_remaining` guarantees a share to every later slot. That guarantee
    only protects the close if the close is last in the list the arithmetic walks."""
    assert oqc.SLOT_TIMES_ET[-1] == time(15, 59)
    assert oqc.slot_allowance(oqc.SESSION_CALL_CEILING - 5, 1) == 5


# ── 2. the grid cannot spend before the ruling funds it ─────────────────────

@pytest.mark.asyncio
async def test_the_grid_MAKES_NO_VENDOR_CALL_while_its_tag_is_unregistered():
    """THE GATE THAT MATTERS, checked on calls rather than on a flag.

    An unregistered tag is not inert: `quota_for` falls back to DEFAULT_QUOTA 500 and the job
    would spend them. The assertion is therefore that `_fetch` is never reached.
    """
    assert not oqg.tag_is_registered(), (
        "option_quote_grid is in QUOTAS -- if that is the funding ruling landing, this test "
        "is the one to update, deliberately, after re-reading R-IV.1398(b)1")
    calls = {"n": 0}

    async def _counting(ticker, expiry):
        calls["n"] += 1
        return None, 0

    real = oqg._fetch
    oqg._fetch = _counting
    try:
        out = await oqg.capture_slot(
            now=datetime(2026, 10, 26, 11, 0, tzinfo=ET).astimezone(UTC))
    finally:
        oqg._fetch = real

    assert calls["n"] == 0, "the grid spent %d calls while unfunded" % calls["n"]
    assert out["blocked"] is True
    assert out["captured"] == 0
    assert oqg.session_ceiling() == 0


def test_the_two_gates_are_reported_SEPARATELY():
    """"the ruling has not funded this" and "the operator has not switched it on" have
    different fixes, and one message for both is the collapse this register keeps filing."""
    from integrations import uw_governor as gov

    assert "QUOTAS" in (oqg.preflight() or ""), oqg.preflight()

    gov.QUOTAS[oqg.CALLER_TAG] = (1000, gov.TIER_STANDARD)
    try:
        reason = oqg.preflight()
        assert reason is not None
        assert oqg.ENV_FLAG in reason, reason
        assert "QUOTAS" not in reason, (
            "with the tag registered the block must name the ENV gate, not the funding one")
        assert oqg.session_ceiling() == int(1000 * oqg.SESSION_CEILING_FRACTION) == 960

        os.environ[oqg.ENV_FLAG] = "true"
        try:
            assert oqg.preflight() is None, "both gates open and it still refuses"
        finally:
            del os.environ[oqg.ENV_FLAG]
    finally:
        gov.QUOTAS.pop(oqg.CALLER_TAG, None)


def test_an_empty_env_value_is_OFF_not_ON():
    """Railway returns '' for an unset reference, which is why the repo uses `or` rather than
    a getenv default. An empty string must not read as enabled."""
    os.environ[oqg.ENV_FLAG] = ""
    try:
        assert oqg.enabled() is False
    finally:
        del os.environ[oqg.ENV_FLAG]


def test_an_unreadable_quota_table_is_not_a_licence_to_spend():
    """Fail-CLOSED on the unknown, which is the opposite of the governor's own fail-open rule
    for an unmeasured ACCOUNT -- and deliberately so. Opening on an unknown account keeps live
    traffic alive; opening on an unknown quota table would spend money nobody has approved."""
    import sys
    real = sys.modules.get("integrations.uw_governor")
    sys.modules["integrations.uw_governor"] = None   # import raises
    try:
        assert oqg.tag_is_registered() is False
        assert oqg.session_ceiling() == 0
    finally:
        if real is not None:
            sys.modules["integrations.uw_governor"] = real
        else:
            sys.modules.pop("integrations.uw_governor", None)


# ── 3. the grid's shape ─────────────────────────────────────────────────────

def test_seventyfive_slots_every_five_minutes_0945_to_1555():
    assert len(oqg.SLOT_TIMES_ET) == 75
    assert oqg.SLOT_TIMES_ET[0] == time(9, 45)
    assert oqg.SLOT_TIMES_ET[-1] == time(15, 55)
    gaps = {(datetime.combine(MON, b) - datetime.combine(MON, a)).total_seconds()
            for a, b in zip(oqg.SLOT_TIMES_ET, oqg.SLOT_TIMES_ET[1:])}
    assert gaps == {300.0}


def test_no_two_grid_slots_can_contend():
    """The grace must be under the spacing, or an instant belongs to two slots and the one it
    is stored as depends on which the loop happened to reach."""
    assert oqg.SLOT_GRACE_MINUTES * 60 < 300
    assert oqg.SLOT_GRACE_MINUTES * 60 > oqg.POLL_SECONDS


@pytest.mark.parametrize("hh,mm,expect", [
    (9, 44, None),
    (9, 45, "09:45"),
    (9, 47, "09:45"),
    (9, 48, None),        # past the grace, before 09:50
    (9, 50, "09:50"),
    (12, 0, "12:00"),
    (15, 55, "15:55"),
    (15, 57, "15:55"),
    (15, 58, None),       # the grid stops BEFORE the close; 15:59 belongs to the other job
    (16, 30, None),
])
def test_grid_due_slot(hh, mm, expect):
    got = oqg.due_slot(datetime(2026, 10, 26, hh, mm, tzinfo=ET))
    assert (got.strftime("%H:%M") if got else None) == expect


def test_no_grid_slot_on_a_weekend():
    assert oqg.due_slot(datetime(2026, 10, 24, 12, 0, tzinfo=ET)) is None   # Saturday
    assert oqg.due_slot(datetime(2026, 10, 25, 12, 0, tzinfo=ET)) is None   # Sunday


def test_the_last_grid_slot_is_never_starved():
    """POSITIVE CONTROL. Walk all 75 slots spending the full allowance each time; the last
    must still get a positive one, because the governor sheds what arrives last and what
    arrives last here is 15:55."""
    n = len(oqg.SLOT_TIMES_ET)
    ceiling = 640
    used, per_slot = 0, []
    for i in range(n):
        a = oqg.slot_allowance(used, n - i, ceiling)
        per_slot.append(a)
        used += a
    assert used <= ceiling, used
    assert per_slot[-1] > 0, per_slot
    assert min(per_slot) > 0, per_slot


def test_eight_tickers_one_expiry_each_is_what_the_calls_report_was_built_on():
    """The calls/day figure reported to SPINE is 75 x 8 x 1. If the ticker list or the
    one-expiry rule changes, that figure is wrong and the funding ruling was given on a
    different job than the one running."""
    assert len(oqg.TICKERS) == 8
    assert set(oqg.TICKERS) == {"SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA"}
    oqg._nearest_expiry.update({t: "2026-10-26" for t in oqg.TICKERS})
    pairs = oqg.plan_pairs(MON)
    assert len(pairs) == 8, pairs
    assert len({p[0] for p in pairs}) == 8


# ── 4. the implied move ─────────────────────────────────────────────────────

def _c(kind, strike, bid=None, ask=None, iv=None, delta=None):
    return {"type": kind, "strike": float(strike), "bid": bid, "ask": ask, "iv": iv,
            "delta": delta, "volume": 0, "open_interest": 0,
            "ticker": "TEST", "expiry": MON, "symbol": "X"}


def test_the_straddle_route_and_the_IV_route_COMPUTE_THE_SAME_QUANTITY():
    """THE CLAIM IN THE DOCSTRING, tested rather than asserted in prose.

    An ATM straddle is worth 0.7979 x S*sigma*sqrt(T), so straddle x sqrt(pi/2) is the
    one-sigma move. Built here from a known sigma and T: S = 100, sigma = 0.20, T = 0.01
    years, so the move is 100 x 0.20 x 0.1 = 2.00 and the straddle that implies it is
    2.00 x 0.7979 = 1.5958. Both routes must return 2.00, or the two methods recorded in
    `implied_move_method` are not comparable and a reader mixing them is mixing units.
    """
    S, sigma, T = 100.0, 0.20, 0.01
    want = S * sigma * math.sqrt(T)
    straddle = want * 2.0 / math.sqrt(2.0 * math.pi)   # 0.7979 x S*sigma*sqrt(T)

    expiry = MON
    close = datetime.combine(expiry, time(16, 0), tzinfo=ET)
    now = close - timedelta(seconds=T * oqg.SECONDS_PER_YEAR)
    assert abs(oqg.years_to_expiry(now, expiry) - T) < 1e-9

    half = straddle / 2.0
    both = oqg.implied_move(_c("call", S, bid=half - 0.01, ask=half + 0.01),
                            _c("put", S, bid=half - 0.01, ask=half + 0.01),
                            S, now, expiry)
    assert both[1] == oqg.MOVE_FROM_STRADDLE
    assert abs(both[0] - want) < 0.01, (both, want)

    # No mids anywhere -> the IV route, on the same inputs.
    iv_only = oqg.implied_move(_c("call", S, iv=sigma), _c("put", S, iv=sigma),
                               S, now, expiry)
    assert iv_only[1] == oqg.MOVE_FROM_IV
    assert abs(iv_only[0] - want) < 1e-6, (iv_only, want)

    assert abs(both[0] - iv_only[0]) < 0.01, (
        "the two recorded methods disagree, so `implied_move` does not mean one thing")


def test_the_move_is_NULL_WITH_A_REASON_when_neither_route_can_answer():
    """Conventions #37/#41: a NULL with a recorded reason is deliberate, not a gap. The two
    ATM rows are still stored -- a dated ATM quote is evidence on its own, and dropping the
    slot because the short leg is missing would lose the whole observation."""
    now = datetime(2026, 10, 26, 11, 0, tzinfo=ET)
    move, method = oqg.implied_move(_c("call", 100), _c("put", 100), 100.0, now, MON)
    assert move is None
    assert method == oqg.MOVE_NONE

    legs, centre, _atm_m, move, method, degen = oqg.build_legs(
        [_c("call", 100, delta=0.50), _c("put", 100, delta=-0.50),
         _c("call", 105), _c("put", 95)], now, MON)
    assert centre == 100.0
    assert move is None and method == oqg.MOVE_NONE
    roles = {r for r, _ in legs}
    assert roles == {oqg.LEG_ATM_CALL, oqg.LEG_ATM_PUT}, roles
    assert degen is False


def test_an_expired_T_does_not_divide_by_a_negative_root():
    """`years_to_expiry` clamps at zero, so a slot captured after an expiry's close cannot
    produce a complex or negative move."""
    past = datetime(2026, 10, 26, 17, 0, tzinfo=ET)
    assert oqg.years_to_expiry(past, MON) == 0.0
    move, method = oqg.implied_move(_c("call", 100, iv=0.2), _c("put", 100, iv=0.2),
                                    100.0, past, MON)
    assert move is None and method == oqg.MOVE_NONE


# ── 5. the short leg ────────────────────────────────────────────────────────

def test_the_short_leg_sits_one_move_out_on_each_side():
    strikes = [90.0, 95.0, 100.0, 105.0, 110.0, 115.0]
    call, degen_c = oqg.short_strike(strikes, 100.0, 5.4, +1)
    put, degen_p = oqg.short_strike(strikes, 100.0, 5.4, -1)
    assert call == 105.0 and put == 95.0
    assert degen_c is False and degen_p is False


def test_a_SUB_INCREMENT_move_is_labelled_degenerate_not_silently_atm():
    """Near a 0-DTE close the one-sigma move falls under one strike increment. The vertical is
    then one increment wide -- real and tradeable -- and the row must say so, because a reader
    cannot otherwise tell a tiny move from a broken centre."""
    strikes = [90.0, 95.0, 100.0, 105.0, 110.0]
    call, degen = oqg.short_strike(strikes, 100.0, 0.4, +1)
    assert call == 105.0, "the short leg collapsed onto ATM: that is not a vertical"
    assert degen is True
    put, degen_p = oqg.short_strike(strikes, 100.0, 0.4, -1)
    assert put == 95.0 and degen_p is True


def test_the_short_leg_is_never_the_atm_strike():
    strikes = [95.0, 100.0, 105.0]
    for move in (0.0, 0.01, 1.0, 2.5, 4.9, 5.0, 50.0):
        for direction in (+1, -1):
            k, _ = oqg.short_strike(strikes, 100.0, move, direction)
            assert k != 100.0, (move, direction, k)


def test_no_strike_on_a_side_is_None_not_a_fabricated_one():
    assert oqg.short_strike([95.0, 100.0], 100.0, 5.0, +1) == (None, False)


def test_build_legs_returns_four_named_legs_on_a_normal_chain():
    now = datetime(2026, 10, 26, 11, 0, tzinfo=ET)
    chain = []
    for k in (90, 95, 100, 105, 110):
        chain.append(_c("call", k, bid=1.0, ask=1.1, delta=0.50 if k == 100 else 0.30))
        chain.append(_c("put", k, bid=1.0, ask=1.1, delta=-0.50 if k == 100 else -0.30))
    legs, centre, atm_method, move, method, _degen = oqg.build_legs(chain, now, MON)
    assert centre == 100.0
    assert atm_method == oqc.ATM_FROM_DELTA
    assert method == oqg.MOVE_FROM_STRADDLE
    assert move is not None and move > 0
    roles = [r for r, _ in legs]
    assert sorted(roles) == sorted([oqg.LEG_ATM_CALL, oqg.LEG_ATM_PUT,
                                    oqg.LEG_SHORT_CALL, oqg.LEG_SHORT_PUT]), roles
    short_call = next(c for r, c in legs if r == oqg.LEG_SHORT_CALL)
    short_put = next(c for r, c in legs if r == oqg.LEG_SHORT_PUT)
    assert short_call["strike"] > centre > short_put["strike"]


# ── 6. expiry discovery ─────────────────────────────────────────────────────

def test_the_window_REACHES_FRIDAY_FROM_MONDAY_which_0_to_3_does_not():
    """THE HOLE IN THE 30-MINUTE JOB'S WINDOW, which this grid cannot inherit.

    On a Monday, 0-3 DTE is Mon/Tue/Wed/Thu. A name whose only expiry is Friday has none of
    them, so a grid keyed on the nearest expiry would record nothing for it all day -- while
    spending four probes a day to discover that.
    """
    dtes = [k for _d, k in oqc.candidate_expiries(MON)]
    assert max(dtes) == 3, "the 30-minute job's window changed; re-read R-IV.1082(b)"

    grid = oqg.candidate_expiries(MON)
    assert date(2026, 10, 30) in [d for d, _k in grid], grid    # the Friday
    assert 4 in [k for _d, k in grid]
    assert all(d.weekday() < 5 for d, _k in grid), "a weekend date was offered as an expiry"


def test_discovery_is_ONCE_A_DAY_not_once_a_slot():
    """75 slots x 8 tickers of probing would be 2,400 calls, not 600. The remembered hit is
    what makes the reported figure the real one."""
    assert oqg.next_probe("SPY", MON) == (MON, 0)
    oqg._nearest_expiry["SPY"] = "2026-10-30"
    for _ in range(10):
        assert oqg.next_probe("SPY", MON) == (date(2026, 10, 30), 4)


def test_an_empty_probe_is_remembered_and_the_NEXT_dte_is_tried():
    assert oqg.next_probe("SMH", MON) == (MON, 0)
    oqg._probed_empty[("SMH", MON.isoformat())] = True
    assert oqg.next_probe("SMH", MON) == (TUE, 1)
    oqg._probed_empty[("SMH", TUE.isoformat())] = True
    assert oqg.next_probe("SMH", MON) == (date(2026, 10, 28), 2)


def test_an_exhausted_ticker_stops_costing_calls():
    for d, _k in oqg.candidate_expiries(MON):
        oqg._probed_empty[("SMH", d.isoformat())] = True
    assert oqg.next_probe("SMH", MON) is None
    assert oqg._nearest_expiry["SMH"] is None
    assert oqg.next_probe("SMH", MON) is None
    assert "SMH" not in {t for t, _e, _d in oqg.plan_pairs(MON)}


def test_pairs_are_ordered_so_the_FARTHEST_expiry_is_shed_first():
    oqg._nearest_expiry.update({"SPY": "2026-10-26", "QQQ": "2026-10-26",
                                "SMH": "2026-10-30", "TSLA": "2026-10-28"})
    for t in ("IWM", "NVDA", "AAPL", "MSFT"):
        oqg._nearest_expiry[t] = None
    pairs = oqg.plan_pairs(MON)
    assert [p[2] for p in pairs] == sorted(p[2] for p in pairs)
    assert pairs[-1][0] == "SMH", pairs


# ── 7. the vendor call: own tag, no cache ───────────────────────────────────

def test_the_grid_does_not_spend_the_FORBIDDEN_tag():
    """Scanned on PARSED code. This file's own docstring names `option_contracts` to explain
    why it is forbidden, and a raw-text scan would fail on that explanation -- the trap this
    suite has now hit seventeen times."""
    code = code_of_file(GRID_FILE)
    assert "option_contracts" not in code, (
        "the grid references option_contracts in executable code; R-IV.1082(b) forbids it")
    assert "get_options_snapshot" not in code
    for cache_fn in ("cache_get", "cache_set"):
        assert cache_fn not in code, cache_fn


def test_the_grid_passes_its_OWN_tag_and_its_own_expiry_parameter():
    code = function_code(GRID_FILE, "_fetch")
    assert "CALLER_TAG" in code and "caller=" in code
    assert oqg.CALLER_TAG == "option_quote_grid"
    assert oqg.CALLER_TAG != oqc.CALLER_TAG, (
        "sharing the 30-minute job's tag would make the grid's spend unattributable and would "
        "shed the two jobs together")
    assert "expiry" in code


# ── 8. end to end on a funded, enabled slot ─────────────────────────────────

class _Conn:
    def __init__(self, sink):
        self.sink = sink

    async def execute(self, sql, *args):
        self.sink.append(args)

    async def fetch(self, *a, **k):
        return []


class _Acq:
    def __init__(self, sink):
        self.sink = sink

    async def __aenter__(self):
        return _Conn(self.sink)

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, sink):
        self.sink = sink

    def acquire(self):
        return _Acq(self.sink)


@pytest.mark.asyncio
async def test_a_funded_slot_writes_FOUR_LEGS_per_ticker_on_EIGHT_calls():
    """The whole path with the gates open: one call per ticker, four rows per call.

    32 rows from 8 calls is the arithmetic the calls/day report rests on. If a future edit
    made it two calls per ticker, the report to SPINE would be half the real cost.
    """
    import database.postgres_client as pg
    from integrations import uw_governor as gov

    sink = []
    calls = []

    async def _fake_fetch(ticker, expiry):
        calls.append((ticker, expiry))
        raw = []
        for k in (90, 95, 100, 105, 110):
            for kind, d in (("C", 0.50 if k == 100 else 0.30),
                            ("P", -0.50 if k == 100 else -0.30)):
                raw.append({"option_symbol": "%s261026%s%08d" % (ticker, kind, k * 1000),
                            "nbbo_bid": 1.0, "nbbo_ask": 1.2, "delta": d,
                            "implied_volatility": 0.25, "volume": 7, "open_interest": 9})
        return raw, len(raw)

    async def _fake_pool():
        return _Pool(sink)

    gov.QUOTAS[oqg.CALLER_TAG] = (1000, gov.TIER_STANDARD)
    os.environ[oqg.ENV_FLAG] = "true"
    real_fetch, real_pool = oqg._fetch, pg.get_postgres_client
    oqg._fetch, pg.get_postgres_client = _fake_fetch, _fake_pool
    try:
        out = await oqg.capture_slot(
            now=datetime(2026, 10, 26, 11, 0, tzinfo=ET).astimezone(UTC))
    finally:
        oqg._fetch, pg.get_postgres_client = real_fetch, real_pool
        del os.environ[oqg.ENV_FLAG]
        gov.QUOTAS.pop(oqg.CALLER_TAG, None)

    assert out.get("blocked") is not True, out
    assert out["slot"] == "11:00"
    assert len(calls) == 8, calls
    assert {c[0] for c in calls} == set(oqg.TICKERS)
    assert out["captured"] == 8, out
    assert out["rows"] == 32, out
    assert out["calls"] == 8
    assert out["move_methods"] == {oqg.MOVE_FROM_STRADDLE: 8}, out["move_methods"]
    assert len(sink) == 32

    # Every row carries the six columns R-IV.1398(b)1 names, and the leg role.
    roles = {row[6] for row in sink}
    assert roles == {oqg.LEG_ATM_CALL, oqg.LEG_ATM_PUT,
                     oqg.LEG_SHORT_CALL, oqg.LEG_SHORT_PUT}, roles
    for row in sink:
        session_date, slot_et, _cap, _tkr, expiry, dte = row[0], row[1], row[2], row[3], row[4], row[5]
        strike, bid, ask = row[8], row[9], row[10]
        atm = row[16]
        assert slot_et == "11:00"
        assert isinstance(expiry, date) and isinstance(dte, int)
        assert strike and bid is not None and ask is not None and atm == 100.0


@pytest.mark.asyncio
async def test_the_second_visit_to_a_captured_slot_spends_nothing():
    """Idempotence per slot. The loop wakes twice inside the 2-minute grace by design, and a
    second fetch would double the measured cost of every slot."""
    import database.postgres_client as pg
    from integrations import uw_governor as gov

    calls = []

    async def _fake_fetch(ticker, expiry):
        calls.append(ticker)
        return [], 0

    async def _fake_pool():
        return _Pool([])

    gov.QUOTAS[oqg.CALLER_TAG] = (1000, gov.TIER_STANDARD)
    os.environ[oqg.ENV_FLAG] = "true"
    real_fetch, real_pool = oqg._fetch, pg.get_postgres_client
    oqg._fetch, pg.get_postgres_client = _fake_fetch, _fake_pool
    try:
        now = datetime(2026, 10, 26, 11, 0, tzinfo=ET).astimezone(UTC)
        first = await oqg.capture_slot(now=now)
        second = await oqg.capture_slot(now=now + timedelta(seconds=30))
    finally:
        oqg._fetch, pg.get_postgres_client = real_fetch, real_pool
        del os.environ[oqg.ENV_FLAG]
        gov.QUOTAS.pop(oqg.CALLER_TAG, None)

    n_first = len(calls)
    assert n_first == 8, calls
    assert first["slot"] == "11:00"
    assert second["reason"] == "already captured"
    assert len(calls) == n_first, "the slot was fetched twice"


# ── 9. the table, and the surface ───────────────────────────────────────────

def test_the_grid_table_is_created_by_the_STARTUP_MIGRATIONS():
    """R-IV.1052(b)'s first-boot guard: a READ path must not query a table nothing creates.
    `capture_status` selects from option_quote_grid, so the DDL has to be in the startup
    path -- and `position_orientation` is the standing example of a column read by code and
    migrated by nothing."""
    src = read_source(PG_FILE)
    assert "CREATE TABLE IF NOT EXISTS option_quote_grid" in src
    status = function_code(GRID_FILE, "capture_status")
    assert "option_quote_grid" in status


def test_the_grid_tables_identity_is_the_LEG_ROLE():
    """The strike is an OUTCOME of the move calculation and moves slot to slot for the same
    leg, so (type, strike) is the wrong key: the same conflict target as the 30-minute table
    would let a re-run insert a second short call at a different strike for one slot."""
    src = read_source(PG_FILE)
    i = src.index("CREATE TABLE IF NOT EXISTS option_quote_grid")
    ddl = src[i:src.index("CREATE INDEX IF NOT EXISTS idx_oqg_session_slot", i)]
    m = re.search(r"UNIQUE \(([^)]*)\)", ddl)
    assert m, ddl[-400:]
    key = [c.strip() for c in m.group(1).split(",")]
    assert key == ["session_date", "slot_et", "ticker", "expiry", "leg_role"], key

    upsert = function_code(GRID_FILE, "_store")
    assert "leg_role" in upsert
    for col in ("implied_move", "implied_move_method", "short_leg_degenerate", "atm_strike"):
        assert col in upsert, col


@pytest.mark.asyncio
async def test_the_health_surface_NAMES_the_block_rather_than_looking_idle():
    """A job that is deliberately off and a job that is broken must not look the same. The
    surface carries the reason, both gates, and the slot total."""
    st = await oqg.capture_status()
    assert st["job"] == "option_quote_grid"
    assert st["caller_tag"] == oqg.CALLER_TAG
    assert st["blocked"] and "QUOTAS" in st["blocked"]
    assert st["tag_registered"] is False
    assert st["env_enabled"] is False
    assert st["slots_total"] == 75
    # While blocked, nothing is EXPECTED -- a refusal by ruling is not 75 missed slots, and
    # reporting it as one would bury the real alarm the day it fires.
    assert st["slots_expected_so_far"] == 0
    assert st["slots_missed"] == []
    assert st["ceiling"] == 0
