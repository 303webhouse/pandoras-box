"""R-IV.1203(b) — the designated settled-close series: Polygon, verified before it is written.

THE TWO PROPERTIES THAT MATTER MOST, and both are faults this lane has already paid for once:

  1. THE SESSION DATE IS READ IN UTC. Polygon stamps a daily aggregate at UTC midnight, and
     `datetime.fromtimestamp(ms/1000)` converts through the LOCAL zone -- so on a UTC-6 machine
     every bar comes back labelled one session EARLY. The first probe for this ruling did
     exactly that and reported the 763.25 close as 2026-10-15 when it is 2026-10-16. It is
     Convention #39's finding (a UTC-midnight stamp misread by a session) in a fresh place.

  2. NOTHING IS WRITTEN UNVERIFIED, AND NOTHING IS WRITTEN PARTIALLY. R-IV.1203(b)1: the
     nightly reads a session only once settled and checks the close against the UW chart close
     before writing; a mismatch writes nothing and raises health to DEGRADED. "Could not check"
     is treated as a mismatch, because writing an unchecked close would make the check
     decorative.

NO NETWORK HERE. Every test drives the pure parts or a fake connection. The live span was
measured separately (501 sessions, 2024-10-17 to 2026-10-16) and that number is not pinned in a
test -- it grows by one every session, and a test asserting it would fail tomorrow.
"""
from __future__ import annotations

import datetime as dt
import os

import pytest

from ._srcscan import code_of_file, read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE = os.path.join(BACKEND, "stable_engine", "bars_polygon.py")


# ── 1. the UTC session date ────────────────────────────────────────────────

