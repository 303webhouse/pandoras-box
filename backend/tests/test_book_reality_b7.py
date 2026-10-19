"""B7's grid: the arithmetic, the exclusions, and the flag.

THESE ARE THE MOST HARMFUL NUMBERS IN THE QUEUE, because they appear as dollar figures about
Nick's own book. So the tests here check the two things a plausible-looking wrong grid would
get wrong: the SIGN (does a long put gain when SPY falls?) and the SCALE (the 100x contract
multiplier, and the beta).

The stock row is checked against arithmetic done by hand, which is also one of the three rows
QUERY recomputes under R-IV.1239(e)5.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from api import book_reality as api
from models import book_reality_b7 as br

TODAY = _dt.date(2026, 10, 19)
R = 0.0428


def _spread(**kw):
    base = {"ticker": "MSFT", "account": "robinhood", "structure": "put_debit_spread",
            "quantity": 2, "long_strike": 400.0, "short_strike": 390.0,
            "expiry": _dt.date(2026, 11, 20), "current_price": 0.09}
    base.update(kw)
    return base


def _stock(**kw):
    base = {"ticker": "SQQQ", "account": "fidelity_roth", "structure": "stock",
            "quantity": 20, "current_price": 38.9}
    base.update(kw)
    return base


# ── 1. the flag ───────────────────────────────────────────────────────────

def test_THE_FLAG_SHIPS_OFF():
    """R-IV.1239(e)4. The constant is the shipped state, and it is a CONSTANT rather than an
    env var: the surface coming up because a deploy variable was set is not the same event as
    SPINE having ruled on QUERY's check."""
    assert api.B7_ENABLED is False


# ── 2. scale: the 100x multiplier and the beta ────────────────────────────

def test_THE_STOCK_ROW_MATCHES_ARITHMETIC_DONE_BY_HAND():
    """20 shares of SQQQ at 38.90 with an adjusted beta of -2.9, SPY -10%:
        20 * 38.90 * (-2.9 * -0.10) = +225.62
    This is one of the three rows QUERY recomputes (R-IV.1239(e)5), so it is pinned here to the
    cent of the hand figure rather than to the code's own output."""
    got = br.position_cells(_stock(), spot=38.9, beta=-2.9, r=R, today=TODAY)
    assert got["cells"][0] is not None
    assert abs(got["cells"][0] - 225.62) < 0.01, got["cells"][0]
    # And the +5% column is the mirror: 20 * 38.90 * (-2.9 * 0.05) = -112.81
    assert abs(got["cells"][4] - (-112.81)) < 0.01, got["cells"][4]


def test_AN_OPTION_CELL_CARRIES_THE_CONTRACT_MULTIPLIER():
    """A missing x100 is the largest single error available in this file: it would understate
    every option row by two orders of magnitude and the grid would still look plausible."""
    assert br.CONTRACT_MULTIPLIER == 100
    one = br.position_cells(_spread(quantity=1), spot=520.0, beta=1.0, r=R, today=TODAY)
    two = br.position_cells(_spread(quantity=2), spot=520.0, beta=1.0, r=R, today=TODAY)
    assert abs(two["cells"][0] - 2 * one["cells"][0]) < 1e-6
    # A 10% SPY fall on a beta-1 name moves MSFT to 468. The spread is worth more there than
    # at 520, so the cell is a GAIN of at least a dollar -- not cents, which is what a missing
    # multiplier would produce.
    assert one["cells"][0] > 1.0, one["cells"][0]


def test_BETA_SCALES_THE_MOVE_AND_IS_NEVER_DEFAULTED():
    """No beta means NO CELL. A beta defaulted to 1.0 would model SQQQ as SPY -- wrong by about
    threefold and in the wrong direction."""
    # approx, not ==: -10.0/100 * -3.0 is 0.30000000000000004 in binary floating point, and
    # a test that demands exact equality on a product of decimals is testing IEEE 754.
    assert br.underlying_move(-10.0, 2.0) == pytest.approx(-0.2)
    assert br.underlying_move(-10.0, -3.0) == pytest.approx(0.3)
    assert br.underlying_move(-10.0, None) is None
    no_beta = br.position_cells(_stock(), spot=38.9, beta=None, r=R, today=TODAY)
    assert no_beta["cells"] is None and "no beta" in no_beta["reason"]


# ── 3. sign: the direction a wrong grid would get wrong ───────────────────

def test_A_LONG_PUT_SPREAD_GAINS_WHEN_SPY_FALLS():
    got = br.position_cells(_spread(), spot=520.0, beta=1.05, r=R, today=TODAY)
    cells = got["cells"]
    assert cells[0] > cells[1] > cells[2] > 0, cells      # -10, -5, -3 all gains, decreasing
    assert cells[3] < 0 and cells[4] < cells[3], cells    # +3, +5 losses, increasing


def test_AN_INVERSE_ETF_GAINS_WHEN_SPY_FALLS():
    """The sign that matters most: a long SQQQ holding is short the market."""
    got = br.position_cells(_stock(), spot=38.9, beta=-2.9, r=R, today=TODAY)
    assert got["cells"][0] > 0 and got["cells"][4] < 0


# ── 4. the implied-vol solve ──────────────────────────────────────────────

