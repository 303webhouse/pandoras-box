"""Triton Amendment 4 (R-IV.521, ordered by R-IV.522(b)) — session gaps and provenance.

Convention #30 throughout: each refusal is paired with a case that must SUCCEED.
A no-substitution rule that refused everything would pass every negative test and
grade nothing, which is the failure mode hardest to see from the outside.
"""

from datetime import date

import pytest

from jobs import triton_shadow_common as common
from jobs import triton_shadow_grader as grader


SESSION = date(2026, 9, 22)          # the session the vendor held for ~1 in 5 symbols
IDX_WITH = {date(2026, 9, 21): 100.0, SESSION: 110.0, date(2026, 9, 23): 120.0}
IDX_WITHOUT = {date(2026, 9, 21): 100.0, date(2026, 9, 23): 120.0}


# -- (b) the lookup can no longer hide a substitution ------------------------

def test_close_on_or_near_says_which_session_it_used():
    """The substitution behaviour is unchanged for the callers that want it
    (R-IV.522(b)2) — what changed is that the date comes back with it."""
    close, used = common.close_on_or_near(IDX_WITH, SESSION)
    assert (close, used) == (110.0, SESSION)

    close, used = common.close_on_or_near(IDX_WITHOUT, SESSION)
    assert close == 120.0                      # it still substitutes...
    assert used == date(2026, 9, 23)           # ...and now it says so


def test_close_on_or_near_with_nothing_near_returns_a_pair_of_nones():
    assert common.close_on_or_near({}, SESSION) == (None, None)


# -- (c) inside the window there is no substitution at all -------------------

def test_close_on_session_takes_the_session_or_nothing():
    assert common.close_on_session(IDX_WITH, SESSION) == 110.0        # positive control
    assert common.close_on_session(IDX_WITHOUT, SESSION) is None
    # A neighbour one day away is exactly the case the old lookup accepted.
    assert date(2026, 9, 23) in IDX_WITHOUT


# -- the three separate requests --------------------------------------------

class _Pool:
    """Counts absences per (ticker, session) the way the table does."""

    def __init__(self, start=0):
        self.counts = {}
        self.start = start

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return _Conn(pool)

            async def __aexit__(self, *a):
                return False

        return _Ctx()


class _Conn:
    def __init__(self, pool):
        self.pool = pool

    async def fetchval(self, sql, ticker, session_date, provider):
        key = (ticker, session_date, provider)
        self.pool.counts[key] = self.pool.counts.get(key, self.pool.start) + 1
        return self.pool.counts[key]


@pytest.mark.asyncio
async def test_a_present_bar_is_graded_and_nothing_is_counted():
    """POSITIVE CONTROL. The strict path must still produce a close."""
    pool = _Pool()
    close, used, gap = await grader._close_for_session(
        pool, IDX_WITH, SESSION, ticker="AAA", provider="yfinance", strict=True)
    assert (close, used, gap) == (110.0, SESSION, None)
    assert pool.counts == {}


@pytest.mark.asyncio
async def test_an_absent_bar_is_retried_before_it_is_called_a_gap():
    pool = _Pool()
    seen = []
    for _ in range(grader.SESSION_GAP_MIN_ATTEMPTS):
        close, used, gap = await grader._close_for_session(
            pool, IDX_WITHOUT, SESSION, ticker="AAA", provider="yfinance", strict=True)
        assert close is None and used is None       # never a neighbour's close
        seen.append(gap)
    assert seen[:-1] == [grader.SESSION_BAR_RETRYING] * (
        grader.SESSION_GAP_MIN_ATTEMPTS - 1)
    assert seen[-1] == grader.SESSION_GAP
    assert pool.counts[("AAA", SESSION, "yfinance")] == grader.SESSION_GAP_MIN_ATTEMPTS


@pytest.mark.asyncio
async def test_one_failure_is_never_a_gap():
    pool = _Pool()
    _c, _u, gap = await grader._close_for_session(
        pool, IDX_WITHOUT, SESSION, ticker="AAA", provider="yfinance", strict=True)
    assert gap == grader.SESSION_BAR_RETRYING
    assert gap != grader.SESSION_GAP


@pytest.mark.asyncio
async def test_an_unreadable_counter_names_the_gap_rather_than_holding_forever():
    class _Broken:
        def acquire(self):
            raise RuntimeError("no pool")

    _c, _u, gap = await grader._close_for_session(
        _Broken(), IDX_WITHOUT, SESSION, ticker="AAA", provider="yfinance", strict=True)
    assert gap == grader.SESSION_GAP


