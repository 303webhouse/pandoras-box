"""Convention #29 (R-IV.511(c)) — quantity is the size OPENED, not the remainder.

    unified_positions.quantity   = the size opened. It does not move on a reduction.
    SUM(position_lots.qty)       = the OPEN REMAINDER — disposal lots are negative.
    SUM(qty) WHERE qty > 0       = the size opened, and THAT equals quantity.

Measured live 2026-09-23: 350 positions carry lots; **350 of 350** have
SUM(qty WHERE qty>0) == quantity, zero mismatches. **14** of them have
SUM(all qty) != quantity — they are partially closed, and they are exactly the
rows the previous comment ("SUM(qty) still equals the position") described
wrongly, by the amount disposed.

These are pure-function tests over the shapes; the live reconciliation is the
query recorded above and in the lane state, not a CI dependency on prod data.
"""

import pytest


def opened(lots):
    """The size opened — acquisitions only."""
    return sum(q for q in lots if q > 0)


def remainder(lots):
    """What is still open — acquisitions net of negative disposal lots."""
    return sum(lots)


def test_an_untouched_position_reads_the_same_both_ways():
    lots = [10.0]
    assert opened(lots) == 10.0
    assert remainder(lots) == 10.0


def test_a_partial_close_moves_the_remainder_and_NOT_the_opened_size():
    """The case the old comment got wrong."""
    lots = [10.0, -4.0]            # bought 10, disposed 4
    assert opened(lots) == 10.0    # == unified_positions.quantity
    assert remainder(lots) == 6.0  # what is still open
    assert opened(lots) != remainder(lots)


def test_a_scale_in_adds_to_both():
    lots = [10.0, 5.0]
    assert opened(lots) == 15.0 and remainder(lots) == 15.0


def test_a_fully_closed_position_still_reports_the_size_it_opened():
    lots = [10.0, -10.0]
    assert opened(lots) == 10.0, "quantity must not collapse to zero on a full close"
    assert remainder(lots) == 0.0


@pytest.mark.parametrize("lots,qty", [
    ([10.0], 10.0),
    ([10.0, -4.0], 10.0),
    ([7.0, 3.0, -5.0], 10.0),
    ([1.0, 1.0, 1.0], 3.0),
])
def test_the_invariant_that_holds_wherever_lots_exist(lots, qty):
    """SUM(positive lot qty) == unified_positions.quantity. 350/350 live."""
    assert opened(lots) == qty


def test_the_remainder_is_never_used_as_the_opened_size():
    """A guard on the confusion itself: for any position with a disposal, the two
    figures differ, so code that reaches for one when it means the other is wrong
    by a measurable amount rather than subtly."""
    lots = [12.0, -3.0]
    assert remainder(lots) == 9.0
    assert abs(opened(lots) - remainder(lots)) == 3.0   # exactly the amount disposed
