"""A row with no entry_price still gets a mark. R-IV.1381(c).

WHAT WAS WRONG, measured by ABACUS on production. Five open rows had NEVER been priced -- 988
GDXJ, 989 XLU, 990 XLE, 991 GDXJ and 998 IWM. Not "priced and stale": `mark_status` and
`mark_checked_at` were NULL, which reads as "never attempted". Siblings holding the SAME
tickers were priced from the SAME fetch in the same cycle.

The cause was one condition on the write:

    if current_price is not None and unrealized is not None:

With no `entry_price` there is no unrealized, so the branch was skipped entirely and the row
got no price, no status and no timestamp. **A missing entry is a gap in the BOOK. It is not a
reason to refuse to say what a position is worth** -- and because an unpriced row holds the
account balance at a floor, this one gate is what put the >= markers on the balances and
"UNAVAILABLE" on Day P&L.

THE MULTIPLIER IS THE TRAP, and R-IV.1381(c)3 names it. `_compute_unrealized_pnl` takes a
PER-UNIT price and applies x100 itself for options, so the divisor differs by kind. Measured
against the already-priced rows on production, 2026-10-23:

    EQUITY   cost_basis / quantity           reproduces entry_price EXACTLY on all 8 priced
                                             equity rows
    OPTION   cost_basis / (quantity * 100)   reproduces it on the priced option rows

Dividing an option by `quantity` alone hands the function a figure 100x too large, which it
then multiplies by 100 again. 998 IWM is the only option among the five.

THE DERIVED VALUE IS NEVER WRITTEN BACK into `entry_price`: book fields belong to POSITIONS, and
a derived number stored in a book column cannot be told from one Nick entered.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from ._srcscan import read_source                                   # noqa: E402

SRC = read_source(str(_BACKEND / "api" / "unified_positions.py"))


def derive(cost_basis, quantity, is_equity):
    """The rule as the job implements it, for arithmetic the tests can check directly."""
    return cost_basis / (quantity if is_equity else quantity * 100.0)


# ── the arithmetic, against production's own priced rows ────────────────────

@pytest.mark.parametrize("cb,qty,entry", [
    (199.85, 10, 19.985),        # PDBC
    (549.08, 5, 109.816),        # GDXJ ...401A
    (549.23, 5, 109.846),        # GDXJ ...ROTH  <- 1007, the sibling of 988
    (550.63, 5, 110.126),        # SHV
    (1139.58, 3, 379.86),        # VTI
    (130.10, 2, 65.05),          # XLE
    (204.83, 5, 40.966),         # XLU
])
def test_EQUITY_cost_basis_over_quantity_reproduces_the_stored_entry(cb, qty, entry):
    """The rule is not asserted, it is CHECKED against rows that already carry an entry. If
    cost_basis meant something else, these would not land on the stored number."""
    assert round(derive(cb, qty, True), 3) == round(entry, 3)


@pytest.mark.parametrize("cb,qty,entry", [
    (20.08, 2, 0.1004),          # IBIT
    (38.18, 2, 0.1909),          # BX
    (48.18, 2, 0.2409),          # TSLA
])
def test_OPTION_needs_the_HUNDRED_or_it_is_a_hundred_times_out(cb, qty, entry):
    assert round(derive(cb, qty, False), 4) == round(entry, 4)
    # and the equity form on an option is exactly 100x wrong -- the trap (c)3 names
    assert round(derive(cb, qty, True) / derive(cb, qty, False)) == 100


def test_GDXJ_988_derives_from_its_OWN_basis_not_its_siblings():
    """988 and 1007 are different buys on different days. The derivation must use 988's own
    cost_basis, not copy a sibling's entry -- which would silently invent a price."""
    eight_eight = derive(532.00, 5, True)        # 988 / 991, bought 10-15
    sibling = derive(549.23, 5, True)            # 1007, bought 10-16
    assert round(eight_eight, 2) == 106.40
    assert round(sibling, 3) == 109.846
    assert eight_eight != sibling


def test_IWM_998_is_the_option_case():
    """cost_basis 204.25 over 2 contracts. Per unit that is 1.0212, not 102.125."""
    assert round(derive(204.25, 2, False), 4) == 1.0212
    assert round(derive(204.25, 2, True), 3) == 102.125        # what the equity rule would give


# ── the code itself ─────────────────────────────────────────────────────────

def test_the_write_is_NO_LONGER_gated_on_the_P_AND_L():
    """(c)1. The mark is written whether or not an entry exists."""
    assert "if current_price is not None and unrealized is not None:" not in SRC
    assert "THE MARK IS WRITTEN WHETHER OR NOT THERE IS AN ENTRY" in SRC


def test_the_entry_guard_is_an_EXPLICIT_NONE_CHECK():
    """(c)2. `if row["entry_price"]` treats a real 0.00 as absent, and 0.00 is legitimate."""
    assert 'float(row["entry_price"]) if row["entry_price"] else None' not in SRC
    assert '_ep_raw is not None' in SRC


def test_a_ZERO_entry_is_kept_not_treated_as_missing():
    """The falsy bug, as arithmetic: 0.0 is not None."""
    for raw in (0, 0.0, "0.00"):
        assert (float(raw) if raw is not None else None) == 0.0


def test_the_derived_entry_is_NEVER_written_into_entry_price():
    """Book fields belong to POSITIONS. A derived number in a book column cannot be told from
    one Nick entered."""
    i = SRC.index("entry_for_pnl = entry_price")
    block = SRC[i:i + 4000]
    assert "SET entry_price" not in block
    assert "entry_price = $" not in block
    assert "NEVER WRITTEN BACK" in SRC


def test_the_P_AND_L_uses_the_DERIVED_entry_and_the_mark_does_not():
    """Every _compute_unrealized_pnl call in the job takes `entry_for_pnl`; nothing else does."""
    import re
    # SCOPED TO run_mark_to_market. The first version scanned the whole file and caught the
    # PATCH recompute's calls, which legitimately pass the STORED entry -- R-IV.1381(c) is
    # about the mark job only, and a file-wide scan made a true statement about the wrong code.
    i = SRC.index("async def run_mark_to_market(")
    j = SRC.index("async def ", i + 10)
    job = SRC[i:j]
    calls = re.findall(r"_compute_unrealized_pnl\(\s*([A-Za-z_]+)", job)
    assert calls, "expected the job's P&L calls"
    assert all(c == "entry_for_pnl" for c in calls), calls


def test_an_UNUSABLE_basis_is_named_rather_than_guessed():
    """No cost_basis and no entry means no P&L -- and the row still gets its mark."""
    assert "no entry and no usable cost_basis" in SRC


def test_the_multiplier_rule_is_written_down_with_its_measurement():
    """The next reader must be able to see WHY the divisor differs, or they will 'simplify' it
    back to cost_basis / quantity."""
    assert "THE MULTIPLIER IS THE TRAP" in SRC
    assert "reproduces entry_price EXACTLY" in SRC
