"""R-IV.988(b)/(c): the walk stops at its session's start, and the queue is the exchange calendar.

MEASURED, not assumed. Against the 1,208,687 prints already on F:, the queried `date` DOES
appear among its own executed dates (418,682 rows), so `date=D` starts the walk at D and runs
on backwards past D's start -- that overrun, not late reporting, is what produced 36-55%
duplication by `tracking_id`. Estimated effect of the stop on that same archive: 2,420 calls
-> 846, a 65% reduction.

WHY A PAGE MINIMUM IS A SAFE PLACE TO TEST. Each page asks for prints `older_than` the previous
page's MINIMUM, so the page sequence is monotonically non-increasing by construction of the
cursor, whatever the order within a page. A page minimum below the floor therefore guarantees
every later page is below it too.

Every stop assertion here is PAIRED with a control that must NOT stop (Convention #30): an
instrument that always says "stop" would pass a one-sided test while collecting one page per
session and calling every session complete.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from datetime import date, datetime, timezone

from jobs import darkpool_backfill as dp


# -- (c) the calendar ------------------------------------------------------------------

def test_labor_day_is_not_enqueued_but_its_neighbours_are():
    """2026-09-07 is Labor Day. The `weekday() < 5` queue spent ~8 calls a night on it."""
    sessions = dp.trading_sessions(date(2026, 9, 1), date(2026, 9, 11))
    assert date(2026, 9, 7) not in sessions, "Labor Day is still enqueued"
    # POSITIVE CONTROLS: the surrounding sessions must survive. A calendar that excluded
    # everything would pass the assertion above.
    assert date(2026, 9, 4) in sessions
    assert date(2026, 9, 8) in sessions
    assert len(sessions) == 8, sessions


def test_weekends_and_other_holidays_also_excluded():
    sessions = dp.trading_sessions(date(2026, 11, 23), date(2026, 12, 27))
    assert date(2026, 11, 26) not in sessions, "Thanksgiving enqueued"
    assert date(2026, 12, 25) not in sessions, "Christmas enqueued"
    assert date(2026, 11, 28) not in sessions, "a Saturday enqueued"
    assert date(2026, 11, 24) in sessions
    assert date(2026, 12, 24) in sessions


def test_the_calendar_is_the_one_author_not_a_weekday_test():
    """The job must not carry its own holiday opinion -- R-IV.988(c).

    The check PARSES; it does not grep. The docstring of `trading_sessions` says the word
    `weekday` while explaining why `weekday() < 5` was wrong, so a substring scan of the raw
    source fails on the very comment that documents the fix. The docstring node is excluded
    BY IDENTITY -- comparing text to `ast.get_docstring()` never matches, because that
    CLEANS indentation.
    """
    src = inspect.getsource(dp.trading_sessions)      # module-level: already dedented
    fn = ast.parse(src).body[0]
    doc = fn.body[0].value if fn.body and isinstance(fn.body[0], ast.Expr) else None
    body = [n for n in fn.body if not (isinstance(n, ast.Expr) and n.value is doc)]
    code = chr(10).join(ast.unparse(n) for n in body)
    assert "weekday" not in code, "trading_sessions still decides the calendar itself"
    assert "is_trading_day" in code, "it no longer asks the calendar at all"
    # POSITIVE CONTROL: the stripper must not have emptied the body. A scan of "" passes
    # every "X not in code" assertion ever written.
    assert len(code) > 120, "the docstring stripper ate the body: %r" % code


# -- (b) the floor ---------------------------------------------------------------------

def test_session_start_is_0400_et_across_the_dst_boundary():
    """04:00 ET, not 09:30: the feed carries pre-market prints from 04:00 (SPY's oldest
    archived print of 2026-08-31 is 08:00:12Z = 04:00:12 EDT). A 09:30 floor would stop the
    walk before the session's own pre-market prints had been collected."""
    edt = dp.session_start_utc(date(2026, 8, 31))          # EDT, UTC-4
    assert edt == datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc), edt
    est = dp.session_start_utc(date(2026, 1, 15))          # EST, UTC-5
    assert est == datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc), est
    # The pair is the point: a hardcoded UTC offset passes one and fails the other.
    assert edt.hour != est.hour


def test_parse_executed_reads_the_vendors_actual_shape():
    """All 172,642 archived SPY rows are `%Y-%m-%dT%H:%M:%SZ`. Measured, not assumed."""
    got = dp._parse_executed("2026-08-31T08:00:12Z")
    assert got == datetime(2026, 8, 31, 8, 0, 12, tzinfo=timezone.utc)
    assert dp._parse_executed("2026-08-31T08:00:12+00:00") == got
    # A naive stamp is read as UTC rather than guessed at.
    assert dp._parse_executed("2026-08-31T08:00:12").tzinfo is timezone.utc
    # NEVER raises -- a junk stamp must not abort a night's run.
    for junk in (None, "", "not a date", 0):
        assert dp._parse_executed(junk) is None


