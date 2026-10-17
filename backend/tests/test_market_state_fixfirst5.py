"""fix-first #5 — `market_state` from the MA stack and the ADX band.

WHY IT IS A COMPOSITION AND NOT NEW ARITHMETIC. Both inputs already have one author each, and
the point of the field is that the pairing stops being re-derived by eye. The live book carries
`bucket_reason` prose like "with-trend (above all four MAs, ADX 23.2)" — a classification done
by hand, per row, in a free-text column.

    indicators/moving_averages.py   stack_state: bullish (20>50>120>200) / bearish /
                                    transitioning / None
    read_only/chart_indicators.py   adx.trend_strength: trending (>=25) / developing (>=20) /
                                    ranging (<20) / None

THE RULE is strategy-lab §6.2, the one written-down definition in the repo:

    ADX < 20                            -> range
    ADX >= 25 AND the stack is aligned  -> trend
    anything else                       -> transition

The alignment clause is what makes this more than an ADX band: an ADX of 30 across a tangled
stack is a transition, because `transitioning` is the stack saying it is not aligned.

A DISAGREEMENT THIS FIELD SURFACES, asserted below so it cannot be lost. The live GUSH row
(`POS_GUSH_20261016_165128`) reads "with-trend (above all four MAs, ADX 23.2), eligible". §6.2
calls ADX 23.2 a TRANSITION — 23.2 is below the 25 floor. So the served field contradicts a
classification already written into a live row, and one of the two is wrong: either the floor is
not right for bucket eligibility, or "with-trend" there was a judgement that does not follow
§6.2. Not resolved here; pinned so the contradiction is visible rather than discovered later.
"""
from __future__ import annotations

import io
import os

import pytest

from services.read_only.chart_indicators import (MARKET_STATE_RANGE_BELOW,
                                                 MARKET_STATE_TREND_AT, market_state)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ABOVE_ALL = {"20": "above", "50": "above", "120": "above", "200": "above"}
BELOW_ALL = {"20": "below", "50": "below", "120": "below", "200": "below"}
MIXED = {"20": "above", "50": "below", "120": "above", "200": "below"}


# ── the three states ─────────────────────────────────────────────────────────

def test_below_the_range_floor_is_a_range():
    r = market_state(14.0, "bullish", ABOVE_ALL)
    assert r["state"] == "range"
    assert "below 20" in r["basis"]


def test_a_range_has_no_direction():
    """A range is not going anywhere, so a direction would be a claim the state denies."""
    assert market_state(14.0, "bullish", ABOVE_ALL)["direction"] is None


def test_at_or_above_the_trend_floor_with_an_aligned_stack_is_a_trend():
    r = market_state(30.0, "bullish", ABOVE_ALL)
    assert r["state"] == "trend"
    assert r["direction"] == "up"


def test_a_bearish_aligned_stack_trends_DOWN():
    r = market_state(30.0, "bearish", BELOW_ALL)
    assert r["state"] == "trend"
    assert r["direction"] == "down"


def test_a_STRONG_ADX_ACROSS_A_TANGLED_STACK_IS_A_TRANSITION():
    """THE CLAUSE THAT MAKES THIS MORE THAN AN ADX BAND. `transitioning` is the stack telling
    you it is not aligned, so a high ADX over it is movement without a trend. Reading the ADX
    alone would call this a trend and be wrong in the most confident direction."""
    r = market_state(30.0, "transitioning", MIXED)
    assert r["state"] == "transition"
    assert r["direction"] is None
    assert "not a trend" in r["basis"]


def test_between_the_floors_is_a_transition():
    r = market_state(22.0, "bearish", MIXED)
    assert r["state"] == "transition"
    assert "between" in r["basis"]


def test_a_transition_still_reports_the_stacks_direction_when_it_is_aligned():
    """"Aligned bearish, but ADX only 22" is a different thing to know from "tangled stack",
    and the state alone cannot say which."""
    r = market_state(22.0, "bearish", MIXED)
    assert r["direction"] == "down"
    assert market_state(22.0, "transitioning", MIXED)["direction"] is None


# ── the boundaries, both of them ─────────────────────────────────────────────

def test_exactly_the_range_floor_is_NOT_a_range():
    """The rule is `< 20`, so 20 itself is not a range. A boundary belongs to one side and the
    test says which."""
    assert market_state(MARKET_STATE_RANGE_BELOW, "bullish", None)["state"] == "transition"


