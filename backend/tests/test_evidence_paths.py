"""R-IV.463(e)(f)(g) -- corrections carry exit_date and a derived max_loss; legs say where they
came from; a relabelled source re-derives provenance; a position that ended before the book
recorded it is entered from its evidence.

FAIL-FIRST against the pre-2026-09-19 tree: correct-realized could not write exit_date and left
max_loss stale (352, 358); leg entry stamped PRINCIPAL_REPORTED on legs read from a broker
export; a source relabel left provenance behind; and ids 512/513 could be recorded only by
direct SQL, because every create moves cash and every close needs an OPEN row.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from api import unified_positions as U  # noqa: E402
from models.position_lots import IMPORTED, PRINCIPAL_REPORTED, provenance_for_parent  # noqa: E402
from models.position_risk import calculate_position_risk  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


class _Acq:
    def __init__(self, c): self.c = c
    async def __aenter__(self): return self.c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _conn(fetchrow=None, fetch=None, fetchval=None):
    conn = MagicMock()
    conn.calls = []

    async def execute(sql, *args):
        conn.calls.append((" ".join(sql.split()), args))

    conn.execute = execute
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch = AsyncMock(side_effect=fetch or (lambda sql, *a: []))
    conn.fetchval = AsyncMock(side_effect=fetchval or (lambda sql, *a: None))
    conn.transaction = lambda: _Txn()
    return conn


def _pool(monkeypatch, conn):
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))


# --- (e) correct-realized: exit_date, and max_loss derived ------------------------------------
GUSH = {"position_id": "G", "status": "CLOSED", "realized_pnl": 6.29, "exit_price": 39.5,
        "quantity": 15.35049, "entry_price": 39.09, "cost_basis": 600.05, "notes": "",
        "exit_date": None, "max_loss": 586.35, "structure": "stock", "long_strike": None,
        "short_strike": None, "legs": None, "entry_side": None}


def _correct(monkeypatch, row, **body):
    conn = _conn(fetchrow=row)
    _pool(monkeypatch, conn)
    req = U.CorrectRealizedRequest(**{"evidence": "export L149", "reason": "the broker is the "
                                      "record", "ruling": "R-IV.463(e)", **body})
    return _run(U.correct_realized(row["position_id"], req)), conn


def test_a_stale_max_loss_is_brought_into_line_by_a_correction_with_no_figure(monkeypatch):
    expected = round(calculate_position_risk("stock", 39.09, 15.35049)["max_loss"], 2)
    assert expected != 586.35
    out, conn = _correct(monkeypatch, dict(GUSH))
    assert out["max_loss_derived"] == expected
    upd = [c for c in conn.calls if c[0].startswith("UPDATE unified_positions")][0]
    assert "max_loss = $1" in upd[0] and upd[1][0] == expected
    assert any("(derived)" in ch for ch in out["changes"])


def test_nothing_to_correct_is_still_refused(monkeypatch):
    row = dict(GUSH, max_loss=round(calculate_position_risk("stock", 39.09, 15.35049)["max_loss"], 2))
    with pytest.raises(HTTPException) as e:
        _correct(monkeypatch, row)
    assert "no figure" in e.value.detail


def test_exit_date_is_corrected_as_the_principals_day(monkeypatch):
    out, conn = _correct(monkeypatch, dict(GUSH), exit_date="2026-07-17")
    upd = [c for c in conn.calls if c[0].startswith("UPDATE unified_positions")][0]
    written = [a for a in upd[1] if isinstance(a, datetime)][0]
    assert written == datetime(2026, 7, 17, 6, 0, tzinfo=timezone.utc), "00:00 Denver, MDT"


def test_a_future_exit_date_is_refused():
    with pytest.raises(HTTPException) as e:
        U._when_from_evidence("2099-01-01", "exit_date")
    assert "future" in e.value.detail


# --- (e) legs say where they came from --------------------------------------------------------
def test_leg_source_is_the_lots_vocabulary():
    assert U._leg_source("import") == "IMPORT" and U._leg_source(None) == "MANUAL"
    with pytest.raises(HTTPException):
        U._leg_source("EXPORT")


def test_adding_a_leg_from_an_export_stamps_it_imported():
    src = inspect.getsource(U.add_position_leg)
    assert "provenance_for_lot(leg_source, req.price)" in src and '"broker-export"' in src


def _leg_row(prov):
    return {"id": 9, "leg_seq": 1, "option_type": "PUT", "side": "LONG", "strike": 100.0,
            "expiry": None, "qty": 1.0, "price": 0.5, "provenance": prov, "broker_ref": None,
            "ticker": "X"}


def test_a_source_only_edit_relabels_the_leg_and_says_so(monkeypatch):
    conn = _conn(fetchrow=_leg_row(PRINCIPAL_REPORTED))
    _pool(monkeypatch, conn)
    monkeypatch.setattr(U, "_audit_leg", AsyncMock())
    out = _run(U.update_position_leg("P", 1, U.LegPatchRequest(source="IMPORT", reason="export")))
    assert ("UPDATE position_legs SET provenance = $1 WHERE id = $2", (IMPORTED, 9)) in conn.calls
    assert "provenance" in out["changed"]


def test_a_relabel_never_unverifies_a_verified_leg(monkeypatch):
    conn = _conn(fetchrow=_leg_row("BROKER_VERIFIED"))
    _pool(monkeypatch, conn)
    monkeypatch.setattr(U, "_audit_leg", AsyncMock())
    _run(U.update_position_leg("P", 1, U.LegPatchRequest(source="IMPORT")))
    assert not any("SET provenance" in c[0] for c in conn.calls)


# --- (f) a relabelled row source re-derives provenance ----------------------------------------
def test_a_row_relabelled_to_a_broker_source_reads_imported():
    assert provenance_for_parent("BROKER_EXPORT", 0) == IMPORTED
    assert provenance_for_parent("MANUAL", 0) == PRINCIPAL_REPORTED
    src = inspect.getsource(U.update_position)
    assert "provenance = CASE WHEN provenance = ${idx} THEN provenance" in src
    assert "params.append(BROKER_VERIFIED)" in src


# --- (g) a position that ended before the book held it ----------------------------------------
def _evidence(monkeypatch, fetchval=None, **body):
    conn = _conn(fetchval=fetchval or (lambda sql, *a: 77 if "position_lots" in sql and
                                       "INSERT" in sql else None))
    _pool(monkeypatch, conn)
    base = {"ticker": "XLE", "account": "ROBINHOOD", "structure": "long_call", "quantity": 1,
            "entry_price": 0.18, "entry_date": "2026-07-15", "exit_date": "2026-07-17",
            "exit_price": 0.45, "long_strike": 60, "expiry": "2026-07-31",
            "evidence": "export lines 212/219", "reason": "partial close missing from the book",
            "ruling": "R-IV.458(d)"}
    base.update(body)
    return _run(U.create_closed_from_evidence(U.ClosedFromEvidenceRequest(**base))), conn


def test_id_512_rebuilt_through_the_path(monkeypatch):
    out, conn = _evidence(monkeypatch)
    ins = [c for c in conn.calls if c[0].startswith("INSERT INTO unified_positions")][0]
    args = ins[1]
    assert out["realized_pnl"] == 27.0 and "derived gross" in out["realized_basis"]
    assert out["max_loss"] == 18.0 and out["cost_basis"] == 18.0
    assert "CLOSED" in args and "BROKER_EXPORT" in args and IMPORTED in args
    assert out["cash_moved"] is False and out["opening_lot_id"] == 77
    assert any("CREATED FROM EVIDENCE" in str(a) and "export lines 212/219" in str(a)
               for a in args)


def test_id_513_rebuilt_from_its_legs(monkeypatch):
    legs = [U.EntryLeg(option_type="CALL", side="LONG", strike=60, expiry="2026-08-21"),
            U.EntryLeg(option_type="CALL", side="SHORT", strike=65, expiry="2026-08-21")]
    out, conn = _evidence(monkeypatch, structure="call_debit_spread", entry_price=0.29,
                          entry_date="2026-07-07", exit_date="2026-07-08", exit_price=0.58,
                          long_strike=None, expiry=None, legs=legs, trade_id=593)
    assert out["realized_pnl"] == 29.0 and out["max_loss"] == 29.0 and out["legs"] == 2
    assert sum(1 for c in conn.calls if c[0].startswith("INSERT INTO position_legs")) == 2


def test_the_records_realized_figure_is_kept(monkeypatch):
    out, _ = _evidence(monkeypatch, realized_pnl=26.95)
    assert out["realized_pnl"] == 26.95 and out["realized_basis"] == "the record's figure"


@pytest.mark.parametrize("body,phrase", [
    ({"evidence": " "}, "evidence is required"),
    ({"status": "OPEN"}, "has ENDED"),
    ({"source": "MANUAL"}, "import source"),
    ({"exit_price": None}, "R-IV.454(d)"),
    ({"exit_date": "2026-07-01"}, "before entry_date"),
])
def test_what_the_path_refuses(monkeypatch, body, phrase):
    with pytest.raises(HTTPException) as e:
        _evidence(monkeypatch, **body)
    assert phrase in e.value.detail


def test_an_event_already_in_the_book_is_refused(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _evidence(monkeypatch, broker_ref="RH-1",
                  fetchval=lambda sql, *a: "POS_XLE_20260715_R458D1" if "broker_ref" in sql else None)
    assert e.value.status_code == 409 and "already recorded" in e.value.detail


def test_no_cash_moves():
    src = inspect.getsource(U.create_closed_from_evidence)
    assert "_adjust_account_cash" not in src and "cash_flows" not in src
