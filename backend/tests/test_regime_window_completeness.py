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
        sessions, required = args
        n = len(sessions)
        self.asked.append((n, tuple(sessions)))
        # What the query ASKED for, which is where the tolerance shows up.
        if not hasattr(self, "required"):
            self.required = {}
        self.required[n] = required
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


# -- the anchor lag ----------------------------------------------------------
#
# ONE STEP BEYOND the ruling, flagged in the report. Measured live 2026-09-24: the
# envelope said as_of 1.6h, flatline false, degraded false, while metrics_date was
# 2026-09-21 -- three sessions back. The nightly had run an hour before and simply
# re-published 09-21's numbers, so every staleness signal read healthy.

def test_an_anchor_that_is_current_does_not_degrade_the_read():
    """POSITIVE CONTROL for the lag arm."""
    lag = {"metrics_date": "2026-09-23", "newest_complete_session": "2026-09-23",
           "sessions_behind": 0}
    assert st.completeness_verdict({}, lag) == (False, None)


def test_an_anchor_behind_a_complete_session_degrades_and_says_both_dates():
    lag = {"metrics_date": "2026-09-21", "newest_complete_session": "2026-09-23",
           "sessions_behind": 2}
    degraded, reason = st.completeness_verdict({}, lag)
    assert degraded is True
    assert "2 sessions behind" in reason
    assert "2026-09-21" in reason and "2026-09-23" in reason


def test_one_session_behind_reads_as_singular():
    lag = {"metrics_date": "2026-09-22", "newest_complete_session": "2026-09-23",
           "sessions_behind": 1}
    _d, reason = st.completeness_verdict({}, lag)
    assert "1 session behind" in reason


def test_both_faults_are_reported_together_not_one_instead_of_the_other():
    windows = {"20": _w(20, 40.4, True)}
    lag = {"metrics_date": "2026-09-21", "newest_complete_session": "2026-09-23",
           "sessions_behind": 2}
    degraded, reason = st.completeness_verdict(windows, lag)
    assert degraded is True
    assert "20d at 40.4%" in reason and "2 sessions behind" in reason


def test_an_unmeasurable_lag_is_not_read_as_a_healthy_one():
    """None means the calendar could not answer, which is not zero."""
    lag = {"metrics_date": "2026-09-21", "newest_complete_session": None,
           "sessions_behind": None}
    # It does not fabricate a lag reason it cannot support...
    degraded, reason = st.completeness_verdict({}, lag)
    assert (degraded, reason) == (False, None)
    # ...and a real lag still fires, so the guard above is not just always-quiet.
    assert st.completeness_verdict({}, dict(lag, sessions_behind=3))[0] is True


class _LagConn:
    def __init__(self, universe, newest):
        self.universe = universe
        self.newest = newest
        self.required = None

    async def fetchval(self, sql, *args):
        if "stable_daily_bars" in sql:
            self.required = args[0]
            return self.newest
        return self.universe


@pytest.mark.asyncio
async def test_the_lag_uses_scorings_own_required_ticker_count():
    from stable_engine.scoring import ANCHOR_MIN_COVERAGE, ANCHOR_MIN_TICKERS_FLOOR

    conn = _LagConn(255, date(2026, 9, 23))
    out = await st._anchor_lag(conn, date(2026, 9, 21))
    assert conn.required == max(ANCHOR_MIN_TICKERS_FLOOR, int(255 * ANCHOR_MIN_COVERAGE))
    assert out["sessions_behind"] == 2          # 09-22 and 09-23 are both sessions
    assert out["newest_complete_session"] == "2026-09-23"


@pytest.mark.asyncio
async def test_no_complete_session_at_all_reports_nothing_rather_than_zero():
    conn = _LagConn(255, None)
    out = await st._anchor_lag(conn, date(2026, 9, 21))
    assert out["sessions_behind"] is None
    assert out["newest_complete_session"] is None


# -- R-IV.535(c)2: the tolerance ---------------------------------------------

@pytest.mark.parametrize("n,allowed", [
    (1, 0), (5, 0), (10, 0), (19, 0), (20, 1), (39, 1), (40, 2), (50, 2),
    (200, 10), (252, 12),
])
def test_the_tolerance_is_floor_n_over_twenty(n, allowed):
    """R-IV.535(c)2, on every window length, no exclusions."""
    assert st.window_tolerance(n) == allowed


