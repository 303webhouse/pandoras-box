"""A credit spread's economics — R-IV.605(f) / R-IV.607(c).

Everything in `position_economics` assumed long premium: you can lose what you paid, and you
gain when the mark rises. A credit spread is the other way round on both counts, and the book
has just taken its first (SOUN 234, `POS_SOUN_20260129_IMP201`).

THE ROW, MEASURED — and note it is CLOSED, so the live economics short-circuits on it and these
tests use its SHAPE with an open remainder:

    structure     put_credit_spread      long_strike 2.5   short_strike 5
    quantity      2                      entry_price 0.4791
    cost_basis    -95.82  (signed negative: the position took cash in)
    max_loss      NULL    (nothing computed one)
    lots          qty +1 @ 0.48, qty +1 @ 0.48  -> surviving_cost +96.00

**The lots and the row disagree about the sign and both are right.** The lots record the size of
the leg held and leave the direction to the structure; the row carries the signed basis. So the
sign is read from the STRUCTURE, never from a number whose convention differs between the two
places it is stored.

R-IV.1181(c)2 CLOSED THE REMAINING GAP: the lots' 0.18 of fees now enter the basis too, so the
derived figure is -95.82 -- the row's stored `cost_basis`, to the cent, as recorded above. The
sign came from the structure already; the magnitude now agrees as well. Every figure in this
file that moved, moved by that 0.18, in the direction a fee always goes: a debit costs more and
a credit nets less.
"""

from datetime import datetime

import pytest

from services.position_economics import (economics, is_credit_structure, money_in,
                                         spread_width)

SOUN = {"position_id": "POS_SOUN_20260129_IMP201", "ticker": "SOUN", "asset_type": "OPTION",
        "status": "OPEN", "structure": "put_credit_spread",
        "long_strike": 2.5, "short_strike": 5, "quantity": 2}

OPEN_LOTS = [
    {"id": 1707, "qty": 1, "price": 0.48, "fees": 0.09,
     "fill_time": datetime(2026, 1, 29), "source": "IMPORT"},
    {"id": 1708, "qty": 1, "price": 0.48, "fees": 0.09,
     "fill_time": datetime(2026, 1, 29), "source": "IMPORT"},
]


def _e(mark=0.30, **over):
    return economics(dict(SOUN, **over), OPEN_LOTS, mark=mark)


# ─────────────────── which structures take cash in

class TestTheVocabulary:

    @pytest.mark.parametrize("structure", [
        "put_credit_spread", "call_credit_spread", "bull_put_spread",
        "bear_call_spread", "short_put", "short_call",
    ])
    def test_credit_structures(self, structure):
        assert is_credit_structure(structure)

    @pytest.mark.parametrize("structure", [
        "put_debit_spread", "call_debit_spread", "long_put", "long_call",
        "stock", "iron_condor", "", None,
    ])
    def test_everything_else_is_not(self, structure):
        assert not is_credit_structure(structure)

    def test_a_composite_is_read_by_its_first_component(self):
        assert is_credit_structure("put_credit_spread+long_put")
        assert not is_credit_structure("put_debit_spread+short_put")


# ─────────────────── the signed basis

class TestTheBasisIsSigned:

    def test_a_credit_position_reports_money_in(self):
        """Without this a reader is told a credit spread cost him 96 when it paid him 96.

        R-IV.1181(c)2: and the figure is the CASH one, -95.82 -- the gross -96.00 plus the
        0.18 of fees, which is what the row itself stores. The sign comes from the structure,
        the fees from the lots.
        """
        e = _e()
        assert e["cost_at_remainder"] == -95.82
        assert e["cost_at_remainder_gross"] == -96.0
        assert e["basis_direction"] == "credit"

    def test_a_debit_position_also_carries_its_fees(self):
        """Was `test_a_debit_position_is_unchanged`, and the rename is the point: R-IV.1181
        says debit rows were overstated by their fees too, so this side moves as well. A
        debit COSTS MORE than its premium -- 96.18, not 96.00."""
        e = _e(structure="put_debit_spread")
        assert e["cost_at_remainder"] == 96.18
        assert e["cost_at_remainder_gross"] == 96.0
        assert e.get("basis_direction") is None

    def test_the_row_and_the_lots_now_AGREE_to_the_cent(self):
        """THIS TEST'S PREMISE IS RESOLVED, which is why it is renamed.

        The row stored -95.82 and the lots derived -96.00: the sign was reconciled by the
        structure, the 0.18 difference was the fees, and nothing reconciled that. Now the fees
        enter the basis and the two are the same number. A derived figure matching an
        independently stored one to the cent is the strongest check available here, so it is
        asserted as an equality rather than as two separate facts.
        """
        assert money_in(-95.82) == -95.82          # as POSITIONS stored the row
        assert _e()["cost_at_remainder"] == -95.82  # as the lots now derive it
        assert _e()["cost_at_remainder"] == money_in(-95.82)


# ─────────────────── max_loss is the width, less the credit

