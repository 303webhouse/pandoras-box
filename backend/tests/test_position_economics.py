"""Gap 1 — a position's money comes from the lots that are still open.

R-IV.526(b) and R-IV.522(a). The acceptance cases SPINE named are here by name and
by their real figures: **WEAT 367** (max_loss at six-contract scope on a
three-contract remainder) and **ABNB 379** (P&L at one contract of two, on a basis
taken from max_loss rather than from the lots).

Convention #30 throughout: every refusal is paired with a case that must succeed.
An economics module that returned None for everything would satisfy every "it does
not substitute" test and serve nothing.
"""

from datetime import datetime, timezone

import pytest

from services import position_economics as pe


def lot(qty, price, day=None, lot_id=1):
    return {
        "id": lot_id, "qty": qty, "price": price,
        "fill_time": datetime(2026, 9, day or 1, tzinfo=timezone.utc),
    }


OPTION = {"asset_type": "OPTION", "position_id": "P", "ticker": "T"}
EQUITY = {"asset_type": "EQUITY", "position_id": "P", "ticker": "T"}


# -- the acceptance cases ----------------------------------------------------

def test_weat_367_max_loss_is_three_contracts_not_six():
    """The row stored $30.00 — six-contract scope on a three-contract remainder —
    while its CLOSED roll sibling carried the correct $15.00. One lot, 3 @ 0.05."""
    e = pe.economics(OPTION, [lot(3, "0.05", 3)], mark="0.025")
    assert e["open_remainder"] == 3.0
    assert e["cost_at_remainder"] == 15.00
    assert e["max_loss"] == 15.00              # was 30.00
    assert e["unit_cost"] == pytest.approx(0.05)
    assert e["unrealized_pnl"] == -7.50


def test_abnb_379_pnl_is_two_contracts_and_the_basis_is_the_lots():
    """Stored P&L reproduced as `(mark - max_loss/100/quantity) x 100 x 1`: a
    one-contract scope AND a basis of 0.2009 that is not the 0.20 actually paid.
    R-IV.522(a): the basis comes from the lots."""
    row = dict(OPTION, max_loss="40.18", quantity=2)      # the figure it must ignore
    e = pe.economics(row, [lot(2, "0.20", 11)], mark="2.84")

    assert e["unit_cost"] == pytest.approx(0.20)          # not 0.2009
    assert e["cost_at_remainder"] == 40.00                # not 40.18
    assert e["unrealized_pnl"] == 528.00                  # (2.84-0.20)*100*2
    assert e["unrealized_pnl"] != 263.91                  # what one contract gave


def test_gush_cost_is_every_lot_not_the_first_one():
    """Stored max_loss was $694.65 — the first lot's 15 shares, to the cent, on a
    25-share remainder."""
    e = pe.economics(EQUITY, [lot(15, "46.31", 18, 1), lot(10, "43.0264", 21, 2)])
    assert e["open_remainder"] == 25.0
    assert e["cost_at_remainder"] == 1124.91
    assert e["max_loss"] == 1124.91                       # was 694.65


# -- the open remainder ------------------------------------------------------

def test_no_lots_and_no_open_remainder_are_different_answers():
    """Collapsing them is how a never-lotted row came to read as a flat one."""
    assert pe.open_remainder([]) is None
    assert pe.open_remainder([lot(2, "1.00"), lot(-2, "1.50")]) == 0


def test_a_row_with_no_lots_states_a_reason_and_no_figure():
    e = pe.economics(OPTION, [], mark="1.00")
    assert e["max_loss"] is None and e["unrealized_pnl"] is None
    assert e["basis_reason"] == pe.NO_LOTS
    # Positive control: the same row WITH lots produces figures.
    assert pe.economics(OPTION, [lot(2, "1.00")], mark="1.00")["max_loss"] == 200.0


def test_a_closed_out_remainder_produces_no_money_either():
    e = pe.economics(OPTION, [lot(2, "1.00", 1, 1), lot(-2, "1.50", 2, 2)])
    assert e["open_remainder"] == 0.0
    assert e["max_loss"] is None
    assert e["basis_reason"] == pe.NO_OPEN_REMAINDER