def test_the_windows_the_regime_reads_get_the_ruled_tolerances():
    expected = {1: 0, 5: 0, 20: 1, 50: 2, 200: 10, 252: 12}
    for n, _feeds in st.REGIME_WINDOWS:
        assert st.window_tolerance(n) == expected[n]


@pytest.mark.asyncio
async def test_a_window_asks_for_n_minus_its_tolerance_sessions():
    """The query must use `>= n - allowed`, not `= n`. Asserted by what it ASKS for,
    because the fixture's counts cannot tell the two apart."""
    conn = _Conn(255, {})
    await st._window_completeness(conn, date(2026, 9, 23))
    asked = {n: req for n, req in getattr(conn, "required", {}).items()}
    assert asked == {1: 1, 5: 5, 20: 19, 50: 48, 200: 190, 252: 240}


@pytest.mark.asyncio
async def test_the_tolerance_is_served_so_a_reader_need_not_infer_it():
    conn = _Conn(255, {1: 250, 5: 103, 20: 250, 50: 250, 200: 249, 252: 249})
    out = await st._window_completeness(conn, date(2026, 9, 23))
    assert out["5"]["misses_allowed"] == 0 and out["5"]["sessions_required"] == 5
    assert out["20"]["misses_allowed"] == 1 and out["20"]["sessions_required"] == 19


@pytest.mark.asyncio
async def test_one_hole_leaves_the_short_window_short_and_the_long_ones_whole():
    """THE INTENDED ASYMMETRY (R-IV.535(c)2), on the live shape of 2026-09-22: the
    5-day window reads on the 103 symbols that hold it, the longer ones tolerate it."""
    conn = _Conn(255, {1: 250, 5: 103, 20: 250, 50: 250, 200: 249, 252: 249})
    out = await st._window_completeness(conn, date(2026, 9, 23))
    assert out["5"]["pct"] == 40.4 and out["5"]["below_floor"] is True
    for n in ("20", "50", "200", "252"):
        assert out[n]["below_floor"] is False, n
    # And the read stays DEGRADED, naming only the window that is short.
    degraded, reason = st.completeness_verdict(out)
    assert degraded is True
    assert "5d at 40.4%" in reason
    assert "20d" not in reason


# -- R-IV.535(c)1: an incomplete session never blocks a later complete one ---

def test_the_anchor_takes_the_newest_complete_date_not_the_newest_date():
    """Pinned rather than trusted. `anchor_date` orders by date DESC with a HAVING on
    coverage, so an incomplete date is never a candidate and cannot stand in front of
    a later complete one. On 2026-09-24 the live anchor was 09-23 with 09-22 still
    holding 135 bars of 679, which is this rule working."""
    import inspect

    from stable_engine import scoring

    src = inspect.getsource(scoring.anchor_date)
    assert "HAVING COUNT(DISTINCT ticker) >= %s" in src
    assert "ORDER BY date DESC" in src
    # It must not fall back to MAX(date) when nothing qualifies -- that is the defect
    # the docstring names, and returning None is what keeps readers empty instead of
    # anchored on a two-ticker date.
    assert "NOT anchoring on MAX(date)" in src
    assert "return None, 0, required" in src


# -- R-IV.535(c)3: a healed session makes every window over it stale ---------

def test_the_span_covers_every_stored_date_at_or_after_the_healed_session():
    import inspect

    from stable_engine import scoring

    src = inspect.getsource(scoring.score_dates_spanning)
    assert "date >= %s" in src
    assert "anchor = %s" in src


def test_the_recompute_replaces_rather_than_adding_a_second_opinion():
    """`store_theme_scores` deletes the whole (date, anchor) set first, so a recompute
    replaces. Two sets of scores for one date would double every rank."""
    import inspect

    from stable_engine import scoring

    assert "DELETE FROM stable_theme_scores WHERE anchor = %s" in \
        inspect.getsource(scoring.store_theme_scores)
    assert "store_theme_scores" in inspect.getsource(scoring.recompute_theme_scores)


def test_the_nightly_detects_a_heal_by_difference_and_names_it():
    """No new table and no state between passes: the gate is asked before and after
    the re-requests, and the difference is the heal."""
    import inspect

    from jobs import stable_jobs

    src = inspect.getsource(stable_jobs._nightly_work)
    assert "incomplete_before" in src
    assert "score_dates_spanning" in src
    assert "recompute_theme_scores" in src
    # On the face, so a heal reads as work done rather than a figure that changed
    # overnight on its own.
    assert '"healed_sessions"' in src
    assert '"recomputed_after_heal"' in src
