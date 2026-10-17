"""R-IV.1195(c) — the purge freeze: no startup path deletes from triton_flow_shadow.

WHY THIS TEST EXISTS, and why it is not "the DELETE is gone, done". A 90-day retention window
measured from NOW() is a MOVING EDGE. It had already swept rows the record treated as fixed --
the "id <= 377783 = 7,014" figure measured 6,993 later because the purge ran on every deploy --
and around 2026-11-14 it reaches rows fired from 2026-08-17, the registered forward test's own
data, days before the 11-20 TRITON decision. Deleting the statement fixes today. Only a test
fixes the next deploy that adds one back.

THE RULING IS EXPLICIT THAT IT IS REMOVED, NOT NARROWED, so this test does not check a window.
It checks that no DELETE against the table exists at all.

NO QUERY, PER R-IV.1192(b). This test reads SOURCE. It never counts rows, and in particular
never counts NULL `graded_at` inside the sealed set.

THE COMMENT PROBLEM, which has caught me eleven times now. Migration 021 quotes the disabled
statement verbatim inside the comment explaining why it must not run, so a naive
`"DELETE FROM triton_flow_shadow" not in src` would fail on the explanation and pass on the
crime. Every scan below strips comments first -- `ast.unparse` for Python (which drops comments
but KEEPS docstrings, so those go too), a line scrubber for SQL -- with controls proving the
scrubbers can still see a real statement and do still hide the commented one.

(The freeze comment in postgres_client.py does NOT quote it; it says "a 90-day retention DELETE
on UNGRADED triton_flow_shadow rows". I asserted otherwise at first and the test failed, which
was the test being wrong about the file rather than the other way round.)
"""
from __future__ import annotations

import os
import re

import pytest

from ._srcscan import code_of_file, function_code

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
CLIENT = os.path.join(BACKEND, "database", "postgres_client.py")
MIGRATION = os.path.join(ROOT, "migrations", "021_triton_flow_shadow.sql")

#: Matches a delete against the table with any whitespace or a TABLE keyword between.
PURGE = re.compile(r"(?:DELETE\s+FROM|TRUNCATE)\s+(?:TABLE\s+)?triton_flow_shadow\b", re.I)


def _sql_code_only(sql: str) -> str:
    """SQL with `--` comments and /* */ blocks removed.

    The freeze comment in migration 021 quotes the disabled statement verbatim, so a scan that
    did not do this would report the explanation as the offence.
    """
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


# ── the ruled assertion ─────────────────────────────────────────────────────

def test_INIT_DATABASE_DOES_NOT_DELETE_FROM_TRITON_FLOW_SHADOW():
    """THE RULING. It ran from init_database() on every boot; it is gone."""
    code = function_code(CLIENT, "init_database")
    assert not PURGE.search(code), PURGE.search(code).group(0)


def test_no_module_under_backend_deletes_from_the_table():
    """Wider than the ruling asks, because the next one could land anywhere. A startup path is
    whatever `main.py` reaches, and enumerating that is less reliable than scanning all of it."""
    offenders = []
    for base, _dirs, files in os.walk(BACKEND):
        if "tests" in base.split(os.sep) or "__pycache__" in base:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(base, f)
            try:
                code = code_of_file(path)
            except SyntaxError:
                continue
            if PURGE.search(code):
                offenders.append(os.path.relpath(path, ROOT))
    assert offenders == [], offenders


def test_the_removal_is_not_a_narrowed_WINDOW():
    """R-IV.1195(c): "Do not narrow it, remove it." A 90-day edge and a 180-day edge are the
    same defect at different speeds, so no interval against this table survives either."""
    code = function_code(CLIENT, "init_database")
    window = re.compile(r"triton_flow_shadow[^;]{0,400}?INTERVAL\s*'\s*\d+\s+days?\s*'", re.I | re.S)
    assert not window.search(code)


