"""Money reaches a NUMERIC column as a Decimal — R-IV.783(c).

THE DEFECT, reproduced before it was fixed. POSITIONS found AVGO 517's `realized_pnl` stored as
−16.000000000000004. The mechanism is not a missing round: `_compute_unrealized_pnl` already
rounds to 2dp on every return path, which is why OPEN rows were clean. It is that **a rounded
float is still a float**, and a float cannot hold most cent values exactly, so passing one for a
NUMERIC parameter materialises its full binary expansion in the column.

Reproduced against the stored values, to the last digit:

    Decimal(round(36.15, 2))   -> 36.14999999999999857891452847979962825775146484375   = GDX 191
    Decimal(round(-150.74, 2)) -> -150.740000000000009094947017729282379150390625      = GUSH 204
    Decimal(round(6.21, 2))    -> 6.20999999999999996447286321199499070644378662109375 = SIL 405
    Decimal(round(1055.7, 2))  -> 1055.700000000000045474735088646411895751953125       = GUSH 204 max_loss

So `round(x, 2)` rounds the VALUE and leaves the REPRESENTATION, and the column records the
representation.

AND `money_in` DID NOT FIX IT. It ends in `float(...)`, so R-IV.613(c)3's PATCH fix quantized the
value and handed back the same tail-carrying double. That fix was incomplete from the day it
shipped, which is the thing worth remembering: a helper named for money can still be the wrong
helper for a column.
"""
import inspect
import io
import os
from decimal import Decimal

import pytest

from services.position_economics import money, money_db, money_in


class TestItReproducesTheStoredTails:
    """The evidence that the diagnosis is the mechanism and not a plausible story."""

    @pytest.mark.parametrize("value,stored", [
        (36.15, "36.14999999999999857891452847979962825775146484375"),
        (-150.74, "-150.740000000000009094947017729282379150390625"),
        (6.21, "6.20999999999999996447286321199499070644378662109375"),
        (1055.70, "1055.700000000000045474735088646411895751953125"),
    ])
    def test_a_rounded_float_still_carries_the_exact_tail_that_was_stored(self, value, stored):
        assert str(Decimal(round(value, 2))) == stored

    def test_money_in_inherits_the_very_same_tail(self):
        """POSITIVE CONTROL for why a new helper was needed rather than reusing the old one."""
        assert isinstance(money_in(36.15), float)
        assert str(Decimal(money_in(36.15))) == (
            "36.14999999999999857891452847979962825775146484375")

    def test_money_also_returns_a_float_and_is_an_OUTPUT_helper(self):
        assert isinstance(money(Decimal("36.15")), float)


class TestMoneyDbIsCleanAtTheColumn:
    @pytest.mark.parametrize("value", [36.15, -150.74, 6.21, 1055.70, 0.07, -0.01])
    def test_it_returns_a_Decimal_with_no_tail(self, value):
        d = money_db(value)
        assert isinstance(d, Decimal)
        assert d == Decimal(str(d))
        assert -2 <= d.as_tuple().exponent <= 0 or d.as_tuple().exponent == -2

    def test_AVGO_517s_exact_value_becomes_clean(self):
        """The row that opened R-IV.783(c)."""
        assert money_db(-16.000000000000004) == Decimal("-16.00")
        assert str(money_db(-16.000000000000004)) == "-16.00"

    @pytest.mark.parametrize("raw,want", [("2.675", "2.68"), ("0.145", "0.15"),
                                          ("8.345", "8.35"), ("-2.675", "-2.68")])
    def test_it_is_HALF_UP_where_python_round_is_not(self, raw, want):
        """#27 requires HALF-UP. Python's round is banker's on the binary value: 2.675 -> 2.67
        and 0.145 -> 0.14, both wrong by a cent in the direction nobody chose."""
        assert str(money_db(raw)) == want
        assert money_db(raw) != Decimal(str(round(float(raw), 2))) or want == str(
            round(float(raw), 2))

    @pytest.mark.parametrize("junk", [None, "", "abc", float("nan"), float("inf")])
    def test_unreadable_is_None_never_zero(self, junk):
        """A figure nobody gave and a figure of zero are different claims. `nan` matters
        specifically: it passes every `if not x` guard, since `not nan` is False."""
        assert money_db(junk) is None

    def test_a_Decimal_in_stays_exact(self):
        assert money_db(Decimal("1234.56")) == Decimal("1234.56")

    def test_zero_is_zero_and_not_None(self):
        assert money_db(0) == Decimal("0.00")
        assert money_db(0) is not None


class TestTheWritePathsUseIt:
    def _src(self, rel):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return io.open(os.path.join(base, *rel.split("/")), encoding="utf-8-sig").read()

    def test_the_PATCH_money_fields_no_longer_use_money_in(self):
        src = self._src("api/unified_positions.py")
        assert "money_db as _money_patch" in src
        assert "money_db as _money_patch2" in src
        assert "money_in as _money_patch" not in src

    def test_the_mark_job_quantizes_before_the_parameter(self):
        """This is the path that produced the 47 stored unrealized tails."""
        src = self._src("api/unified_positions.py")
        assert "mark, unreal = _mdb(mark), _mdb(unreal)" in src
        i = src.index("_compute_unrealized_pnl(entry_price, mark, quantity, structure")
        j = src.index("mark, unreal = _mdb(mark), _mdb(unreal)")
        assert i < j, "the quantize must come after the computation and before the write"

    def test_compute_unrealized_still_rounds_and_that_is_not_the_fix(self):
        """Kept deliberately. Rounding is still right for the returned figure; it was never
        sufficient for the column, and a reader should not 'simplify' one into the other."""
        from api import unified_positions as UP
        s = inspect.getsource(UP._compute_unrealized_pnl)
        assert s.count("round(") >= 3