def test_lexicographic_min_equals_chronological_min_for_this_shape():
    """`_oldest_cursor` uses min() on STRINGS. That equals the chronological minimum only
    because the vendor's shape is fixed-width and UTC. Pinned so a format change fails here
    rather than silently choosing the wrong cursor."""
    stamps = ["2026-09-04T23:59:49Z", "2026-08-31T08:00:12Z", "2026-09-01T13:45:00Z"]
    rows = [{"executed_at": s} for s in stamps]
    assert dp._oldest_cursor(rows) == min(stamps)
    assert dp._parse_executed(dp._oldest_cursor(rows)) == min(
        dp._parse_executed(s) for s in stamps)


# -- (b) the stop, in the loop ---------------------------------------------------------

class _FakeConn:
    """Keyed on the actual SQL. collect_one calls fetchrow TWICE for different things -- the
    resume lookup and the whole-session totals -- and a fake that answered None to both
    crashed on int(tot["pages"]) instead of testing anything."""

    def __init__(self):
        self.stored = []

    async def fetchrow(self, sql, *a, **k):
        if "count(*) AS pages" in sql:
            return {"pages": len(self.stored), "prints": len(self.stored) * dp.PAGE_LIMIT}
        return None          # no resume row: start at page 1

    async def execute(self, sql, *a, **k):
        self.stored.append(a)
        return "INSERT 0 1"


class _FakePool:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *exc):
                return False
        return _Ctx()


def _page(stamps):
    return {"data": [{"executed_at": s, "tracking_id": s} for s in stamps]}


def _walk(monkeypatch, pages):
    """Run collect_one against a scripted page sequence and report what it did."""
    calls = {"n": 0}

    async def fake_fetch(ticker, session, cursor, budget):
        i = calls["n"]
        calls["n"] += 1
        budget.spend()
        if i >= len(pages):
            return {"data": []}, None
        return _page(pages[i]), None

    # Patch the name the LOOP resolves, not the one the function was defined under.
    monkeypatch.setattr(dp, "fetch_page", fake_fetch)
    res = asyncio.run(dp.collect_one(_FakePool(), "SPY", date(2026, 9, 4), dp.Budget(1000)))
    res["_calls"] = calls["n"]
    return res


def test_walk_stops_when_a_page_crosses_the_session_start(monkeypatch):
    """Session 2026-09-04, floor 08:00Z. Page 2's oldest is 09-03 -> stop, complete."""
    full = ["2026-09-04T14:%02d:00Z" % (m % 60) for m in range(dp.PAGE_LIMIT)]
    crossing = ["2026-09-04T08:30:00Z"] * (dp.PAGE_LIMIT - 1) + ["2026-09-03T19:00:00Z"]
    res = _walk(monkeypatch, [full, crossing, full, full])
    assert res["exhausted"] is True, res
    assert "executed before" in res["stop"], res["stop"]
    # It must stop AT the crossing page, not walk on into 09-02.
    assert res["_calls"] == 2, "spent %d calls; the stop did not hold" % res["_calls"]


def test_walk_does_NOT_stop_while_pages_stay_inside_the_session(monkeypatch):
    """THE CONTROL. Same shape, no page crossing the floor: the walk must continue and must
    NOT be marked complete by the boundary rule. Without this, a stop that always fired would
    pass the test above while collecting one page per session and calling it whole."""
    pages = [["2026-09-04T%02d:30:00Z" % h] * dp.PAGE_LIMIT for h in (19, 17, 15, 13, 11, 9)]
    res = _walk(monkeypatch, pages)
    assert res["_calls"] > 2, "the walk stopped early: %d calls" % res["_calls"]
    assert "executed before" not in res["stop"], res["stop"]


def test_a_print_exactly_at_the_session_start_does_not_stop_the_walk(monkeypatch):
    """The floor is inclusive: 04:00:00 ET belongs to the session it starts."""
    at_floor = ["2026-09-04T08:00:00Z"] * dp.PAGE_LIMIT
    res = _walk(monkeypatch, [at_floor, at_floor])
    assert "executed before" not in res["stop"], res["stop"]


def test_completeness_is_decided_by_executed_date_not_by_the_query(monkeypatch):
    """R-IV.988(b): 'Mark a ticker-date complete by EXECUTED date.' The old code called a
    session complete on a short page, which is why 'sessions secured' counted which QUERY
    returned a page rather than where a print happened -- wrong in BOTH directions."""
    crossing = ["2026-09-04T08:10:00Z"] * (dp.PAGE_LIMIT - 1) + ["2026-09-01T10:00:00Z"]
    res = _walk(monkeypatch, [crossing])
    assert res["exhausted"] is True
    assert str(date(2026, 9, 4)) in res["stop"], res["stop"]