def test_the_migration_file_has_no_LIVE_purge():
    """Not a startup path -- nothing in the app executes migrations/*.sql -- but replaying 021
    by hand would no-op every CREATE ... IF NOT EXISTS and then delete live rows."""
    sql = _sql_code_only(open(MIGRATION, encoding="utf-8-sig").read())
    assert not PURGE.search(sql)


def test_the_FILES_STILL_EXPLAIN_WHY_in_a_comment():
    """The inverse of the scan. A statement deleted with no trace invites the next author to add
    it back as an obvious omission, so the reason stays in the file where they will be looking."""
    for path in (CLIENT, MIGRATION):
        raw = open(path, encoding="utf-8-sig").read()
        assert "R-IV.1195(c)" in raw, path
        assert "DEF-TRITON-RETENTION-DARK" in raw, path
    assert "7,014" in open(CLIENT, encoding="utf-8-sig").read(), (
        "the decaying figure is recorded where the decay was caused")


# ── the scrubbers are not blind (positive controls, convention #30) ─────────

def test_POSITIVE_CONTROL_the_python_scan_still_sees_a_real_delete():
    """Without this, a regex that matched nothing would satisfy every test above."""
    import ast
    import tests._srcscan as srcscan
    src = ("async def init_database(conn):\n"
           "    await conn.execute('DELETE FROM triton_flow_shadow WHERE graded_at IS NULL')\n")
    code = ast.unparse(srcscan.strip_docstrings(ast.parse(src)))
    assert PURGE.search(code), "the scan cannot see a delete it is supposed to catch"


def test_POSITIVE_CONTROL_the_sql_scrubber_still_sees_a_real_delete():
    live = "CREATE TABLE x();\nDELETE FROM triton_flow_shadow WHERE graded_at IS NULL;\n"
    assert PURGE.search(_sql_code_only(live))


def test_POSITIVE_CONTROL_the_sql_scrubber_DOES_hide_the_commented_one():
    """The other half, and the pair that makes this suite mean anything: migration 021 really
    does quote the statement verbatim in prose, and the scrubber really does ignore it.

    Only the SQL file is checked here. I first wrote this against postgres_client.py too and it
    failed -- correctly. That comment reads "a 90-day retention DELETE on UNGRADED
    triton_flow_shadow rows", which is not the statement and not something the regex should
    match. The test was wrong about the file, so the test moved.
    """
    raw = open(MIGRATION, encoding="utf-8-sig").read()
    assert PURGE.search(raw), "021 quotes the disabled statement in its freeze comment"
    assert not PURGE.search(_sql_code_only(raw))
    assert not PURGE.search(function_code(CLIENT, "init_database"))


def test_POSITIVE_CONTROL_an_unrelated_retention_purge_is_UNTOUCHED():
    """Proves one statement was removed, not the retention machinery. `flow_events` keeps its
    purge, and a scan that had swept it out would be over-broad."""
    code = function_code(CLIENT, "init_database")
    assert re.search(r"DELETE\s+FROM\s+flow_events", code, re.I), (
        "the flow_events purge is not under this freeze and must still be there")


# ── the seal (R-IV.1192(b)) ─────────────────────────────────────────────────

def test_this_test_file_runs_NO_QUERY():
    """R-IV.1192(b): no count inside the sealed set, not even of NULL `graded_at`.

    Asked of the IMPORT TABLE, not of the file's text. A banned-substring scan over this file
    fails on its own list of banned substrings -- which is the same self-reference fault as the
    comment problem in the module docstring, one level up. What the rule actually cares about is
    whether this module can reach a database at all, and imports answer that exactly.
    """
    import ast
    tree = ast.parse(open(os.path.abspath(__file__), encoding="utf-8-sig").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.update(a.name for a in node.names)
    for db in ("asyncpg", "psycopg2", "sqlalchemy", "redis", "requests", "httpx", "aiohttp"):
        assert db not in imported, db
    assert imported <= {"__future__", "os", "re", "pytest", "ast", "annotations", "tests",
                        "_srcscan", "code_of_file", "function_code"}, imported
