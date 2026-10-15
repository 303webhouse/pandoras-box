"""The 20% tactical reminder — R-IV.1033(e). Market value, reminder-level, never blocks.

Every assertion here is paired with a control, because each clause of the ruling has an
opposite failure: a cap that never fires and a cap that fires on everything are both useless,
and so are a percentage of an unknown total and a figure that silently omits an unvalued row.
"""
from __future__ import annotations

import ast
import inspect
from decimal import Decimal

from models import roth_tactical_cap as cap


def _row(**kw):
    base = {"position_id": "P1", "account": "FIDELITY_ROTH", "classification": "TACTICAL",
            "structure": "stock", "open_quantity": 100, "quantity": 100,
            "current_price": 10}
    base.update(kw)
    return base


# -- market value --------------------------------------------------------------------

def test_market_value_uses_open_quantity_never_quantity():
    """Convention #29. `quantity` does not shrink on a partial exit, so a cap computed from it
    would overstate every partially-closed position."""
    mv, why = cap.market_value(_row(quantity=100, open_quantity=25))
    assert why is None
    assert mv == Decimal("250")          # 25 x 10 x 1; off `quantity` it would be 1000


def test_a_null_open_quantity_is_unknown_not_zero():
    mv, why = cap.market_value(_row(open_quantity=None))
    assert mv is None
    assert "not zero" in why, why


def test_contracts_carry_the_100_multiplier_and_shares_do_not():
    assert cap.market_value(_row(structure="put_debit_spread", open_quantity=2,
                                 current_price="0.19"))[0] == Decimal("38.00")
    assert cap.market_value(_row(structure="stock", open_quantity=2,
                                 current_price="0.19"))[0] == Decimal("0.38")


def test_an_unpriceable_row_is_unvalued_not_zero():
    mv, why = cap.market_value(_row(current_price=None))
    assert mv is None
    assert "current_price" in why, why


# -- classification ------------------------------------------------------------------

def test_a_null_classification_counts_as_tactical_PROVISIONALLY():
    """Reading NULL as "not tactical" is how `strategy_tag` under-read this very cap: SOXS
    alone at 8.26% against the truth of SOXS + TSLQ at 19.50%."""
    tactical, provisional = cap.is_tactical(_row(classification=None))
    assert tactical is True
    assert provisional is True


def test_an_explicit_tactical_is_NOT_provisional():
    tactical, provisional = cap.is_tactical(_row(classification="TACTICAL"))
    assert (tactical, provisional) == (True, False)


def test_a_strategic_row_is_not_counted_at_all():
    """THE CONTROL. Without it, a function that returned True for everything would pass both
    tests above and the cap would read 100%."""
    assert cap.is_tactical(_row(classification="STRATEGIC")) == (False, False)


def test_classification_is_read_case_insensitively():
    assert cap.is_tactical(_row(classification="tactical"))[0] is True


# -- the share -----------------------------------------------------------------------

def test_the_percentage_is_market_value_over_account_total():
    rows = [_row(position_id="A", open_quantity=100, current_price=10),      # 1,000
            _row(position_id="B", open_quantity=50, current_price=20)]       # 1,000
    v = cap.tactical_share(rows, "FIDELITY_ROTH", 10000)
    assert v["pct"] == "20.0", v
    assert v["at_or_over"] is True
    assert v["positions_counted"] == 2


def test_just_under_the_threshold_does_NOT_fire():
    """THE PAIR for the test above. 19.9% is not 20%."""
    v = cap.tactical_share([_row(open_quantity=199, current_price=10)], "FIDELITY_ROTH", 10000)
    assert v["pct"] == "19.9"
    assert v["at_or_over"] is False
    assert cap.should_push(v, None) is False


def test_an_unusable_account_value_gives_pct_None_NOT_zero():
    """A percentage of an unknown total is not a number. Zero would read as "nothing
    tactical", which is the fake-healthy answer."""
    for bad in (None, 0, "", "-5"):
        v = cap.tactical_share([_row()], "FIDELITY_ROTH", bad)
        assert v["pct"] is None, bad
        assert v["at_or_over"] is False
        assert "NOT reported as zero" in v["reason"]


def test_an_unvalued_tactical_row_makes_the_figure_UNDERSTATE_and_says_so():
    rows = [_row(position_id="A", open_quantity=100, current_price=10),
            _row(position_id="B", current_price=None)]
    v = cap.tactical_share(rows, "FIDELITY_ROTH", 10000)
    assert v["pct"] == "10.0"
    assert len(v["unvalued"]) == 1
    assert "UNDERSTATES" in v["reason"], v["reason"]


def test_only_the_named_account_is_counted():
    rows = [_row(position_id="A", account="FIDELITY_ROTH", open_quantity=100),
            _row(position_id="B", account="ROBINHOOD", open_quantity=1000)]
    v = cap.tactical_share(rows, "FIDELITY_ROTH", 10000)
    assert v["positions_counted"] == 1
    assert v["pct"] == "10.0"


def test_scope_does_not_depend_on_case():
    """`is_in_scope` once answered differently for FIDELITY_401A and fidelity_401a."""
    assert cap.in_scope({"account": "fidelity_401a"}) is True
    assert cap.in_scope({"account": "FIDELITY_401A"}) is True
    assert cap.in_scope({"account": "ROBINHOOD"}) is False
    v = cap.tactical_share([_row(account="fidelity_roth", open_quantity=100)],
                           "FIDELITY_ROTH", 10000)
    assert v["positions_counted"] == 1


# -- the push ------------------------------------------------------------------------

def test_the_push_carries_PERCENT_ONLY_and_no_money():
    from integrations.ntfy_push import _assert_no_money
    v = cap.tactical_share([_row(open_quantity=250, current_price=10)], "FIDELITY_ROTH", 10000)
    text = cap.push_text(v)
    assert "25.0%" in text
    assert "$" not in text
    # The real guard, not a lookalike: this is the function the sender uses.
    _assert_no_money(text)


def test_a_provisional_count_SAYS_provisional():
    v = cap.tactical_share([_row(classification=None, open_quantity=250, current_price=10)],
                           "FIDELITY_ROTH", 10000)
    assert v["provisional"] is True
    assert "provisional" in cap.push_text(v)
    # And the control: an explicitly classified book does not claim provisionality.
    v2 = cap.tactical_share([_row(classification="TACTICAL", open_quantity=250,
                                  current_price=10)], "FIDELITY_ROTH", 10000)
    assert v2["provisional"] is False
    assert "provisional" not in cap.push_text(v2)


def test_it_pushes_once_then_only_when_the_FIGURE_MOVES():
    """"Once" cannot mean "once ever": 20% -> 31% is news. Quiet while it sits still."""
    v = cap.tactical_share([_row(open_quantity=250, current_price=10)], "FIDELITY_ROTH", 10000)
    assert cap.should_push(v, None) is True          # first crossing
    assert cap.should_push(v, "25.0") is False       # unchanged -> quiet
    assert cap.should_push(v, "22.0") is True        # moved -> speak


def test_nothing_in_this_module_can_block_a_write():
    """Reminder-level, per the principal's ruling. Asserted against the PARSED source: a
    comment promising not to block would satisfy a substring search."""
    src = inspect.getsource(cap)
    tree = ast.parse(src)
    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
    assert not raises, "this module raises, so it can block a write: %d site(s)" % len(raises)
    assert "HTTPException" not in src
