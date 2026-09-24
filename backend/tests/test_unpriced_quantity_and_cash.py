"""R-IV.456(a)(b)(c) — unpriced quantity is never priced, a cash correction is labelled, and the
CSV sync's close action is retired.

FAIL-FIRST against the pre-2026-09-18 tree: a PATCH that raised quantity repriced the new units at
the old entry and wrote the invented basis over a correct one (NVDA 415: 32.00 -> 48.00); there was
no way to correct the cash snapshot except a fabricated deposit or raw SQL; and the CSV sync closed
positions with its own date and no result.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

ROOT = pathlib.Path(__file__).resolve().parents[2]


# --- (a) the guard -------------------------------------------------------------------------
def test_a_quantity_increase_with_no_price_marks_the_row_instead_of_repricing():
    from api import unified_positions as U
    src = inspect.getsource(U.update_position)
    assert "req.quantity > old_q and req.cost_basis is None and req.entry_price is None" in src
    assert "basis_incomplete_reason" in src
    assert "UPDATE unified_positions SET cost_basis" not in src, "nothing reprices on an edit"


def test_the_add_and_reduce_paths_write_the_reason_with_the_basis():
    src = (ROOT / "backend" / "api" / "unified_positions.py").read_text(encoding="utf-8")
    flat = " ".join(src.split())
    assert flat.count("basis_incomplete_reason = $4") == 2, "add-lot and reduce both mark it"


def test_the_migration_marks_nvda_415_with_what_is_uncovered():
    sql = (ROOT / "migrations" / "045_basis_incomplete.sql").read_text(encoding="utf-8")
    assert "POS_NVDA_20260911_001150" in sql
    assert "basis 32.00 covers 2 structures" in sql and "marks, not fills" in sql
    assert "-- DOWN" in sql


def test_the_leg_path_never_reprices_the_parent():
    """The parent honours its legs' NULLs: no leg write touches the position's basis."""
    from api import unified_positions as U
    for fn in (U.add_position_leg, U.update_position_leg, U.delete_position_leg):
        assert "cost_basis" not in inspect.getsource(fn), fn.__name__


# --- (b) the labelled cash adjustment ---------------------------------------------------------
class _Acq:
    def __init__(self, c): self.c = c
    async def __aenter__(self): return self.c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


def _adjust(monkeypatch, anchored=False, **body):
    """`anchored` is R-IV.551(b): once an account has an OPENING_BALANCE event its
    stored cash total is read-only history, so an adjustment records itself and moves
    nothing. The default is UNANCHORED, which is what these tests were written
    against and what every account was before the anchors landed."""
    from api import unified_positions as U
    conn = MagicMock()
    conn.calls = []
    conn.fetchrow = AsyncMock(return_value={"account_name": "ROBINHOOD", "cash": 367.39})

    async def execute(sql, *args):
        conn.calls.append((" ".join(sql.split()), args))

    async def fetchval(sql, *args):
        conn.calls.append((" ".join(sql.split()), args))
        if "OPENING_BALANCE" in str(args) or "flow_type = $2" in sql:
            return 1 if anchored else None
        return 1

    conn.execute, conn.fetchval = execute, fetchval
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    req = U.CashAdjustmentRequest(**{"account": "ROBINHOOD", "amount": 16.0,
                                     "reason": "reverse the PATCH recompute's debit",
                                     "ruling": "R-IV.456(b)", **body})
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(U.record_cash_adjustment(req)), conn
    finally:
        loop.close()


def test_an_adjustment_moves_the_snapshot_and_records_itself(monkeypatch):
    out, conn = _adjust(monkeypatch)
    assert out["cash_before"] == 367.39 and out["cash_after"] == 383.39
    assert out["not_a_deposit"] is True
    ins = [c for c in conn.calls if "INSERT INTO cash_adjustments" in c[0]]
    assert len(ins) == 1 and ins[0][1][5] == "R-IV.456(b)"


def test_an_adjustment_on_an_anchored_account_records_itself_and_moves_nothing(monkeypatch):
    """R-IV.551(b). The adjustment is still EVIDENCE either way -- it is recorded
    exactly as before -- but on an anchored account it no longer moves a total that
    nothing reads."""
    out, conn = _adjust(monkeypatch, anchored=True)
    assert out["cash_before"] == 367.39
    assert out["cash_after"] == 367.39                      # unmoved
    ins = [c for c in conn.calls if "INSERT INTO cash_adjustments" in c[0]]
    assert len(ins) == 1                                    # still recorded
    assert not [c for c in conn.calls if "UPDATE account_balances" in c[0]]


def test_an_adjustment_never_writes_a_cash_flow(monkeypatch):
    """cash_flows is read as external money by every return figure.

    WRITES, not mentions: the anchor check added at R-IV.551(b) SELECTs from
    cash_flows to decide whether the stored total is retired, and a read is not a
    write. The original assertion banned the word, which would now fail on a query
    that puts nothing in the table."""
    _, conn = _adjust(monkeypatch)
    writes = [c for c in conn.calls
              if "cash_flows" in c[0]
              and any(w in c[0].upper() for w in ("INSERT", "UPDATE", "DELETE"))]
    assert not writes
    # Positive control: the read the guard makes IS there, so this is not passing
    # because the fixture stopped exercising cash_flows altogether.
    assert [c for c in conn.calls if "cash_flows" in c[0]]


@pytest.mark.parametrize("field", ["reason", "ruling"])
def test_an_adjustment_without_a_reason_or_a_ruling_is_refused(monkeypatch, field):
    with pytest.raises(HTTPException) as e:
        _adjust(monkeypatch, **{field: "  "})
    assert e.value.status_code == 400


def test_an_adjustment_reads_the_account_vocabulary(monkeypatch):
    with pytest.raises(HTTPException):
        _adjust(monkeypatch, account="SCHWAB")


# --- (c) the retired close action ------------------------------------------------------------
def test_the_sync_reports_a_close_and_writes_nothing():
    src = (ROOT / "scripts" / "sync_rh_csv.py").read_text(encoding="utf-8")
    i = src.index('elif a.op == "CLOSE":')
    branch = src[i:src.index("# NO_OP_FLAG", i)]
    assert "_apply_close(cur" not in branch, "the close branch no longer writes"
    assert "CLOSE_NOT_APPLIED" in branch


def test_the_retired_close_raises_if_anything_calls_it():
    src = (ROOT / "scripts" / "sync_rh_csv.py").read_text(encoding="utf-8")
    i = src.index("def _apply_close(")
    assert "raise RuntimeError" in src[i:i + 900]


# --- (d) the import tool ---------------------------------------------------------------------
def test_the_import_counts_every_book_row_as_coverage():
    """Counting only unlinked rows queued duplicates for import."""
    src = (ROOT / "scripts" / "book_from_trades.py").read_text(encoding="utf-8")
    assert "AND trade_id IS NULL" not in src.split("book = [dict(r)")[1].split("]")[0]


def test_the_import_links_only_a_clean_one_to_one():
    src = (ROOT / "scripts" / "book_from_trades.py").read_text(encoding="utf-8")
    flat = " ".join(src.split())
    assert ("len(trades_by_day[k]) == 1 and len(unlinked_by_day[k]) == 1 "
            "and len(book_by_day[k]) == 1") in flat


def test_the_import_never_changes_a_linked_book_figure():
    src = (ROOT / "scripts" / "book_from_trades.py").read_text(encoding="utf-8")
    link = [ln for ln in src.splitlines() if "UPDATE unified_positions SET trade_id" in ln]
    assert len(link) == 1 and "realized" not in link[0] and "cost_basis" not in link[0]
