"""`reached_floor` is the ONE author of "this ticker-session is complete" — R-IV.993(d).

MEASURED CAUSE. `exhausted = TRUE` is set by any stop, and the F: export filtered on it alone,
so 2026-09-08, 09-14 and 09-21 went onto the permanent archive while QUERY's A0 marked all
three incomplete. QUERY was right: SPY's 09-08 walk reached 08:00:16Z against a floor of
08:00:00Z -- sixteen seconds short of proving it held the whole session.

R-IV.988(b) already defines completeness the way QUERY measures it ("the walk reached prints
executed before that date's 04:00 ET start"). The column records that one fact so no reader
re-derives it from a prose `stop_reason`, which is how the two came to disagree.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from datetime import date, datetime, timezone

from jobs import darkpool_backfill as dp


class _FakeConn:
    def __init__(self):
        self.stored = []
        self.session_writes = []

    async def fetchrow(self, sql, *a, **k):
        if "count(*) AS pages" in sql:
            return {"pages": len(self.stored), "prints": len(self.stored) * dp.PAGE_LIMIT}
        return None

    async def execute(self, sql, *a, **k):
        if "darkpool_backfill_sessions" in sql and "INSERT" in sql:
            self.session_writes.append(a)
        else:
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
    calls = {"n": 0}

    async def fake_fetch(ticker, session, cursor, budget):
        i = calls["n"]
        calls["n"] += 1
        budget.spend()
        if i >= len(pages):
            return {"data": []}, None
        return _page(pages[i]), None

    monkeypatch.setattr(dp, "fetch_page", fake_fetch)
    pool = _FakePool()
    res = asyncio.run(dp.collect_one(pool, "SPY", date(2026, 9, 8), dp.Budget(1000)))
    res["_writes"] = pool.conn.session_writes
    return res


def test_crossing_the_floor_is_the_only_thing_that_sets_reached_floor(monkeypatch):
    full = ["2026-09-08T14:%02d:00Z" % (m % 60) for m in range(dp.PAGE_LIMIT)]
    crossing = ["2026-09-08T08:30:00Z"] * (dp.PAGE_LIMIT - 1) + ["2026-09-04T19:00:00Z"]
    res = _walk(monkeypatch, [full, crossing])
    assert res["exhausted"] is True
    assert res["reached_floor"] is True, res


def test_a_short_page_sets_exhausted_but_NOT_reached_floor(monkeypatch):
    """THE DEFECT, pinned. This is exactly 2026-09-08: the walk ended at the session's first
    print (04:00:16 ET) without ever proving anything lay before it."""
    short = ["2026-09-08T08:00:16Z"] * (dp.PAGE_LIMIT - 1)      # one short of a full page
    res = _walk(monkeypatch, [short])
    assert res["exhausted"] is True, res
    assert res["reached_floor"] is False, (
        "a short page claimed completeness; this is the 09-08 defect")


def test_a_stalled_cursor_sets_exhausted_but_NOT_reached_floor(monkeypatch):
    same = ["2026-09-08T08:00:16Z"] * dp.PAGE_LIMIT
    res = _walk(monkeypatch, [same, same, same])
    assert res["exhausted"] is True
    assert res["reached_floor"] is False, res


def test_an_empty_first_page_sets_exhausted_but_NOT_reached_floor(monkeypatch):
    res = _walk(monkeypatch, [])
    assert res["exhausted"] is True
    assert res["reached_floor"] is False, res


def test_the_flag_is_written_to_the_session_row(monkeypatch):
    """It must reach the DB, not just the return value: the export reads the COLUMN."""
    crossing = ["2026-09-08T08:30:00Z"] * (dp.PAGE_LIMIT - 1) + ["2026-09-04T19:00:00Z"]
    res = _walk(monkeypatch, [crossing])
    writes = res["_writes"]
    assert writes, "no session row was written"
    assert writes[-1][-1] is True, writes[-1]


def test_there_is_exactly_one_place_that_sets_it_true():
    """A PARSED check, prose stripped. Two authors of this fact is the fault being closed."""
    src = inspect.getsource(dp)
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                docs.add(id(node.body[0].value))
    assigns = [n for n in ast.walk(tree)
               if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "reached_floor" for t in n.targets)
               and isinstance(n.value, ast.Constant) and n.value.value is True]
    assert len(assigns) == 1, "reached_floor is set True in %d places" % len(assigns)


def test_secured_and_the_export_filter_both_require_the_column():
    """The two readers that disagreed must now ask the same question."""
    assert "reached_floor = TRUE" in dp.ALL_SECURED_SQL, dp.ALL_SECURED_SQL
    assert "exhausted = TRUE" in dp.ALL_SECURED_SQL


def test_the_backfill_sql_only_touches_undetermined_rows():
    """NULL means not yet determined, which is NOT false. Recomputing a decided row would let
    a later empty page un-prove a session that had already crossed."""
    sql = dp.BACKFILL_REACHED_FLOOR_SQL
    assert "reached_floor IS NULL" in sql, sql
    assert "NOT_APPLICABLE%" in sql, "closed sessions must be left alone"
    assert "04:00" in sql and "America/New_York" in sql, "the floor must be 04:00 ET"


def test_the_upsert_keeps_a_proved_session_proved():
    """STICKY. A resumed run that stops on a short page must not clear an earlier proof."""
    sql = dp.UPSERT_SESSION
    assert "COALESCE(darkpool_backfill_sessions.reached_floor, FALSE)" in sql, sql
    assert "OR COALESCE(EXCLUDED.reached_floor, FALSE)" in sql, sql
