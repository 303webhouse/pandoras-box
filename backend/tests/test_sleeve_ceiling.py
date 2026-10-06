"""The sleeve ceiling sums over the registry, not over named keys — R-IV.644(d) / TA-070.

Trade Analysis ruled the base: **10% of all tracked accounts combined**, which follows the
principal's own rule of Fidelity plus Robinhood. The cash floor is $200.

THE HUB DID NOT COMPUTE IT. It existed twice as prose — `docs/committee-training-parameters.md`
said *"about 10% of FIDELITY_ROTH + ROBINHOOD combined"* — and once as a mock in
`frontend/v2.js`, with a hardcoded `ceiling: 968` and its own note admitting *"sleeve ceiling
and cash floor have no read endpoint (figures here are mock)"*. A number the committee sizes
against, that nothing computes, is a number that silently stops being true.

AND IT HAD. Both written forms name TWO accounts; a third tracked account arrived 2026-10-01,
so a base of named keys already omitted it. It reads the same today only because the 401(a) is
still at 0.00 pending POSITIONS' funding — which is exactly the kind of coincidence that hides
a defect until the day it matters.
"""

import pytest

from models.accounts import CANONICAL_ACCOUNTS, FIDELITY_401A, FIDELITY_ROTH, ROBINHOOD
from services.sleeve_ceiling import (CASH_FLOOR_USD, CEILING_FRACTION, SLEEVE_ACCOUNT,
                                     ceiling_from_balances, headroom)

# the live balances on 2026-10-05, before POSITIONS books the 401(a)'s funding
LIVE = {ROBINHOOD: 835.69, FIDELITY_ROTH: 8842.09, FIDELITY_401A: 0.00}


class TestTheRuledFigures:

    def test_the_fraction_and_the_floor(self):
        assert CEILING_FRACTION == 0.10
        assert CASH_FLOOR_USD == 200.00
        assert SLEEVE_ACCOUNT == ROBINHOOD

    def test_the_live_figure(self):
        """8842.09 + 835.69 + 0.00 = 9677.78, so the ceiling is 967.78 — which is why the
        mock's 968 looked right. It was right by coincidence, off a two-account base."""
        r = ceiling_from_balances(LIVE)
        assert r["base_total"] == 9677.78
        assert r["ceiling"] == 967.78
        assert r["cash_floor"] == 200.0
        assert not r["partial"]

    def test_the_rule_names_the_registry_not_two_keys(self):
        r = ceiling_from_balances(LIVE)
        assert r["base_accounts"] == list(CANONICAL_ACCOUNTS)
        assert "all tracked accounts" in r["rule"]


class TestANewAccountCannotBeLeftOutSilently:

    def test_the_base_is_every_tracked_account(self):
        """THE POINT OF THE MODULE. The base is the registry, so adding an account to
        CANONICAL_ACCOUNTS moves the ceiling by construction — no second list to update."""
        r = ceiling_from_balances(LIVE)
        assert set(r["base_balances"]) == set(CANONICAL_ACCOUNTS)

    def test_the_third_account_moves_the_figure_once_it_is_funded(self):
        """It reads the same today only because the 401(a) is at 0.00. Fund it and the
        ceiling must move — a base of named keys would not have."""
        funded = dict(LIVE, **{FIDELITY_401A: 11_075.62})
        r = ceiling_from_balances(funded)
        assert r["base_total"] == 20_753.40
        assert r["ceiling"] == 2_075.34
        assert r["ceiling"] != ceiling_from_balances(LIVE)["ceiling"]

    def test_a_two_account_base_would_now_be_wrong(self):
        """Stated as arithmetic, because this is the defect: the old prose base omits the
        401(a), and once funded that is a ceiling understated by a tenth of its balance."""
        two_account_base = LIVE[ROBINHOOD] + LIVE[FIDELITY_ROTH] + 11_075.62 - 11_075.62
        assert round(two_account_base * CEILING_FRACTION, 2) == 967.78
        funded = dict(LIVE, **{FIDELITY_401A: 11_075.62})
        assert ceiling_from_balances(funded)["ceiling"] == 2_075.34


