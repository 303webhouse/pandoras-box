"""A READ NEVER WAITS ON A WRITER — R-IV.1052(b). The guard that would have caught it twice.

TWICE IN ONE SESSION I SHIPPED A READ THAT DEPENDED ON A WRITER HAVING RUN:

  1. `services/read_only/market_profile.py` SELECTed `pythia_events.script_version`, a column
     created by an `ALTER TABLE` inside the PYTHIA webhook's INSERT path. The webhook was
     rejecting every alert, so nothing ever created the column and `hub_get_market_profile`
     returned `column "script_version" does not exist` for EVERY ticker -- a hard outage.
  2. The same read then computed `feed_health` from `pythia_webhook_rejections`, a table
     created inside the REJECTION handler. First live read-back: `feed_health "unknown"`.

Both were caught by reading the live surface after deploying. Neither was caught by the suite,
because no test exercised a first-boot database. I wrote the lesson into the first commit
message and repeated it in the next feature, which is exactly why it has to be a test.

THREE CHECKS, cheapest first:
  * every TABLE a read path queries is created by the STARTUP migrations;
  * every COLUMN a read path selects that is added by an ALTER is added AT STARTUP -- the
    precise generalisation of failure (1), where the only creator was a writer;
  * every MCP tool runs against a simulated first-boot database (startup tables present and
    EMPTY, everything else raising UndefinedTable) without a missing-table error.

AND THE SCAN PARSES, IT DOES NOT GREP. The first version of this file regexed FROM/JOIN over
raw source and reported sixty "tables" that were Python imports (`from __future__`, `from
services`) and plain English (`from the`, `from these`) -- the prose trap, in the guard written
to catch a different kind of blindness. Table names are now taken only from string literals
that actually contain SELECT, found with `ast`.
"""
from __future__ import annotations

import ast
import io
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)

#: The files that run at boot. A table or column these create exists for every reader.
STARTUP_FILES = ("main.py", os.path.join("database", "postgres_client.py"))

#: Read paths: the surfaces a consumer reaches. `api` is included because R-IV.1052(b) names
#: read ENDPOINTS as well as MCP tools.
READ_DIRS = (os.path.join("services", "read_only"), os.path.join("hub_mcp", "tools"), "api")

_CREATE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", re.I)
_ADD_COL = re.compile(r"ADD COLUMN IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", re.I)
#: The ALTER's TARGET. A column is only meaningful with the table it is on: `reached_floor`
#: on a table that first boot does not have at all is the TABLE's debt, counted once, not a
#: second independent finding.
_ALTER = re.compile(r"ALTER TABLE\s+(?:IF EXISTS\s+)?([a-z_][a-z0-9_]*)", re.I)
_FROM = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", re.I)
_SQLISH = re.compile(r"SELECT\b", re.I)

#: PRE-EXISTING DEBT, recorded so NEW violations fail while the old ones stay visible.
#:
#: Each of these is a read that would fail or degrade on a genuinely fresh database. They are
#: not mine and not this ruling's scope, but they are the same fault, so they are listed by
#: name with the file that reads them. THIS SET MUST SHRINK AND NEVER GROW -- adding to it is
#: how a debt register becomes a permission slip.
KNOWN_FIRST_BOOT_DEBT = {
    "darkpool_backfill_pages", "darkpool_backfill_runs", "darkpool_backfill_sessions",
    "lightning_cards", "v2_dashboard_layout", "close_attempts", "watchlist_config",
    "stable_daily_bars", "stable_ext_quotes", "stable_intraday_points", "stable_metrics",
    "stable_theme_scores", "stable_universe", "stable_live_strip", "stable_movers",
    "stable_zweig",
}

#: Same, for columns.
KNOWN_FIRST_BOOT_COLUMN_DEBT = {
    "confluence_count", "confluence_tier", "confluence_updated_at", "prior_close",
}

#: Not tables: SQL constructs, catalog views, and CTE/alias names. Listed explicitly so a real
#: table can never be excused by a clever pattern.
_NOT_TABLES = frozenset({
    "lateral", "unnest", "jsonb_array_elements", "generate_series", "select", "values",
    "information_schema", "prints", "agg", "sub", "latest", "ranked", "base", "cte",
    "rows", "src", "lots", "closures", "scores", "events",
})


def _read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def _py_files(rel_dir):
    root = os.path.join(BACKEND, rel_dir)
    out = []
    for dirpath, _d, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for f in files:
            if f.endswith(".py") and not f.startswith("__"):
                out.append(os.path.join(dirpath, f))
    return out


def strip_sql_comments(sql):
    """SQL with its `--` line comments removed.

    The SAME trap one level down: a SQL literal's own comments are prose, and "…from the
    lots…" inside one reads as a table named `the`. `ast` strips prose from Python; this
    strips it from SQL. Already learned once in test_reached_floor_r993's `_sql_code`.
    """
    out = []
    for line in (sql or "").splitlines():
        i = line.find("--")
        out.append(line if i < 0 else line[:i])
    return "\n".join(out)


