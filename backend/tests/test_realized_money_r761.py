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

    def test_branch1_dates_on_the_TRADE_DATE_and_branch2_on_the_exit(self):
        """The whole reason closures are the primary source: they carry their own date, and an
        open row's `exit_date` is NULL.

        R-IV.1281(b): this asserted `c.created_at`, which was the right column under R-IV.761(b)
        and became WRONG at R-IV.1270 -- a write timestamp is not a trade date, and dating on it
        read +3,535.22 for a window whose trades sum to -191.99. The assertion follows the ruling
        rather than being relaxed: branch 1 dates on `trade_date` and must NOT fall back to
        `created_at`, because a COALESCE would put an undated closure back in the window by the
        very timestamp the fix removed.
        """
        c, f, _ = self._sql(None)
        assert "c.trade_date" in c
        assert "c.created_at" not in c
        assert "p.exit_date" not in c
        assert "p.exit_date" in f

    def test_branch1_EXCLUDES_the_undated_rather_than_dating_them_some_other_way(self):
        """A closure with no trade date is not placed at all -- it is reported separately."""
        c, _, _ = self._sql(None)
        assert "c.trade_date IS NOT NULL" in c

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
    """Canned rows per QUERY, routed on the SQL — never on the order the calls arrive in.

    R-IV.1281(b). This stub used to queue three lists and `pop(0)` them positionally, with the
    loader's call ORDER as its contract. R-IV.1270 added a fourth read (the undated closures) and
    every test here died on `IndexError: pop from empty list` -- ten failures pointing at an empty
    list rather than at the read that was added, which is the least informative way a fixture can
    break.

    A POSITIONAL FIXTURE ENCODES THE WRONG FACT. What each test means is "the closures query
    returns these rows"; what it said was "the second call returns these rows". The two agree only
    until someone reorders or inserts a read -- and then the fixture hands branch 2's rows to the
    dropped-row query, which in the worst case passes while testing nothing. Routing on the SQL
    says the thing the test means, and an unrecognised query raises instead of silently handing
    back the wrong rows.
    """

    def __init__(self, closures, fallback, dropped, undated=()):
        self.closures = list(closures)
        self.fallback = list(fallback)
        self.dropped = list(dropped)
        self.undated = list(undated)
        self.seen = []

    async def fetch(self, sql, *params):
        if "SUM(c.realized)" in sql:
            self.seen.append("closures")
            return self.closures
        if "c.trade_date IS NULL" in sql:
            self.seen.append("undated")
            return self.undated
        if "p.exit_date IS NOT NULL" in sql:
            self.seen.append("fallback")
            return self.fallback
        if "p.exit_date IS NULL" in sql:
            self.seen.append("dropped")
            return self.dropped
        raise AssertionError("this stub has no route for: %s" % " ".join(sql.split())[:160])


# Every read the loader is expected to make. Named, so a read that STOPS happening fails here --
# which is the half of the old `calls == 3` assertion worth keeping. A read that is ADDED no longer
# breaks the fixture; it fails this list instead, with its own name.
EXPECTED_READS = {"closures", "fallback", "dropped", "undated"}


async def _run(closures, fallback, dropped=(), undated=()):
    from api.abacus import _load_realized_money
    pool = _StubPool(closures, fallback, dropped, undated)
    out = await _load_realized_money(pool, None, date(2026, 10, 8))
    assert set(pool.seen) == EXPECTED_READS, (
        "the loader's reads changed: saw %r, expected %r" % (sorted(set(pool.seen)),
                                                             sorted(EXPECTED_READS)))
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


class TestTheUndatedClosuresAppearInExactlyOnePlace:
    """R-IV.1281(b): the rows the `trade_date IS NOT NULL` filter drops must appear in the
    "date unknown" line AND NOWHERE ELSE.

    Both halves are asserted, because each alone would pass a broken implementation: a bucket that
    is served but also summed into the money would satisfy "it appears", and a row dropped from
    every total without being served would satisfy "it is not in the money". The pair is the
    contract -- excluded from the figures, present on the page.
    """

    UNDATED = [
        {"id": 1942, "position_id": "POS_IWM_20261006_R652", "account": "ROBINHOOD",
         "ticker": "IWM", "status": "EXPIRED", "realized": -13.08},
        {"id": 1943, "position_id": "POS_NVDA_20261008_171815", "account": "ROBINHOOD",
         "ticker": "NVDA", "status": "EXPIRED", "realized": -44.18},
    ]

    @pytest.mark.asyncio
    async def test_they_are_served_with_their_money_and_their_rows(self):
        out = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, undated=self.UNDATED)
        u = out["date_unknown"]
        assert u["count"] == 2
        assert u["total"] == -57.26, "BUILD's figure, to the cent"
        assert u["in_any_total"] is False
        assert [r["ticker"] for r in u["rows"]] == ["IWM", "NVDA"]
        assert u["by_account"]["ROBINHOOD"] == -57.26

    @pytest.mark.asyncio
    async def test_their_money_is_in_NO_total(self):
        """The control is the SAME book without them: every money figure must be identical."""
        with_them = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, undated=self.UNDATED)
        without = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, undated=[])
        assert with_them["combined"] == without["combined"]
        assert with_them["by_account"] == without["by_account"]
        assert with_them["fallback"]["total"] == without["fallback"]["total"]
        # And the empty case says nothing is unplaced, with a NULL total rather than 0.00.
        assert without["date_unknown"]["count"] == 0
        assert without["date_unknown"]["total"] is None

    @pytest.mark.asyncio
    async def test_they_are_not_smuggled_into_the_other_two_disclosure_blocks(self):
        """`fallback` and `excluded_no_date` answer different questions; a row in two blocks at
        once would be counted twice by any reader that sums the disclosures."""
        out = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, undated=self.UNDATED)
        ids = {r["position_id"] for r in out["date_unknown"]["rows"]}
        assert not ids & {r["position_id"] for r in out["fallback"]["rows"]}
        assert not ids & {r["position_id"] for r in out["excluded_no_date"]["rows"]}

    @pytest.mark.asyncio
    async def test_the_dating_block_names_the_trade_date_as_the_basis(self):
        out = await _run(CONTROL_CLOSURES, CONTROL_FALLBACK, undated=self.UNDATED)
        assert out["dating"]["basis"] == "position_lot_closures.trade_date"
        assert "created_at" not in out["dating"]["basis"]
