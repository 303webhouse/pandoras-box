"""An unquoted option counts at intrinsic, so the ceiling publishes — R-IV.657(d).

*"A limit set slightly low is safe; one that never publishes limits nothing."*

The sleeve ceiling had stopped publishing, and the cause was structural rather than transient:
Robinhood is the options sleeve the ceiling governs, the hub has **no options pricer**, so its
option rows read `mark_status = UNAVAILABLE` and the account's value stayed PARTIAL for good.
A cap nobody can read is a cap nobody honours.

MEASURED 2026-10-06, after the fix: base 24,748.46, **ceiling 2,474.85**, `partial: False`. The
one unquoted row (XLF, 13 contracts, `put_debit_spread+long_put`, strikes 45/40) prices at
**0.00** against an underlying of 53.88 — both puts far out of the money — and is named on the
face with the basis it was read from.

INTRINSIC IS A FLOOR, NEVER A MARK. An option is worth intrinsic *plus* time value, and time
value is exactly what cannot be computed without a pricer. Every figure here understates, in
one direction, on purpose — which is what makes it safe for a cap and wrong for a valuation.
"""

import pytest

from models.option_intrinsic import (OPTION_MULTIPLIER, first_component, intrinsic_value,
                                     leg_intrinsic_per_unit)

# the live row, as the book holds it
XLF = {"structure": "put_debit_spread+long_put", "direction": "SHORT", "quantity": 13,
       "long_strike": 45, "short_strike": 40, "legs": None}


class TestTheLiveRow:

    def test_out_of_the_money_is_zero(self):
        """53.88 against 45/40 puts. "Zero when out of the money" is the ruling's own words,
        and it is the common case for the far-dated protection in this book."""
        value, basis = intrinsic_value(XLF, 53.880001068115234)
        assert value == 0.0
        assert "underlying 53.88" in basis

    def test_in_the_money_is_the_spread_at_its_strikes(self):
        """At 43 the 45 put is 2.00 in the money and the 40 put is worthless, so the spread
        is 2.00 x 100 x 13 = 2,600."""
        assert intrinsic_value(XLF, 43.0)[0] == 2_600.00

    def test_it_cannot_exceed_the_width(self):
        """A vertical is bounded by (long − short). Without the cap, a deep move would
        publish an unbounded number and the ceiling with it."""
        width = (45 - 40) * OPTION_MULTIPLIER * 13
        assert intrinsic_value(XLF, 40.0)[0] == width == 6_500.00
        assert intrinsic_value(XLF, 10.0)[0] == width

    def test_the_composite_is_named_as_understating(self):
        """`put_debit_spread+long_put` carries only two strikes, and the mark reason shows a
        third leg (30P). The extra put cannot be valued from the row, so the figure covers the
        spread and SAYS so — silence would publish a number that looks whole."""
        _, basis = intrinsic_value(XLF, 43.0)
        assert "COMPOSITE" in basis
        assert "understates" in basis

    def test_at_the_strike_is_zero_not_negative(self):
        assert intrinsic_value(XLF, 45.0)[0] == 0.0


class TestAnUnreadUnderlyingIsNotAWorthlessOption:

    @pytest.mark.parametrize("px", [None, 0, -1, float("nan")])
    def test_no_price_means_no_figure(self, px):
        """None, not 0.00. Zero would assert the row is worthless rather than unread, and the
        account must keep its PARTIAL mark instead of publishing off a guess."""
        value, basis = intrinsic_value(XLF, px)
        assert value is None
        assert "cannot be computed" in basis

    def test_nan_does_not_survive(self):
        """`float("nan")` passes every `if not x` guard — `not nan` is False — and one NaN in
        the base makes the whole ceiling NaN, which serialises as a number."""
        assert intrinsic_value(XLF, float("nan"))[0] is None


