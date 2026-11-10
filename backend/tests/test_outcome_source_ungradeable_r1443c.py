"""R-IV.1443(c): an UNGRADEABLE write to signals must SUCCEED.

`jobs/outcome_resolver._mark_ungradeable` writes outcome_source = 'UNGRADEABLE'. Production's
CHECK (migration 017) never listed it, so the first such row would be refused and retried
forever. The fix widens the constraint from one list, `database.outcome_source_check`.

THE WRITE PROOF runs the REAL `_mark_ungradeable` against a SQL engine that ENFORCES the
constraint (SQLite; no Postgres on this machine), built from the same `check_clause()` the
boot step uses. With 017's old list the identical write is refused: the negative control.
"""
from __future__ import annotations

import asyncio
import os
import re
import sqlite3

import pytest

from database import outcome_source_check as osc

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)

#: Migration 017's list, as production holds it today.
OLD_VALUES = ("BAR_WALK", "ACTUAL_TRADE", "COUNTERFACTUAL", "EXPIRED", "INVALIDATED",
              "PROJECTED_FROM_BAR_WALK", "OPTIONS_PNL", "FWD_RETURN", "COMMITTEE_REVIEW")

#: pg_get_constraintdef as production printed it (read 2026-11-10 via the read-only MCP).
LIVE_DEF = ("CHECK (((outcome_source IS NULL) OR ((outcome_source)::text = ANY ((ARRAY["
            + ", ".join("'%s'::character varying" % v for v in OLD_VALUES) + "])::text[]))))")


# ── a SQLite pool that speaks just enough asyncpg for _mark_ungradeable ─────

class _Conn:
    def __init__(self, db):
        self.db = db

    async def execute(self, sql, *args):
        sql = re.sub(r"\$\d+", "?", sql).replace("NOW()", "CURRENT_TIMESTAMP")
        self.db.execute(sql, args)
        self.db.commit()


class _Acq:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return _Conn(self.db)

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, db):
        self.db = db

    def acquire(self):
        return _Acq(self.db)


def _signals_table(values):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE signals (signal_id TEXT PRIMARY KEY, outcome TEXT, "
               "outcome_resolved_at TEXT, outcome_source TEXT, "
               "CONSTRAINT outcome_source_valid CHECK (%s))" % osc.check_clause(values))
    db.execute("INSERT INTO signals (signal_id) VALUES ('S1')")
    db.commit()
    return db


def _mark(db):
    from jobs.outcome_resolver import _mark_ungradeable
    asyncio.run(_mark_ungradeable(_Pool(db), "S1", "no usable fire timestamp"))


# ── the write ───────────────────────────────────────────────────────────────

def test_an_UNGRADEABLE_write_succeeds_under_the_new_constraint():
    db = _signals_table(osc.OUTCOME_SOURCE_VALUES)
    _mark(db)
    assert db.execute("SELECT outcome, outcome_source FROM signals").fetchone() == \
        ("UNGRADEABLE", "UNGRADEABLE")


def test_the_same_write_is_refused_under_the_old_constraint():
    """Negative control: production's list today refuses it, which is the defect."""
    db = _signals_table(OLD_VALUES)
    with pytest.raises(sqlite3.IntegrityError):
        _mark(db)


def test_the_constraint_still_refuses_a_value_nobody_writes():
    db = _signals_table(osc.OUTCOME_SOURCE_VALUES)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE signals SET outcome_source = 'TYPO' WHERE signal_id = 'S1'")


# ── one list ────────────────────────────────────────────────────────────────

def test_every_writer_constant_is_in_the_list():
    from jobs import outcome_resolver
    assert outcome_resolver.UNGRADEABLE_SOURCE in osc.OUTCOME_SOURCE_VALUES


def test_every_literal_outcome_source_written_in_backend_is_in_the_list():
    pat = re.compile(r"outcome_source\s*=\s*'([A-Z_]+)'")
    found = set()
    for root, dirs, files in os.walk(BACKEND):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__")]
        for f in files:
            if f.endswith(".py"):
                found |= set(pat.findall(open(os.path.join(root, f), encoding="utf-8",
                                              errors="replace").read()))
    assert found, "the scan found nothing, so it proves nothing"
    assert found <= set(osc.OUTCOME_SOURCE_VALUES), found - set(osc.OUTCOME_SOURCE_VALUES)


def test_the_widening_keeps_every_old_value():
    assert set(OLD_VALUES) < set(osc.OUTCOME_SOURCE_VALUES)


def test_migration_056_mirrors_the_list():
    sql = open(os.path.join(REPO, "migrations", "056_outcome_source_ungradeable.sql"),
               encoding="utf-8").read()
    body = sql.split("ADD CONSTRAINT", 1)[1]
    assert tuple(re.findall(r"'([A-Z_]+)'", body)) == osc.OUTCOME_SOURCE_VALUES


def test_the_live_definition_reads_as_missing_UNGRADEABLE():
    assert osc.missing_from(LIVE_DEF) == ["UNGRADEABLE"]


# ── the boot step ───────────────────────────────────────────────────────────

class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _BootConn:
    def __init__(self, definition, fail=False):
        self.definition, self.fail, self.sql = definition, fail, []

    async def fetchval(self, sql, *args):
        if self.fail:
            raise RuntimeError("db down")
        return self.definition

    async def execute(self, sql, *args):
        self.sql.append(sql)

    def transaction(self):
        return _Txn()


def test_boot_widens_a_constraint_that_lacks_UNGRADEABLE():
    c = _BootConn(LIVE_DEF)
    assert asyncio.run(osc.ensure_outcome_source_check(c)) == "widened: UNGRADEABLE"
    joined = "\n".join(c.sql)
    assert "DROP CONSTRAINT IF EXISTS outcome_source_valid" in joined
    assert "'UNGRADEABLE'" in joined and "NOT VALID" in joined
    assert c.sql[-1] == "ALTER TABLE signals VALIDATE CONSTRAINT outcome_source_valid"
    assert any("lock_timeout" in s for s in c.sql)


def test_boot_leaves_a_complete_constraint_alone():
    full = "CHECK (" + ", ".join("'%s'" % v for v in osc.OUTCOME_SOURCE_VALUES) + ")"
    c = _BootConn(full)
    assert asyncio.run(osc.ensure_outcome_source_check(c)) == "unchanged"
    assert c.sql == []


def test_boot_never_raises():
    c = _BootConn(None, fail=True)
    assert asyncio.run(osc.ensure_outcome_source_check(c)).startswith("failed")


def test_init_database_runs_the_step():
    src = open(os.path.join(BACKEND, "database", "postgres_client.py"), encoding="utf-8").read()
    assert "await ensure_outcome_source_check(conn)" in src