def test_without_a_mark_the_cost_still_stands_but_the_pnl_does_not():
    e = pe.economics(OPTION, [lot(2, "1.00")], mark=None)
    assert e["max_loss"] == 200.0                 # cost needs no mark
    assert e["unrealized_pnl"] is None
    assert e["basis_reason"] == pe.NO_MARK


# -- FIFO ---------------------------------------------------------------------

def test_a_disposal_consumes_the_oldest_lot_first():
    """Two lots at different prices, half sold: the cost still open is the NEWER
    lot's, because the older one went. Taking the average would misprice it."""
    lots = [lot(10, "10.00", 1, 1), lot(10, "20.00", 2, 2), lot(-10, "15.00", 3, 3)]
    assert pe.open_remainder(lots) == 10
    assert pe.surviving_cost(lots) == 200            # the 20.00 lot, not the 10.00
    e = pe.economics(EQUITY, lots)
    assert e["cost_at_remainder"] == 200.00
    assert e["unit_cost"] == pytest.approx(20.0)


def test_a_partial_disposal_eats_into_one_lot():
    lots = [lot(10, "10.00", 1, 1), lot(-4, "12.00", 2, 2)]
    assert pe.surviving_cost(lots) == 60             # 6 shares still at 10.00


def test_selling_more_than_was_ever_bought_states_no_cost():
    lots = [lot(2, "1.00", 1, 1), lot(-5, "1.50", 2, 2)]
    assert pe.surviving_cost(lots) is None
    # Positive control: a sane pair does state one.
    assert pe.surviving_cost([lot(5, "1.00", 1, 1), lot(-2, "1.50", 2, 2)]) == 3


def test_lots_are_ordered_by_fill_time_not_by_arrival():
    """They come back in whatever order the caller had. FIFO is about the fills."""
    newer = lot(10, "20.00", 2, 2)
    older = lot(10, "10.00", 1, 1)
    sold = lot(-10, "15.00", 3, 3)
    assert pe.surviving_cost([newer, sold, older]) == 200


def test_a_lot_with_no_fill_time_sorts_last_rather_than_first():
    """Silently first would make it the one FIFO consumes, which is a guess."""
    unstamped = {"id": 9, "qty": 10, "price": "99.00", "fill_time": None}
    lots = [lot(10, "10.00", 1, 1), unstamped, lot(-10, "15.00", 3, 3)]
    assert pe.surviving_cost(lots) == 990            # the unstamped lot survived


# -- the multiplier ----------------------------------------------------------

def test_an_option_carries_the_hundred_and_a_share_does_not():
    assert pe.economics(OPTION, [lot(2, "0.50")])["cost_at_remainder"] == 100.00
    assert pe.economics(EQUITY, [lot(2, "0.50")])["cost_at_remainder"] == 1.00


# -- money is Decimal, HALF-UP (convention #27) ------------------------------

def test_money_rounds_half_up_not_to_even():
    from decimal import Decimal

    assert pe.money(Decimal("0.005")) == 0.01        # banker's rounding gives 0.00
    assert pe.money(Decimal("0.015")) == 0.02
    assert pe.money(None) is None


def test_a_third_of_a_cent_does_not_drift_through_the_multiplier():
    e = pe.economics(OPTION, [lot(3, "0.005")])
    assert e["cost_at_remainder"] == 1.50


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "nan"])
def test_a_non_finite_value_is_not_a_number_here_either(bad):
    """The same rule Triton needed: float("nan") succeeds and then passes every
    `if not x` guard downstream."""
    assert pe._d(bad) is None
    assert pe.economics(OPTION, [lot(2, bad)])["cost_at_remainder"] is None
    # Positive control.
    assert pe._d("1.25") is not None


# -- R-IV.517(e): the close date ---------------------------------------------

def test_the_close_date_is_the_disposal_that_took_it_to_zero():
    lots = [lot(10, "10.00", 1, 1), lot(-4, "11.00", 5, 2), lot(-6, "12.00", 9, 3)]
    d, lot_id, why = pe.close_date_from_lots(lots)
    assert (d.isoformat(), lot_id, why) == ("2026-09-09", 3, None)


def test_a_partial_disposal_does_not_close_the_position():
    lots = [lot(10, "10.00", 1, 1), lot(-4, "11.00", 5, 2)]
    d, _lot_id, why = pe.close_date_from_lots(lots)
    assert d is None
    assert why == "no disposal takes this position to zero"


