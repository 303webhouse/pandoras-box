"""B5's Fear Price: the unit trap, the headline, the curve's opposite sense, and the straddle.

THE UNIT TRAP IS THE REASON THIS FILE LEADS WITH IT. VIX is an annualised implied volatility in
percentage points; a 20-day standard deviation of daily returns is about 0.008. Subtracting the
second from the first produces a ~17-point "premium" every single day, in the right direction,
with a plausible-looking number -- the exact shape of a bug that survives for a month.
"""
from __future__ import annotations

import math

from models import fear_price_b5 as fp


def _closes(start: float, daily_sigma: float, n: int, seed: int = 5):
    """A price path with a KNOWN daily volatility, so realized vol has a right answer."""
    import random

    rnd = random.Random(seed)
    out, p = [start], start
    for _ in range(n):
        p *= math.exp(rnd.gauss(0, daily_sigma))
        out.append(p)
    return out


# ── 1. the units ──────────────────────────────────────────────────────────

def test_REALIZED_VOL_IS_ANNUALISED_AND_IN_PERCENTAGE_POINTS():
    """A 1%-a-day path is about 16 vol, not 0.01. The right unit is the whole reason the
    headline means anything."""
    rv = fp.realized_vol(_closes(100.0, 0.01, 400))
    assert rv is not None
    assert 10 < rv < 25, rv
    # And double the daily sigma roughly doubles it.
    rv2 = fp.realized_vol(_closes(100.0, 0.02, 400))
    assert 1.6 < rv2 / rv < 2.4


def test_THE_GAP_IS_A_DIFFERENCE_OF_LIKE_UNITS():
    """VIX 18 against a 16-vol tape is a 2-point premium, not a 17.99-point one."""
    g, basis = fp.gap(18.0, _closes(100.0, 0.01, 400))
    assert g is not None and -4 < g < 8, g
    assert "annualised realized" in basis


def test_TOO_SHORT_A_HISTORY_IS_NONE_WITH_A_REASON():
    """Not 0.0, and not a shorter window silently substituted."""
    assert fp.realized_vol([100.0, 101.0, 100.5]) is None
    g, basis = fp.gap(18.0, [100.0, 101.0])
    assert g is None and "fewer than 20 returns" in basis
    g2, basis2 = fp.gap(None, _closes(100.0, 0.01, 400))
    assert g2 is None and "no reading" in basis2


def test_A_HOLE_IS_A_MISSING_SESSION_NOT_A_FLAT_ONE():
    """A None carried forward as the previous close would add a zero return and understate
    realized vol -- which would overstate the premium, in the direction a vol seller likes."""
    with_hole = fp.returns([100.0, None, 102.0])
    assert len(with_hole) == 1
    assert with_hole[0] == math.log(102.0 / 100.0)


# ── 2. the headline describes, and says how many indices it used ──────────

def test_THE_HEADLINE_STATES_HOW_MANY_INDICES_IT_IS_DRAWN_FROM():
    """Three words from three indices and the same three words from one are different claims."""
    word, lean, basis = fp.headline([6.0, 4.0, 5.0])
    assert word == "PREMIUM RICH" and lean == "bear" and "3 of 3" in basis
    word2, _, basis2 = fp.headline([6.0, None, None])
    assert word2 == "PREMIUM RICH" and "1 of 3" in basis2


def test_FAIR_IS_ITS_OWN_ANSWER_AND_CHEAP_IS_NOT_BULLISH_BY_DEFAULT():
    assert fp.headline([0.5, -0.5, 0.0])[0] == "PREMIUM FAIR"
    assert fp.headline([0.5, -0.5, 0.0])[1] == "neutral"
    assert fp.headline([-6.0, -4.0])[0] == "PREMIUM CHEAP"


def test_NO_GAPS_MEANS_NO_HEADLINE():
    word, lean, basis = fp.headline([None, None, None])
    assert word is None and lean is None and "no implied-minus-realized gap" in basis


# ── 3. the VIX curve's INVERTED is the opposite sense to the yield curve ──

def test_INVERTED_ON_THE_VIX_CURVE_MEANS_THE_FRONT_IS_ABOVE_THE_BACK():
    """The opposite of the yield curve's INVERTED, and both tiles sit on the same screen. The
    basis states the direction so the word cannot be read against the wrong curve."""
    label, basis = fp.curve_label([24.0, 22.0, 20.0, 19.0])
    assert label == "INVERTED"
    assert "above" in basis and "near-term fear" in basis
    up, ubasis = fp.curve_label([16.0, 17.0, 18.5, 19.0])
    assert up == "UPWARD" and "below" in ubasis
    assert fp.curve_label([18.0, 18.2])[0] == "FLAT"


def test_ONE_TENOR_IS_NOT_A_CURVE():
    assert fp.curve_label([18.0, None, None, None]) == (
        None, "fewer than two tenors are available")


# ── 4. SKEW's percentile ──────────────────────────────────────────────────

def test_THE_PERCENTILE_IS_A_RANK_NOT_A_Z():
    """SKEW is bounded and skewed; a z-score would imply a symmetry the series does not have."""
    hist = list(range(100, 200))
    assert fp.percentile(150, hist) == 50
    assert fp.percentile(199, hist) == 99
    assert fp.percentile(100, hist) == 0


def test_TOO_LITTLE_HISTORY_CANNOT_BE_RANKED():
    assert fp.percentile(150, [100, 200]) is None
    assert fp.percentile(None, list(range(100))) is None


def test_THE_ORDINAL_READS_CORRECTLY_INCLUDING_THE_TEENS():
    assert fp.ordinal(81) == "81st"
    assert fp.ordinal(82) == "82nd"
    assert fp.ordinal(83) == "83rd"
    assert fp.ordinal(84) == "84th"
    assert fp.ordinal(11) == "11th", "not 11st"
    assert fp.ordinal(12) == "12th"
    assert fp.ordinal(13) == "13th"
    assert fp.ordinal(None) is None


# ── 5. the expected move ──────────────────────────────────────────────────

def test_THE_STRADDLE_IS_THE_EXPECTED_MOVE_IN_DOLLARS_AND_PERCENT():
    em = fp.expected_move(600.0, 9.0, 9.0, days=8, label="SPY MOVE → FOMC")
    assert em["available"] is True
    assert em["dollars"] == 18.0 and em["pct"] == 3.0
    assert em["value"] == "±$18 · ±3.0%"
    assert em["days"] == "8d"
    assert em["approx"] is True, "it is an approximation and must say so"
    assert "ATM straddle" in em["basis"]


def test_A_MISSING_LEG_IS_UNAVAILABLE_AND_NEVER_ONE_SIDE_DOUBLED():
    """Doubling the one leg that priced would read as a measurement. It is not one."""
    em = fp.expected_move(600.0, 9.0, None)
    assert em["available"] is False
    assert "ATM put" in em["reason"]
    assert "dollars" not in em
    em2 = fp.expected_move(None, 9.0, 9.0)
    assert em2["available"] is False and "spot" in em2["reason"]
