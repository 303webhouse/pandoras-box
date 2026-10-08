"""The realized total is the money, not the finished trades — R-IV.761(b).

THE DEFECT. The realized aggregate filtered `LOWER(status) IN ('closed','expired')`, so the
money booked by a PARTIAL exit — which sits on a row that is still OPEN — vanished. Measured
2026-10-08: the aggregate read 3,500.25 against a true 3,607.73, short by 107.48 across three
rows (HYG 516 52.00, PDBC 953 8.48, IWM 956 47.00).

WHY NEITHER OBVIOUS FIX WORKS, both measured before writing a line:

  * Relaxing the status filter is not enough. All three OPEN rows have `exit_date IS NULL`, and
    the census bounds its window ON `exit_date` — so there is no date to place them by.
  * Summing the closures ledger alone reads 3,840.31, too high by 232.58, because eight rows
    carry a recorded `realized_pnl` and NO closure rows at all. It would discard eight real
    losses and make the book read better than it is.

So the formula is two-branch, and the controls below are fixtures rather than live reads: the
book is being actively rewritten by POSITIONS' closure backfill (R-IV.760(c)), and a test pinned
to a live total would fail for reasons that have nothing to do with this code.
"""
import ast
import io
import os
from datetime import date

import pytest

from models import position_status as PS

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestTheTwoQuestionsAreDifferent:
    """`counts_as_realized` asks "is the trade finished?"; `realized_money_counts` asks "is this
    money in the account?". A partial exit answers no to the first and yes to the second."""

    def test_an_open_row_is_money_but_not_a_finished_trade(self):
        assert PS.realized_money_counts("OPEN") is True
        assert PS.counts_as_realized("OPEN") is False

    def test_closed_and_expired_are_both(self):
        for s in ("CLOSED", "EXPIRED"):
            assert PS.realized_money_counts(s) is True
            assert PS.counts_as_realized(s) is True

    def test_a_duplicate_is_neither(self):
        """Its money belongs to its keeper; counting both is the double-count the status exists
        to prevent."""
        assert PS.realized_money_counts("DUPLICATE_OF") is False
        assert PS.counts_as_realized("DUPLICATE_OF") is False

    @pytest.mark.parametrize("s", [None, "", "WEIRD", "Partially Closed", "closed_x"])
    def test_an_UNKNOWN_status_is_not_money(self, s):
        """POSITIVE CONTROL for the choice NOT to write `not is_retired(status)`. That form reads
        every unrecognised value as money, which is the same mistake as `!= 'OPEN'`."""
        assert PS.realized_money_counts(s) is False

    def test_case_and_whitespace_do_not_change_the_answer(self):
        assert PS.realized_money_counts(" open ") is True
        assert PS.realized_money_counts("Closed") is True

    def test_the_two_sets_are_not_the_same_object(self):
        """If someone later aliases one to the other, the distinction dies silently."""
        assert PS.MONEY_STATUSES != PS.REALIZED_STATUSES
        assert PS.OPEN in PS.MONEY_STATUSES and PS.OPEN not in PS.REALIZED_STATUSES
        assert PS.DUPLICATE_OF not in PS.MONEY_STATUSES


class TestTheSqlSaysWhatItMeans:
    def _sql(self, first, last=date(2026, 10, 8)):
        from api.abacus import _realized_money_sql
        return _realized_money_sql(first, last)

    def test_branch1_dates_on_the_CLOSURE_and_branch2_on_the_exit(self):
        """The whole reason closures are the primary source: they carry their own date, and an
        open row's `exit_date` is NULL."""
        c, f, _ = self._sql(None)
        assert "c.created_at" in c and "p.exit_date" not in c
        assert "p.exit_date" in f

    def test_both_branches_exclude_DUPLICATE_OF(self):
        c, f, _ = self._sql(None)
        for sql in (c, f):
            assert "'DUPLICATE_OF'" in sql
            assert "<>" in sql

    def test_branch2_uses_NOT_EXISTS_not_a_zero_sum(self):
        """A row whose closures genuinely net to zero IS covered by branch 1. Testing
        `SUM(realized) = 0` instead would count it in both branches."""
        _, f, _ = self._sql(None)
        assert "NOT EXISTS" in f
        assert "SUM" not in f.upper().split("NOT EXISTS")[1][:200]

    def test_an_open_window_binds_one_param_and_a_closed_window_two(self):
        assert len(self._sql(None)[2]) == 1
        assert len(self._sql(date(2026, 1, 1))[2]) == 2

    def test_branch1_joins_on_position_id_the_text_key(self):
        """`position_lot_closures.position_id` is TEXT and matches `unified_positions.position_id`;
        joining on the integer `id` would silently match nothing (it errored when I tried)."""
        c, _, _ = self._sql(None)
        assert "p.position_id = c.position_id" in c or "c.position_id = p.position_id" in c
        assert "p.id" not in c.replace("p.id_", "")