def test_exactly_the_trend_floor_IS_a_trend():
    """The rule is `>= 25`."""
    assert market_state(MARKET_STATE_TREND_AT, "bullish", None)["state"] == "trend"


def test_just_under_each_floor():
    assert market_state(19.9, "bullish", None)["state"] == "range"
    assert market_state(24.9, "bullish", None)["state"] == "transition"


# ── no input, no state ───────────────────────────────────────────────────────

@pytest.mark.parametrize("adx,stack,named", [
    (None, "bullish", "adx"),
    (30.0, None, "stack_state"),
    (None, None, "adx"),
])
def test_a_missing_input_gives_no_state_and_names_what_was_missing(adx, stack, named):
    """Defaulting to "transition" would read as a measurement of an unmeasured market, and
    would be indistinguishable from a genuine transition."""
    r = market_state(adx, stack, None)
    assert r["state"] is None
    assert r["direction"] is None
    assert named in r["reason"]


def test_both_missing_names_both():
    r = market_state(None, None, None)
    assert "adx" in r["reason"] and "stack_state" in r["reason"]


def test_an_absent_state_is_None_and_not_the_string_unknown():
    """A sentinel string would pass every truthiness check a reader writes and sort among the
    real states."""
    r = market_state(None, None, None)
    assert r["state"] is None
    assert r["state"] is not False and r["state"] != "unknown"


# ── the price-vs summary, reported beside and never folded in ────────────────

@pytest.mark.parametrize("pv,want", [
    (ABOVE_ALL, "above"), (BELOW_ALL, "below"), (MIXED, "mixed"),
    ({"20": "above", "50": None}, None), (None, None), ({}, None),
])
def test_price_vs_all_summarises_every_MA_or_refuses(pv, want):
    """"Above all four MAs" is the phrase the book's own notes use, so it is served — but it is
    NOT part of the state, which is the §6.2 rule and nothing else. One unreadable MA makes the
    summary None rather than "mixed", because "mixed" is a measurement."""
    assert market_state(30.0, "bullish", pv)["price_vs_all"] == want


def test_price_vs_does_not_change_the_state():
    """The §6.2 rule reads the stack ORDER and the ADX. Where price sits is context."""
    for pv in (ABOVE_ALL, BELOW_ALL, MIXED, None):
        assert market_state(30.0, "bullish", pv)["state"] == "trend"


# ── the thresholds are the ones already published ────────────────────────────

def test_the_floors_match_the_adx_bands_this_module_already_serves():
    """Two sets of thresholds for one question is how two surfaces come to disagree about the
    same tape. `trend_strength` uses 25 and 20; so does this."""
    src = io.open(os.path.join(BACKEND, "services", "read_only", "chart_indicators.py"),
                  encoding="utf-8").read()
    assert "elif adx_val >= 25:" in src
    assert "elif adx_val >= 20:" in src
    assert MARKET_STATE_TREND_AT == 25.0
    assert MARKET_STATE_RANGE_BELOW == 20.0


def test_the_state_is_served_on_the_payload_with_a_warning_when_undecidable():
    """`warnings` is how every other missing indicator here is surfaced, so an undecidable
    state goes in the same place rather than being left for a reader to notice."""
    src = io.open(os.path.join(BACKEND, "services", "read_only", "chart_indicators.py"),
                  encoding="utf-8").read()
    assert '"market_state": _ms,' in src
    assert 'warnings.append("market_state null' in src


# ── the disagreement with a live row ─────────────────────────────────────────

def test_IT_CONTRADICTS_A_LIVE_ROWS_OWN_CLASSIFICATION():
    """PINNED SO IT CANNOT BE LOST. The live GUSH row reads "with-trend (above all four MAs,
    ADX 23.2), eligible". §6.2 calls 23.2 a TRANSITION, because it is below the 25 floor.

    One of the two is wrong — either the floor is not right for bucket eligibility, or that
    "with-trend" was a judgement that does not follow §6.2. This test does not resolve it; it
    makes the contradiction a fact in the suite rather than something found later by a reader
    comparing a served field against a row's prose.
    """
    r = market_state(23.2, "bullish", ABOVE_ALL)
    assert r["state"] == "transition", (
        "if this becomes 'trend', the floor was changed -- re-read fix-first #5 and the GUSH "
        "row's bucket_reason together before accepting it")
    assert r["direction"] == "up", "the stack IS aligned; it is the ADX that falls short"
