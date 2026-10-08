"""A debit structure cannot lose less than nothing — R-IV.761(c).

THE DEFECT. `economics()`'s long-premium branch sets `max_loss = cost_total`, which assumes you
paid something to open. Row 978 is a `put_debit_spread` whose basis is **-8.86**: penny-inverted
fills opened a debit structure for a net CREDIT, so `cost_total` came out negative and the row
published a max_loss of **-8.86**. A negative worst case reads as better than flat, and it sorts
above every real risk in the book.

The same figure feeds `capital_at_risk_from_derived`, where a negative contribution makes the
WHOLE BOOK look less exposed than it is -- one row quietly reducing the total.

WHAT THE FLOOR MUST NOT TOUCH. A credit spread's basis is negative BY DESIGN: it took cash in,
and `basis_direction == "credit"` records that. Flooring every negative would change the shape
this module deliberately signs, so the floor is keyed on the DEBIT case alone. SOUN 234 is the
control for that.
"""
from decimal import Decimal

import pytest

from services.position_economics import (capital_at_risk_from_derived, economics,
                                         is_credit_structure)

LOTS_ONE = [{"qty": 1, "price": 0.0, "acquired_at": "2026-10-01"}]


def _row(structure, cost_per_unit, **kw):
    """A one-contract option row whose lots carry `cost_per_unit`, signed."""
    r = {"asset_type": "OPTION", "status": "OPEN", "structure": structure,
         "position_id": "POS_TEST", "ticker": "TST"}
    r.update(kw)
    lots = [{"qty": 1, "price": cost_per_unit, "acquired_at": "2026-10-01"}]
    return r, lots


class TestTheDebitFloor:
    def test_row_978s_shape_publishes_0_and_not_minus_8_86(self):
        """THE CONTROL. basis -8.86 on a put_debit_spread -> max_loss 0.00."""
        row, lots = _row("put_debit_spread", Decimal("-0.0886"))
        out = economics(row, lots)
        assert out["max_loss"] == 0.0
        assert out["max_loss"] != -8.86
        assert out["max_loss_basis"] == "opened for a net credit; cannot lose below zero"

    def test_the_reason_is_published_not_just_the_number(self):
        """A floored figure that does not say it was floored is a number nobody can audit."""
        row, lots = _row("put_debit_spread", Decimal("-0.0886"))
        out = economics(row, lots)
        assert "net credit" in (out.get("max_loss_basis") or "")

    def test_an_ordinary_debit_is_untouched(self):
        """POSITIVE CONTROL (#30): the floor must not alter the normal case."""
        row, lots = _row("call_debit_spread", Decimal("1.50"))
        out = economics(row, lots)
        assert out["max_loss"] == 150.0

    def test_long_premium_is_untouched(self):
        row, lots = _row("long_call", Decimal("2.25"))
        out = economics(row, lots)
        assert out["max_loss"] == 225.0

    @pytest.mark.parametrize("unit,expected", [
        (Decimal("-0.0886"), 0.0), (Decimal("-0.01"), 0.0), (Decimal("-5.00"), 0.0),
        (Decimal("0.00"), 0.0), (Decimal("0.01"), 1.0),
    ])
    def test_the_floor_is_at_zero_from_either_side(self, unit, expected):
        row, lots = _row("put_debit_spread", unit)
        assert economics(row, lots)["max_loss"] == expected

    def test_a_floored_row_is_never_reported_as_a_credit_structure(self):
        """It is a DEBIT structure that happened to open for a credit. Calling it a credit
        structure would route it into the width-minus-credit branch, which needs strikes it may
        not have, and would publish a different claim about what it is."""
        assert is_credit_structure("put_debit_spread") is False


