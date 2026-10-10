"""R-IV.827(e) — an expired row's lots are closed, or the row says it needs the document.

THE DEFECT POSITIONS FOUND. The sweep marked IWM 956 EXPIRED at 20:05:32Z and left its lots
netting +1: 13.08 of basis still unrealized, `trade_outcome` UNKNOWN, `exit_price` NULL. A
terminal row whose lots are still open is the #29 disagreement at its worst — the row says the
trade is over while every lot-derived figure (capital at risk, open remainder, realized) keeps
counting it. POSITIONS had already fixed the same thing by hand on 562 and 518: three rows, one
cause.

THE TWO CASES THE RULING NAMES, and the second is the load-bearing one:
  * every leg OUT of the money at the expiry close -> lots closed at 0, realized = -basis;
  * anything IN the money or undeterminable      -> NO closure, row marked NEEDS_DOCUMENT.

Convention #30 throughout: each "it settles" is paired with a case that must NOT, because a
settler that closed everything at zero would pass every positive test and silently book an
assigned position as a total loss.
"""
from __future__ import annotations

import sys
from decimal import Decimal

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models import expiry_settlement as es  # noqa: E402


def _leg(seq, option_type="PUT", strike=76, side="LONG"):
    return {"leg_seq": seq, "option_type": option_type, "strike": strike, "side": side}


# ── the per-leg boundary ─────────────────────────────────────────────────────────────────────
class TestLegMoneyness:
    @pytest.mark.parametrize("otype,strike,close,otm", [
        ("PUT", 76, 80, True),      ("PUT", 76, 70, False),
        ("CALL", 100, 95, True),    ("CALL", 100, 105, False),
        ("put", 76, 80, True),      ("Call", 100, 95, True),
    ])
    def test_the_obvious_cases(self, otype, strike, close, otm):
        assert es.leg_moneyness(otype, strike, close) is otm

    @pytest.mark.parametrize("otype,strike", [("PUT", 76), ("CALL", 100)])
    def test_exactly_AT_the_strike_is_OUT_of_the_money(self, otype, strike):
        """A contract at the money expires worthless. Stated as a test because the boundary is
        the one thing a `<` written from memory gets wrong, and getting it wrong either books a
        real assignment as worthless or sends a worthless expiry for a document."""
        assert es.leg_moneyness(otype, strike, strike) is True

    def test_side_does_not_change_moneyness(self):
        """Moneyness is a property of the CONTRACT against the settlement price. Long or short
        decides who pays, not whether the option finished in the money — conflating them reads a
        short OTM leg as ITM."""
        import inspect

        assert "side" not in inspect.signature(es.leg_moneyness).parameters

    @pytest.mark.parametrize("otype,strike,close", [
        ("PUT", None, 80), ("PUT", 76, None), (None, 76, 80), ("WARRANT", 76, 80),
        ("PUT", "n/a", 80),
    ])
    def test_anything_unusable_is_None_and_never_guessed_as_OTM(self, otype, strike, close):
        """Defaulting any of these to OTM would close a real position at zero."""
        assert es.leg_moneyness(otype, strike, close) is None


# ── the row verdict ──────────────────────────────────────────────────────────────────────────
class TestSettle:
    def test_every_leg_out_of_the_money_settles(self):
        v, reason = es.settle([_leg(1, strike=76), _leg(2, strike=73)], 80)
        assert v == es.ALL_OTM and reason is None
        assert es.closes_at_zero(v) is True

    def test_ONE_leg_in_the_money_stops_the_whole_row(self):
        """CONTROL. The spread's other leg being worthless is irrelevant: an ITM leg settles
        through assignment at a price only the broker document states."""
        v, reason = es.settle([_leg(1, strike=76), _leg(2, strike=73)], 75)
        assert v == es.ANY_ITM
        assert es.closes_at_zero(v) is False
        assert "IN the money" in reason and "broker document" in reason

    @pytest.mark.parametrize("legs,close,fragment", [
        ([_leg(1)], None, "no close recorded"),
        ([], 80, "no legs recorded"),
        ([_leg(1, strike=None)], 80, "no usable option_type/strike"),
        ([_leg(1, option_type="X")], 80, "no usable option_type/strike"),
    ])
    def test_undeterminable_says_which_thing_was_missing(self, legs, close, fragment):
        v, reason = es.settle(legs, close)
        assert v == es.UNDETERMINABLE
        assert es.closes_at_zero(v) is False
        assert fragment in reason

    def test_only_all_otm_may_write_money(self):
        """The single rule the writer depends on."""
        assert es.closes_at_zero(es.ALL_OTM) is True
        for v in (es.ANY_ITM, es.UNDETERMINABLE, "anything_else", "", None):
            assert es.closes_at_zero(v) is False


