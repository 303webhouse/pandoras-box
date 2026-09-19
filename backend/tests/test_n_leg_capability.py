"""R-IV.458(a)(b)(c), R-IV.460 — N legs as a capability; marks from legs; exact quantities.

FAIL-FIRST against the pre-2026-09-18 tree: the mark path chose its method from the structure
NAME (a put_butterfly was priced as its 100P alone, +21.00 on no fill); legs entry stopped at four;
nothing computed a leg set's extremes before save; quantity was INTEGER so a broker's fractional
share could not be recorded; and a closed row's quantity, entry or basis could not be corrected.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models.leg_payoff import analyze, display_strikes, recognize  # noqa: E402
from services.leg_mark import (  # noqa: E402
    mark_from_legs, name_path_priced_same_legs, payoff_range, prior_is_good,
    prior_mark_came_from_legs, stale_reason, structure_ratios,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
E = "2026-10-16"


def L(t, s, k, p=None, q=1, e=E):
    return {"option_type": t, "side": s, "strike": k, "price": p, "qty": q, "expiry": e}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- the payoff engine, on textbook cases ---------------------------------------------------
@pytest.mark.parametrize("legs,name,profit,loss,bes", [
    ([L("PUT", "LONG", 100, 3), L("PUT", "SHORT", 90, 1)], "put_debit_spread", 800, 200, [98]),
    ([L("CALL", "LONG", 100, 5)], "long_call", "UNLIMITED", 500, [105]),
    ([L("CALL", "SHORT", 100, 5)], "short_call", 500, "UNLIMITED", [105]),
    ([L("PUT", "LONG", 90, 1), L("PUT", "SHORT", 95, 2), L("CALL", "SHORT", 105, 2),
      L("CALL", "LONG", 110, 1)], "iron_condor", 200, 300, [93, 107]),
    ([L("CALL", "LONG", 90, 12), L("CALL", "SHORT", 100, 5, 2), L("CALL", "LONG", 110, 1)],
     "call_butterfly", 700, 300, [93, 107]),
])
def test_known_structures_are_named_and_priced_correctly(legs, name, profit, loss, bes):
    a = analyze(legs)
    assert recognize(legs) == name
    assert a["max_profit"] == profit and a["max_loss"] == loss
    assert a["breakevens"] == [float(b) for b in bes]


def test_six_legs_are_accepted_with_no_ceiling():
    legs = [L("PUT", "LONG", 80, 1), L("PUT", "SHORT", 85, 2), L("PUT", "LONG", 90, 1),
            L("CALL", "LONG", 110, 1), L("CALL", "SHORT", 115, 2), L("CALL", "LONG", 120, 1)]
    a = analyze(legs)
    assert a["computable"] and a["legs"] == 6
    assert recognize(legs) == "custom", "an unnamed shape is CUSTOM, and still analysed"


def test_an_unpriced_leg_reports_the_shape_and_not_invented_dollars():
    a = analyze([L("PUT", "LONG", 100), L("PUT", "SHORT", 90)])
    assert a["net_premium"] is None and a["max_loss"] is None
    assert "no price" in a["reason"]


def test_legs_on_two_expiries_are_not_given_a_single_expiry_payoff():
    legs = [L("CALL", "SHORT", 100, 2, 1, "2026-10-16"), L("CALL", "LONG", 100, 4, 1, "2026-11-20")]
    a = analyze(legs)
    assert recognize(legs) == "calendar"
    assert a["computable"] is False and a["net_premium"] == 2.0
    assert "different dates" in a["reason"]


def test_nvda_415s_legs_are_not_a_butterfly():
    """1:1:1 at 100/90/50 is a put debit spread plus a long 50P. The label stands by ruling;
    the recognizer says what the legs are."""
    legs = [L("PUT", "LONG", 100, q=3), L("PUT", "SHORT", 90, q=3), L("PUT", "LONG", 50, q=3)]
    assert recognize(legs) == "custom"


def test_the_two_strike_columns_are_derived_for_display():
    s = display_strikes([L("PUT", "LONG", 45), L("PUT", "SHORT", 40), L("PUT", "LONG", 30)])
    assert s == {"long_strike": 45.0, "short_strike": 40.0}


# --- marking from legs --------------------------------------------------------------------
def test_ratios_are_per_structure_and_a_disagreement_is_refused():
    assert structure_ratios([{"qty": 3}, {"qty": 6}, {"qty": 3}], 3) == [1, 2, 1]
    assert structure_ratios([{"qty": 10}, {"qty": 10}], 8) is None, "XLF: legs 10, row 8"


def test_a_position_is_marked_from_every_leg_across_expiries():
    calls = []

    async def pricer(tk, group, expiry):
        calls.append((expiry, len(group)))
        # signed BUY-minus-SELL: the short near call is worth -1.0, the long far call +1.4
        return {"net_mark": -1.0 if expiry == "2026-10-16" else 1.4, "leg_details": []}
    legs = [L("CALL", "SHORT", 100, q=2, e="2026-10-16"), L("CALL", "LONG", 100, q=2, e="2026-11-20")]
    out = _run(mark_from_legs("SPY", legs, 2, "calendar", pricer))
    assert out["ok"] and abs(out["net_mark"] - 0.4) < 1e-9
    assert sorted(calls) == [("2026-10-16", 1), ("2026-11-20", 1)]
    assert out["reason"].startswith("priced from 2 leg(s)")
    assert prior_mark_came_from_legs(out["reason"]), "a bounded legs mark is a good prior"


def test_a_missing_quote_makes_the_mark_unavailable_not_partial():
    async def pricer(tk, group, expiry):
        return None
    legs = [L("PUT", "LONG", 100, q=3, e="2027-01-15"), L("PUT", "SHORT", 90, q=3, e="2027-01-15"),
            L("PUT", "LONG", 50, q=3, e="2027-01-15")]
    out = _run(mark_from_legs("NVDA", legs, 3, "put_butterfly", pricer))
    assert out["ok"] is False and "no quote" in out["reason"]
    assert "different structure" in out["reason"]


def test_a_row_that_disagrees_with_its_legs_is_unavailable():
    async def pricer(*a):
        raise AssertionError("must not price a position whose scale is unknown")
    legs = [L("PUT", "LONG", 45, q=10), L("PUT", "SHORT", 40, q=10), L("PUT", "LONG", 30, q=10)]
    out = _run(mark_from_legs("XLF", legs, 8, "put_debit_spread", pricer))
    assert out["ok"] is False and "the row says quantity 8" in out["reason"]


def test_only_a_legs_derived_prior_may_survive_a_failed_cycle():
    good = "priced from 2 leg(s) (put_debit_spread), within what they can be worth"
    assert prior_mark_came_from_legs(good)
    # written before the bound existed: abs() of the net, so possibly an impossible value flipped
    # positive (QQQ 356: 0.01 = abs(0.02 - 0.03)). Not a good prior.
    assert not prior_mark_came_from_legs("priced from 2 leg(s) (put_debit_spread)")
    assert not prior_mark_came_from_legs(None)
    assert not prior_mark_came_from_legs("OK")
    # a STALE prior keeps reading as good, and says why it was not refreshed, without stacking
    once = stale_reason(good, "no quote for the 2026-10-16 leg(s) 350P")
    assert prior_mark_came_from_legs(once) and "not refreshed: no quote" in once
    assert stale_reason(once, "outside") == good + " | not refreshed: outside"
    assert stale_reason(None, None) == "prior mark kept | not refreshed: no reason given"


def _leg(t, s, k, q=2, e=E):
    return {"option_type": t, "side": s, "strike": k, "qty": q, "expiry": e}


@pytest.mark.parametrize("legs,structure,ls,ss,prior,good", [
    # the census's correct class: the two-strike path priced exactly these contracts
    ([_leg("PUT", "LONG", 60), _leg("PUT", "SHORT", 55)], "put_debit_spread", 60, 55, 0.035, True),
    ([_leg("PUT", "LONG", 60)], "long_put", 60, None, 0.02, True),
    # SLV 316: a debit spread marked -0.085 -- nothing the path priced is worth less than nothing
    ([_leg("CALL", "LONG", 120), _leg("CALL", "SHORT", 130)], "call_debit_spread", 120, 130,
     -0.085, False),
    # NVDA 415 / XLF 300: three legs -- the path priced a different structure
    ([_leg("PUT", "LONG", 100), _leg("PUT", "SHORT", 90), _leg("PUT", "LONG", 50)],
     "put_butterfly", 100, 90, 0.10, False),
    # the name says call, the legs are puts: the path priced the wrong contracts
    ([_leg("PUT", "LONG", 60), _leg("PUT", "SHORT", 55)], "call_debit_spread", 60, 55, 0.03, False),
    # the strikes the path read are not the strikes held
    ([_leg("PUT", "LONG", 60), _leg("PUT", "SHORT", 50)], "put_debit_spread", 60, 55, 0.03, False),
    # a leg on another expiry
    ([_leg("PUT", "LONG", 60), _leg("PUT", "SHORT", 55, e="2026-11-20")], "put_debit_spread",
     60, 55, 0.03, False),
    # no prior at all
    ([_leg("PUT", "LONG", 60)], "long_put", 60, None, None, False),
])
def test_a_prior_is_good_only_where_the_two_strike_path_priced_the_legs_held(
        legs, structure, ls, ss, prior, good):
    assert name_path_priced_same_legs(legs, structure, E, ls, ss, 2, prior) is good


def test_a_row_that_disagrees_with_its_legs_keeps_no_name_path_prior():
    legs = [_leg("PUT", "LONG", 45, q=10), _leg("PUT", "SHORT", 40, q=10)]
    assert not name_path_priced_same_legs(legs, "put_debit_spread", E, 45, 40, 8, 0.01)


def test_the_stale_branch_asks_who_wrote_the_prior():
    from api import unified_positions as U
    src = inspect.getsource(U.run_mark_to_market)
    i = src.index("A POSITION WITH LEGS IS MARKED FROM ITS LEGS")
    block = src[i:src.index("# --- Multi-leg path", i)]
    stale = block[block.index("prior_is_good("):block.index("mark_status = 'STALE'")]
    assert 'row.get("mark_reason")' in stale


def test_a_pre_bound_legs_prior_is_not_rescued_by_its_shape():
    """QQQ 356: a plain vertical whose prior 0.01 was abs(-0.01), written by the legs path before
    the bound. The shape matches what the two-strike path prices; the writer does not."""
    legs = [_leg("PUT", "LONG", 360, q=8), _leg("PUT", "SHORT", 350, q=8)]
    args = (legs, "put_debit_spread", E, 360, 350, 8, 0.01)
    pre_bound = "priced from 2 leg(s) (put_debit_spread)"
    assert not prior_is_good(pre_bound, *args)
    assert not prior_is_good(stale_reason(pre_bound, "outside"), *args)
    assert prior_is_good(pre_bound + ", within what they can be worth", *args)
    assert prior_is_good(None, *args), "a two-strike prior on the same legs is still good"
    assert prior_is_good(stale_reason(None, "no quote"), *args)


def test_a_legs_position_never_falls_through_to_a_name_based_path():
    from api import unified_positions as U
    src = inspect.getsource(U.run_mark_to_market)
    i = src.index("A POSITION WITH LEGS IS MARKED FROM ITS LEGS")
    block = src[i:src.index("# --- Multi-leg path", i)]
    assert "continue" in block
    assert "mark_status = 'UNAVAILABLE'" in block and "current_price = NULL" in block


# --- a net outside what the legs can be worth is not a price (R-IV.462(d)) -------------------
def _g(t, a, k, q=1):
    return {"option_type": t, "action": a, "strike": k, "quantity": q}


@pytest.mark.parametrize("group,low,high", [
    ([_g("call", "BUY", 120), _g("call", "SELL", 130)], 0, 10),          # debit vertical: 0..width
    ([_g("put", "SELL", 100), _g("put", "BUY", 90)], -10, 0),            # credit vertical, as held
    ([_g("put", "BUY", 100), _g("put", "SELL", 90), _g("put", "BUY", 50)], 0, 60),  # NVDA 415
    ([_g("call", "BUY", 90), _g("call", "SELL", 100, 2), _g("call", "BUY", 110)], 0, 10),
    ([_g("call", "BUY", 100)], 0, float("inf")),                          # no ceiling
    ([_g("call", "SELL", 100)], float("-inf"), 0),                        # no floor
])
def test_payoff_range_is_what_one_structure_can_be_worth(group, low, high):
    assert payoff_range(group) == (low, high)


def _price_at(net):
    async def pricer(tk, group, expiry):
        return {"net_mark": net, "leg_details": []}
    return pricer


def test_slv_316s_quotes_are_refused_not_turned_positive():
    """120C at 0.02 and 130C at 0.105: a higher-strike call priced above a lower one. The old
    path stored -0.085; the first legs path stored abs() of it, +0.085. Neither is a price."""
    legs = [L("CALL", "LONG", 120, q=5, e="2026-09-30"), L("CALL", "SHORT", 130, q=5, e="2026-09-30")]
    out = _run(mark_from_legs("SLV", legs, 5, "call_debit_spread", _price_at(-0.085)))
    assert out["ok"] is False and "outside what they can be worth" in out["reason"]
    assert "+0.00 to +10.00" in out["reason"]


def test_a_vertical_priced_above_its_width_is_refused():
    legs = [L("PUT", "LONG", 100, q=2), L("PUT", "SHORT", 90, q=2)]
    out = _run(mark_from_legs("X", legs, 2, "put_debit_spread", _price_at(10.5)))
    assert out["ok"] is False and "outside" in out["reason"]


def test_a_credit_structure_is_bounded_in_its_own_sign():
    legs = [L("PUT", "SHORT", 100, q=1), L("PUT", "LONG", 90, q=1)]
    assert _run(mark_from_legs("X", legs, 1, "put_credit_spread", _price_at(-3.0)))["ok"]
    assert not _run(mark_from_legs("X", legs, 1, "put_credit_spread", _price_at(0.02)))["ok"]


def test_a_long_call_has_no_ceiling_to_break():
    legs = [L("CALL", "LONG", 100, q=1)]
    out = _run(mark_from_legs("X", legs, 1, "long_call", _price_at(250.0)))
    assert out["ok"] and "no ceiling" not in out["reason"]


def test_a_near_worthless_spread_one_tick_below_zero_is_still_refused():
    """QQQ 427 at -0.005: nearly worthless is a real state; below zero is not one."""
    legs = [L("PUT", "LONG", 640, q=4), L("PUT", "SHORT", 630, q=4)]
    assert not _run(mark_from_legs("QQQ", legs, 4, "put_debit_spread", _price_at(-0.005)))["ok"]


# --- exact quantity (R-IV.458(b)) ---------------------------------------------------------
def test_quantity_is_numeric_in_the_migration_and_the_fresh_create():
    sql = (ROOT / "migrations" / "047_quantity_exact_and_mark_reason.sql").read_text(encoding="utf-8")
    assert "ALTER COLUMN quantity TYPE NUMERIC" in sql
    boot = (ROOT / "backend" / "database" / "postgres_client.py").read_text(encoding="utf-8")
    assert "quantity NUMERIC NOT NULL DEFAULT 1" in boot


def test_a_decimal_quantity_does_not_break_the_arithmetic():
    from decimal import Decimal
    from api.unified_positions import _compute_unrealized_pnl
    from models.position_risk import calculate_position_risk
    assert _compute_unrealized_pnl(39.09, 39.50, Decimal("15.35049"), "stock",
                                   direction="LONG") == pytest.approx(6.29, abs=0.01)
    calculate_position_risk("stock", 39.09, Decimal("15.35049"))


def test_the_lots_paths_store_the_exact_sum():
    src = (ROOT / "backend" / "api" / "unified_positions.py").read_text(encoding="utf-8")
    assert "INTEGER) cannot hold" not in src, "the fraction refusal is gone with the INTEGER column"
    assert src.count('stored_qty = agg["qty"]') == 2


# --- correcting a closed row's shape (R-IV.458(b)(c)) -------------------------------------------
class _Acq:
    def __init__(self, c): self.c = c
    async def __aenter__(self): return self.c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


def _correct(monkeypatch, lots, **body):
    from api import unified_positions as U
    conn = MagicMock()
    conn.calls = []
    conn.fetchrow = AsyncMock(return_value={
        "position_id": "G", "status": "CLOSED", "realized_pnl": 6.40, "exit_price": 39.5,
        "quantity": 15, "entry_price": 39.09, "cost_basis": 586.35, "notes": ""})
    # the row's lots answer the lots query; it has no legs (R-IV.463(e) derives max_loss)
    conn.fetch = AsyncMock(side_effect=lambda sql, *a: [{"source": s} for s in lots]
                           if "position_lots" in sql else [])

    async def execute(sql, *args):
        conn.calls.append((" ".join(sql.split()), args))

    conn.execute = execute
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    req = U.CorrectRealizedRequest(**{"evidence": "export L149: 0.35049 @ 39.09",
                                      "reason": "the broker is the record",
                                      "ruling": "R-IV.458(b)", **body})
    return _run(U.correct_realized("G", req)), conn


def test_a_fractional_quantity_is_corrected_and_its_legacy_copy_follows(monkeypatch):
    out, conn = _correct(monkeypatch, ["LEGACY-SINGLE-LOT"], quantity=15.35049, realized_pnl=6.29)
    assert out["legacy_lot_regenerated"] is True
    assert any("UPDATE position_lots" in c[0] for c in conn.calls)
    upd = [c for c in conn.calls if c[0].startswith("UPDATE unified_positions")][0]
    assert 15.35049 in upd[1] and "quantity 15 -> 15.35049" in upd[1][-2]


def test_a_row_with_real_fills_is_corrected_through_its_fills(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _correct(monkeypatch, ["MANUAL"], entry_price=0.46)
    assert "correct the fills" in e.value.detail


def test_a_correction_with_no_figure_is_refused(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _correct(monkeypatch, [])
    assert "no figure" in e.value.detail


# --- the endpoints exist, in the right order ---------------------------------------------------
def test_preview_and_with_legs_are_routes():
    from api import unified_positions as U
    paths = {r.path for r in U.router.routes}
    assert "/v2/positions/legs/preview" in paths and "/v2/positions/with-legs" in paths


def test_with_legs_writes_row_legs_lot_and_outcome_in_one_transaction():
    from api import unified_positions as U
    src = inspect.getsource(U.create_position_with_legs)
    for table in ("INSERT INTO unified_positions", "INSERT INTO position_legs",
                  "INSERT INTO position_lots", "INSERT INTO position_legs_migration"):
        assert table in src
    assert "async with conn.transaction():" in src
    assert "basis_incomplete_reason" in src, "an unknown entry is marked, not invented"
