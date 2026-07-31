"""DEF-GREEKS-ZERO — coverage-aware greeks aggregation.

The core regression, in one sentence: a two-leg position with one leg unpriced
must not report the single-leg sum as the portfolio total. Before the fix,
`(g.get("delta") or 0)` made an unknown leg a zero-contribution leg, so a partial
sum was presented as a whole-portfolio number with no indication. An understated
delta tells the operator he carries LESS risk than he does.
"""
import asyncio

import pytest

from integrations import uw_api


def _contract(strike, expiry, ctype, greeks):
    """A chain entry shaped like the UW snapshot `_find_contract` expects."""
    c = {
        "details": {
            "contract_type": ctype,
            "expiration_date": expiry,
            "strike_price": strike,
        },
        "underlying_asset": {"price": 100.0},
    }
    if greeks is not None:
        c["greeks"] = greeks
    return c


FULL = {"delta": 0.50, "gamma": 0.02, "theta": -0.10, "vega": 0.30}
EXPIRY = "2026-09-18"


def _summary(chain, positions, monkeypatch):
    async def fake_snapshot(_underlying):
        return chain
    monkeypatch.setattr(uw_api, "get_options_snapshot", fake_snapshot)
    return asyncio.run(uw_api.get_ticker_greeks_summary("TEST", positions))


SPREAD = [{
    "structure": "call_debit_spread",
    "quantity": 1,
    "expiry": EXPIRY,
    "long_strike": 100,
    "short_strike": 110,
}]


def test_core_regression_partial_coverage_is_not_reported_as_total(monkeypatch):
    """THE defect. Long leg priced, short leg has no greeks at all."""
    chain = [
        _contract(100, EXPIRY, "call", FULL),
        _contract(110, EXPIRY, "call", None),   # present in chain, greeks absent
    ]
    r = _summary(chain, SPREAD, monkeypatch)

    # The sum is a FLOOR built from one of two legs...
    assert r["legs_expected"] == 2
    assert r["legs_priced"] == 2          # both contracts found
    assert r["coverage"]["delta"]["priced"] == 1   # ...but only one carried delta
    # ...and it must NOT be advertised as complete.
    assert r["complete"] is False, "partial coverage must never report complete"
    # The old code returned 50.0 - 0 = 50.0 and called it the portfolio delta.
    # It is still 50.0, but it is now labelled a floor via coverage, not a total.
    assert r["net_delta"] == 50.0


def test_unknown_leg_does_not_subtract_zero(monkeypatch):
    """The short leg must not silently contribute 0 to the net."""
    both = [_contract(100, EXPIRY, "call", FULL), _contract(110, EXPIRY, "call", FULL)]
    r_full = _summary(both, SPREAD, monkeypatch)
    # Fully priced spread nets to zero delta (0.50 long - 0.50 short) * 1 * 100.
    assert r_full["net_delta"] == 0.0
    assert r_full["complete"] is True

    partial = [_contract(100, EXPIRY, "call", FULL), _contract(110, EXPIRY, "call", None)]
    r_part = _summary(partial, SPREAD, monkeypatch)
    # Same position, one leg unknown. If these two were indistinguishable the
    # operator could not tell a hedged book from a half-measured one.
    assert r_part["net_delta"] != r_full["net_delta"]
    assert r_part["complete"] is False


def test_flat_book_with_full_coverage_reports_zero_not_none(monkeypatch):
    """R2: zero is a FACT when it is measured. It must not read as unknown."""
    chain = [_contract(100, EXPIRY, "call", FULL), _contract(110, EXPIRY, "call", FULL)]
    r = _summary(chain, SPREAD, monkeypatch)
    assert r["net_delta"] == 0.0
    assert r["net_delta"] is not None
    assert r["complete"] is True


def test_no_legs_priced_reports_none_not_zero(monkeypatch):
    """Zero coverage is UNKNOWN. Never 0."""
    chain = [_contract(100, EXPIRY, "call", None), _contract(110, EXPIRY, "call", None)]
    r = _summary(chain, SPREAD, monkeypatch)
    for g in ("delta", "gamma", "theta", "vega"):
        assert r[f"net_{g}"] is None, f"{g} with no priced legs must be None, not 0"
    assert r["complete"] is False


def test_empty_chain_counts_legs_as_expected_not_invisible(monkeypatch):
    """An empty chain is zero coverage, not 'no answer'."""
    r = _summary([], SPREAD, monkeypatch)
    assert r is not None, "empty chain must still report coverage"
    assert r["legs_expected"] == 2
    assert r["legs_priced"] == 0
    assert r["net_delta"] is None
    assert r["complete"] is False


def test_option_missing_expiry_counts_as_uncovered_leg(monkeypatch):
    """A silently-skipped option used to make coverage look complete."""
    positions = [{
        "structure": "call_debit_spread",
        "quantity": 1,
        "expiry": None,           # unpriceable
        "long_strike": 100,
        "short_strike": 110,
    }]
    r = _summary([_contract(100, EXPIRY, "call", FULL)], positions, monkeypatch)
    assert r["legs_expected"] == 2, "an option we cannot price is still expected"
    assert r["legs_priced"] == 0
    assert r["complete"] is False


def test_equity_position_is_excluded_from_coverage(monkeypatch):
    """A stock has no greeks concept — it must not count as a coverage gap."""
    positions = [{"structure": "long_stock", "quantity": 100, "expiry": None, "long_strike": None}]
    r = _summary([], positions, monkeypatch)
    assert r["legs_expected"] == 0
    assert r["complete"] is False  # nothing measured, so nothing to claim


def test_every_greek_is_covered_not_just_delta(monkeypatch):
    """Spine addition (a): gamma/theta/vega carried the identical coercion."""
    partial_greeks = {"delta": 0.5, "gamma": None, "theta": -0.1, "vega": None}
    chain = [_contract(100, EXPIRY, "call", partial_greeks)]
    positions = [{"structure": "long_call", "quantity": 1, "expiry": EXPIRY, "long_strike": 100}]
    r = _summary(chain, positions, monkeypatch)
    assert r["net_delta"] == 50.0
    assert r["net_theta"] == -10.0
    assert r["net_gamma"] is None, "gamma absent must be None, not 0"
    assert r["net_vega"] is None, "vega absent must be None, not 0"
    assert r["complete"] is False
