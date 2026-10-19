"""`bs_price` and `implied_vol` against PUBLISHED reference values. R-IV.1239(e)1.

The ruling asks for published references rather than self-consistency, and the reason is
exactly right: a pricer tested only against its own output is tested against its own mistakes.
The anchor here is Hull's worked example, which has appeared in every edition of *Options,
Futures and Other Derivatives* for thirty years:

    S = 42, K = 40, r = 10%, sigma = 20%, T = 0.5  ->  call 4.76, put 0.81

Everything else in this file is either a second published identity (put-call parity, which is
arbitrage rather than a model), a boundary a price must satisfy on pain of free money, or a
round trip through the solver.
"""
from __future__ import annotations

import math

import pytest

from utils.options_math import bs_price, implied_vol


# ── 1. the published reference ────────────────────────────────────────────

def test_HULLS_WORKED_EXAMPLE():
    """S=42, K=40, r=10%, sigma=20%, T=0.5 -> call 4.76, put 0.81.

    To two decimals, which is the precision the textbook states them to. Tightening this test
    beyond the published precision would be asserting my own arithmetic, not the reference.
    """
    call = bs_price(42.0, 40.0, 0.5, 0.10, 0.20, "call")
    put = bs_price(42.0, 40.0, 0.5, 0.10, 0.20, "put")
    assert call is not None and put is not None
    assert round(call, 2) == 4.76, call
    assert round(put, 2) == 0.81, put


def test_PUT_CALL_PARITY_HOLDS_AS_AN_IDENTITY():
    """C - P = S - K*exp(-rT). This is ARBITRAGE, not a model: if the pricer breaks it, the
    pricer is wrong whatever the model says. Checked across a grid rather than one point."""
    for S in (80.0, 100.0, 120.0):
        for K in (90.0, 100.0, 110.0):
            for T in (0.05, 0.5, 2.0):
                for sigma in (0.1, 0.3, 0.8):
                    c = bs_price(S, K, T, 0.04, sigma, "call")
                    p = bs_price(S, K, T, 0.04, sigma, "put")
                    assert c is not None and p is not None
                    lhs = c - p
                    rhs = S - K * math.exp(-0.04 * T)
                    assert abs(lhs - rhs) < 1e-8, (S, K, T, sigma, lhs, rhs)


# ── 2. boundaries a price cannot violate ──────────────────────────────────

def test_A_PRICE_IS_NEVER_BELOW_INTRINSIC_OR_ABOVE_THE_UNDERLYING():
    """Both bounds are free money if violated."""
    for S, K, T, sig in ((100.0, 60.0, 1.0, 0.3), (100.0, 140.0, 0.1, 0.9),
                         (50.0, 50.0, 2.0, 0.15)):
        c = bs_price(S, K, T, 0.04, sig, "call")
        p = bs_price(S, K, T, 0.04, sig, "put")
        assert c >= max(0.0, S - K * math.exp(-0.04 * T)) - 1e-9
        assert c <= S + 1e-9
        assert p >= max(0.0, K * math.exp(-0.04 * T) - S) - 1e-9
        assert p <= K + 1e-9


def test_AT_EXPIRY_THE_PRICE_IS_INTRINSIC_AND_NOT_NONE():
    """A position at expiry HAS a value. Returning None there would make the last day of every
    spread in the book unreadable, which is the day it matters most."""
    assert bs_price(105.0, 100.0, 0.0, 0.04, 0.3, "call") == 5.0
    assert bs_price(95.0, 100.0, 0.0, 0.04, 0.3, "call") == 0.0
    assert bs_price(95.0, 100.0, -1.0, 0.04, 0.3, "put") == 5.0
    assert bs_price(105.0, 100.0, 0.0, 0.04, None, "put") == 0.0, "no vol needed at expiry"


def test_MORE_VOL_IS_NEVER_WORTH_LESS():
    """Monotonic in vol, which is also what licences the solver's bisection."""
    prev = -1.0
    for sigma in (0.05, 0.1, 0.2, 0.4, 0.8, 1.6):
        v = bs_price(100.0, 100.0, 0.5, 0.04, sigma, "call")
        assert v > prev
        prev = v


def test_DEGENERATE_INPUTS_ARE_NONE_NOT_ZERO():
    """A zero price is a claim that the option is worthless. None is "not priceable"."""
    assert bs_price(0.0, 100.0, 1.0, 0.04, 0.3, "call") is None
    assert bs_price(100.0, 0.0, 1.0, 0.04, 0.3, "call") is None
    assert bs_price(100.0, 100.0, 1.0, 0.04, 0.0, "call") is None
    assert bs_price(100.0, 100.0, 1.0, 0.04, None, "call") is None
    assert bs_price(None, 100.0, 1.0, 0.04, 0.3, "call") is None


# ── 3. the solver ─────────────────────────────────────────────────────────

def test_THE_SOLVER_RECOVERS_THE_VOL_IT_WAS_PRICED_AT():
    """Round trip: price at a known vol, solve the price, get the vol back."""
    for sigma in (0.08, 0.17, 0.35, 0.90, 2.0):
        target = bs_price(100.0, 105.0, 0.4, 0.04, sigma, "call")
        got, basis = implied_vol(
            target, lambda iv: bs_price(100.0, 105.0, 0.4, 0.04, iv, "call"))
        assert got is not None, basis
        assert abs(got - sigma) < 1e-4, (sigma, got)


def test_THE_SOLVER_WORKS_ON_A_SPREAD_PRICED_AT_ONE_SHARED_VOL():
    """A spread has no per-leg mark in this book -- only its net price -- so a single shared
    vol is the only thing that net mark can identify. That is the assumption, and it is the
    reason the solver is generic in its pricer rather than hard-coded to one option."""
    def spread(iv):
        long_leg = bs_price(100.0, 100.0, 0.3, 0.04, iv, "put")
        short_leg = bs_price(100.0, 90.0, 0.3, 0.04, iv, "put")
        if long_leg is None or short_leg is None:
            return None
        return long_leg - short_leg

    target = spread(0.28)
    got, basis = implied_vol(target, spread)
    assert got is not None and abs(got - 0.28) < 1e-3, (got, basis)


def test_A_MARK_OUTSIDE_THE_BRACKET_IS_UNSOLVABLE_AND_NOT_CLAMPED():
    """A vol clamped to the bracket's edge would then be used to reprice the position and would
    look like a measurement. It is refused, with the range stated."""
    got, basis = implied_vol(
        99.0, lambda iv: bs_price(100.0, 105.0, 0.4, 0.04, iv, "call"))
    assert got is None
    assert "outside" in basis and "1%" in basis
    got2, basis2 = implied_vol(
        0.0, lambda iv: bs_price(100.0, 105.0, 0.4, 0.04, iv, "call"))
    assert got2 is None and "non-positive" in basis2


def test_THE_SOLVER_REPORTS_A_PRICER_THAT_CANNOT_VALUE_THE_STRUCTURE():
    got, basis = implied_vol(5.0, lambda iv: None)
    assert got is None and "could not value" in basis