class _StubPool:
    """Returns canned rows for the three fetches, in the order `_load_realized_money` makes them."""

    def __init__(self, closures, fallback, dropped):
        self._queued = [closures, fallback, dropped]
        self.calls = 0

    async def fetch(self, sql, *params):
        self.calls += 1
        return self._queued.pop(0)


async def _run(closures, fallback, dropped=()):
    from api.abacus import _load_realized_money
    pool = _StubPool(list(closures), list(fallback), list(dropped))
    out = await _load_realized_money(pool, None, date(2026, 10, 8))
    assert pool.calls == 3, "all three reads must happen, including the dropped-row read"
    return out


# The book as R-IV.761(b)'s controls describe it: branch 1 per account, branch 2 the eight rows.
CONTROL_CLOSURES = [
    {"account": "FIDELITY_401A", "v": 70.72, "n": 10},
    {"account": "FIDELITY_ROTH", "v": 1036.17, "n": 205},
    {"account": "ROBINHOOD", "v": 2733.42, "n": 345},
]
CONTROL_FALLBACK = [
    {"account": "ROBINHOOD", "position_id": "POS_IBIT_20260312_200350", "ticker": "IBIT",
     "status": "CLOSED", "v": -147.00, "exit_day": date(2026, 3, 12)},
    {"account": "ROBINHOOD", "position_id": "POS_KNX_20260719_T579", "ticker": "KNX",
     "status": "CLOSED", "v": -50.00, "exit_day": date(2026, 7, 19)},
    {"account": "ROBINHOOD", "position_id": "POS_IWM_20260923_134750", "ticker": "IWM",
     "status": "CLOSED", "v": 43.80, "exit_day": date(2026, 9, 23)},
    {"account": "ROBINHOOD", "position_id": "POS_SLV_20260610_173645", "ticker": "SLV",
     "status": "EXPIRED", "v": -28.10, "exit_day": date(2026, 6, 10)},
    {"account": "ROBINHOOD", "position_id": "POS_IWM_20260325_185323", "ticker": "IWM",
     "status": "CLOSED", "v": -25.00, "exit_day": date(2026, 3, 25)},
    {"account": "ROBINHOOD", "position_id": "POS_IWM_20260924_183017", "ticker": "IWM",
     "status": "EXPIRED", "v": -16.18, "exit_day": date(2026, 9, 24)},
    {"account": "ROBINHOOD", "position_id": "POS_QQQ_20260929_172353", "ticker": "QQQ",
     "status": "EXPIRED", "v": -7.10, "exit_day": date(2026, 9, 29)},
    {"account": "ROBINHOOD", "position_id": "POS_IBIT_20260325_185246", "ticker": "IBIT",
     "status": "CLOSED", "v": -3.00, "exit_day": date(2026, 3, 25)},
]


