"""R-IV.844(d) — `trade_outcome` is served as STORED, and a row that is not open is never "OPEN".

THE DEFECT (TA-138 / POSITIONS). `hub_get_positions` RECOMPUTED the outcome:

    outcome = "OPEN"
    if status == "CLOSED":
        ... derive WIN/LOSS/BREAKEVEN from realized_pnl or unrealized_pnl ...

Two faults in one expression. It invented a verdict from the money instead of reading the column
the book keeps, and its DEFAULT asserted the most consequential thing available — that the
position is still open — about every status it had not been taught about.

MEASURED ON THE LIVE BOOK BEFORE THE FIX:

    124 non-open rows served as "OPEN"   -- 84 DUPLICATE_OF, 40 EXPIRED
    103 rows served something other than what they stored, 37 of them EXPIRED rows storing LOSS
    IWM 956 (EXPIRED, stored UNKNOWN) served as "OPEN" -- which is how POSITIONS found it

The derivation was safe to delete because all 534 CLOSED rows carry a stored outcome and ZERO of
them disagreed with the derived one, so nothing that was right became wrong. That check is the
reason this is a correction rather than a swap of one guess for another.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from hub_mcp.tools.positions import DESCRIPTION, _build_position  # noqa: E402


def _row(**over):
    row = {"position_id": "P1", "ticker": "IWM", "account": "ROBINHOOD", "status": "OPEN"}
    row.update(over)
    return row


class TestTheStoredValueIsServed:
    @pytest.mark.parametrize("status", ["CLOSED", "EXPIRED", "DUPLICATE_OF", "OPEN"])
    @pytest.mark.parametrize("stored", ["WIN", "LOSS", "BREAKEVEN", "UNKNOWN"])
    def test_whatever_the_row_stores_is_what_is_served(self, status, stored):
        out = _build_position(_row(status=status, trade_outcome=stored))
        assert out["trade_outcome"] == stored

    def test_the_money_no_longer_invents_a_verdict(self):
        """A CLOSED row storing LOSS is served LOSS even when the P&L columns say otherwise —
        the book's recorded result wins over an arithmetic guess about it."""
        out = _build_position(_row(status="CLOSED", trade_outcome="LOSS",
                                   realized_pnl=250.0, unrealized_pnl=250.0))
        assert out["trade_outcome"] == "LOSS"

    def test_IWM_956s_exact_shape(self):
        """The row POSITIONS found: EXPIRED, stored UNKNOWN, previously served "OPEN"."""
        out = _build_position(_row(position_id="POS_IWM_20261006_R652", status="EXPIRED",
                                   trade_outcome="UNKNOWN", exit_price=None))
        assert out["trade_outcome"] == "UNKNOWN"


class TestANonOpenRowIsNeverServedOPEN:
    @pytest.mark.parametrize("status", ["CLOSED", "EXPIRED", "DUPLICATE_OF"])
    def test_with_no_stored_outcome_it_is_UNKNOWN_not_OPEN(self, status):
        """21 DUPLICATE_OF rows are in exactly this state. "OPEN" would be a claim about the
        book that the row itself contradicts."""
        out = _build_position(_row(status=status))
        assert out["trade_outcome"] == "UNKNOWN"
        assert out["trade_outcome"] != "OPEN"

    @pytest.mark.parametrize("status", ["CLOSED", "EXPIRED", "DUPLICATE_OF", "", None, "WEIRD"])
    def test_no_status_except_OPEN_can_produce_OPEN_without_storing_it(self, status):
        """Including a status nobody has taught it about — the default is what broke this, so
        the default is what gets pinned."""
        out = _build_position(_row(status=status))
        if (status or "").upper() == "OPEN":
            pytest.skip("that is the one case that may be OPEN")
        assert out["trade_outcome"] == "UNKNOWN"

    def test_an_OPEN_row_with_nothing_stored_is_still_OPEN(self):
        """POSITIVE CONTROL. All 30 open rows store no outcome, and "OPEN" is correct for them —
        a fix that returned UNKNOWN everywhere would pass every test above and break the book."""
        out = _build_position(_row(status="OPEN"))
        assert out["trade_outcome"] == "OPEN"

    def test_lowercase_open_still_counts_as_open(self):
        out = _build_position(_row(status="open"))
        assert out["trade_outcome"] == "OPEN"


class TestTheDerivationIsGone:
    def test_realized_and_unrealized_no_longer_decide_the_outcome(self):
        import inspect

        from hub_mcp.tools import positions as mod

        src = inspect.getsource(mod._build_position)
        assert 'unrealized = row.get("realized_pnl")' not in src
        assert "elif unrealized > 0:" not in src

    def test_the_stored_column_is_read(self):
        import inspect

        from hub_mcp.tools import positions as mod

        src = inspect.getsource(mod._build_position)
        assert 'stored_outcome = row.get("trade_outcome")' in src


class TestTheDescriptionWarnsAboutBothTraps:
    def test_CLOSED_does_not_mean_everything_that_ended(self):
        assert "status=CLOSED` returns CLOSED rows ONLY" in DESCRIPTION
        assert "EXPIRED and DUPLICATE_OF rows appear only" in DESCRIPTION
        assert "ALL" in DESCRIPTION

    def test_trade_outcome_is_not_an_open_filter(self):
        assert "NOT an open-position filter" in DESCRIPTION
        assert "open_quantity > 0" in DESCRIPTION

    def test_the_standing_rule_names_both_forbidden_fields(self):
        """R-IV.844(d)3: select open rows by open_quantity > 0, never by trade_outcome or
        strategy_tag."""
        assert "never by `trade_outcome`" in DESCRIPTION
        assert "never by `strategy_tag`" in DESCRIPTION
        assert "R-IV.844(d)3" in DESCRIPTION

    def test_it_states_the_measured_cost(self):
        """A warning that names the number is harder to dismiss than one that does not."""
        assert "124 rows" in DESCRIPTION