# ── the money ────────────────────────────────────────────────────────────────────────────────
class TestRealizedOnAWorthlessExpiry:
    def test_realized_is_minus_the_basis(self):
        """5 contracts at 0.136 with a 100 multiplier cost 68.00, so realized is -68.00.
        Proceeds are exactly zero — this is settlement, not a P&L model."""
        assert es.realized_for_worthless_expiry(5, 0.136, 100) == Decimal("-68.000")

    def test_equity_multiplier_is_respected(self):
        assert es.realized_for_worthless_expiry(10, 2.50, 1) == Decimal("-25.00")

    def test_fees_are_part_of_the_loss(self):
        assert es.realized_for_worthless_expiry(5, 0.136, 100, fees=1.30) == Decimal("-69.300")

    def test_a_negative_lot_qty_does_not_flip_the_sign(self):
        """A loss is a loss whichever way the quantity was recorded."""
        assert es.realized_for_worthless_expiry(-5, 0.136, 100) == Decimal("-68.000")

    def test_an_unpriced_lot_returns_None_rather_than_zero(self):
        """A lot with no price has no KNOWN basis, and writing 0 would claim it cost nothing —
        which is exactly the fake-zero this register keeps removing."""
        assert es.realized_for_worthless_expiry(5, None, 100) is None
        assert es.realized_for_worthless_expiry(None, 0.136, 100) is None

    def test_money_is_Decimal_not_float(self):
        """#27: a NUMERIC column records the representation, so a float tail would be stored."""
        out = es.realized_for_worthless_expiry(5, 0.136, 100)
        assert isinstance(out, Decimal)
        assert "0000000" not in str(out), out


# ── what the sweep reports ───────────────────────────────────────────────────────────────────
class TestTheReport:
    def test_waiting_rows_are_LISTED_not_merely_counted(self):
        """A count tells POSITIONS that work exists; a list tells them where it is."""
        s = es.summarise([
            {"position_id": "A", "ticker": "IWM", "verdict": es.ALL_OTM, "reason": None},
            {"position_id": "B", "ticker": "NVDA", "verdict": es.ANY_ITM, "reason": "itm"},
            {"position_id": "C", "ticker": "XLF", "verdict": es.UNDETERMINABLE, "reason": "no close"},
        ])
        assert s["expired"] == 3 and s["settled_worthless"] == 1 and s["needs_document"] == 2
        ids = [r["position_id"] for r in s["needs_document_rows"]]
        assert ids == ["B", "C"]
        assert all(r["reason"] for r in s["needs_document_rows"])

    def test_an_all_settled_sweep_lists_nothing(self):
        s = es.summarise([{"position_id": "A", "verdict": es.ALL_OTM}])
        assert s["needs_document"] == 0 and s["needs_document_rows"] == []

    def test_it_states_its_own_rule(self):
        assert "out of the money" in es.summarise([])["basis"]