def test_the_close_date_never_comes_from_created_at():
    """Every one of the 24 disposal lots in this book was created in one backfill on
    2026-09-24, so `created_at` would date two years of closures to one morning."""
    lots = [
        dict(lot(10, "10.00", 1, 1), created_at=datetime(2026, 9, 24, tzinfo=timezone.utc)),
        dict(lot(-10, "11.00", 5, 2), created_at=datetime(2026, 9, 24, tzinfo=timezone.utc)),
    ]
    d, _lot_id, _why = pe.close_date_from_lots(lots)
    assert d.isoformat() == "2026-09-05"
    assert d.isoformat() != "2026-09-24"


def test_a_reopened_position_takes_the_LAST_zero_not_the_first():
    """Sold out, bought back, sold out again. The close is the second zero."""
    lots = [lot(5, "1.00", 1, 1), lot(-5, "1.10", 3, 2),
            lot(5, "1.20", 6, 3), lot(-5, "1.30", 9, 4)]
    d, lot_id, _why = pe.close_date_from_lots(lots)
    assert (d.isoformat(), lot_id) == ("2026-09-09", 4)


def test_no_lots_gives_a_reason_not_a_date():
    assert pe.close_date_from_lots([]) == (None, None, pe.NO_LOTS)


def test_a_disposal_with_no_fill_time_names_itself_rather_than_guessing():
    lots = [lot(5, "1.00", 1, 1),
            {"id": 7, "qty": -5, "price": "1.10", "fill_time": None}]
    d, lot_id, why = pe.close_date_from_lots(lots)
    assert d is None and lot_id == 7
    assert "no fill_time" in why


# -- capital at risk ---------------------------------------------------------

def _row(pid, ticker, at="OPTION", **kw):
    return dict({"position_id": pid, "ticker": ticker, "asset_type": at}, **kw)


def test_capital_at_risk_is_cost_derived_and_sums_no_max_loss():
    """R-IV.207(d) forbids summing max_loss. The stored figures here are deliberately
    wrong in both directions, and neither reaches the total."""
    rows = [_row("A", "WEAT", max_loss="30.00"), _row("B", "GUSH", "EQUITY",
                                                      max_loss="694.65")]
    lots = {"A": [lot(3, "0.05")],
            "B": [lot(15, "46.31", 18, 1), lot(10, "43.0264", 21, 2)]}
    out = pe.capital_at_risk(rows, lots)
    assert out["capital_at_risk_cost_basis"] == 15.00 + 1124.91
    assert out["complete"] is True
    assert "cost at the open remainder" in out["basis"]


def test_a_row_without_lots_is_excluded_counted_and_named():
    rows = [_row("A", "WEAT"), _row("B", "PDBC", "EQUITY", cost_basis="989.50")]
    out = pe.capital_at_risk(rows, {"A": [lot(3, "0.05")]})
    assert out["capital_at_risk_cost_basis"] == 15.00     # 989.50 does NOT stand in
    assert out["positions_included"] == 1
    assert out["positions_excluded"] == 1
    assert out["complete"] is False
    assert out["excluded"][0]["ticker"] == "PDBC"
    assert out["excluded"][0]["reason"] == pe.NO_LOTS


def test_the_two_entry_points_agree():
    """One arithmetic, two doors: from lots, and from rows already carrying their
    derived block. A second sum is how max_loss and the total drifted apart."""
    rows = [_row("A", "WEAT"), _row("B", "PDBC", "EQUITY")]
    lots = {"A": [lot(3, "0.05")]}
    from_lots = pe.capital_at_risk(rows, lots)
    attached = [dict(r, derived=pe.economics(r, lots.get(r["position_id"]) or []))
                for r in rows]
    assert pe.capital_at_risk_from_derived(attached) == from_lots


def test_an_empty_book_publishes_zero_and_calls_itself_complete():
    out = pe.capital_at_risk([], {})
    assert out["capital_at_risk_cost_basis"] == 0.0
    assert out["complete"] is True


# -- R-IV.548(b): a closed row holds no risk, whatever its lots say ----------
#
# Most closures in this book were booked without a disposal lot -- 308 of them -- so
# SUM(lot qty) stays POSITIVE on a position that is over. The arithmetic was right and
# the question was wrong. POSITIONS measured the cost: 301 non-OPEN rows carrying a
# positive remainder, $88,016.87 of risk that does not exist, published to four
# committee seats for sizing.