@pytest.mark.asyncio
async def test_an_out_of_window_row_keeps_the_neighbour_probe():
    """R-IV.522(b)2 left other callers' behaviour alone. `strict=False` is that path,
    and it substitutes AND reports the date."""
    pool = _Pool()
    close, used, gap = await grader._close_for_session(
        pool, IDX_WITHOUT, SESSION, ticker="AAA", provider="uw", strict=False)
    assert (close, used, gap) == (120.0, date(2026, 9, 23), None)
    assert pool.counts == {}


# -- (d) the gap text a read's face is built from ---------------------------

def test_the_gap_text_names_horizon_and_session():
    assert grader._gap_text({3: date(2026, 9, 22)}) == "3d@2026-09-22"
    assert grader._gap_text({5: date(2026, 9, 24), 1: date(2026, 9, 18)}) == \
        "1d@2026-09-18,5d@2026-09-24"
    assert grader._gap_text({}) is None


# -- a horizon session is a weekday the exchange traded ---------------------

@pytest.mark.parametrize("d,expected", [
    (date(2026, 9, 22), True),        # a Tuesday session
    (date(2026, 9, 26), False),       # a Saturday
    (date(2026, 11, 26), False),      # Thanksgiving
    (date(2026, 9, 7), False),        # Labor Day
])
def test_horizon_is_session_reads_the_calendar(d, expected):
    assert common.horizon_is_session(d) is expected


def test_no_exchange_holiday_falls_inside_the_registered_window():
    """R-IV.522(b)4, as a standing check rather than a remembered measurement.

    nth_trading_day walks Mon-Fri with no holiday calendar, so the weekday walk and
    the exchange calendar agree only while the window holds no holiday. This test
    fails the day that stops being true — including if the window is ever extended.
    """
    from stable_engine.market_calendar import add_trading_days

    first = common.TRITON_WINDOW_FIRST_SESSION
    last_horizon = add_trading_days(common.TRITON_WINDOW_LAST_SESSION, max(grader.HORIZONS))
    from stable_engine.market_calendar import MARKET_HOLIDAYS
    inside = sorted(d for d in MARKET_HOLIDAYS if first <= d <= last_horizon)
    assert inside == [], "an exchange holiday now falls inside the window: %s" % inside


def test_the_weekday_walk_and_the_calendar_agree_across_the_whole_window():
    """The stronger form: for every in-window session and every horizon, the horizon
    nth_trading_day computes IS a session. That is what makes the weekday walk safe
    here, and it is checked rather than argued."""
    from datetime import timedelta

    d = common.TRITON_WINDOW_FIRST_SESSION
    checked = 0
    while d <= common.TRITON_WINDOW_LAST_SESSION:
        if common.horizon_is_session(d):
            for k in grader.HORIZONS:
                assert common.horizon_is_session(common.nth_trading_day(d, k)) is True
                checked += 1
        d += timedelta(days=1)
    assert checked == 34 * len(grader.HORIZONS)      # 34 sessions, R-IV.485(b)


# -- the cohorts, read off the registration ---------------------------------

def test_the_seven_cohorts_hold_the_registration_s_thirty_four_sessions():
    from stable_engine.market_calendar import is_trading_day
    from datetime import timedelta

    total = 0
    last = None
    for k in range(1, 8):
        lo, hi = common.cohort_bounds("W%d" % k)
        d = lo
        while d <= hi:
            if is_trading_day(d):
                total += 1
            d += timedelta(days=1)
        last = hi
    assert total == 34
    assert common.cohort_bounds("W1")[0] == common.TRITON_WINDOW_FIRST_SESSION
    assert last == common.TRITON_WINDOW_LAST_SESSION


@pytest.mark.parametrize("d,expected", [
    (date(2026, 9, 15), "W1"), (date(2026, 9, 18), "W1"),
    (date(2026, 9, 21), "W2"), (date(2026, 9, 22), "W2"),
    (date(2026, 10, 30), "W7"),
    (date(2026, 9, 14), None), (date(2026, 11, 2), None),
])
def test_cohort_of_a_session(d, expected):
    assert common.cohort_of(d) == expected


@pytest.mark.parametrize("name", ["W0", "W8", "", None, "X1", "W", "week1"])
def test_an_unknown_cohort_name_is_refused(name):
    assert common.cohort_bounds(name) is None


