"""R-IV.451(a)/454(f) — the book reader, built to the six rulings; and the chip, both directions.

FAIL-FIRST against the pre-2026-09-18 tree: no reader over unified_positions existed for the
analytics routes, and the coverage chip measured only what the book held that `trades` lacked.
The acceptance test found the other direction too (70 trades in the figure with no book row), so
the routes are NOT switched yet -- this file tests the reader and the corrected chip.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from analytics import queries as Q  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
T = datetime(2026, 9, 14, tzinfo=timezone.utc)


def _row(**kw):
    base = {"id": 1, "position_id": "P", "trade_id": None, "ticker": "SOXS", "direction": "LONG",
            "structure": "stock", "account": "FIDELITY_ROTH", "status": "CLOSED",
            "entry_date": T, "exit_date": T, "realized_pnl": 32.25, "unrealized_pnl": None,
            "cost_basis": 982.45, "source": "MANUAL", "signal_id": None, "notes": None,
            "trade_outcome": None, "backfill_exempt_reason": None}
    base.update(kw)
    return base


# --- the six rulings, at the projection -------------------------------------------------
def test_a_closed_row_carries_its_realized_and_a_percent_on_its_basis():
    out = Q.book_row_to_trade_shape(_row())
    assert out["pnl_dollars"] == 32.25 and out["result_known"] is True
    assert round(out["pnl_percent"], 3) == round(32.25 / 982.45 * 100, 3)
    assert out["closed_at"] == T and out["source_table"] == "unified_positions"


def test_a_row_that_ended_with_no_result_is_counted_and_never_summed():
    """Ruling (2): a NULL read as 0 is a fabricated flat trade."""
    out = Q.book_row_to_trade_shape(_row(realized_pnl=None, trade_outcome="UNKNOWN"))
    assert out["pnl_dollars"] is None and out["result_known"] is False


def test_percent_return_is_null_on_a_zero_basis_not_infinite():
    """Ruling (6): the source of the impossible percentages on the principal's screen."""
    assert Q.book_row_to_trade_shape(_row(cost_basis=0))["pnl_percent"] is None
    assert Q.book_row_to_trade_shape(_row(cost_basis=None))["pnl_percent"] is None


def test_an_undated_terminal_row_is_flagged_not_dropped():
    """The NULL-predicate rule: it cannot be placed in a window, so it is surfaced."""
    out = Q.book_row_to_trade_shape(_row(exit_date=None))
    assert out["undated"] is True


def test_an_open_row_carries_its_unrealized_not_a_realized():
    out = Q.book_row_to_trade_shape(_row(status="OPEN", realized_pnl=None, unrealized_pnl=-5.5,
                                         exit_date=None))
    assert out["pnl_dollars"] == -5.5 and out["undated"] is False and out["result_known"]


def test_fields_the_book_does_not_hold_are_named_not_invented():
    out = Q.book_row_to_trade_shape(_row())
    for f in Q.BOOK_FIELDS_NOT_IN_BOOK:
        assert out[f] is None


def test_group_e_is_visible_on_the_projection():
    out = Q.book_row_to_trade_shape(_row(realized_pnl=None, backfill_exempt_reason="GROUP E"))
    assert out["backfill_exempt"] is True and out["result_known"] is False


def test_the_reader_excludes_retired_duplicates_and_counts_them():
    """Ruling (3): by vocabulary, and visibly."""
    rows = [_row(id=1, status="CLOSED"), _row(id=2, status="DUPLICATE_OF")]
    with patch.object(Q, "fetch_rows", new=AsyncMock(return_value=rows)):
        out = asyncio.run(Q.get_book_rows(days=30))
    assert [r["id"] for r in out["rows"]] == [1] and out["retired_excluded"] == 1


def test_the_reader_windows_terminal_rows_on_exit_and_keeps_undated_ones():
    """Ruling (1) and the NULL rule, in the SQL the reader issues."""
    captured = {}

    async def fake(sql, params):
        captured["sql"] = " ".join(sql.split())
        return []
    with patch.object(Q, "fetch_rows", new=fake):
        asyncio.run(Q.get_book_rows(days=30))
    sql = captured["sql"]
    assert "UPPER(p.status) <> 'OPEN' AND (p.exit_date IS NULL OR p.exit_date BETWEEN $1 AND $2)" in sql
    assert "UPPER(p.status) = 'OPEN' AND (p.entry_date IS NULL OR p.entry_date BETWEEN $1 AND $2)" in sql


def test_the_account_filter_reads_every_alias():
    """Ruling (4)."""
    captured = {}

    async def fake(sql, params):
        captured["params"] = params
        return []
    with patch.object(Q, "fetch_rows", new=fake):
        asyncio.run(Q.get_book_rows(account="FIDELITY_ROTH", days=30))
    spellings = captured["params"][2]
    assert "FIDELITY_ROTH" in spellings and "FIDELITY" in spellings


# --- the chip, both directions ---------------------------------------------------------------
def test_the_chip_names_what_the_figure_holds_that_the_book_does_not():
    """Found by the acceptance test: the gap runs both ways, and naming one direction reads as
    'the rest is right'."""
    calls = [[{"unlinked": 109, "absent": 77, "absent_realized": -1373.64,
               "unknown_result": 20}],
             [{"n": 70, "pnl": 356.10}]]
    with patch.object(Q, "fetch_rows", new=AsyncMock(side_effect=calls)):
        out = asyncio.run(Q.book_coverage_gap())
    assert out["trades_orphans"] == 70 and out["trades_orphans_pnl"] == 356.10
    assert "77 closes" in out["chip"] and "70 trades" in out["chip"]
    assert out["complete"] is False


def test_the_chip_counts_trades_that_have_a_book_row_but_no_link():
    """After the import, the only unlinked trades left were ones whose day HAS a book row they
    could not be paired with. A 'no book row that day' test went silent about all of them."""
    calls = [[{"unlinked": 0, "absent": 0, "absent_realized": 0, "unknown_result": 0}],
             [{"n": 23, "pnl": 846.73, "no_book_row": 0}]]
    with patch.object(Q, "fetch_rows", new=AsyncMock(side_effect=calls)):
        out = asyncio.run(Q.book_coverage_gap())
    assert out["complete"] is False
    assert "23 trades" in out["chip"] and "not linked to the book" in out["chip"]
    assert "0 with no book row at all" in out["chip"]


def test_the_chip_is_complete_only_when_both_directions_are_empty():
    calls = [[{"unlinked": 0, "absent": 0, "absent_realized": 0, "unknown_result": 0}],
             [{"n": 3, "pnl": 1.0}]]
    with patch.object(Q, "fetch_rows", new=AsyncMock(side_effect=calls)):
        out = asyncio.run(Q.book_coverage_gap())
    assert out["complete"] is False, "orphans alone make the figure partial"


# --- the acceptance instrument ---------------------------------------------------------------
def test_the_acceptance_script_reconciles_by_population_and_fails_on_a_residue():
    src = (ROOT / "scripts" / "analytics_book_reconcile.py").read_text(encoding="utf-8")
    for pop in ("book_only", "trades_only", "retired_in_old", "linked_delta"):
        assert pop in src
    assert "unexplained" in src and "must be 0.00" in src
    assert "return 0 if round(surplus - explained, 2) == 0 else 1" in src


def test_the_routes_are_not_switched_until_the_second_gap_is_ruled():
    """The book reader exists; the routes still read trades, with the chip."""
    api = (ROOT / "backend" / "analytics" / "api.py").read_text(encoding="utf-8")
    assert "get_book_rows(" not in api