@pytest.mark.parametrize("status", ["CLOSED", "EXPIRED", "DUPLICATE_OF", "closed"])
def test_a_row_that_is_over_states_no_remainder_and_no_max_loss(status):
    row = dict(OPTION, status=status)
    e = pe.economics(row, [lot(3, "0.05", 3)], mark="0.025")
    assert e["open_remainder"] is None
    assert e["max_loss"] is None
    assert e["unrealized_pnl"] is None
    assert e["cost_at_remainder"] is None
    assert status.upper() in e["basis_reason"]
    assert "realized" in e["basis_reason"]


def test_the_same_row_open_still_states_everything():
    """POSITIVE CONTROL. The status check must not be a blanket refusal -- the same
    lots on an OPEN row produce the full set."""
    e = pe.economics(dict(OPTION, status="OPEN"), [lot(3, "0.05", 3)], mark="0.025")
    assert e["open_remainder"] == 3.0
    assert e["max_loss"] == 15.00
    assert e["unrealized_pnl"] == -7.50


def test_a_row_with_no_status_at_all_is_still_measured():
    """The guard keys on a status that says the row is over, not on the absence of
    one -- a fixture or a partial SELECT without the column must not go dark."""
    e = pe.economics(OPTION, [lot(3, "0.05", 3)], mark="0.025")
    assert e["max_loss"] == 15.00


def _mixed_book():
    """Two open rows and three closed ones, every closed row carrying live lots --
    which is exactly the live shape: closures booked without a disposal."""
    lots = {"O1": [lot(3, "0.05")], "O2": [lot(2, "0.20")],
            "C1": [lot(50, "88.28")], "C2": [lot(30, "73.28")], "C3": [lot(60, "35.99")]}
    rows = [_row("O1", "WEAT", status="OPEN"), _row("O2", "ABNB", status="OPEN"),
            _row("C1", "TLT", "EQUITY", status="CLOSED"),
            _row("C2", "SQQQ", "EQUITY", status="CLOSED"),
            _row("C3", "GUSH", "EQUITY", status="EXPIRED")]
    return rows, lots


def test_capital_at_risk_counts_open_rows_only_whatever_the_filter():
    """THE CONTROL R-IV.548(b) ASKED FOR: status=ALL must publish the same figure as
    status=OPEN. A caller asking for ALL wants to SEE the closed rows, never to add
    them to the book's risk."""
    rows, lots = _mixed_book()
    all_rows = pe.capital_at_risk(rows, lots)
    open_rows = pe.capital_at_risk([r for r in rows if r["status"] == "OPEN"], lots)
    closed_rows = pe.capital_at_risk([r for r in rows if r["status"] != "OPEN"], lots)

    assert all_rows["capital_at_risk_cost_basis"] == open_rows["capital_at_risk_cost_basis"]
    assert all_rows["capital_at_risk_cost_basis"] == 15.00 + 40.00
    assert closed_rows["capital_at_risk_cost_basis"] == 0.0
    # Positive control: the closed rows DO hold lots worth real money, so the figure
    # above is a decision, not an empty fixture.
    assert sum(float(l[0]["qty"]) * float(l[0]["price"])
               for k, l in lots.items() if k.startswith("C")) > 8000


def test_the_closed_rows_are_counted_apart_from_the_ones_missing_lots():
    """An excluded row should have counted and could not. Reporting 400 closures that
    way would bury the handful that actually need lots."""
    rows, lots = _mixed_book()
    out = pe.capital_at_risk(rows, lots)
    assert out["positions_not_open"] == 3
    assert out["positions_excluded"] == 0
    assert out["complete"] is True
    assert out["positions_included"] == 2


def test_a_missing_lot_on_an_open_row_still_shows_up_as_excluded():
    """POSITIVE CONTROL for the split above: the excluded list must still work."""
    rows, lots = _mixed_book()
    lots.pop("O2")
    out = pe.capital_at_risk(rows, lots)
    assert out["positions_excluded"] == 1
    assert out["excluded"][0]["ticker"] == "ABNB"
    assert out["complete"] is False
    assert out["positions_not_open"] == 3
