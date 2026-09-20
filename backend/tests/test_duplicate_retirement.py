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
from models.accounts import (  # noqa: E402
    FIDELITY_ROTH, reconciliation_scope, scope_for, scope_sql,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "043_duplicate_retirement.sql"
BOOT = ROOT / "backend" / "database" / "postgres_client.py"
ANALYTICS = ROOT / "backend" / "analytics" / "api.py"

sys.path.insert(0, str(ROOT / "scripts"))


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


DUP = {"position_id": "dup", "ticker": "BITX", "status": "CLOSED", "realized_pnl": -16.5,
       "trade_id": None}
KEEPER = {"position_id": "keep", "ticker": "BITX", "status": "CLOSED", "realized_pnl": -16.0,
          "trade_id": None}


def test_a_link_follows_the_keeper_when_the_row_it_sat_on_is_retired(monkeypatch):
    """R-IV.465(c): the trade happened ONCE. Retiring the row it was recorded against is a
    bookkeeping act, so the link moves to the row that now carries the trade (BITX: the link to
    trades id 619 sat on the retired row while its keeper carried none)."""
    out, conn = _retire(monkeypatch, {"dup": dict(DUP, trade_id=619), "keep": dict(KEEPER)})
    assert out["link_moved_to_keeper"] == 619 and out["link_conflict"] is None
    keeper_write = [e for e in conn.executed if e[1] and e[1][-1] == "keep"][0]
    assert keeper_write[1][0] == 619 and "LINK FOLLOWED from retired dup" in keeper_write[1][1]
    retired_write = [e for e in conn.executed if "SET status = $1" in e[0]][0]
    assert retired_write[1][3] == 619, "the retired row's link is cleared in the same write"
    assert "LINK MOVED to keeper keep" in retired_write[1][4]


def test_a_link_that_disagrees_with_the_keepers_own_is_left_for_adjudication(monkeypatch):
    out, conn = _retire(monkeypatch, {"dup": dict(DUP, trade_id=619),
                                      "keep": dict(KEEPER, trade_id=700)})
    assert out["link_moved_to_keeper"] is None and "for adjudication" in out["link_conflict"]
    retired_write = [e for e in conn.executed if "SET status = $1" in e[0]][0]
    assert retired_write[1][3] is None, "nothing is moved while the two disagree"
    assert "LINK NOT MOVED" in retired_write[1][4]


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


def test_a_moved_link_appends_its_line_and_overwrites_nothing(monkeypatch):
    """R-IV.465(c) writes one line when a link moves. The duplicate's own notes are the record
    of what caused the duplication: they are appended to, never replaced."""
    _, conn = _retire(monkeypatch, {"dup": dict(DUP, trade_id=619), "keep": dict(KEEPER)})
    writes = [e for e in conn.executed if "notes" in e[0]]
    assert writes, "a moved link is recorded"
    for sql, _args in writes:
        assert "notes = COALESCE(notes, '') ||" in sql and "SET notes = $" not in sql


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
    flat = " ".join(src.replace("#", " ").split()).lower()
    assert "reports absence where there is duplication" in flat
    assert "reads every row touching that window, in any status" in flat


# --- boot resilience (measured 2026-09-18) --------------------------------------------------
def test_a_constraint_that_cannot_be_added_does_not_end_the_boot():
    """One row carrying the status without its pointer stopped the rest of the DDL sequence
    silently: the app served, the schema bootstrap did not finish, and the index that came
    after it was simply never created."""
    boot = BOOT.read_text(encoding="utf-8")
    i = boot.index("unified_positions_duplicate_pointer")
    window = boot[i - 1500:i + 2500]
    assert "try:" in window and "except Exception" in window, (
        "an ALTER that raises here takes every statement after it down with it")


def test_a_refused_constraint_names_the_rows_that_blocked_it():
    """A warning that says only 'not applied' leaves the next reader to re-derive which rows
    were in the way."""
    boot = BOOT.read_text(encoding="utf-8")
    assert "blocking rows:" in boot
    assert "SELECT position_id, status, duplicate_of FROM unified_positions" in boot


# --- the amended rule: label, status AND window (R-IV.450(a)) -------------------------------
def test_a_reconciliation_scope_filters_no_status_at_all():
    """The proximate cause of the duplicate was `status = 'OPEN'`, not the alias: a row opened
    and closed inside the window is exactly the row a status filter hides."""
    clause, params = reconciliation_scope("FIDELITY_ROTH", "2026-09-01", "2026-09-17")
    assert "status" not in clause.lower(), "a status filter is what hid the round trip"
    assert "= ANY($1::text[])" in clause and "FIDELITY" in params[0]


def test_the_window_is_overlap_and_not_containment():
    """A row opened before the window and closed inside it is in the window."""
    clause, _ = reconciliation_scope("ROBINHOOD", "2026-09-01", "2026-09-17")
    assert "entry_date <= $3" in clause and "exit_date >= $2" in clause
    assert "entry_date >= $2" not in clause, "containment would drop the earlier opening"


def test_an_open_row_is_never_excluded_by_its_null_exit_date():
    clause, _ = reconciliation_scope("ROBINHOOD", "2026-09-01", "2026-09-17")
    assert "exit_date IS NULL OR" in clause


def test_the_corrected_cause_is_recorded_not_quietly_edited():
    """The module said the alias hid the row. It did not — LIKE 'FIDELITY%' matched both."""
    src = (ROOT / "backend" / "models" / "accounts.py").read_text(encoding="utf-8")
    flat = " ".join(src.replace("#", " ").split())
    assert "CORRECTION, R-IV.450(a)" in flat
    assert "That was WRONG and is recorded rather than quietly edited" in flat
    assert "proximate cause was the STATUS scope" in flat


def test_the_governing_line_is_on_the_face_of_both_modules():
    acc = (ROOT / "backend" / "models" / "accounts.py").read_text(encoding="utf-8")
    st = (ROOT / "backend" / "models" / "position_status.py").read_text(encoding="utf-8")
    line = "duplicate and an absence present identically"
    assert line in " ".join(acc.replace("#", " ").split()).lower()
    assert line in " ".join(st.split()).lower()


# --- the lift, corrected (R-IV.450(e)) ------------------------------------------------------
def test_the_reference_classifier_reads_segments_not_a_character_window():
    """The notes DO say which order each reference is, two hundred characters away."""
    import lift_broker_refs_from_notes as L
    note = ("09-08 Bought 4 @ 94.85 -> basis 379.40. SECOND COPX lot; id 406 is the 09-02 lot "
            "(4 @ 89.20, basis 356.80). Combined 8 shares, basis 736.20. D5 sleeve member by "
            "id - the roster must add this lot. Ref 26251-P9TZC2, order 26251-FYD2J. "
            "|| R-IV.447(b) CLOSE, ref 26254-Q7D3D4. Same 09-11 8-share sale.")
    assert L.classify(note) == [("entry", "26251-P9TZC2"), ("exit", "26254-Q7D3D4")]


def test_a_close_only_note_yields_no_entry_reference():
    """id 409 has two fills on the open side and no single reference for them."""
    import lift_broker_refs_from_notes as L
    got = L.classify("1-3 day trade || R-IV.447(b) CLOSE, ref 26257-PBS5D3.")
    assert got == [("exit", "26257-PBS5D3")]


def test_a_retired_duplicate_never_acquires_broker_evidence():
    src = (ROOT / "scripts" / "lift_broker_refs_from_notes.py").read_text(encoding="utf-8")
    assert "if is_retired(r[\"status\"]):" in src
    assert "belongs to the row it duplicates" in src


def test_the_remap_covers_every_table_that_stores_the_label():
    import remap_legacy_account_label as R
    names = {t for t, *_ in R.TABLES}
    assert {"unified_positions", "closed_positions", "trades"} <= names
    src = (ROOT / "scripts" / "remap_legacy_account_label.py").read_text(encoding="utf-8")
    assert "EVERY TABLE" in src.upper()