class TestAnUnknownBalanceIsNotZero:

    @pytest.mark.parametrize("bad", [None, "", "n/a", float("nan")])
    def test_a_missing_figure_makes_the_base_partial_and_publishes_no_ceiling(self, bad):
        """Summing an unknown as zero understates the base, which understates the ceiling,
        which reads as less headroom than the principal has — and he would size down against
        a number nobody checked."""
        r = ceiling_from_balances(dict(LIVE, **{FIDELITY_401A: bad}))
        assert r["partial"] is True
        assert r["ceiling"] is None
        assert FIDELITY_401A in r["partial_reason"]
        assert "not zero" in r["partial_reason"]

    def test_an_absent_account_is_partial_too(self):
        """A key the query did not return is as unknown as a null."""
        r = ceiling_from_balances({ROBINHOOD: 835.69, FIDELITY_ROTH: 8842.09})
        assert r["partial"] is True and r["ceiling"] is None

    def test_a_genuine_zero_is_NOT_partial(self):
        """POSITIVE CONTROL for the whole partial branch: 0.00 is a real reading — the
        401(a) is registered and empty — and must not be confused with absence."""
        r = ceiling_from_balances(LIVE)
        assert r["base_balances"][FIDELITY_401A] == 0.0
        assert r["partial"] is False and r["ceiling"] == 967.78


class TestTheRetiredLabelsCannotEnterTheBase:

    @pytest.mark.parametrize("label", ["BROKERAGE_LINK_401K", "Fidelity 401A",
                                       "Fidelity 403B", "Interactive Brokers"])
    def test_a_row_under_a_retired_label_contributes_nothing(self, label):
        """Only registry keys contribute, so the parked 401(a)+403(b) snapshot cannot be
        summed into a ceiling however it is spelled (R-IV.638(b)2)."""
        r = ceiling_from_balances(dict(LIVE, **{label: 11_642.35}))
        assert r["base_total"] == 9677.78
        assert r["ceiling"] == 967.78
        assert label not in r["base_balances"]


class TestAPlaceholderZeroIsNotAReading:
    """MEASURED 2026-10-05: FIDELITY_401A's balance is 0.00 -- a placeholder written at
    registration because the column is NOT NULL (R-IV.632(c)) -- while the account holds FOUR
    open positions. The pure function cannot tell that from a true zero, because both are the
    number 0, so the route cross-checks against open positions and passes None instead.

    Summing a placeholder understates the base, which understates the ceiling, which reads as
    less headroom than the principal has. He would size down against a number nobody checked.
    """

    def test_the_route_nulls_a_zero_balance_that_holds_positions(self):
        import ast
        import io as _io
        import os as _os
        import tokenize

        src = _io.open(_os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "api/portfolio.py"), encoding="utf-8-sig").read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    src = src.replace(doc, "")
        lines = src.splitlines(keepends=True)
        try:
            for tok in tokenize.generate_tokens(_io.StringIO(src).readline):
                if tok.type == tokenize.COMMENT:
                    r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
                    lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
        except (tokenize.TokenError, IndentationError):
            pass
        code = "".join(lines)
        assert "holds_positions" in code
        assert "balances[a] = None" in code

    def test_the_effect_a_nulled_placeholder_has(self):
        """Once nulled, the base is partial and NO ceiling is published — which is the point.
        A ceiling off an incomplete base is not this ceiling."""
        r = ceiling_from_balances({ROBINHOOD: 835.69, FIDELITY_ROTH: 8842.09,
                                   FIDELITY_401A: None})
        assert r["partial"] is True
        assert r["ceiling"] is None

    def test_a_zero_balance_with_NO_positions_stays_a_real_zero(self):
        """POSITIVE CONTROL: an account genuinely empty reads 0.00 and the ceiling publishes.
        The cross-check must not turn every zero into an unknown."""
        r = ceiling_from_balances(LIVE)
        assert r["partial"] is False and r["ceiling"] == 967.78


class TestHeadroom:

    def test_headroom_is_the_ceiling_less_what_is_at_risk(self):
        assert headroom(967.78, 412.0) == 555.78

    @pytest.mark.parametrize("c,a", [(None, 412.0), (967.78, None), (None, None)])
    def test_unknown_in_unknown_out(self, c, a):
        """A headroom computed against an unknown ceiling is the shape of answer that gets
        acted on."""
        assert headroom(c, a) is None
