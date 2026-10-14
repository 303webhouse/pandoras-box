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


def _sql_code(sql: str) -> str:
    """SQL with its `--` line comments stripped.

    FIFTH OCCURRENCE OF THE SAME TRAP. A scan of raw SQL for `reached_floor IS NULL` matched
    the COMMENT explaining why that clause was wrong. `ast` strips prose from Python; nothing
    did for SQL, so this does. A comment documenting a fix must never fail the test asserting
    the fix.
    """
    out = []
    for line in sql.splitlines():
        i = line.find("--")
        out.append(line if i < 0 else line[:i])
    return chr(10).join(out)



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
    assert "reached_floor = TRUE" in _sql_code(dp.ALL_SECURED_SQL), dp.ALL_SECURED_SQL
    assert "exhausted = TRUE" in _sql_code(dp.ALL_SECURED_SQL)


def test_the_backfill_sql_never_un_proves_a_session():
    """A PROVED session must never be revisited, or a later empty page could un-prove it.

    R-IV.1005(d) widened the scope from "undecided rows" to "every row not yet proved",
    because the b1-only pass had already written FALSE to 09-08, 09-14 and 09-21 -- so
    `reached_floor IS NULL` would have shut b2 out of exactly the sessions it exists for.
    TRUE is still never touched, so the protection is identical by a different clause.
    """
    sql = _sql_code(dp.BACKFILL_REACHED_FLOOR_SQL)
    assert "COALESCE(s.reached_floor, FALSE) = FALSE" in sql, sql
    assert "reached_floor IS NULL" not in sql, "b2 cannot reach rows already written FALSE"
    assert "NOT_APPLICABLE%" in sql, "closed sessions must be left alone"
    assert "04:00" in sql and "America/New_York" in sql, "the floor must be 04:00 ET"


def test_the_vendor_cap_is_READ_not_hardcoded():
    """R-IV.1005(d). PAGE_LIMIT is what this job REQUESTS, not what the vendor promises; a
    hardcoded cap would make every final page look short -- and so every session look
    exhausted -- the moment the vendor served fewer per page."""
    sql = _sql_code(dp.BACKFILL_REACHED_FLOOR_SQL)
    assert "MAX(row_count)" in sql, sql
    assert "observed_cap" in sql, sql
    assert "500" not in sql, "a literal page cap appears in the completeness SQL"


def test_b2_requires_an_unbroken_chain_and_an_early_first_print():
    sql = _sql_code(dp.BACKFILL_REACHED_FLOOR_SQL)
    assert "unbroken" in sql, sql
    assert "MAX(page_no) = COUNT(*)" in sql, "a chain with a hole is not a chain"
    # R-IV.1010(c): 04:15, not 09:30. Every complete session in the window starts within 20
    # SECONDS of 04:00 ET, so a 09:30 bound was five and a half hours of slack on a boundary
    # the data says is twenty seconds wide.
    assert "04:15" in sql, "b2 must bound the earliest print at 04:15 ET"
    assert "09:30" not in sql, "the old loose bound is still in the completeness SQL"


def test_suspect_is_a_third_state_not_a_flavour_of_complete():
    """A short page at 04:00 ET is exhaustion; at 11:00 on SPY it is truncation. Recording
    them alike is how 09-08 reached a permanent archive unproved."""
    sql = _sql_code(dp.SUSPECT_SESSIONS_SQL)
    assert "04:15" in sql and "04:00" in sql, sql
    # SUSPECT rows must NOT be among those the UPDATE sets TRUE.
    upd = _sql_code(dp.BACKFILL_REACHED_FLOOR_SQL)
    assert "earliest_print <=" in upd, upd


def test_the_upsert_keeps_a_proved_session_proved():
    """STICKY. A resumed run that stops on a short page must not clear an earlier proof."""
    sql = _sql_code(dp.UPSERT_SESSION)
    assert "COALESCE(darkpool_backfill_sessions.reached_floor, FALSE)" in sql, sql
    assert "OR COALESCE(EXCLUDED.reached_floor, FALSE)" in sql, sql