class TestTheLegMath:

    @pytest.mark.parametrize("otype,side,strike,px,expected", [
        ("put", "long", 45, 43, 2.0),
        ("put", "long", 45, 50, 0.0),
        ("put", "short", 40, 35, -5.0),      # an obligation is negative
        ("call", "long", 100, 110, 10.0),
        ("call", "long", 100, 90, 0.0),
        ("call", "short", 100, 110, -10.0),
    ])
    def test_a_leg_is_signed_by_its_side(self, otype, side, strike, px, expected):
        assert leg_intrinsic_per_unit(otype, side, strike, px) == expected

    def test_a_short_leg_is_not_treated_as_zero(self):
        """THE DIRECTION THAT MATTERS. Counting a short leg as zero values every credit
        spread at its long leg alone — overstating, which is the wrong way for a cap."""
        assert leg_intrinsic_per_unit("put", "short", 40, 35) < 0

    def test_recorded_legs_are_preferred_over_strikes(self):
        """Where the row HAS legs, they are read: they carry each leg's own side, type and
        ratio, which two strike columns cannot express."""
        row = dict(XLF, legs=[
            {"option_type": "put", "side": "long", "strike": 45, "ratio": 1},
            {"option_type": "put", "side": "short", "strike": 40, "ratio": 1},
            {"option_type": "put", "side": "long", "strike": 30, "ratio": 1},
        ])
        value, basis = intrinsic_value(row, 43.0)
        assert "3 recorded leg(s)" in basis
        assert value == 2_600.00          # the 30P is worthless at 43, and is counted

    def test_an_unreadable_leg_is_counted_as_zero_and_said(self):
        row = dict(XLF, legs=[
            {"option_type": "put", "side": "long", "strike": 45, "ratio": 1},
            {"option_type": "put", "side": "short", "strike": None, "ratio": 1},
        ])
        value, basis = intrinsic_value(row, 43.0)
        assert "1 leg(s) unreadable" in basis
        assert value == 2_600.00


class TestWhatCannotBeRead:

    def test_an_unknown_structure_is_zero_with_a_reason(self):
        """Zero UNDERSTATES, which is safe for a cap — and the reason travels with it, so the
        face shows a row that contributed nothing and why."""
        value, basis = intrinsic_value(
            {"structure": "iron_condor", "quantity": 1, "legs": None}, 100.0)
        assert value == 0.0
        assert "neither legs nor usable strikes" in basis
        assert "understates" in basis

    def test_a_composite_is_read_by_its_first_component(self):
        assert first_component("put_debit_spread+long_put") == "put_debit_spread"
        assert first_component("long_call") == "long_call"
        assert first_component(None) is None

    def test_a_zero_quantity_is_zero(self):
        assert intrinsic_value(dict(XLF, quantity=0), 43.0)[0] == 0.0

    def test_a_single_option_uses_its_one_strike(self):
        row = {"structure": "long_put", "quantity": 2, "long_strike": 50, "legs": None}
        assert intrinsic_value(row, 45.0)[0] == 5.0 * OPTION_MULTIPLIER * 2


class TestTheCeilingPublishesOnThatBase:

    def test_the_route_tops_up_and_names_each_row(self):
        import ast
        import io
        import os
        import tokenize

        backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = io.open(os.path.join(backend, "api/portfolio.py"),
                      encoding="utf-8-sig").read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    src = src.replace(doc, "")
        lines = src.splitlines(keepends=True)
        try:
            for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                if tok.type == tokenize.COMMENT:
                    r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
                    lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
        except (tokenize.TokenError, IndentationError):
            pass
        code = "".join(lines)
        assert "_intrinsic_for_unquoted_options" in code
        assert '"intrinsic_rows"' in code
        assert '"intrinsic_added"' in code

    def test_a_row_whose_underlying_is_unread_keeps_the_account_partial(self):
        """The top-up only completes an account when EVERY unvalued row in it got a figure.
        One unread underlying and the account stays PARTIAL — publishing a base with a hole
        in it is the fault the floor exists to avoid, not a smaller version of it."""
        import ast
        import io
        import os

        backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = io.open(os.path.join(backend, "api/portfolio.py"), encoding="utf-8-sig").read()
        assert "if priced >= holes:" in src

    def test_the_underlying_price_reads_spot_not_price(self):
        """The quote service returns the spot under `spot`. Reading `price` returns None for
        every ticker, and the intrinsic then never computes — which is how this looked on the
        first run."""
        import inspect

        import api.portfolio as pf

        src = inspect.getsource(pf._underlying_price)
        assert '.get("spot")' in src
        assert "auto_adjust=False" in src