class TestMaxLoss:

    def test_the_width_comes_from_the_strikes(self):
        assert spread_width(SOUN) == 2.5
        assert spread_width(dict(SOUN, short_strike=None)) is None
        assert spread_width(dict(SOUN, long_strike=5, short_strike=5)) is None

    def test_width_times_hundred_times_qty_minus_the_credit(self):
        """The credit kept is the NET credit -- what actually arrived -- so the worst case is
        0.18 wider than when it was taken gross."""
        e = _e()
        assert e["max_loss"] == 2.5 * 100 * 2 - 95.82 == 404.18
        assert "less the 95.82 credit kept" in e["max_loss_basis"]

    def test_it_is_never_the_cost(self):
        """THE DEFECT. `max_loss = cost` is right for long premium. Here the position took cash
        in, so publishing the cost would report 96 of risk on a position that can lose 404 — and
        where the lots happen to carry a negative sign it would report a NEGATIVE max_loss,
        which reads as no risk at all."""
        e = _e()
        assert e["max_loss"] != e["cost_at_remainder"]
        assert e["max_loss"] != abs(e["cost_at_remainder"])
        assert e["max_loss"] > 0

    def test_the_credit_is_taken_as_a_MAGNITUDE(self):
        """Taking the lots' sign literally made the credit 0 and the worst case the full 500 —
        overstating this row's risk by the whole premium."""
        assert _e()["max_loss"] == 404.18

    def test_without_both_strikes_there_is_no_figure_and_a_reason(self):
        """A credit spread of unknown width has unknown risk. The one thing not to do is fall
        back to the cost, which is the number this branch exists to stop."""
        e = _e(short_strike=None)
        assert e["max_loss"] is None
        assert "does not carry both strikes" in e["basis_reason"]
        assert "no max_loss is published" in e["basis_reason"]

    def test_a_credit_wider_than_the_spread_cannot_lose(self):
        """Clamped at zero rather than reported as a negative worst case."""
        rich = [dict(OPEN_LOTS[0], price=9.0), dict(OPEN_LOTS[1], price=9.0)]
        e = economics(dict(SOUN), rich, mark=1.0)
        assert e["max_loss"] == 0.0

    def test_a_debit_spread_still_reads_its_cost(self):
        """POSITIVE CONTROL: the change is narrow. The cost is now the CASH cost, because the
        money that left the account is the premium plus the fees paid to put it on."""
        e = _e(structure="put_debit_spread")
        assert e["max_loss"] == 96.18
        assert e.get("max_loss_basis") is None


# ─────────────────── the P&L reads by cash direction

class TestCashDirection:

    @pytest.mark.parametrize("mark,expected,note", [
        (0.30, 35.82, "bought back cheaper: the credit kept, less the cost to close"),
        (0.90, -84.18, "costs more to close than was received"),
        # NOT ZERO ANY MORE, and this row is the clearest statement of the whole change:
        # closing at the price you sold at leaves you down the fees. The old figure of 0.00
        # said a round trip was free.
        (0.48, -0.18, "flat at the price it was sold, less the fees paid to get there"),
    ])
    def test_a_credit_spread_gains_when_the_mark_falls(self, mark, expected, note):
        """THE DEFECT. `value - cost` reports -36.00 on a position that is 36.00 up, because it
        assumes you bought the thing."""
        assert _e(mark=mark)["unrealized_pnl"] == expected, note

    @pytest.mark.parametrize("mark,expected", [(0.90, 83.82), (0.30, -36.18),
                                               (0.48, -0.18)])
    def test_a_debit_spread_gains_when_the_mark_rises(self, mark, expected):
        """POSITIVE CONTROL: the two are mirror images, and the debit side is untouched."""
        assert _e(mark=mark, structure="put_debit_spread")["unrealized_pnl"] == expected

    def test_the_direction_is_named_on_the_credit_side(self):
        assert "credit" in _e()["pnl_direction"]
        assert _e(structure="put_debit_spread").get("pnl_direction") is None

    def test_the_two_sides_MIRROR_ONLY_WHEN_THERE_ARE_NO_FEES(self):
        """THE OLD CLAIM WAS A FEE-FREE IDEALISATION, and it is now false on purpose.

        A fee is paid whichever way the trade went, so it hurts BOTH sides. Two positions at
        the same mark therefore differ by TWICE the fees, not by nothing -- 0.36 on this row.
        An exact mirror would require the fee to help one side, which no fee does.

        So the mirror is asserted where it is true (zero fees) and the asymmetry is asserted
        where it is not, with its size named. Simply loosening the tolerance would have hidden
        the fact instead of stating it.
        """
        free = [dict(l, fees=0) for l in OPEN_LOTS]
        for mark in (0.10, 0.30, 0.48, 0.90, 2.00):
            credit = economics(dict(SOUN), free, mark=mark)["unrealized_pnl"]
            debit = economics(dict(SOUN, structure="put_debit_spread"), free,
                              mark=mark)["unrealized_pnl"]
            assert credit == pytest.approx(-debit), mark

        total_fees = sum(l["fees"] for l in OPEN_LOTS)
        for mark in (0.10, 0.30, 0.48, 0.90, 2.00):
            credit = _e(mark=mark)["unrealized_pnl"]
            debit = _e(mark=mark, structure="put_debit_spread")["unrealized_pnl"]
            # each side is worse than its mirror by its own fees, so the pair is out by 2x
            assert credit + debit == pytest.approx(-2 * total_fees, abs=0.005), mark


# ─────────────────── the closed row itself

def test_the_real_soun_row_is_closed_and_still_carries_realized_only():
    """SOUN 234 is CLOSED. A position that is over carries realized P&L only — no remainder, no
    max_loss, no unrealized — and that short-circuit is R-IV.548(b) and must not be weakened by
    the credit branch sitting below it."""
    e = economics(dict(SOUN, status="CLOSED"), OPEN_LOTS, mark=0.30)
    assert e["max_loss"] is None
    assert e.get("unrealized_pnl") is None
    assert e["status"] == "CLOSED"
    assert "carries realized P&L only" in e["basis_reason"]