# -- the fresh-grade command's contract -------------------------------------

def test_the_fresh_grade_command_writes_no_grade_into_the_shadow_table():
    """Amendment 4(e) keeps the pre-amendment grades. The command appends versions;
    if it ever learned to UPDATE triton_flow_shadow it would destroy the comparison
    that shows what the substitution did."""
    import ast
    import inspect

    from jobs import triton_fresh_grade as fg

    tree = ast.parse(inspect.getsource(fg))
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docs.add(id(first.value))
    # The docstrings NAME these on purpose, so only live strings are scanned.
    live = " ".join(n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docs).upper()
    assert "UPDATE TRITON_FLOW_SHADOW" not in live
    assert "GRADED_AT" not in live
    # Positive control: it DOES write the versions table, so the scan is live.
    assert "INSERT INTO TRITON_GRADE_VERSIONS" in live


def test_the_fresh_grade_command_needs_a_cohort_or_ids():
    import asyncio

    from jobs.triton_fresh_grade import fresh_grade

    res = asyncio.run(fresh_grade())
    assert "error" in res and res["versions_written"] == 0


def test_the_fresh_grade_command_refuses_an_unknown_cohort():
    import asyncio

    from jobs.triton_fresh_grade import fresh_grade

    res = asyncio.run(fresh_grade(cohort="W9"))
    assert "unknown cohort" in res["error"]


# -- a NaN is an absent bar, not a price -------------------------------------
#
# Found in the live table on 2026-09-24, AFTER Amendment 4's first deploy: 62
# in-window row-horizons hold `NaN` in triton_flow_shadow, on horizons 2026-09-22
# and 2026-09-23. `float("nan")` succeeds, so the price converter admitted it, and
# every downstream guard was written as `if not x` — and `not nan` is False.

NAN = float("nan")
INF = float("inf")


@pytest.mark.parametrize("bad", [NAN, INF, -INF, "nan", "inf", "-Infinity"])
def test_the_price_converter_refuses_a_non_finite_value(bad):
    assert common._f(bad) is None
    # Positive control: it still converts a real price, from either type.
    assert common._f("123.45") == 123.45
    assert common._f(7) == 7.0


@pytest.mark.parametrize("bad", [NAN, INF, -INF])
def test_a_non_finite_close_is_an_absent_bar_in_both_lookups(bad):
    idx = {SESSION: bad, date(2026, 9, 23): 120.0}
    assert common.close_on_session(idx, SESSION) is None
    # The neighbour probe skips it and keeps looking, rather than returning NaN.
    close, used = common.close_on_or_near(idx, SESSION)
    assert (close, used) == (120.0, date(2026, 9, 23))


@pytest.mark.asyncio
async def test_a_non_finite_bar_is_retried_and_then_called_a_gap():
    """The whole point: the session's key EXISTS in the index, so a presence check
    would have passed. It is the value that is not a price."""
    pool = _Pool()
    idx = {date(2026, 9, 21): 100.0, SESSION: NAN, date(2026, 9, 23): 120.0}
    seen = []
    for _ in range(grader.SESSION_GAP_MIN_ATTEMPTS):
        close, used, gap = await grader._close_for_session(
            pool, idx, SESSION, ticker="AAA", provider="yfinance", strict=True)
        assert close is None and used is None
        seen.append(gap)
    assert seen[-1] == grader.SESSION_GAP


def test_a_return_that_is_not_a_number_is_not_a_grade():
    assert grader._dir_adj(100.0, 110.0, "BULL") == 10.0        # positive control
    assert grader._dir_adj(100.0, 110.0, "BEAR") == -10.0       # positive control
    assert grader._dir_adj(100.0, NAN, "BULL") is None
    assert grader._dir_adj(NAN, 110.0, "BULL") is None
    assert grader._dir_adj(0.0, 110.0, "BULL") is None
    assert grader._dir_adj(100.0, INF, "BULL") is None


def test_a_nan_entry_would_have_passed_the_old_entry_guard():
    """Why `_f` is the right place for the fix, kept as a standing note.

    The grader's entry check is `if not entry or entry <= 0`. Against NaN both
    halves are False, so the guard passes it — which is how a NaN entry produced
    NaN grades. The fix is that `_f` never hands one over in the first place."""
    entry = NAN
    assert not (not entry or entry <= 0)        # the old guard DID let it through
    assert common._f(NAN) is None               # and now it cannot arrive
