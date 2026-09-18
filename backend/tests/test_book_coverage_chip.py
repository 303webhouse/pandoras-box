"""R-IV.451(a) — until analytics reads the book, every analytics figure says what it is missing.

FAIL-FIRST against the pre-2026-09-18 tree: /trade-stats, /trades and /export/trades read the
`trades` table, which only the close endpoint fills, and none of them said so — 77 closes and
-1,373.64 of realized were absent from every figure without a mark on any of them.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from analytics import queries as Q  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _gap(row):
    with patch.object(Q, "fetch_rows", new=AsyncMock(return_value=[row])):
        return asyncio.run(Q.book_coverage_gap())


def test_the_chip_names_what_the_figure_is_missing():
    out = _gap({"unlinked": 109, "absent": 77, "absent_realized": -1373.64,
                "unknown_result": 23})
    assert out["complete"] is False
    assert out["absent_closes"] == 77 and out["absent_realized"] == -1373.64
    assert "77 closes" in out["chip"] and "-1,373.64" in out["chip"]
    assert out["unknown_result_closes"] == 23


def test_a_complete_figure_carries_no_chip():
    out = _gap({"unlinked": 0, "absent": 0, "absent_realized": 0, "unknown_result": 0})
    assert out["complete"] is True and out["chip"] is None


def test_an_unmeasurable_gap_is_never_reported_as_complete():
    """A coverage read that fails must not read like a clean one."""
    with patch.object(Q, "fetch_rows", new=AsyncMock(side_effect=RuntimeError("db down"))):
        out = asyncio.run(Q.book_coverage_gap())
    assert out["complete"] is None
    assert "could not be measured" in out["chip"]


def test_the_figures_are_computed_live_not_quoted():
    """The ruling's 77 / -1,373.64 move every time a close bypasses the endpoint."""
    src = inspect.getsource(Q.book_coverage_gap)
    assert "77" not in src.split('"""')[2] and "1373" not in src.split('"""')[2]
    assert "FROM unified_positions p" in src and "FROM trades t" in src


def test_all_three_populations_are_named_by_method():
    src = inspect.getsource(Q.book_coverage_gap)
    for name in ("unlinked", "absent", "unknown_result"):
        assert name in src


def test_every_route_that_reads_trades_carries_it():
    api = (ROOT / "backend" / "analytics" / "api.py").read_text(encoding="utf-8")
    from analytics import api as A
    for fn in (A.trade_stats, A.list_trades, A.export_trades):
        assert "book_coverage_gap()" in inspect.getsource(fn), fn.__name__
    assert api.count('"book_coverage": await book_coverage_gap()') == 2


def test_the_export_carries_it_in_headers_not_in_the_csv():
    """A chip inside the CSV would break every parser reading it."""
    from analytics import api as A
    src = inspect.getsource(A._csv_response)
    assert "X-Book-Coverage-Complete" in src and "X-Book-Coverage-Gap" in src


def test_which_rollup_reads_what_is_written_down():
    """A fix was credited to the wrong mechanism once; the map is the guard against twice."""
    src = (ROOT / "backend" / "analytics" / "queries.py").read_text(encoding="utf-8")
    assert "WHICH ROLLUP READS WHAT" in src
    assert "/api/analytics/trade-stats    get_trade_rows -> trades" in src