def sql_literals(src):
    """Every string literal in the source that actually contains SQL, comments stripped.

    PARSES rather than greps: `ast` yields string CONSTANTS, so an import line and a sentence
    in a docstring cannot be mistaken for a query. A literal counts as SQL only when it
    contains SELECT, which is what makes a following FROM/JOIN mean a table.
    """
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _SQLISH.search(node.value):
                out.append(strip_sql_comments(node.value))
    return out


def all_created_tables():
    """Every table any CREATE TABLE in the backend makes. Cached on the function.

    THIS IS THE PRECISE FILTER, and it replaces a growing blocklist of English words. A token
    after FROM is only treated as a table when something, somewhere, creates a table by that
    name. Prose can never satisfy that, so `the`, `it`, `outside` and `w` disappear without
    being enumerated -- and a read of a table created SOMEWHERE but not at STARTUP, which is
    exactly the fault, still trips.

    A table nothing creates anywhere is a different bug and is out of scope here.
    """
    cached = getattr(all_created_tables, "_c", None)
    if cached is not None:
        return cached
    found = set()
    for dirpath, _d, files in os.walk(BACKEND):
        if "__pycache__" in dirpath:
            continue
        for f in files:
            if f.endswith((".py", ".sql")):
                found |= {t.lower() for t in _CREATE.findall(
                    _read(os.path.join(dirpath, f)))}
    all_created_tables._c = found
    return found


def tables_read_by(src):
    found = set()
    for lit in sql_literals(src):
        found |= {t.lower() for t in _FROM.findall(lit)}
    known = all_created_tables()
    # Postgres catalog views are always present; they are not application tables.
    return {t for t in found
            if t in known and t not in _NOT_TABLES and not t.startswith("pg_")}


def _startup_sql():
    return "\n".join(_read(os.path.join(BACKEND, f)) for f in STARTUP_FILES)


def startup_tables():
    return {t.lower() for t in _CREATE.findall(_startup_sql())}


def altered_columns(src):
    """{(table, column)} for every `ALTER TABLE t ADD COLUMN IF NOT EXISTS c` in `src`.

    Splits on ALTER TABLE and attributes every ADD COLUMN in each chunk to that chunk's
    table, which is what the multi-column single-statement form (one ALTER, five ADD COLUMNs)
    actually means.
    """
    out = set()
    parts = _ALTER.split(src)
    # parts[0] is whatever preceded the first ALTER; then (table, body) pairs.
    for i in range(1, len(parts) - 1, 2):
        tbl = parts[i].lower()
        out |= {(tbl, c.lower()) for c in _ADD_COL.findall(parts[i + 1])}
    return out


def startup_columns():
    return {c.lower() for c in _ADD_COL.findall(_startup_sql())}


# -- 0. positive controls: every check below is vacuous without these -------------------

def test_the_scans_find_something_at_all():
    """A source-scanning test that finds nothing passes while checking nothing."""
    assert len(startup_tables()) > 40, "startup table scan is broken"
    assert len(startup_columns()) > 3, "startup column scan is broken"
    read_tables = set()
    for rel in READ_DIRS:
        for p in _py_files(rel):
            read_tables |= tables_read_by(_read(p))
    assert len(read_tables) > 10, "read-path SQL scan found only %d tables" % len(read_tables)
    # And it must NOT be picking up prose or imports any more.
    for junk in ("__future__", "typing", "the", "these", "services", "datetime"):
        assert junk not in read_tables, "the scan is reading prose again: %r" % junk


# -- 1. every table a read queries is created at startup -------------------------------

def test_every_table_a_read_path_queries_is_created_at_startup():
    """Catches failure (2): `pythia_webhook_rejections` was created only by the rejection
    handler, so a read of it on a fresh database finds nothing there."""
    created = startup_tables()
    offenders = {}
    for rel in READ_DIRS:
        for path in _py_files(rel):
            for tbl in tables_read_by(_read(path)):
                if tbl in created or tbl in KNOWN_FIRST_BOOT_DEBT:
                    continue
                offenders.setdefault(os.path.relpath(path, BACKEND), set()).add(tbl)
    assert not offenders, (
        "a READ path queries a table the startup migrations do not create -- it will fail or "
        "degrade on a fresh database until some writer happens to run:\n  "
        + "\n  ".join("%s -> %s" % (f, sorted(t)) for f, t in sorted(offenders.items())))


# -- 2. every column a read selects is migrated AT STARTUP -----------------------------

