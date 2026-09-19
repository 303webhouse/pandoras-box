"""R-IV.463(h) -- analytics reads the book.

FAIL-FIRST against the pre-switch tree: /trade-stats, /trades and /export/trades read `trades`,
which one write path fills; the acceptance test (scripts/analytics_book_reconcile.py) reconciled
the switch by population and value on 2026-09-19 (unexplained 0.00) before it shipped.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from analytics import api as A  # noqa: E402
from analytics import queries as Q  # noqa: E402

T = lambda d: datetime(2026, 9, d, 15, 0, tzinfo=timezone.utc)  # noqa: E731


def _row(i, status, pnl, closed=None, opened=None, result_known=True, undated=False, **kw):
    r = {"id": i, "position_id": f"P{i}", "trade_id": None, "ticker": "X", "direction": "LONG",
         "structure": "put_debit_spread", "account": "ROBINHOOD", "status": status,
         "opened_at": opened, "closed_at": closed, "pnl_dollars": pnl, "pnl_percent": None,
         "origin": "manual", "signal_source": None, "linked_signal_bias": None, "notes": "",
         "result_known": result_known, "undated": undated,
         **{f: None for f in Q.BOOK_FIELDS_NOT_IN_BOOK}}
    r.update(kw)
    return r


BOOK = {"rows": [
    _row(1, "closed", 10.0, closed=T(2), opened=T(1)),
    _row(2, "closed", -4.0, closed=T(3), opened=T(1)),
    _row(3, "expired", 99.0, closed=None, opened=T(1), undated=True),      # listed, never summed
    _row(4, "closed", None, closed=T(4), opened=T(1), result_known=False),  # counted, never summed
    _row(5, "open", 5.0, opened=T(5)),
    _row(6, "open", None),                                                  # no date at all
], "retired_excluded": 2}
CHIP = {"source": "unified_positions", "complete": False, "chip": "22 closed trades ..."}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _patched():
    return (patch.object(A, "get_book_rows", new=AsyncMock(return_value=BOOK)),
            patch.object(A, "book_coverage_gap", new=AsyncMock(return_value=CHIP)),
            patch.object(A, "get_latest_benchmarks", new=AsyncMock(return_value={})),
            patch("database.postgres_client.get_postgres_client",
                  new=AsyncMock(side_effect=RuntimeError("no db in tests"))))


def test_trade_stats_sums_only_what_can_be_summed():
    p1, p2, p3, p4 = _patched()
    with p1, p2, p3, p4:
        out = _run(A.trade_stats(days=90))
    assert out["source"] == "unified_positions" and out["book_coverage"] is CHIP
    assert out["pnl"]["realized_dollars"] == 6.0, "the undated 99 and the no-result row stay out"
    assert out["closed"] == 4 and out["closed_summed"] == 2
    assert out["closed_no_result"] == 1 and out["closed_undated"] == 1
    assert out["win_rate"] == 0.5
    assert out["pnl"]["unrealized_dollars"] == 5.0
    assert out["retired_excluded"] == 2
    assert [p["cumulative_pnl"] for p in out["equity_curve"] if "cumulative_pnl" in p] == [10.0, 6.0]


def test_fields_the_book_never_recorded_are_null_not_zero():
    p1, p2, p3, p4 = _patched()
    with p1, p2, p3, p4:
        out = _run(A.trade_stats(days=90))
    assert out["pnl"]["avg_rr_achieved"] is None
    assert out["risk_metrics"]["avg_risk_per_trade_pct"] is None
    assert set(out["fields_not_in_book"]) == set(Q.BOOK_FIELDS_NOT_IN_BOOK)


def test_the_list_orders_rows_with_no_date_without_raising():
    p1, p2, p3, p4 = _patched()
    with p1, p2, p3, p4:
        out = _run(A.list_trades(days=90, limit=200, offset=0, account=None, ticker=None,
                                 direction=None, structure=None, origin=None,
                                 signal_source=None, status=None, search=None, start=None,
                                 end=None))
    assert out["source"] == "unified_positions" and out["total"] == 6
    assert out["rows"][0]["id"] == 6, "the undated row sorts newest, as before"
    assert out["retired_excluded"] == 2


def test_the_export_reads_the_book_and_carries_the_chip_in_headers():
    p1, p2, p3, p4 = _patched()
    with p1, p2, p3, p4:
        resp = _run(A.export_trades(format="csv", account=None, ticker=None, start=None, end=None))
    assert resp.headers["X-Book-Coverage-Complete"] == "false"
    assert resp.headers["X-Book-Coverage-Gap"].startswith("22 closed trades")


def test_the_chip_in_book_mode_names_what_the_book_figure_lacks():
    calls = [[{"unlinked": 90, "absent": 80, "absent_realized": -1496.64,
               "unknown_result": 18, "undated": 9}],
             [{"n": 22, "pnl": 817.73, "no_book_row": 15}]]
    with patch.object(Q, "fetch_rows", new=AsyncMock(side_effect=calls)):
        out = _run(Q.book_coverage_gap(reader="book"))
    assert out["source"] == "unified_positions" and out["complete"] is False
    assert "22 closed trades (+817.73)" in out["chip"]
    assert "18 ended positions have no result" in out["chip"]
    assert "9 ended positions have no exit date" in out["chip"]
    assert "are in the book but not in this figure" not in out["chip"], \
        "what the book holds is now IN the figure"


def test_the_chip_in_book_mode_is_complete_when_no_trade_is_left_out():
    calls = [[{"unlinked": 0, "absent": 0, "absent_realized": 0, "unknown_result": 0,
               "undated": 0}], [{"n": 0, "pnl": 0, "no_book_row": 0}]]
    with patch.object(Q, "fetch_rows", new=AsyncMock(side_effect=calls)):
        out = _run(Q.book_coverage_gap(reader="book"))
    assert out["complete"] is True and out["chip"] is None
