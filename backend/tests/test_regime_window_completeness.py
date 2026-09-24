"""R-IV.522(c) — the regime states how complete each of its windows is.

Every window the regime reads is row-based, so a symbol missing a session does not
lose a day: it reaches one further back, by a different amount from its neighbours.
Session-based windows are the real fix and are queued. Until then the read must at
least say how much of its universe holds each window whole, and go DEGRADED below
scoring's own coverage floor.

Convention #30: each "it goes degraded" case is paired with one that must NOT.
"""

from datetime import date

import pytest

from services.read_only import stable as st


# -- the floor comes from scoring, not from a second copy ---------------------

def test_the_floor_is_scorings_own_anchor_coverage():
    from stable_engine.scoring import ANCHOR_MIN_COVERAGE

    assert st._coverage_floor_pct() == round(ANCHOR_MIN_COVERAGE * 100.0, 1)
    assert st._coverage_floor_pct() == 80.0


# -- the sessions are the exchange's, not weekdays ----------------------------

def test_sessions_back_returns_exchange_sessions_ending_at_the_anchor():
    s = st._sessions_back(date(2026, 9, 23), 5)
    assert s == [date(2026, 9, 17), date(2026, 9, 18), date(2026, 9, 21),
                 date(2026, 9, 22), date(2026, 9, 23)]
    assert len(s) == 5


def test_sessions_back_skips_a_holiday_rather_than_counting_it():
    """Labor Day 2026-09-07 is a Monday and is not a session. A weekday walk would
    include it and silently shorten the window by one real session."""
    s = st._sessions_back(date(2026, 9, 9), 4)
    assert date(2026, 9, 7) not in s
    assert s == [date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 9)]


def test_an_anchor_that_is_not_a_session_steps_back_to_one():
    sat = date(2026, 9, 26)
    assert st._sessions_back(sat, 1) == [date(2026, 9, 25)]


def test_sessions_back_counts_exactly_what_was_asked_for():
    for n in (1, 5, 20, 50):
        assert len(st._sessions_back(date(2026, 9, 23), n)) == n


# -- the verdict --------------------------------------------------------------

def _w(sessions, pct, below):
    return {"sessions": sessions, "pct": pct, "below_floor": below}


def test_a_complete_universe_is_not_degraded_by_completeness():
    """POSITIVE CONTROL. Without this, a verdict that always said DEGRADED would
    pass every other test here."""
    windows = {"1": _w(1, 98.0, False), "20": _w(20, 98.0, False)}
    assert st.completeness_verdict(windows) == (False, None)


def test_one_short_window_degrades_the_read_and_names_itself():
    windows = {"1": _w(1, 98.0, False), "20": _w(20, 40.4, True)}
    degraded, reason = st.completeness_verdict(windows)
    assert degraded is True
    assert "20d at 40.4%" in reason
    assert "80" in reason                     # it says what the floor was
    assert "1d" not in reason                 # and does not accuse a healthy window


def test_several_short_windows_are_listed_shortest_first():
    windows = {"200": _w(200, 40.4, True), "5": _w(5, 40.4, True),
               "20": _w(20, 40.4, True)}
    _degraded, reason = st.completeness_verdict(windows)
    assert reason.index("5d at") < reason.index("20d at") < reason.index("200d at")


def test_a_window_the_calendar_could_not_answer_for_is_degraded_not_ignored():
    windows = {"252": {"sessions": 252, "pct": None, "below_floor": True}}
    degraded, reason = st.completeness_verdict(windows)
    assert degraded is True and "unknown" in reason


def test_an_empty_block_does_not_claim_health():
    """No measurement is not a passing measurement — but it is also not a failure
    the regime can name, so it leaves `degraded` to whatever the snapshot said."""
    assert st.completeness_verdict({}) == (False, None)
    assert st.completeness_verdict(None) == (False, None)


# -- the measurement itself ---------------------------------------------------

class _Conn:
    """Answers the two queries _window_completeness asks, from a fixture book."""

    def __init__(self, universe, complete_by_window):
        self.universe = universe
        self.complete = complete_by_window
        self.asked = []

    async def fetchval(self, sql, *args):
        if "stable_universe u" in sql and "stable_daily_bars" not in sql:
            return self.universe
        sessions, n = args
        self.asked.append((n, tuple(sessions)))
        return self.complete.get(n, 0)


@pytest.mark.asyncio
async def test_completeness_is_measured_against_the_sessions_not_a_row_count():
    conn = _Conn(255, {1: 250, 5: 103, 20: 103, 50: 103, 200: 103, 252: 103})
    out = await st._window_completeness(conn, date(2026, 9, 23))

    assert set(out) == {str(n) for n, _ in st.REGIME_WINDOWS}
    assert out["1"]["complete"] == 250 and out["1"]["pct"] == 98.0
    assert out["1"]["below_floor"] is False              # positive control
    assert out["20"]["pct"] == 40.4 and out["20"]["below_floor"] is True
    # Each window asked for exactly its own N sessions, ending at the anchor.
    for n, sessions in conn.asked:
        assert len(sessions) == n
        assert sessions[-1] == date(2026, 9, 23)
    assert out["5"]["first_session"] == "2026-09-17"
    assert out["5"]["last_session"] == "2026-09-23"


@pytest.mark.asyncio
async def test_every_window_the_regime_reads_is_covered():
    """A window the regime uses but does not measure is the gap this exists to
    close, so the list is asserted rather than trusted."""
    lengths = [n for n, _ in st.REGIME_WINDOWS]
    assert lengths == sorted(lengths)
    for needed in (1, 5, 20, 50, 200, 252):
        assert needed in lengths, "the regime reads a %dd window and does not measure it" % needed


@pytest.mark.asyncio
async def test_an_empty_universe_does_not_divide_by_zero_or_claim_health():
    conn = _Conn(0, {})
    out = await st._window_completeness(conn, date(2026, 9, 23))
    assert out["20"]["pct"] is None
    assert out["20"]["below_floor"] is True
