"""R-IV.449(a)(b) — a duplicate is retired by being marked, and an inventory reads the aliases.

FAIL-FIRST against the pre-2026-09-18 tree: there was no DUPLICATE_OF status, no pointer to a
keeper, no way to retire a row without deleting it, and the analytics rollup partitioned on
`status != "open"` — which counts a retired duplicate as a completed trade and sums one round
trip twice.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models import position_status as PS  # noqa: E402
from models.accounts import FIDELITY_ROTH, scope_for, scope_sql  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "043_duplicate_retirement.sql"
BOOT = ROOT / "backend" / "database" / "postgres_client.py"
ANALYTICS = ROOT / "backend" / "analytics" / "api.py"


# --- the status vocabulary -------------------------------------------------------------
def test_not_open_is_not_the_same_question_as_completed():
    """The whole defect in one assertion: a retired duplicate is neither open nor a result."""
    assert PS.is_open("OPEN") and not PS.is_open("DUPLICATE_OF")
    assert PS.counts_as_realized("CLOSED") and PS.counts_as_realized("EXPIRED")
    assert not PS.counts_as_realized("DUPLICATE_OF"), "its money belongs to the keeper"
    assert not PS.counts_as_realized("OPEN")
    assert PS.is_retired("DUPLICATE_OF") and not PS.is_retired("CLOSED")


def test_the_vocabulary_is_case_and_space_tolerant_at_the_edges():
    assert PS.counts_as_realized(" closed ") and PS.is_open("open")
    assert not PS.counts_as_realized(None)


def test_the_rollup_asks_the_vocabulary_rather_than_negating_open():
    src = ANALYTICS.read_text(encoding="utf-8")
    assert 'str(r.get("status", "")).lower() != "open"' not in src, (
        "partitioning on 'not open' sums a retired duplicate as a completed trade")
    assert "position_status.counts_as_realized(r.get(\"status\"))" in src
    assert "position_status.is_open(r.get(\"status\"))" in src


# --- the schema --------------------------------------------------------------------------
def test_the_keeper_is_named_in_a_column_not_in_prose():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS duplicate_of TEXT" in sql
    assert "-- DOWN" in sql


def test_the_status_and_the_pointer_must_agree():
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    assert "CHECK ((status = 'DUPLICATE_OF') = (duplicate_of IS NOT NULL))" in sql


def test_nothing_may_point_at_itself():
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    assert "CHECK (duplicate_of IS NULL OR duplicate_of <> position_id)" in sql


def test_boot_mirrors_it_and_runs_after_the_table_exists():
    boot = BOOT.read_text(encoding="utf-8")
    assert "unified_positions_duplicate_pointer" in boot
    assert boot.index("ADD COLUMN IF NOT EXISTS duplicate_of") > \
        boot.index("CREATE TABLE IF NOT EXISTS unified_positions (")


def test_the_migration_deletes_nothing():
    sql = MIGRATION.read_text(encoding="utf-8").upper()
    assert "DELETE FROM" not in sql


# --- the endpoint ------------------------------------------------------------------------
class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


def _pool(rows):
    conn = MagicMock()
    conn.executed = []

    async def fetchrow(sql, *args):
        return rows.get(args[0])

    async def execute(sql, *args):
        conn.executed.append((" ".join(sql.split()), args))

    conn.fetchrow, conn.execute = fetchrow, execute
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


DUP = {"position_id": "dup", "ticker": "BITX", "status": "CLOSED", "realized_pnl": -16.5}
KEEPER = {"position_id": "keep", "ticker": "BITX", "status": "CLOSED", "realized_pnl": -16.0}


def _retire(monkeypatch, rows, **body):
    from api import unified_positions as U
    pool, conn = _pool(rows)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    req = U.RetireDuplicateRequest(**{"duplicate_of": "keep",
                                      "reason": "same round trip, broker-matched row kept",
                                      **body})
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(U.retire_duplicate_position("dup", req)), conn
    finally:
        loop.close()


def test_retiring_marks_the_row_and_names_its_keeper(monkeypatch):
    out, conn = _retire(monkeypatch, {"dup": DUP, "keep": KEEPER})
    upd = [e for e in conn.executed if "UPDATE unified_positions" in e[0]]
    assert len(upd) == 1 and upd[0][1][0] == "DUPLICATE_OF" and upd[0][1][1] == "keep"
    assert out["realized_no_longer_counted"] == -16.5


def test_retiring_never_deletes_and_never_touches_the_notes(monkeypatch):
    _, conn = _retire(monkeypatch, {"dup": DUP, "keep": KEEPER})
    assert not [e for e in conn.executed if "DELETE" in e[0].upper()]
    assert not [e for e in conn.executed if "notes" in e[0]]


def test_a_retirement_needs_a_stated_reason(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _retire(monkeypatch, {"dup": DUP, "keep": KEEPER}, reason="   ")
    assert "reason is required" in e.value.detail


def test_a_row_cannot_be_a_duplicate_of_itself(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _retire(monkeypatch, {"dup": DUP}, duplicate_of="dup")
    assert e.value.status_code == 400


def test_the_keeper_has_to_exist(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _retire(monkeypatch, {"dup": DUP})
    assert e.value.status_code == 404 and "carried by nothing" in e.value.detail


def test_a_keeper_that_is_itself_retired_is_refused(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _retire(monkeypatch, {"dup": DUP, "keep": dict(KEEPER, status="DUPLICATE_OF")})
    assert "point at the row that actually holds the trade" in e.value.detail


# --- the reconciliation rule (R-IV.449(b)) -------------------------------------------------
def test_an_inventory_scope_includes_every_known_alias():
    scope = scope_for("FIDELITY_ROTH")
    assert scope[0] == FIDELITY_ROTH
    assert "FIDELITY" in scope, "the alias that hid a row from an account-scoped read"
    assert len(scope) > 1


def test_an_unknown_label_raises_rather_than_scoping_to_itself():
    """Silently scoping to exactly what was typed is the failure this prevents."""
    with pytest.raises(HTTPException):
        scope_for("SCHWAB")


def test_the_sql_helper_matches_every_spelling():
    clause, params = scope_sql("FIDELITY_ROTH")
    assert "= ANY($1::text[])" in clause
    assert "FIDELITY" in params[0] and "FIDELITY_ROTH" in params[0]


def test_the_rule_is_written_where_the_next_reconciliation_will_read_it():
    src = (ROOT / "backend" / "models" / "accounts.py").read_text(encoding="utf-8")
    flat = " ".join(src.replace("#", " ").split())
    assert "reports ABSENCE where there is DUPLICATION" in flat
    assert "or it is not an inventory" in flat.lower()