class TestTheCreditShapeIsUnchanged:
    """SOUN 234's REAL shape, read from the row: `put_credit_spread`, long 2.5 / short 5, qty 2,
    cost_basis -95.82. Its negative basis is the design, not an anomaly.

    My first version of this test invented the structure name `short_put_spread`, which is not in
    `CREDIT_COMPONENTS` -- so `is_credit_structure` said False, the row fell down the DEBIT branch,
    and the test failed against code that was right. The structure vocabulary is the module's, not
    mine to guess at.
    """

    def test_a_credit_spread_keeps_its_signed_negative_basis(self):
        row, lots = _row("put_credit_spread", Decimal("0.48"),
                         long_strike=2.5, short_strike=5.0)
        out = economics(row, lots)
        assert out["basis_direction"] == "credit"
        assert out["cost_at_remainder"] == -48.0, "the credit must stay signed"

    def test_a_credit_spreads_max_loss_is_width_minus_credit_not_zero(self):
        """The floor must not reach this branch: a credit spread's worst case is real and
        positive, and flooring it would be the opposite error."""
        row, lots = _row("put_credit_spread", Decimal("0.48"),
                         long_strike=2.5, short_strike=5.0)
        out = economics(row, lots)
        # width |5 - 2.5| = 2.5, x100 x1 remaining = 250, less the 48 credit kept
        assert out["max_loss"] == 202.0
        assert out["max_loss_basis"] != "opened for a net credit; cannot lose below zero"
        assert "credit kept" in out["max_loss_basis"]

    def test_a_credit_larger_than_the_width_already_floors_at_zero(self):
        """Pre-existing and correct (`_credit_max_loss`), and the new floor must not disturb it:
        two different branches, each flooring for its own reason."""
        row, lots = _row("put_credit_spread", Decimal("4.00"),
                         long_strike=2.5, short_strike=5.0)
        out = economics(row, lots)
        assert out["max_loss"] == 0.0
        assert "credit kept" in out["max_loss_basis"], "the credit branch's own reason, not the floor's"


class TestRow978sRealShape:
    """978 as the row carries it: `put_debit_spread`, long 44 / short 41, qty 14."""

    def test_a_put_debit_spread_with_strikes_still_floors_at_zero(self):
        """It has both strikes, so a reader might expect the width branch -- but a DEBIT spread is
        not a credit structure, so the width is never consulted and the floor is what applies."""
        row, lots = _row("put_debit_spread", Decimal("-0.0886"),
                         long_strike=44.0, short_strike=41.0)
        out = economics(row, lots)
        assert is_credit_structure("put_debit_spread") is False
        assert out["max_loss"] == 0.0
        assert out["max_loss_basis"] == "opened for a net credit; cannot lose below zero"


class TestCapitalAtRiskFloorsTheSameCase:
    R978 = {"position_id": "POS_978", "ticker": "TST", "status": "OPEN",
            "derived": {"cost_at_remainder": -8.86}}
    SOUN = {"position_id": "POS_SOUN_234", "ticker": "SOUN", "status": "OPEN",
            "derived": {"cost_at_remainder": -96.00, "basis_direction": "credit"}}
    PLAIN = {"position_id": "POS_OK", "ticker": "OK", "status": "OPEN",
             "derived": {"cost_at_remainder": 250.00}}

    def test_978_contributes_zero_not_minus_8_86(self):
        assert capital_at_risk_from_derived([self.R978])["capital_at_risk_cost_basis"] == 0.0

    def test_a_credit_spread_still_contributes_its_negative(self):
        """THE CONTROL: SOUN 234's shape is unchanged."""
        assert capital_at_risk_from_derived([self.SOUN])["capital_at_risk_cost_basis"] == -96.0

    def test_the_book_total_floors_only_the_anomaly(self):
        got = capital_at_risk_from_derived(
            [self.R978, self.SOUN, self.PLAIN])["capital_at_risk_cost_basis"]
        assert got == 154.0, "250 + (-96) + 0"

    def test_WITHOUT_the_floor_978_would_reduce_the_books_risk(self):
        """POSITIVE CONTROL for the floor existing at all: the un-floored arithmetic is
        250 - 96 - 8.86 = 145.14, i.e. one row making the book look 8.86 safer."""
        assert round(250.0 - 96.0 - 8.86, 2) == 145.14
        got = capital_at_risk_from_derived(
            [self.R978, self.SOUN, self.PLAIN])["capital_at_risk_cost_basis"]
        assert got != 145.14

    def test_a_row_with_no_basis_is_still_excluded_not_floored(self):
        """Absent and negative are different facts. A row without a basis must keep landing in
        `excluded` with its reason, never be silently counted as zero risk."""
        out = capital_at_risk_from_derived(
            [{"position_id": "POS_NONE", "ticker": "NB", "status": "OPEN",
              "derived": {"cost_at_remainder": None}}])
        assert out["positions_excluded"] == 1
        assert out["capital_at_risk_cost_basis"] == 0.0
        assert out["complete"] is False
