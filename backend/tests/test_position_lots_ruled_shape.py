"""position_lots at the RULED shape, and the figures derived from it (R-IV.441(a)).

FAIL-FIRST against the pre-2026-09-17 tree: models/position_lots.py did not exist, the table's
columns were `quantity` and `fill_date`, there was no provenance anywhere, the blended price
folded fees in, the option multiplier was missing, and an unpriced lot's basis was extrapolated
over the priced lots instead of reading UNKNOWN.

The migration tests are text assertions on purpose. A migration cannot be exercised without a
database, but the two properties that matter here are readable: that the renames are guarded on
BOTH names (so neither shape can make it fail), and that it writes no lot (so the invariant it
is measured by is not satisfied by its own backfill).
"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models.position_lots import (  # noqa: E402
    BROKER_VERIFIED, IMPORTED, PRINCIPAL_REPORTED, PROVENANCE_VALUES, UNKNOWN,
    derive_aggregate, integral_qty, multiplier, provenance_for_lot, provenance_for_parent,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "037_position_lots_ruled_shape.sql"
BOOT = ROOT / "backend" / "database" / "postgres_client.py"
API = ROOT / "backend" / "api" / "unified_positions.py"
PHASE1 = ROOT / "scripts" / "feat_position_lifecycle_phase1.py"


# --- provenance: inherited, never defaulted, never verified -------------------------------
@pytest.mark.parametrize("src", ["IMPORTED_HISTORICAL", "CSV_IMPORT", "CSV_SYNC",
                                 "CSV_RECONCILE", "fidelity_confirm"])
def test_an_imported_parent_gives_an_imported_lot(src):
    assert provenance_for_parent(src, 12.5) == IMPORTED


@pytest.mark.parametrize("src", ["MANUAL", "SCREENSHOT_SYNC", "SIGNAL"])
def test_a_hand_entered_parent_gives_a_reported_lot(src):
    assert provenance_for_parent(src, 12.5) == PRINCIPAL_REPORTED


def test_an_unmapped_parent_falls_to_the_weakest_value_not_the_strongest():
    """A source nobody mapped means nothing is known to have checked the row."""
    assert provenance_for_parent("SOME_FUTURE_IMPORTER", 12.5) == PRINCIPAL_REPORTED
    assert provenance_for_parent(None, 12.5) == PRINCIPAL_REPORTED


def test_an_unpriced_lot_is_unknown_whatever_its_parent_says():
    for src in ("MANUAL", "CSV_IMPORT", "fidelity_confirm", None):
        assert provenance_for_parent(src, None) == UNKNOWN
    assert provenance_for_lot("IMPORT", None) == UNKNOWN


def test_the_write_path_maps_its_two_sources():
    assert provenance_for_lot("MANUAL", 1.0) == PRINCIPAL_REPORTED
    assert provenance_for_lot("IMPORT", 1.0) == IMPORTED


def test_nothing_in_this_module_can_return_broker_verified():
    """BROKER_VERIFIED needs a broker record matched; no path in this build matches one."""
    sources = ["MANUAL", "IMPORT", "CSV_IMPORT", "IMPORTED_HISTORICAL", "fidelity_confirm",
               "SIGNAL", "SCREENSHOT_SYNC", "BROKER_VERIFIED", "", None]
    produced = {provenance_for_parent(s, p) for s in sources for p in (1.0, None)}
    produced |= {provenance_for_lot(s, p) for s in sources for p in (1.0, None)}
    assert BROKER_VERIFIED not in produced
    assert produced <= set(PROVENANCE_VALUES)


# --- the multiplier is the asset's ---------------------------------------------------------
def test_contracts_are_a_hundred_shares_and_equities_are_one():
    assert multiplier("OPTION") == 100
    assert multiplier("SPREAD") == 100
    assert multiplier("option") == 100
    assert multiplier("EQUITY") == 1
    assert multiplier(None) == 1


# --- derivation ----------------------------------------------------------------------------
def test_the_blended_price_is_gross_and_fees_are_reported_beside_it():
    """Folding fees into the per-unit price is net-where-the-convention-is-gross."""
    agg = derive_aggregate([{"qty": 10, "price": 5.0, "fees": 7.0},
                            {"qty": 10, "price": 7.0, "fees": 3.0}], "EQUITY")
    assert agg["entry_price"] == 6.0, "gross blend of 5 and 7 over equal size"
    assert agg["fees"] == 10.0
    assert agg["cost_basis"] == 120.0


def test_an_option_basis_carries_the_hundred():
    agg = derive_aggregate([{"qty": 2, "price": 1.40, "fees": 0}], "OPTION")
    assert agg["multiplier"] == 100
    assert agg["cost_basis"] == pytest.approx(280.0)


def test_the_same_lots_on_an_equity_row_do_not():
    agg = derive_aggregate([{"qty": 2, "price": 1.40, "fees": 0}], "EQUITY")
    assert agg["cost_basis"] == pytest.approx(2.80)


def test_an_unpriced_lot_moves_quantity_and_leaves_the_priced_basis_standing():
    """R-IV.456(a) replaced the first rule. NULL was honest about the unknown and discarded a
    basis that was right for every priced unit; the priced basis now stands and the row says
    what it does not cover."""
    agg = derive_aggregate([{"qty": 10, "price": 5.0, "fees": 0},
                            {"qty": 5, "price": None, "fees": 0}], "EQUITY")
    assert agg["qty"] == 15, "the shares exist whether or not their price is known"
    assert agg["entry_price"] == 5.0, "the blend over PRICED lots"
    assert agg["cost_basis"] == 50.0, "the basis of what is priced, never extrapolated to 75"
    assert agg["basis_complete"] is False and agg["unpriced_qty"] == 5
    assert "covers 10 of 15" in agg["unknown_reason"]


def test_an_empty_lot_set_says_so_rather_than_returning_zero():
    agg = derive_aggregate([], "EQUITY")
    assert agg["qty"] == 0 and agg["cost_basis"] is None
    assert agg["unknown_reason"] == "no lots"


def test_lots_that_net_to_zero_do_not_produce_a_basis():
    agg = derive_aggregate([{"qty": 5, "price": 4.0, "fees": 0},
                            {"qty": -5, "price": 6.0, "fees": 0}], "EQUITY")
    assert agg["qty"] == 0 and agg["cost_basis"] is None


def test_a_fractional_sum_is_not_silently_truncated():
    assert integral_qty(3.0) == 3
    assert integral_qty(-4.0) == -4
    assert integral_qty(2.5) is None, "int() here would drop half a share without an event"
    assert integral_qty(3.0000000001) == 3


# --- the migration ---------------------------------------------------------------------
def test_the_migration_exists_and_carries_a_down():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "-- DOWN" in sql
    assert "RENAME COLUMN fill_time TO fill_date" in sql
    assert "RENAME COLUMN qty TO quantity" in sql


def test_each_rename_is_guarded_on_both_names():
    """The old name present AND the new one absent — so either shape converges, twice run."""
    sql = MIGRATION.read_text(encoding="utf-8")
    for old, new in (("quantity", "qty"), ("fill_date", "fill_time")):
        i = sql.index(f"RENAME COLUMN {old} TO {new}")
        guard = sql[:i]
        assert f"column_name = '{old}'" in guard and f"column_name = '{new}'" in guard


def test_the_migration_writes_no_lot():
    """D9 is FALSE in production and that is the starting state, not a thing to backfill."""
    sql = MIGRATION.read_text(encoding="utf-8").upper()
    assert "INSERT INTO POSITION_LOTS" not in sql


def test_the_migration_never_stamps_a_verification_it_did_not_perform():
    sql = MIGRATION.read_text(encoding="utf-8")
    body = sql.split("-- DOWN")[0]
    stamped = [ln for ln in body.splitlines()
               if "BROKER_VERIFIED" in ln and not ln.strip().startswith("--")]
    # the vocabulary CHECK and the broker_ref constraint may name it; no UPDATE may assign it
    assert all("SET provenance" not in ln for ln in stamped)
    assert "provenance <> 'BROKER_VERIFIED' OR broker_ref IS NOT NULL" in body


def test_boot_mirrors_the_migration():
    """A fresh database and the live one have to reach the same shape (conventions #12)."""
    boot = BOOT.read_text(encoding="utf-8")
    for token in ("CREATE TABLE IF NOT EXISTS position_lots", "fill_time", "qty",
                  "ADD COLUMN IF NOT EXISTS provenance", "ADD COLUMN IF NOT EXISTS broker_ref",
                  "position_lots_provenance_check", "position_lots_verified_needs_ref",
                  "RENAME COLUMN quantity TO qty", "RENAME COLUMN fill_date TO fill_time"):
        assert token in boot, f"boot DDL is missing {token!r}"
    assert "INSERT INTO position_lots" not in boot, "boot must not invent a lot either"


def test_the_one_shot_script_no_longer_creates_or_backfills_the_table():
    """The table outside migrations/ is what made it invisible to a migrations search."""
    src = PHASE1.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS position_lots" not in src
    assert "INSERT INTO position_lots" not in src
    assert "l.qty <> p.quantity" in src, "its remaining read must use the ruled column name"


def test_no_lot_sql_in_the_api_still_uses_the_old_column_names():
    src = API.read_text(encoding="utf-8")
    sql_words = ("SELECT", "INSERT", "UPDATE", "FROM", "ORDER BY", "VALUES", "SET ")
    for line in src.splitlines():
        if "fill_date" in line and any(w in line for w in sql_words):
            pytest.fail(f"a lot query still names fill_date: {line.strip()}")
    assert "(position_id, fill_time, qty, price, fees, source, provenance," in src


def test_the_add_no_longer_merges_a_stale_aggregate():
    """COALESCE kept the pre-add basis when the new one was unknown — a number describing a
    position that no longer exists. The aggregate is written, including as NULL."""
    src = API.read_text(encoding="utf-8")
    assert "entry_price = COALESCE($2, entry_price)" not in src
    assert "SET quantity = $1, entry_price = $2, cost_basis = $3" in src


# --- the route ------------------------------------------------------------------------
class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


def _pool(position, lots_after):
    """A connection that answers the route's three reads and records its writes."""
    conn = MagicMock()
    conn.executed = []

    async def execute(sql, *args):
        conn.executed.append((" ".join(sql.split()), args))

    async def fetchrow(sql, *args):
        if "FROM position_lots WHERE broker_ref" in sql:
            return None          # no existing lot carries this reference
        return position

    async def fetch(sql, *args):
        return [dict(l) for l in lots_after]

    conn.execute = execute
    conn.fetchrow = fetchrow
    conn.fetch = fetch
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


def _run(coro):
    import asyncio
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _add(monkeypatch, position, lots_after, **req):
    from api import unified_positions as U
    pool, conn = _pool(position, lots_after)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    body = {"fill_time": "2026-09-17T14:30:00-04:00", "qty": 1.0, "price": 1.0,
            "fees": 0.0, "source": "MANUAL"}
    body.update(req)
    return _run(U.add_position_lot(position["position_id"], U.AddLotRequest(**body))), conn


OPEN_OPTION = {"position_id": "p1", "ticker": "QQQ", "structure": "VERTICAL",
               "asset_type": "OPTION", "account": "ROBINHOOD", "status": "OPEN"}
OPEN_EQUITY = dict(OPEN_OPTION, asset_type="EQUITY", ticker="SOXS")


def test_the_add_writes_the_ruled_columns_and_a_derived_provenance(monkeypatch):
    out, conn = _add(monkeypatch, OPEN_EQUITY,
                     [{"qty": 10, "price": 5.0, "fees": 0}], qty=10, price=5.0)
    insert = [e for e in conn.executed if "INSERT INTO position_lots" in e[0]]
    assert len(insert) == 1
    sql, args = insert[0]
    assert "fill_time, qty, price, fees, source, provenance, broker_ref" in sql
    assert args[6] == PRINCIPAL_REPORTED, "a MANUAL add is reported, not verified"
    assert out["quantity"] == 10 and out["entry_price"] == 5.0
    assert out["cost_basis"] == 50.0 and out["basis_known"] is True


def test_an_import_add_records_the_broker_reference_it_was_given(monkeypatch):
    out, conn = _add(monkeypatch, OPEN_EQUITY, [{"qty": 3, "price": 2.0, "fees": 0}],
                     qty=3, price=2.0, source="IMPORT", broker_ref="26246-P2JS0Y")
    _, args = [e for e in conn.executed if "INSERT INTO position_lots" in e[0]][0]
    assert args[6] == IMPORTED and args[7] == "26246-P2JS0Y"


def test_an_option_add_stores_a_basis_with_the_contract_multiplier(monkeypatch):
    out, _ = _add(monkeypatch, OPEN_OPTION, [{"qty": 2, "price": 1.40, "fees": 0}],
                  qty=2, price=1.40)
    assert out["cost_basis"] == pytest.approx(280.0), "a missing 100x understates by 99%"


def test_fees_stay_out_of_the_stored_entry_price(monkeypatch):
    out, _ = _add(monkeypatch, OPEN_EQUITY, [{"qty": 10, "price": 5.0, "fees": 4.0}],
                  qty=10, price=5.0, fees=4.0)
    assert out["entry_price"] == 5.0 and out["fees_total"] == 4.0


def test_an_unpriced_lot_keeps_the_priced_basis_and_marks_the_row(monkeypatch):
    """R-IV.456(a): recompute never prices unpriced quantity."""
    out, conn = _add(monkeypatch, OPEN_EQUITY,
                     [{"qty": 10, "price": 5.0, "fees": 0}, {"qty": 5, "price": None,
                                                             "fees": 0}],
                     qty=5, price=None)
    upd = [e for e in conn.executed if "UPDATE unified_positions" in e[0]][0]
    assert upd[1][2] == 50.0, "the priced basis, not 75.00 invented for unpriced units"
    assert upd[1][3] and "covers 10 of 15" in upd[1][3], "the row says what is uncovered"
    assert out["unpriced_lots"] == 1 and out["quantity"] == 15


def test_a_fractional_lot_sum_is_refused_with_the_reason(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _add(monkeypatch, OPEN_EQUITY, [{"qty": 2.5, "price": 5.0, "fees": 0}],
             qty=2.5, price=5.0)
    assert e.value.status_code == 400
    assert "INTEGER" in e.value.detail and "lose shares" in e.value.detail


def test_a_lot_cannot_be_added_to_a_closed_position(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _add(monkeypatch, dict(OPEN_EQUITY, status="CLOSED"),
             [{"qty": 1, "price": 1.0, "fees": 0}])
    assert e.value.status_code == 400


def test_the_old_field_names_are_refused_rather_than_aliased():
    from api.unified_positions import AddLotRequest
    with pytest.raises(Exception):
        AddLotRequest(fill_date="2026-09-17", quantity=1)
    assert set(AddLotRequest.model_fields) >= {"fill_time", "qty", "broker_ref"}
    assert "quantity" not in AddLotRequest.model_fields
