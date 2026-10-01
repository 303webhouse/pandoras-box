"""What the add form must require, and the legs its strikes imply — R-IV.613(c).

564 QQQ was written as a `put_debit_spread` with **no legs, no expiry and no direction**, and the
route reported success. Three separate silences, and fixing the date was only the first.
"""

import ast
import io
import os
from datetime import date

import pytest

from models.position_shape import (SHARES, SINGLE, SPREAD, family_of, legs_from_strikes,
                                   missing_fields, refusal_message)
from services.position_economics import money_in

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = date(2026, 10, 16)


def _code(rel):
    """Live code only: docstrings and comments both removed, spacing preserved."""
    import tokenize

    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    lines = src.splitlines(keepends=True)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
            lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
    except (tokenize.TokenError, IndentationError):
        pass
    return "".join(lines)


# ─────────────────────── (c)1 what each shape requires

class TestTheShapeDecidesWhatIsRequired:

    @pytest.mark.parametrize("structure,family", [
        ("put_debit_spread", SPREAD), ("call_credit_spread", SPREAD),
        ("long_put", SINGLE), ("short_call", SINGLE),
        ("stock", SHARES), ("etf", SHARES),
        ("put_debit_spread+long_put", SPREAD),      # live in the book today
    ])
    def test_the_families(self, structure, family):
        assert family_of(structure) == family

    def test_the_564_qqq_case_is_refused_by_name(self):
        """A spread with no expiry and no strikes. This is the row that prompted the ruling."""
        missing = missing_fields("put_debit_spread", None, None, None)
        assert missing == ["expiry", "long_strike", "short_strike"]
        msg = refusal_message("put_debit_spread", missing)
        assert "a spread" in msg
        assert "Nothing was saved." in msg
        for field in missing:
            assert field in msg

    def test_a_complete_spread_is_accepted(self):
        assert missing_fields("put_debit_spread", "2026-10-16", 600, 590) == []

    def test_a_single_option_needs_one_strike_not_two(self):
        assert missing_fields("long_put", "2026-10-16", 600, None) == []
        assert missing_fields("long_put", "2026-10-16", None, None) == ["long_strike"]

    def test_stock_needs_neither(self):
        assert missing_fields("stock", None, None, None) == []
        assert missing_fields("etf", None, None, None) == []

    def test_a_zero_or_negative_strike_counts_as_missing(self):
        """A zero-strike option is not a thing, and accepting it would put an unusable number
        where every reader expects a price."""
        assert "long_strike" in missing_fields("long_put", "2026-10-16", 0, None)
        assert "long_strike" in missing_fields("long_put", "2026-10-16", -5, None)
        assert "short_strike" in missing_fields("put_debit_spread", "2026-10-16", 600, 0)

    def test_an_unmapped_structure_requires_nothing_and_is_not_refused(self):
        """"We have not described this shape" must not become "you may not record your own
        trade". An iron condor is bookable; it just carries no synthesised legs."""
        assert missing_fields("iron_condor", None, None, None) == []
        assert family_of("iron_condor") is None
        assert legs_from_strikes("iron_condor", EXP, 600, 590, 1) is None

    def test_entry_price_is_deliberately_not_required(self):
        """The principal books rows he has not priced yet, and the economics reports a missing
        basis honestly rather than inventing one."""
        assert missing_fields("put_debit_spread", "2026-10-16", 600, 590) == []


# ─────────────────────── (c)2 the legs come from the strikes