def test_THE_SESSION_DATE_IS_READ_IN_UTC():
    """THE FAULT FROM THE FIRST PROBE. Polygon's stamp for the 2026-10-16 session is UTC
    midnight on 2026-10-16; read through a UTC-6 local zone it becomes 2026-10-15 18:00, whose
    date is the session BEFORE."""
    from stable_engine.bars_polygon import _session_date
    ms = int(dt.datetime(2026, 10, 16, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
    assert _session_date(ms) == dt.date(2026, 10, 16)


def test_the_conversion_DOES_NOT_GO_THROUGH_THE_LOCAL_ZONE():
    """The positive control for the test above: a naive conversion of the SAME stamp gives the
    wrong answer on any negative-offset machine, so this proves the fix is doing work rather
    than the machine happening to sit in UTC."""
    from stable_engine.bars_polygon import _session_date
    ms = int(dt.datetime(2026, 10, 16, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
    naive = dt.datetime.fromtimestamp(ms / 1000.0).date()      # what the first probe did
    utc = _session_date(ms)
    assert utc == dt.date(2026, 10, 16)
    if naive != utc:
        # This machine is not on UTC, so the fault would have been live here.
        assert naive == dt.date(2026, 10, 15), naive
    src = code_of_file(MODULE)
    assert "tz=_dt.timezone.utc" in src or "tz=dt.timezone.utc" in src


def test_every_timestamp_conversion_goes_through_the_one_helper():
    """One conversion point, so the next reader of a Polygon timestamp cannot reintroduce it."""
    src = code_of_file(MODULE)
    assert src.count("fromtimestamp") == 1, (
        "exactly one conversion, inside _session_date")


# ── 2. the basis the ruling names ──────────────────────────────────────────

def test_THE_BASIS_IS_SPLIT_ADJUSTED_AND_NOT_DIVIDEND_ADJUSTED():
    """R-IV.1203(b)1. Polygon's `adjusted=true` is split-only -- it does not adjust for
    dividends -- so that flag IS the ruled basis and no second one is needed."""
    src = code_of_file(MODULE)
    assert "'adjusted': 'true'" in src or '"adjusted": "true"' in src
    raw = read_source(MODULE)
    assert "split-adjusted" in raw and "dividend-UNadjusted" in raw


def test_the_module_records_WHY_the_basis_differs_from_stable_daily_bars():
    """R-IV.1203(c) leaves `stable_daily_bars` fully adjusted because that is correct for moving
    averages. Two bases coexist on purpose, and the reason is written down where someone would
    otherwise "fix" one to match the other."""
    raw = read_source(MODULE)
    assert "designated" in raw
    assert "763.25" in raw, "the number that settled the designation"


# ── 3. verify before write, and never partially ───────────────────────────

@pytest.mark.asyncio
async def test_A_CLOSE_MISMATCH_WRITES_NOTHING_AND_REPORTS_DEGRADED():
    """THE RULED BEHAVIOUR. R-IV.1203(b)1: "A mismatch writes nothing and raises health to
    DEGRADED." """
    from stable_engine import bars_polygon as bp

    writes = []

    class _Conn:
        async def execute(self, sql, *a):
            writes.append(a)

    session = dt.date(2026, 10, 16)

    async def _fetch(t, s, e):
        return [{"date": session, "o": 1.0, "h": 2.0, "l": 0.5, "c": 763.25, "v": 1}]

    async def _uw(t):
        return {session: 999.99}        # disagrees

    orig = (bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S)
    bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S = _fetch, _uw, 0.0
    try:
        import stable_engine.market_calendar as mc
        orig_settled = mc.is_session_settled
        mc.is_session_settled = lambda d, now=None: True
        try:
            out = await bp.capture_session(_Conn(), session, ("SPY",))
        finally:
            mc.is_session_settled = orig_settled
    finally:
        bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S = orig

    assert out["degraded"] is True
    assert out["written"] == 0
    assert writes == [], "nothing may be written on a mismatch"
    assert "MISMATCH" in out["reason"]


@pytest.mark.asyncio
async def test_POSITIVE_CONTROL_an_agreeing_close_IS_written_and_marked_verified():
    """Without this, a capture hard-wired to DEGRADED would satisfy the test above."""
    from stable_engine import bars_polygon as bp

    writes = []

    class _Conn:
        async def execute(self, sql, *a):
            writes.append(a)

    session = dt.date(2026, 10, 16)

    async def _fetch(t, s, e):
        return [{"date": session, "o": 1.0, "h": 2.0, "l": 0.5, "c": 763.25, "v": 1}]

    async def _uw(t):
        return {session: 763.25}

    orig = (bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S)
    bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S = _fetch, _uw, 0.0
    try:
        import stable_engine.market_calendar as mc
        orig_settled = mc.is_session_settled
        mc.is_session_settled = lambda d, now=None: True
        try:
            out = await bp.capture_session(_Conn(), session, ("SPY",))
        finally:
            mc.is_session_settled = orig_settled
    finally:
        bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S = orig

    assert out["degraded"] is False
    assert out["written"] == 1
    assert len(writes) == 1
    assert writes[0][-1] is True, "uw_verified must be TRUE on a checked write"


@pytest.mark.asyncio
async def test_ONE_BAD_TICKER_BLOCKS_THE_WHOLE_SESSION():
    """NO PARTIAL WRITES. A session present for SPY and absent for IWM is a hole that reads as
    data, and the classifier slices all three by the same session date -- so a half-written
    session would silently change what BREADTH measured."""
    from stable_engine import bars_polygon as bp

    writes = []

    class _Conn:
        async def execute(self, sql, *a):
            writes.append(a)

    session = dt.date(2026, 10, 16)
    closes = {"SPY": 763.25, "QQQ": 709.80, "IWM": 270.44}

    async def _fetch(t, s, e):
        return [{"date": session, "o": 1.0, "h": 2.0, "l": 0.5, "c": closes[t], "v": 1}]

    async def _uw(t):
        return {session: closes[t] if t != "IWM" else 111.11}   # IWM disagrees

    orig = (bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S)
    bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S = _fetch, _uw, 0.0
    try:
        import stable_engine.market_calendar as mc
        orig_settled = mc.is_session_settled
        mc.is_session_settled = lambda d, now=None: True
        try:
            out = await bp.capture_session(_Conn(), session, ("SPY", "QQQ", "IWM"))
        finally:
            mc.is_session_settled = orig_settled
    finally:
        bp.fetch_daily, bp.uw_dated_closes, bp.CALL_GAP_S = orig

    assert out["degraded"] is True
    assert writes == [], "SPY and QQQ verified, but nothing is written"


@pytest.mark.asyncio
async def test_AN_UNVERIFIABLE_SESSION_IS_NOT_A_VERIFIED_ONE():
    """Three outcomes, not two. When the UW chart cannot answer for the session being written,
    that is NOT agreement -- writing it would make the check decorative."""
    from stable_engine import bars_polygon as bp
    session = dt.date(2026, 10, 16)

    async def _uw_blank(t):
        return None                     # UW could not answer at all

    async def _uw_other_day(t):
        # R-IV.1423(h)2: a dated series that holds OTHER sessions but not this one.
        return {dt.date(2026, 10, 15): 763.25}

    orig = bp.uw_dated_closes
    try:
        bp.uw_dated_closes = _uw_blank
        ok, why = await bp.verify_close("SPY", session, 763.25)
        assert ok is False and "could not be verified" in why
        bp.uw_dated_closes = _uw_other_day
        ok2, why2 = await bp.verify_close("SPY", session, 763.25)
        assert ok2 is False and "has no regular-session row" in why2 and "could not be verified" in why2
    finally:
        bp.uw_dated_closes = orig


@pytest.mark.asyncio
async def test_AN_UNSETTLED_SESSION_IS_SKIPPED_NOT_DEGRADED():
    """Different states. "Not settled yet" is a normal early run; DEGRADED is a disagreement
    that needs looking at. Collapsing them would cry wolf every evening before the close."""
    from stable_engine import bars_polygon as bp
    import stable_engine.market_calendar as mc

    class _Conn:
        async def execute(self, sql, *a):
            raise AssertionError("nothing may be written")

    orig = mc.is_session_settled
    mc.is_session_settled = lambda d, now=None: False
    try:
        out = await bp.capture_session(_Conn(), dt.date(2026, 10, 16), ("SPY",))
    finally:
        mc.is_session_settled = orig
    assert out["degraded"] is False
    assert out["skipped"] is True
    assert out["written"] == 0


@pytest.mark.asyncio
async def test_UNKNOWN_SETTLEMENT_IS_NOT_SETTLED():
    """`is_session_settled` is three-state and None means "not a trading day, or past the
    horizon". R-IV.1176: that is not YES."""
    from stable_engine import bars_polygon as bp
    import stable_engine.market_calendar as mc

    class _Conn:
        async def execute(self, sql, *a):
            raise AssertionError("nothing may be written")

    orig = mc.is_session_settled
    mc.is_session_settled = lambda d, now=None: None
    try:
        out = await bp.capture_session(_Conn(), dt.date(2026, 10, 17), ("SPY",))
    finally:
        mc.is_session_settled = orig
    assert out["written"] == 0 and out.get("skipped") is True


# ── 4. the backfill tells the truth about what it checked ─────────────────

def test_the_BACKFILL_stores_uw_verified_FALSE():
    """The chart route serves only its newest reading, so two years of history has nothing to be
    checked against. FALSE is the honest record; a TRUE would be a claim nobody verified."""
    src = code_of_file(MODULE)
    i = src.index("async def backfill")
    body = src[i:i + 1800]
    assert "verified=False" in body
    raw = read_source(MODULE)
    assert "a TRUE there would be a claim" in raw


def test_the_bar_store_UPSERTS_while_snapshots_stay_append_only():
    """Deliberately different. A bar is a measurement of a session with one correct value, so a
    corrected vendor figure SHOULD replace a wrong one. A label is a judgement, and replacing
    one destroys the evidence that it changed."""
    src = code_of_file(MODULE)
    assert "ON CONFLICT (ticker, date) DO UPDATE" in src
    seed = code_of_file(os.path.join(BACKEND, "jobs", "regime_seed.py"))
    # R-IV.1288(b)2 NARROWED THE CONFLICT TARGET, not the behaviour. The index it infers is
    # now partial (`WHERE superseded = FALSE`), because the unqualified form made the table's
    # own supersession unusable for one (as_of, rules_version, close_source) -- a superseded
    # row still occupied the key, so a corrected label could only be written by UPDATEing the
    # row it corrected. What this guard is FOR is unchanged and still asserted: DO NOTHING,
    # never DO UPDATE.
    assert ("ON CONFLICT (as_of, rules_version, close_source) WHERE superseded = FALSE"
            in seed), "the conflict target must match the partial unique index"
    assert "DO NOTHING" in seed
    assert "DO UPDATE" not in seed


def test_a_malformed_bar_is_DROPPED_not_defaulted():
    """A zero close would be a price. An absent bar is absent."""
    src = code_of_file(MODULE)
    i = src.index("def _fetch_sync")
    body = src[i:i + 2600]
    assert "unreadable bar" in body
    assert "or 0" in body or "float(r.get" in body    # only volume may default
    raw = read_source(MODULE)
    assert "A zero close would be a price" in raw


def test_the_key_is_never_logged_or_returned():
    """The URL carries it. Printing a URL is printing the key."""
    raw = read_source(MODULE)
    assert "never logged" in raw
    src = code_of_file(MODULE)
    for bad in ("logger.info(url", "logger.warning(url", "logger.error(url", "print(url"):
        assert bad not in src, bad
    # The key is read from the environment and nothing returns it.
    assert "return k" in src and "POLYGON_API_KEY" in src