# ── the two cases the ruling names, end to end against the writer ────────────────────────────
class TestTheWriterPath:
    """R-IV.827(e)'s two required tests, against the real `_settle_expired_lots`.

    An expiring OTM long option must close at 0 with realized = -basis; an ITM row must be
    marked NEEDS_DOCUMENT with NO closure written.
    """

    def _harness(self, legs, close, lots, asset_type="OPTION"):
        """Fakes the three reads and records the writes, so the assertion is on what the
        function WOULD write rather than on its return value alone."""
        import asyncio
        from unittest.mock import patch

        executed = []

        class _Tx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        class _Conn:
            async def fetchrow(self, sql, *a):
                return {"position_id": "P1", "ticker": "IWM", "asset_type": asset_type,
                        "expiry": "2026-10-09", "long_strike": 76, "short_strike": 73}

            async def fetch(self, sql, *a):
                if "position_legs" in sql:
                    return legs
                if "position_lots" in sql:
                    return lots
                return []

            async def fetchval(self, sql, *a):
                executed.append(("fetchval", " ".join(sql.split()), a))
                return 9001

            async def execute(self, sql, *a):
                executed.append(("execute", " ".join(sql.split()), a))

            def transaction(self):
                return _Tx()

        class _Acq:
            async def __aenter__(self):
                return _Conn()

            async def __aexit__(self, *a):
                return False

        class _Pool:
            def acquire(self):
                return _Acq()

        async def _bars(ticker, *a, **k):
            return [{"c": close}] if close is not None else []

        from api import unified_positions as up

        loop = asyncio.new_event_loop()
        with patch.object(up, "get_postgres_client", return_value=_Pool()), \
                patch("integrations.uw_api.get_bars", _bars):
            try:
                out = loop.run_until_complete(up._settle_expired_lots(
                    [{"position_id": "P1", "ticker": "IWM", "expiry": "2026-10-09"}]))
            finally:
                loop.close()
        return out["P1"], executed

    def test_an_expiring_OTM_long_option_closes_at_zero(self):
        legs = [_leg(1, strike=76)]
        lots = [{"id": 1, "qty": Decimal("5"), "price": Decimal("0.136"), "fees": Decimal("0")}]
        info, executed = self._harness(legs, close=80, lots=lots)

        assert info["verdict"] == es.ALL_OTM
        assert info["closed_lots"] == 1
        assert info["realized"] == pytest.approx(-68.0)
        sqls = " | ".join(s for _, s, _ in executed)
        assert "INSERT INTO position_lot_closures" in sqls
        assert "needs_document = NULL" in sqls, "a settled row must not stay flagged"

    def test_an_ITM_row_is_flagged_and_NO_closure_is_written(self):
        legs = [_leg(1, strike=76)]
        lots = [{"id": 1, "qty": Decimal("5"), "price": Decimal("0.136"), "fees": Decimal("0")}]
        info, executed = self._harness(legs, close=70, lots=lots)

        assert info["verdict"] == es.ANY_ITM
        assert info["closed_lots"] == 0
        assert info["realized"] is None
        sqls = " | ".join(s for _, s, _ in executed)
        assert "INSERT INTO position_lot_closures" not in sqls, \
            "an ITM expiry must not have its money invented"
        assert "needs_document = $2" in sqls
        flagged = [a for _, s, a in executed if "needs_document = $2" in s]
        assert flagged and es.NEEDS_DOCUMENT in str(flagged[0])

    def test_a_row_with_no_open_lots_is_left_alone(self):
        """CONTROL. Nothing to close means nothing to write and nothing to flag — a row already
        fully closed must not acquire a flag just for expiring."""
        legs = [_leg(1, strike=76)]
        lots = [{"id": 1, "qty": Decimal("5"), "price": Decimal("0.136"), "fees": Decimal("0")},
                {"id": 2, "qty": Decimal("-5"), "price": Decimal("0.2"), "fees": Decimal("0")}]
        info, executed = self._harness(legs, close=80, lots=lots)
        assert info["net_open_qty"] == 0
        sqls = " | ".join(s for _, s, _ in executed)
        assert "INSERT INTO position_lot_closures" not in sqls
        assert "needs_document" not in sqls

    def test_an_equity_row_never_settles_by_moneyness(self):
        legs = [_leg(1, strike=76)]
        lots = [{"id": 1, "qty": Decimal("5"), "price": Decimal("1.0"), "fees": Decimal("0")}]
        info, _ = self._harness(legs, close=80, lots=lots, asset_type="EQUITY")
        assert info["verdict"] == es.UNDETERMINABLE
        assert "does not expire by moneyness" in info["reason"]

    def test_no_close_for_the_expiry_date_waits(self):
        legs = [_leg(1, strike=76)]
        lots = [{"id": 1, "qty": Decimal("5"), "price": Decimal("0.136"), "fees": Decimal("0")}]
        info, executed = self._harness(legs, close=None, lots=lots)
        assert info["verdict"] == es.UNDETERMINABLE
        assert "no close recorded" in info["reason"]
        assert "INSERT INTO position_lot_closures" not in " | ".join(s for _, s, _ in executed)


class TestTheSweepIsWiredAndCannotLoseTheStatusWrite:
    def test_the_sweep_calls_the_settlement_pass(self):
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up._sweep_expired_positions)
        assert "_settle_expired_lots(expired)" in src

    def test_settlement_failure_never_loses_the_EXPIRED_write(self):
        """The status write is the fact that cannot be lost; settlement is retried next pass.
        So the settlement pass is in its own try/except, outside the UPDATE's transaction."""
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up._sweep_expired_positions)
        at_update = src.index("UPDATE unified_positions")
        at_settle = src.index("_settle_expired_lots(expired)")
        assert at_update < at_settle, "status is written before settlement is attempted"
        assert "rows stay EXPIRED, lots open" in src

    def test_the_column_is_created_at_boot(self):
        import inspect

        from database import postgres_client as pc

        assert "ADD COLUMN IF NOT EXISTS needs_document TEXT" in inspect.getsource(pc)

    def test_needs_document_is_not_a_status_value(self):
        """`status` is (OPEN, CLOSED, EXPIRED, DUPLICATE_OF) and every reader is written against
        that set. The contract did end, so the row is still EXPIRED; the flag is separate."""
        from models.position_status import STATUSES

        assert es.NEEDS_DOCUMENT not in STATUSES
        assert set(STATUSES) == {"OPEN", "CLOSED", "EXPIRED", "DUPLICATE_OF"}
