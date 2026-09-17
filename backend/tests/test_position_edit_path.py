"""R-IV.444(c) — the edit path: add-to, reduce/close FIFO, and what may not be edited.

FAIL-FIRST against the pre-2026-09-17 tree: there was no reduce path at all, no FIFO, no
preview, no closure allocations, no duplicate-reference refusal, and quantity / entry_price /
cost_basis were editable straight through the PATCH while lots computed them.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from api._position_write_scope import (  # noqa: E402
    DERIVED_COLUMNS, assert_derived_not_edited,
)
from models.position_lots import fifo_plan  # noqa: E402

T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _lot(i, qty, price, days=0):
    return {"id": i, "qty": qty, "price": price, "fees": 0,
            "fill_time": T0 + timedelta(days=days)}


# --- FIFO -----------------------------------------------------------------------------------
def test_the_oldest_fill_is_consumed_first():
    plan = fifo_plan([_lot(1, 10, 5.0, 0), _lot(2, 10, 7.0, 10)], 12, 8.0, "EQUITY")
    assert [a["lot_id"] for a in plan["allocations"]] == [1, 2]
    assert plan["allocations"][0]["qty"] == 10 and plan["allocations"][1]["qty"] == 2
    # (8-5)*10 + (8-7)*2 = 32
    assert plan["realized"] == pytest.approx(32.0)
    assert plan["remaining_qty"] == 8 and plan["closes_position"] is False


def test_a_contract_reduction_carries_the_multiplier():
    plan = fifo_plan([_lot(1, 2, 1.40, 0)], 2, 2.00, "OPTION")
    assert plan["multiplier"] == 100
    assert plan["realized"] == pytest.approx(120.0)
    assert plan["closes_position"] is True


def test_fees_reduce_the_realized_result_and_are_reported():
    plan = fifo_plan([_lot(1, 10, 5.0, 0)], 10, 6.0, "EQUITY", fees=4.0)
    assert plan["fees"] == 4.0 and plan["realized"] == pytest.approx(6.0)


def test_a_reduction_larger_than_the_book_is_refused_with_the_shortfall():
    plan = fifo_plan([_lot(1, 5, 5.0, 0)], 8, 6.0, "EQUITY")
    assert plan["sufficient"] is False and plan["shortfall"] == 3
    assert plan["remaining_qty"] is None


def test_an_earlier_disposal_is_netted_before_the_next_one_allocates():
    """The second sale must not re-consume shares the first already took."""
    lots = [_lot(1, 10, 5.0, 0), _lot(2, 10, 7.0, 5), _lot(3, -10, 8.0, 10)]
    plan = fifo_plan(lots, 10, 9.0, "EQUITY")
    assert plan["available_qty"] == 10
    assert [a["lot_id"] for a in plan["allocations"]] == [2]
    assert plan["realized"] == pytest.approx(20.0)


def test_an_unpriced_acquisition_makes_the_result_unknown_not_zero():
    plan = fifo_plan([_lot(1, 10, None, 0)], 10, 9.0, "EQUITY")
    assert plan["realized"] is None and plan["realized_known"] is False
    assert "not a number" in plan["realized_unknown_reason"]
    assert plan["allocations"][0]["realized"] is None


def test_a_disposal_with_no_price_is_also_unknown():
    plan = fifo_plan([_lot(1, 10, 5.0, 0)], 10, None, "EQUITY")
    assert plan["realized"] is None


# --- derived fields ---------------------------------------------------------------------
def test_the_derived_three_are_refused_where_lots_exist():
    for col in ("quantity", "entry_price", "cost_basis"):
        with pytest.raises(HTTPException) as e:
            assert_derived_not_edited([col, "notes"], has_lots=True)
        assert e.value.status_code == 400
        assert "/lots" in e.value.detail and "/reduce" in e.value.detail, (
            "a refusal must name the door that IS open")


def test_the_same_edit_is_allowed_where_there_are_no_lots_to_derive_from():
    """50 positions carry no lot. Refusing there would leave them uncorrectable."""
    assert_derived_not_edited(["quantity", "entry_price"], has_lots=False)


def test_a_non_derived_edit_passes_either_way():
    assert_derived_not_edited(["notes", "stop_loss", "tags"], has_lots=True)
    assert DERIVED_COLUMNS == {"quantity", "entry_price", "cost_basis"}


def test_the_patch_path_checks_the_columns_it_is_about_to_write():
    from api import unified_positions as U
    src = inspect.getsource(U.update_position)
    assert "assert_derived_not_edited(touched, has_lots)" in src
    assert src.index("touched =") < src.index("assert_derived_not_edited")


# --- the endpoint ---------------------------------------------------------------------------
class _Acq:
    def __init__(self, conn): self._c = conn
    async def __aenter__(self): return self._c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


OPEN_EQUITY = {"position_id": "p1", "ticker": "SOXS", "asset_type": "EQUITY",
               "account": "ROBINHOOD", "status": "OPEN"}


def _pool(position, lots, dup=None):
    conn = MagicMock()
    conn.executed = []

    async def fetchrow(sql, *args):
        if "FROM position_lots WHERE broker_ref" in sql:
            return dup
        return position

    async def fetch(sql, *args):
        return [dict(l) for l in lots]

    async def fetchval(sql, *args):
        conn.executed.append((" ".join(sql.split()), args))
        return 99

    async def execute(sql, *args):
        conn.executed.append((" ".join(sql.split()), args))

    conn.fetchrow, conn.fetch, conn.fetchval, conn.execute = fetchrow, fetch, fetchval, execute
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    return pool, conn


def _reduce(monkeypatch, lots, position=OPEN_EQUITY, dup=None, **body):
    from api import unified_positions as U
    pool, conn = _pool(position, lots, dup)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    req = U.ReducePositionRequest(**{"qty": 5, "price": 8.0, **body})
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(U.reduce_position("p1", req)), conn
    finally:
        loop.close()


def test_a_reduction_without_confirm_writes_nothing(monkeypatch):
    out, conn = _reduce(monkeypatch, [_lot(1, 10, 5.0)])
    assert out["status"] == "preview" and out["written"] is False
    assert out["realized"] == pytest.approx(15.0)
    assert not [e for e in conn.executed if "INSERT INTO position_lots" in e[0]]
    assert "confirm=true" in out["note"]


def test_a_confirmed_reduction_writes_a_negative_lot_and_its_allocations(monkeypatch):
    out, conn = _reduce(monkeypatch, [_lot(1, 10, 5.0)], confirm=True)
    ins = [e for e in conn.executed if "INSERT INTO position_lots" in e[0]]
    assert len(ins) == 1 and ins[0][1][2] == -5, "the disposal is its own negative lot"
    closures = [e for e in conn.executed if "INSERT INTO position_lot_closures" in e[0]]
    assert len(closures) == 1 and closures[0][1][3] == 5
    assert out["status"] == "reduced" and out["written"] is True


def test_no_lot_is_ever_updated_by_the_reduce_path(monkeypatch):
    """A lot is a record that something happened; the ledger stops answering if it is edited."""
    _, conn = _reduce(monkeypatch, [_lot(1, 10, 5.0)], confirm=True)
    assert not [e for e in conn.executed if e[0].startswith("UPDATE position_lots")]


def test_a_reduction_beyond_the_lots_is_refused(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _reduce(monkeypatch, [_lot(1, 2, 5.0)], qty=5)
    assert e.value.status_code == 400
    assert "no record of buying" in e.value.detail


def test_a_duplicate_broker_reference_is_refused_on_the_reduce_path(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _reduce(monkeypatch, [_lot(1, 10, 5.0)], confirm=True, broker_ref="26246-P2JS0Y",
                dup={"id": 7, "position_id": "p0"})
    assert e.value.status_code == 409


def test_the_add_path_refuses_a_duplicate_reference_by_naming_the_lot_it_is():
    from api import unified_positions as U
    src = inspect.getsource(U.add_position_lot)
    assert "status_code=409" in src and "already lot" in src


def test_a_reduction_of_zero_or_less_is_refused(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _reduce(monkeypatch, [_lot(1, 10, 5.0)], qty=0)
    assert e.value.status_code == 400


def test_the_plan_is_recomputed_inside_the_transaction(monkeypatch):
    """A confirmation is not a licence to write arithmetic from a minute ago."""
    from api import unified_positions as U
    src = inspect.getsource(U.reduce_position)
    assert "FOR UPDATE" in src
    assert src.count("fifo_plan(") == 2
