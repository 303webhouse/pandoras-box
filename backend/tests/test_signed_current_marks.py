"""R-IV.463(a)(c) -- a mark is current, and it is signed.

FAIL-FIRST against the pre-2026-09-19 tree: a mark took a last trade of any age (the root of legs
priced at different moments), and the legs path stored abs() of the net, so a set that crossed
zero read as the same magnitude on the wrong side.
"""
from __future__ import annotations

import asyncio
import inspect
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from utils.options_math import compute_mark, compute_mid  # noqa: E402
from services.leg_mark import entry_orientation, mark_from_legs  # noqa: E402

E = "2026-10-16"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def C(bid=None, ask=None, last=None, volume=0, strike=100.0, kind="put"):
    return {"details": {"contract_type": kind, "strike_price": strike, "expiration_date": E},
            "last_quote": {"bid": bid, "ask": ask}, "last_trade": {"price": last},
            "day": {"close": last, "volume": volume, "vwap": None}}


# --- (a) what a mark may use ------------------------------------------------------------------
def test_a_two_sided_quote_marks_at_the_mid():
    assert compute_mark(C(0.10, 0.20)) == (0.15, "two-sided quote")


def test_a_trade_this_session_marks_when_the_quote_is_one_sided():
    assert compute_mark(C(0, 0.04, last=0.02, volume=501)) == (0.02, "trade this session")


def test_an_old_trade_is_not_a_mark_but_is_still_a_chain_mid():
    """SPCX 55P at 06:14 UTC 09-19: bid 0, ask 0.02, volume 0. The chain still shows a price;
    a mark does not take it."""
    c = C(0, 0.02, last=0.105, volume=0)
    value, why = compute_mark(c)
    assert value is None and "no trade this session" in why and "volume 0" in why
    assert compute_mid(c) == 0.105, "chains and greeks keep the wider fallback"


def test_the_mark_job_asks_for_marks_and_the_other_callers_do_not():
    from api import unified_positions as U
    from api import market_data as M
    from jobs import b2_options_resolver as R
    mtm = inspect.getsource(U.run_mark_to_market)
    assert mtm.count("for_mark=True") == 4, "legs, legacy JSONB legs, two-strike, single leg"
    for mod in (M, R):
        assert "for_mark=True" not in inspect.getsource(mod)


def test_multi_leg_value_names_every_leg_it_cannot_mark(monkeypatch):
    from integrations import uw_api as W
    chain = [C(0, 0.04, last=0.02, volume=501, strike=360.0),
             C(0, 0.04, last=0.03, volume=0, strike=350.0)]
    monkeypatch.setattr(W, "get_options_snapshot", lambda *a, **k: _async(chain))
    legs = [{"action": "BUY", "option_type": "put", "strike": 360, "quantity": 1},
            {"action": "SELL", "option_type": "put", "strike": 350, "quantity": 1},
            {"action": "SELL", "option_type": "put", "strike": 340, "quantity": 1}]
    out = _run(W.get_multi_leg_value("QQQ", legs, E, for_mark=True))
    assert out["net_mark"] is None
    assert any(u.startswith("350P: no two-sided quote") for u in out["unpriced"])
    assert any(u.startswith("340P: not in the vendor's chain") for u in out["unpriced"])
    assert _run(W.get_multi_leg_value("QQQ", legs[:2], E)) is not None, "a lookup still prices"


async def _async(v):
    return v


def test_the_reason_reaches_the_row():
    async def pricer(tk, group, expiry):
        return {"net_mark": None, "unpriced": ["55P: no two-sided quote (bid 0, ask 0.02) and "
                                                "no trade this session (volume 0)"]}
    legs = [{"option_type": "PUT", "side": "LONG", "strike": 60, "qty": 3, "expiry": E},
            {"option_type": "PUT", "side": "SHORT", "strike": 55, "qty": 3, "expiry": E}]
    out = _run(mark_from_legs("SPCX", legs, 3, "put_debit_spread", pricer))
    assert out["ok"] is False and "55P: no two-sided quote" in out["reason"]


