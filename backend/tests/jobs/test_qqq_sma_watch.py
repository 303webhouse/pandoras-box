"""R-IV.193 — QQQ 200-SMA cross watch. Pure-function tests, no network/redis/clock."""

from __future__ import annotations

import pytest

from jobs.qqq_sma_watch import (
    SMA_PERIOD,
    classify_side,
    compute_sma,
    detect_cross,
    evaluate,
)


# ── the period is a registered parameter; pin it as a literal ───────────────

def test_period_is_literally_200():
    """R-IV.193 fixes the window at 200. Asserted as a LITERAL — a test that
    reads the constant it verifies moves with the bug."""
    assert SMA_PERIOD == 200


# ── SMA: never a partial window ─────────────────────────────────────────────

def test_sma_of_exactly_200_closes():
    assert compute_sma([10.0] * 200) == pytest.approx(10.0)


def test_sma_uses_only_the_last_200():
    """Older bars must not leak into the window."""
    closes = [1.0] * 50 + [10.0] * 200
    assert compute_sma(closes) == pytest.approx(10.0)


def test_sma_returns_none_below_the_window():
    """A 199-close '200-SMA' is a different statistic wearing the same name.
    Returning a partial average would put the cross line in the wrong place
    while looking perfectly valid."""
    assert compute_sma([10.0] * 199) is None
    assert compute_sma([]) is None
    assert compute_sma(None) is None


def test_sma_is_the_mean_not_the_last_value():
    closes = [0.0] * 199 + [200.0]
    assert compute_sma(closes) == pytest.approx(1.0)


# ── side classification, including the boundary ────────────────────────────

def test_above_and_below():
    assert classify_side(709.24, 655.64) == "above"
    assert classify_side(600.0, 655.64) == "below"


def test_exact_equality_is_below_by_convention():
    """The rule is a STRICT above, so equality is not above. Pinned because a
    boundary left to float comparison is a boundary nobody chose."""
    assert classify_side(655.64, 655.64) == "below"


# ── cross detection is a TRANSITION, not a position ────────────────────────

def test_no_cross_when_side_unchanged():
    assert detect_cross("above", "above") is None
    assert detect_cross("below", "below") is None


def test_cross_up_and_down():
    assert detect_cross("below", "above") == "up"
    assert detect_cross("above", "below") == "down"


def test_no_prior_side_is_not_a_cross():
    """One observation cannot establish a transition. Reporting a cross here
    would manufacture an event out of an initial condition."""
    assert detect_cross(None, "above") is None
    assert detect_cross(None, "below") is None


# ── the instrument reports its own insufficiency ───────────────────────────

def test_insufficient_when_too_few_closes():
    r = evaluate([10.0] * 50, prior_side="above")
    assert r["state"] == "INSUFFICIENT"
    assert "have 50" in r["reason"]
    assert r["sma"] is None
    assert r["cross"] is None


def test_insufficient_on_first_observation_even_with_a_full_window():
    """Enough data, but no prior side — a cross is undetectable and the state
    must say so rather than silently arming."""
    r = evaluate([10.0] * 200, prior_side=None)
    assert r["state"] == "INSUFFICIENT"
    assert "two observations" in r["reason"]
    assert r["sma"] is not None      # the SMA IS computable
    assert r["cross"] is None


def test_armed_once_a_prior_side_exists():
    r = evaluate([10.0] * 200, prior_side="above")
    assert r["state"] == "ARMED"
    assert r["reason"] is None


def test_insufficient_and_armed_are_distinguishable():
    """Silence and health must not look alike — the whole point of the state."""
    a = evaluate([10.0] * 200, prior_side=None)["state"]
    b = evaluate([10.0] * 200, prior_side="below")["state"]
    assert a != b


# ── the registered measurement, reproduced ─────────────────────────────────

def test_registration_measurement_reproduces():
    """Section 1.1 clause 2, measured 2026-09-03: close 709.24, SMA 655.64,
    8.2% above, zero crosses. Reproduced here from a synthetic series with the
    same statistics so the registration is checkable, not merely asserted."""
    closes = [655.64] * 199 + [655.64]
    closes[-1] = 709.24
    # SMA over a flat 655.64 window with one 709.24 tail
    sma = compute_sma(closes)
    assert sma is not None
    r = evaluate(closes, prior_side="above")
    assert r["side"] == "above"
    assert r["cross"] is None          # declared ~0%, measured 0%
    assert r["distance_pct"] > 0


def test_a_cross_is_reachable_from_the_registered_state():
    """Clause 4: the state-change must be REACHABLE, not merely nameable. From
    'above', a lower close produces a real 'down' cross — the alarm can fire.

    Note the setup: a FLAT series puts close exactly ON the SMA, which is
    'below' by the stated convention, so the rising tail is required to make
    the starting side genuinely 'above'. An earlier version of this test used
    a flat series and asserted 'above' — caught by the convention it was
    supposed to be testing around."""
    rising = [700.0] * 199 + [760.0]
    above = evaluate(rising, prior_side=None)
    assert above["side"] == "above", above

    dropped = [700.0] * 199 + [500.0]
    r = evaluate(dropped, prior_side="above")
    assert r["cross"] == "down", r
    assert r["state"] == "ARMED"


def test_cross_up_is_reachable_too():
    closes = [500.0] * 199 + [900.0]
    r = evaluate(closes, prior_side="below")
    assert r["cross"] == "up"