class TestLegsFromStrikes:

    def test_a_debit_spread_is_long_the_strike_the_form_called_long(self):
        legs = legs_from_strikes("put_debit_spread", EXP, 600, 590, 2)
        assert [(l["option_type"], l["side"], l["strike"]) for l in legs] == [
            ("put", "long", 600.0), ("put", "short", 590.0)]
        assert all(l["qty"] == 2.0 and l["ratio"] == 1.0 for l in legs)
        assert all(l["expiry"] == EXP for l in legs)

    def test_a_credit_spread_puts_the_short_leg_first_and_keeps_the_strikes_straight(self):
        legs = legs_from_strikes("put_credit_spread", EXP, 590, 600, 1)
        assert [(l["side"], l["strike"]) for l in legs] == [("short", 600.0), ("long", 590.0)]

    def test_a_call_spread_is_calls(self):
        legs = legs_from_strikes("call_debit_spread", EXP, 600, 610, 1)
        assert {l["option_type"] for l in legs} == {"call"}

    def test_a_single_option_gets_one_leg(self):
        legs = legs_from_strikes("long_put", EXP, 600, None, 3)
        assert len(legs) == 1
        assert (legs[0]["option_type"], legs[0]["side"], legs[0]["qty"]) == ("put", "long", 3.0)

    def test_shares_imply_no_legs(self):
        assert legs_from_strikes("stock", EXP, None, None, 100) is None

    def test_none_not_empty_when_the_strikes_are_absent(self):
        """An empty list asserts "this position has no legs", which for a spread is false
        rather than unknown."""
        assert legs_from_strikes("put_debit_spread", EXP, None, None, 1) is None
        assert legs_from_strikes("put_debit_spread", None, 600, 590, 1) is None

    def test_the_shape_matches_what_the_form_supplied_path_produces(self):
        """A synthesised set and a form-supplied one must be indistinguishable downstream, or
        there are two shapes to keep in step."""
        legs = legs_from_strikes("put_debit_spread", EXP, 600, 590, 1)
        for leg in legs:
            assert set(leg) == {"option_type", "side", "strike", "expiry", "qty",
                                "ratio", "price"}


# ─────────────────────── (c)3 no float reaches a numeric column

class TestEveryMoneyFigureIsQuantized:

    def test_the_564_qqq_cost_basis(self):
        """It stored 7.000000000000001 — binary floating point written verbatim into NUMERIC,
        and every figure derived from it inherited the tail."""
        assert money_in(7.000000000000001) == 7.0

    def test_it_rounds_half_up_not_half_even(self):
        """`round(2.675, 2)` is 2.67 in Python — banker's rounding. Convention #27 is HALF-UP."""
        assert money_in(226.385) == 226.39
        assert money_in(-3.005) == -3.01
        assert round(226.385, 2) != money_in(226.385)

    def test_a_missing_price_stays_missing(self):
        """A price nobody gave and a price of zero are different claims."""
        assert money_in(None) is None
        assert money_in("") is None
        assert money_in(0) == 0.0

    def test_nan_does_not_survive(self):
        """`float("nan")` succeeds and passes every `if not x` guard downstream."""
        assert money_in(float("nan")) is None
        assert money_in("nan") is None

    def test_a_numeric_string_from_a_form_still_reads(self):
        assert money_in("12.3456") == 12.35

    def test_the_entry_path_quantizes_every_money_column(self):
        code = _code("api/unified_positions.py")
        assert "money_in as _money" in code
        for name in ("entry_price = _money", "cost_basis = _money(cost_basis)",
                     "max_loss = _money(max_loss)", "stop_loss = _money(req.stop_loss)"):
            assert name in code, name

    def test_the_close_path_no_longer_uses_round(self):
        """Anchored on CREDIT_STRUCTURES, because `realized_pnl` appears at several sites and
        the first is the PATCH path — a window on the wrong one passes for the wrong reason."""
        code = _code("api/unified_positions.py")
        i = code.index("elif s in CREDIT_STRUCTURES:")
        window = code[i - 700:i + 500]
        assert "round(" not in window, window[-320:]
        assert window.count("_money(") >= 4

    def test_the_patch_path_quantizes_too(self):
        """It is a close path as well, and a caller-supplied float lands in NUMERIC as it
        arrives."""
        code = _code("api/unified_positions.py")
        assert "params.append(_money_patch(req.exit_price))" in code
        assert "params.append(_money_patch2(req.realized_pnl))" in code


# ─────────────────────── the wiring

def test_the_add_path_refuses_before_it_writes():
    """The validation must come BEFORE the transaction, or a refusal leaves a row behind."""
    code = _code("api/unified_positions.py")
    i = code.index("missing_fields(req.structure")
    j = code.index("async with pool.acquire() as conn, conn.transaction():", i)
    assert "raise HTTPException" in code[i:j]


def test_the_insert_writes_the_synthesised_legs():
    code = _code("api/unified_positions.py")
    assert "legs_payload = req.legs or legs_from_strikes(" in code
    assert "dumps_jsonb(legs_payload) if legs_payload else None" in code
    # ...and no longer only the form's array.
    assert "dumps_jsonb(req.legs) if req.legs else None" not in code