def test_no_column_a_read_selects_is_created_only_by_a_writer():
    """THE PRECISE GENERALISATION OF FAILURE (1). `script_version` was added by an ALTER inside
    the PYTHIA webhook's INSERT path and nowhere else, so it existed only once an alert had
    been ACCEPTED -- and the webhook was rejecting every one.

    Only columns a READ path selects matter: a writer that adds a column and is the only thing
    that ever reads it cannot strand anyone.
    """
    at_startup = startup_columns()
    read_sql = "\n".join(
        lit for rel in READ_DIRS for p in _py_files(rel) for lit in sql_literals(_read(p)))

    writer_only = {}
    for dirpath, _d, files in os.walk(BACKEND):
        if any(part in dirpath for part in ("tests", "__pycache__", ".venv")):
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            rel = os.path.relpath(path, BACKEND).replace("\\", "/")
            if rel in [s.replace("\\", "/") for s in STARTUP_FILES]:
                continue
            for tbl, col in altered_columns(_read(path)):
                if col in at_startup or col in KNOWN_FIRST_BOOT_COLUMN_DEBT:
                    continue
                if tbl in KNOWN_FIRST_BOOT_DEBT:
                    # The TABLE is already on the register. Listing its columns as well would
                    # report one debt twice and make the register look like it was growing.
                    continue
                if re.search(r"\b%s\b" % re.escape(col), read_sql, re.I):
                    writer_only.setdefault(col, set()).add(rel)
    assert not writer_only, (
        "a READ path selects a column added by an ALTER OUTSIDE the startup path and never at "
        "startup, so the read reaches it before any writer has run -- the `script_version` "
        "outage, generalised:\n  "
        + "\n  ".join("%s <- added only in %s" % (c, sorted(f))
                      for c, f in sorted(writer_only.items())))


# -- 3. every MCP tool survives a simulated first boot ---------------------------------

class _UndefinedTable(Exception):
    """Stands in for asyncpg.UndefinedTableError."""


class _FirstBootConn:
    """A database with the startup tables present and EMPTY, and nothing else.

    Any query naming a table the startup migrations do not create raises, exactly as Postgres
    would on a fresh volume. That is the condition both failures needed and the suite lacked.
    """

    def __init__(self, allowed):
        self.allowed = allowed
        self.seen = set()

    def _check(self, sql):
        s = sql or ""
        if not _SQLISH.search(s):
            return
        for tbl in {t.lower() for t in _FROM.findall(s)}:
            if tbl in _NOT_TABLES or tbl.startswith("pg_"):
                continue
            self.seen.add(tbl)
            if tbl not in self.allowed:
                raise _UndefinedTable('relation "%s" does not exist' % tbl)

    async def fetch(self, sql, *a, **k):
        self._check(sql)
        return []

    async def fetchrow(self, sql, *a, **k):
        self._check(sql)
        return None

    async def fetchval(self, sql, *a, **k):
        self._check(sql)
        return None

    async def execute(self, sql, *a, **k):
        self._check(sql)
        return "OK"


class _FirstBootPool:
    def __init__(self, allowed):
        self.conn = _FirstBootConn(allowed)

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *exc):
                return False
        return _Ctx()


def _tool_callables():
    """Every `hub_get_*` coroutine the MCP exposes, by module."""
    import importlib
    import inspect
    found = []
    for path in _py_files(os.path.join("hub_mcp", "tools")):
        mod_name = "hub_mcp.tools." + os.path.basename(path)[:-3]
        try:
            mod = importlib.import_module(mod_name)
        except Exception:                                           # noqa: BLE001
            continue
        for name, fn in vars(mod).items():
            if name.startswith("hub_get_") and inspect.iscoroutinefunction(fn):
                found.append((mod_name, name, fn))
    return found


def test_the_tool_scan_finds_tools_at_all():
    tools = _tool_callables()
    assert len(tools) >= 10, "only found %d hub_get_* tools" % len(tools)


def test_every_mcp_tool_survives_a_first_boot_database(monkeypatch):
    """Calls every `hub_get_*` tool against a first-boot database, failing on any
    missing-table error.

    A tool that cannot bind its arguments is SKIPPED: this test is about the DATABASE, not
    argument shapes. A missing-table error is never skipped.
    """
    import asyncio
    import importlib
    import inspect

    allowed = startup_tables()
    pool = _FirstBootPool(allowed)

    async def fake_pool():
        return pool

    import database.postgres_client as pc
    monkeypatch.setattr(pc, "get_postgres_client", fake_pool)

    failures = []
    for mod_name, name, fn in _tool_callables():
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "get_postgres_client"):
            monkeypatch.setattr(mod, "get_postgres_client", fake_pool, raising=False)
        kwargs = {}
        for pname, p in inspect.signature(fn).parameters.items():
            if p.default is not inspect.Parameter.empty:
                continue
            kwargs[pname] = ("2026-10-16" if ("expiry" in pname or "date" in pname)
                             else "SPY")
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fn(**kwargs))
        except _UndefinedTable as exc:
            failures.append("%s.%s -> %s" % (mod_name, name, exc))
        except TypeError:
            continue
        except Exception:                                           # noqa: BLE001
            continue
        finally:
            loop.close()
    assert not failures, (
        "these MCP tools query a table the startup migrations do not create, so they fail on "
        "a fresh database:\n  " + "\n  ".join(failures))