def test_THE_VOL_COMES_FROM_THE_POSITIONS_OWN_MARK():
    """Not from a vendor IV field -- a plan-gated `implied_volatility` has already arrived as
    null in this repo. For a spread the solve finds ONE shared vol, which is all a net mark can
    identify, and that is stated rather than implied."""
    iv, basis = br.solve_iv(_spread(), spot=520.0, r=R, today=TODAY)
    assert iv is not None and 0.05 < iv < 3.0, (iv, basis)
    assert "own mark" in basis
    # Re-pricing at the solved vol reproduces the mark, which is what "solved" has to mean.
    v, _ = br.price_structure("put_debit_spread", spot=520.0, long_strike=400.0,
                              short_strike=390.0, T=br.years_to_expiry(
                                  _dt.date(2026, 11, 20), TODAY), r=R, iv=iv)
    assert abs(v / br.CONTRACT_MULTIPLIER - 0.09) < 1e-3


def test_NO_MARK_MEANS_NO_CELL_RATHER_THAN_A_GUESSED_VOL():
    iv, basis = br.solve_iv(_spread(current_price=None), spot=520.0, r=R, today=TODAY)
    assert iv is None and "no current mark" in basis
    got = br.position_cells(_spread(current_price=None), spot=520.0, beta=1.0, r=R,
                            today=TODAY)
    assert got["cells"] is None and "no volatility" in got["reason"]


def test_SHARES_NEED_NO_VOLATILITY():
    iv, basis = br.solve_iv(_stock(), spot=38.9, r=R, today=TODAY)
    assert iv is None and "need no volatility" in basis
    assert br.position_cells(_stock(), spot=38.9, beta=-2.9, r=R,
                             today=TODAY)["cells"] is not None


# ── 5. what is NOT modelled, and the total ────────────────────────────────

def test_A_COMPOSITE_IS_NOT_PRICED_AND_SAYS_WHY():
    """The book holds `put_debit_spread+long_put`. Its net mark cannot be split across legs, so
    no single vol identifies it -- the same reason TA-168 holds composites in the B2 cut."""
    v, basis = br.price_structure("put_debit_spread+long_put", spot=100.0, long_strike=100.0,
                                  short_strike=90.0, T=0.1, r=R, iv=0.3)
    assert v is None and "COMPOSITE" in basis


def test_AN_UNMODELLED_POSITION_IS_EXCLUDED_FROM_THE_TOTAL_AND_LISTED():
    """Treating it as zero would make the total read as complete. The row is named instead."""
    g = br.grid([_stock(), _spread(structure="put_debit_spread+long_put")],
                spots={"SQQQ": 38.9, "MSFT": 520.0},
                betas={"SQQQ": -2.9, "MSFT": 1.05}, r=R, today=TODAY)
    assert g["modelled_positions"] == 1
    assert [n["ticker"] for n in g["not_modelled"]] == ["MSFT"]
    assert "COMPOSITE" in g["not_modelled"][0]["reason"]
    # The total equals the one modelled row, not the two.
    roth = [r for r in g["rows"] if r["key"] == "ROTH"][0]
    total = [r for r in g["rows"] if r["total"]][0]
    assert roth["cells"] == total["cells"]


def test_AN_ACCOUNT_OUTSIDE_THE_THREE_IS_NOT_FOLDED_IN():
    """Exact-name identity, never a prefix: a prefix match would fold a future
    `fidelity_roth_ira` into ROTH silently, and parked money is held out by name."""
    assert br.account_row("ROBINHOOD") == "RH"
    assert br.account_row("fidelity_401a") == "401A"
    assert br.account_row("fidelity_roth_ira") is None
    assert br.account_row(None) is None
    g = br.grid([_stock(account="ahrp_403b")], spots={"SQQQ": 38.9}, betas={"SQQQ": -2.9},
                r=R, today=TODAY)
    assert g["modelled_positions"] == 0
    assert "not one of the three book accounts" in g["not_modelled"][0]["reason"]


# ── 6. the worst cell, and the labels ─────────────────────────────────────

def test_THE_WORST_CELL_IS_AN_ACCOUNT_CELL_NEVER_THE_TOTAL():
    """The total nets accounts and would hide which one is exposed, which is the whole point of
    naming a worst cell."""
    g = br.grid([_stock(), _spread()], spots={"SQQQ": 38.9, "MSFT": 520.0},
                betas={"SQQQ": -2.9, "MSFT": 1.05}, r=R, today=TODAY)
    assert g["worst"]["where"] in ("ROTH @ SPY +5%", "RH @ SPY +5%", "ROTH @ SPY +3%",
                                  "RH @ SPY +3%")
    assert "nets accounts" in g["worst"]["basis"]
    assert g["worst"]["value"].startswith("-$")


def test_EVERY_FIGURE_IS_LABELLED_MODEL_ESTIMATE_AND_THE_VOL_MODE_IS_ON_SCREEN():
    """R-IV.1239(e)2 and (e)3. And the mode names the absent one: the mock had a "VOL REACTS"
    toggle, and a toggle that does nothing is worse than no toggle."""
    g = br.grid([_stock()], spots={"SQQQ": 38.9}, betas={"SQQQ": -2.9}, r=R, today=TODAY)
    assert g["label"] == "model estimate"
    assert "model estimate" in g["caption"]
    assert g["vol_mode"] == "VOL HELD (sticky-strike)"
    assert "VOL REACTS" in g["vol_mode_basis"] and "not implemented" in g["vol_mode_basis"]
    assert "UNDERSTATES a long put" in g["vol_mode_basis"]


def test_THE_COLUMNS_ARE_THE_RULED_SCENARIOS():
    assert br.SCENARIOS == (-10.0, -5.0, -3.0, 3.0, 5.0)
    g = br.grid([], spots={}, betas={}, r=R, today=TODAY)
    assert g["columns"] == ["-10%", "-5%", "-3%", "+3%", "+5%"]
    assert [r["key"] for r in g["rows"]] == ["RH", "ROTH", "401A", "TOTAL"]