@pytest.mark.asyncio
class TestTheControls:
    """R-IV.761(b)'s four figures, as a fixture. 2,733.42 + (-232.58) = 2,500.84 for ROBINHOOD,
    and 3,840.31 + (-232.58) = 3,607.73 combined."""

    async def test_all_four_account_totals(self):
        out = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK)
        assert out["by_account"]["FIDELITY_401A"] == 70.72
        assert out["by_account"]["FIDELITY_ROTH"] == 1036.17
        assert out["by_account"]["ROBINHOOD"] == 2500.84
        assert out["combined"] == 3607.73

    async def test_the_parts_sum_to_the_whole(self):
        out = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK)
        assert round(sum(out["by_account"].values()), 2) == out["combined"]

    async def test_WITHOUT_the_fallback_branch_the_total_is_wrong_by_232_58(self):
        """POSITIVE CONTROL (#30) for branch 2 existing at all. This IS the prescribed
        closures-only fix, and it over-reports by exactly the eight dropped losses."""
        out = await _run(CONTROL_CLOSURES, [])
        assert out["combined"] == 3840.31
        assert round(3840.31 - 3607.73, 2) == 232.58
        assert out["by_account"]["ROBINHOOD"] == 2733.42

    async def test_WITHOUT_the_closures_branch_only_the_fallback_remains(self):
        out = await _run([], CONTROL_FALLBACK)
        assert out["combined"] == -232.58

    async def test_the_fallback_rows_are_listed_and_counted(self):
        out = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK)
        assert out["fallback"]["count"] == 8
        assert out["fallback"]["total"] == -232.58
        assert {r["ticker"] for r in out["fallback"]["rows"]} == {"IBIT", "KNX", "IWM", "SLV",
                                                                 "QQQ"}
        assert all(r["account"] == "ROBINHOOD" for r in out["fallback"]["rows"])

    async def test_the_fallback_count_reaching_zero_is_the_expected_end_state(self):
        """POSITIONS backfills the eight under R-IV.760(c). The guard must behave when they are
        gone -- an empty fallback is a total, not a crash."""
        out = await _run(CONTROL_CLOSURES, [])
        assert out["fallback"]["count"] == 0
        assert out["fallback"]["total"] == 0.0


@pytest.mark.asyncio
class TestNothingDropsSilently:
    """The row BOTH branches miss: realized recorded, no closures, no exit_date to window on.
    Measured live 2026-10-08: XLF 300, OPEN, ROBINHOOD, -119.23 -- money the account holds and
    the total cannot see. It must be SERVED, not assumed absent."""

    XLF = [{"account": "ROBINHOOD", "position_id": "POS_XLF_20260609_233055", "ticker": "XLF",
            "status": "OPEN", "realized_pnl": -119.23}]

    async def test_the_dropped_row_is_reported_with_its_reason(self):
        out = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, self.XLF)
        ex = out["excluded_no_date"]
        assert ex["count"] == 1
        assert ex["rows"][0]["ticker"] == "XLF"
        assert ex["rows"][0]["realized_pnl"] == -119.23
        assert "no exit_date" in ex["rows"][0]["why"]

    async def test_a_dropped_row_does_NOT_enter_the_total(self):
        """It is excluded on purpose -- there is no date to place it in a window. Reporting it and
        counting it are different acts, and silently counting it would put money in whatever
        window happened to be asked for."""
        with_xlf = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, self.XLF)
        without = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, [])
        assert with_xlf["combined"] == without["combined"] == 3607.73

    async def test_an_empty_dropped_list_still_reports_a_count(self):
        """POSITIVE CONTROL: zero must be served as zero, not omitted. An absent key reads as
        'nothing was checked', which is the silence this whole block exists to remove."""
        out = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, [])
        assert out["excluded_no_date"]["count"] == 0
        assert out["excluded_no_date"]["rows"] == []


class TestTheOtherReadersWereNotWidened:
    """R-IV.761(b): `_load_book_live` and `analytics/api.py` stay on finished trades."""

    def _src(self, rel):
        return io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()

    def test_load_book_live_still_uses_the_census_predicate(self):
        src = self._src(os.path.join("api", "abacus.py"))
        body = src[src.index("async def _load_book_live"):]
        body = body[:body.index("async def ", 10)]
        assert "_census_where(first, last)" in body
        assert "_load_realized_money" not in body, "the live census must not take the money total"

    def test_analytics_still_sums_pnl_dollars_over_finished_trades(self):
        """For an OPEN row `pnl_dollars` is the UNREALIZED mark, so widening this reader would
        add unrealized into realized. Pinned so nobody 'fixes' it by symmetry."""
        src = self._src(os.path.join("analytics", "api.py"))
        assert "position_status.counts_as_realized(r.get(\"status\"))" in src
        assert "realized_money_counts" not in src

    def test_net_profit_no_longer_comes_from_the_census_sum(self):
        src = self._src(os.path.join("api", "abacus.py"))
        assert 'round(sum(acc["pnls"]), 2)' not in src, "net_profit must come from the money total"
        assert "realized[\"by_account\"]" in src

    def test_win_rate_still_comes_from_the_census(self):
        src = self._src(os.path.join("api", "abacus.py"))
        assert 'wins / counted' in src