# --- (c) the side, and the sign ---------------------------------------------------------------
def L(t, s, k, q=1, p=None, e=E):
    return {"option_type": t, "side": s, "strike": k, "qty": q, "price": p, "expiry": e}


@pytest.mark.parametrize("legs,side,expected", [
    ([L("PUT", "LONG", 100), L("PUT", "SHORT", 90)], None, (1, "payoff")),       # debit vertical
    ([L("PUT", "SHORT", 100), L("PUT", "LONG", 90)], None, (-1, "payoff")),      # credit vertical
    ([L("PUT", "LONG", 100), L("PUT", "SHORT", 90), L("PUT", "LONG", 50)], None, (1, "payoff")),
    # a 1x2 call ratio can be worth either sign: its side comes from the fills...
    ([L("CALL", "LONG", 100, 1, 3.0), L("CALL", "SHORT", 110, 2, 1.0)], None, (1, "entry prices")),
    ([L("CALL", "LONG", 100, 1, 1.0), L("CALL", "SHORT", 110, 2, 1.5)], None, (-1, "entry prices")),
    # ...or from the side recorded at entry...
    ([L("CALL", "LONG", 100, 1), L("CALL", "SHORT", 110, 2)], "CREDIT", (-1, "entry side")),
    # ...and with neither, it is not guessed
    ([L("CALL", "LONG", 100, 1), L("CALL", "SHORT", 110, 2)], None, (None, "unrecorded")),
])
def test_the_side_follows_from_the_legs_then_the_fills_then_the_record(legs, side, expected):
    assert entry_orientation(legs, side) == expected


def test_a_payoff_that_cannot_change_sign_overrides_a_recorded_side():
    legs = [L("PUT", "LONG", 100), L("PUT", "SHORT", 90)]
    assert entry_orientation(legs, "CREDIT") == (1, "payoff")


def test_pnl_reads_the_signed_mark_against_the_side():
    from api.unified_positions import _compute_unrealized_pnl as P
    # a credit received at 1.00 that has crossed zero and is now worth +0.30 to the holder:
    # the mark in the entry's orientation is -0.30, and the position is up 1.30
    assert P(1.00, -0.30, 1, "custom", orientation=-1) == 130.0
    assert P(1.00, 0.40, 1, "custom", orientation=-1) == 60.0      # cost to close 0.40
    assert P(1.00, 1.50, 2, "custom", orientation=1) == 100.0      # debit, up 0.50 x 2
    # the name rule is unchanged for rows without legs
    assert P(1.00, 0.40, 1, "put_credit_spread") == 60.0
    assert P(1.00, 1.40, 1, "iron_condor", direction="LONG") == 40.0


def test_abs_is_retired_from_the_mark_path():
    from api import unified_positions as U
    src = inspect.getsource(U.run_mark_to_market)
    assert 'abs(float(outcome["net_mark"]))' not in src
    assert 'abs(result["net_mark"])' not in src
    assert "orientation * float(outcome[\"net_mark\"])" in src


def test_a_side_that_is_not_recorded_is_unavailable_not_guessed():
    from api import unified_positions as U
    src = inspect.getsource(U.run_mark_to_market)
    assert "which way this position was entered is not recorded" in src


def test_with_legs_refuses_a_net_whose_sign_contradicts_the_payoff(monkeypatch):
    from api import unified_positions as U
    req = U.WithLegsRequest(ticker="QQQ", account="ROBINHOOD", quantity=1, net_price=-0.80,
                            legs=[U.EntryLeg(option_type="PUT", side="LONG", strike=100,
                                             expiry=E),
                                  U.EntryLeg(option_type="PUT", side="SHORT", strike=90,
                                             expiry=E)])
    monkeypatch.setattr(U, "get_postgres_client", lambda: (_ for _ in ()).throw(
        AssertionError("must refuse before writing")))
    with pytest.raises(HTTPException) as e:
        _run(U.create_position_with_legs(req))
    assert e.value.status_code == 400 and "only be entered for a debit" in e.value.detail


def test_with_legs_records_the_side():
    from api import unified_positions as U
    src = inspect.getsource(U.create_position_with_legs)
    assert "entry_side" in src and "incomplete, req.notes, entry_side, row_source" in src
