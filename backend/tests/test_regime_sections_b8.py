"""B8 sections 2-6 and 8: the FRED and ratio reads, and what each says when its source is absent.

R-IV.1246(b)'s standing rule is the spine of this file: A SOURCE THAT FAILS SHOWS
"unavailable", NEVER A MOCK VALUE. So most of what is tested here is the ABSENT case, because
that is the one that can lie.
"""
from __future__ import annotations

import datetime as _dt

from models import regime_sections_b8 as rs


def _pts(n, start=2.8, step=0.01):
    d0 = _dt.date(2026, 1, 1)
    return [(d0 + _dt.timedelta(days=i), start + i * step) for i in range(n)]


# ── section 2, credit ─────────────────────────────────────────────────────

def test_HY_OAS_IS_CONVERTED_TO_BASIS_POINTS_ONCE():
    """FRED publishes BAMLH0A0HYM2 in PERCENTAGE POINTS. A reader who assumes basis points is
    out by a factor of 100, so the conversion happens once, here, and the payload says so."""
    b = rs.credit_block([(_dt.date(2026, 10, 15), 3.23)] * 2)
    assert b["available"] is True
    assert b["bp"] == 323.0, b["bp"]
    assert "BASIS POINTS" in b["basis"]


def test_NO_HY_OBSERVATION_IS_UNAVAILABLE_WITH_A_REASON():
    b = rs.credit_block([])
    assert b["available"] is False and rs.HY_SERIES in b["reason"]
    assert "bp" not in b, "an unavailable section must not carry a figure"


def test_THE_CREDIT_WORD_AND_THE_CHANGE_ARE_BOTH_SHOWN():
    """Credit usually widens before equities break, so tight-but-widening is a different fact
    from tight-and-flat. The level gets the word; the change is reported beside it rather than
    folded into it."""
    b = rs.credit_block(_pts(40, start=2.0, step=0.05))
    assert b["word"] in ("WIDE", "CALM", "MIDDLING")
    assert b["change_20d_bp"] is not None and b["change_20d_bp"] > 0


# ── section 5, rates ──────────────────────────────────────────────────────

def test_THE_REAL_RATE_AND_THE_BREAKEVEN_ARE_NEVER_COMBINED():
    """A rising real rate is tightening; a rising breakeven is inflation expectation. Summing
    or averaging them would report two different pieces of news as one."""
    b = rs.rates_block({"DFII10": _pts(30), "T10YIE": _pts(30, start=2.3)})
    assert [r["key"] for r in b["rows"]] == ["real_10y", "breakeven_10y"]
    assert all(r["available"] for r in b["rows"])
    assert "different news" in b["basis"]


def test_MOVE_IS_UNAVAILABLE_WITH_ITS_REASON_NOT_A_SUBSTITUTE():
    b = rs.rates_block({"DFII10": _pts(30), "T10YIE": _pts(30)})
    assert b["move"]["available"] is False
    assert "no free source" in b["move"]["reason"]
    assert rs.rates_block({"DFII10": _pts(30)}, move=84.2)["move"]["value"] == 84.2


def test_ONE_DEAD_SERIES_LEAVES_THE_OTHER_INTACT():
    b = rs.rates_block({"DFII10": _pts(30), "T10YIE": []})
    assert b["available"] is True
    rows = {r["key"]: r for r in b["rows"]}
    assert rows["real_10y"]["available"] is True
    assert rows["breakeven_10y"]["available"] is False
    assert "T10YIE" in rows["breakeven_10y"]["reason"]


# ── section 4, leadership ─────────────────────────────────────────────────

def test_THE_LEGS_ARE_PAIRED_FROM_THE_NEWEST_END():
    """A missing session in one leg must not shift the other by a day, so both series are
    trimmed to their common length from the RIGHT."""
    r = rs.ratio_row("X/Y", [100.0 + i for i in range(40)], [100.0] * 25, "x leading")
    assert r["available"] is True
    assert r["change_pct"] == 16.8, r["change_pct"]


def test_TOO_FEW_PAIRED_SESSIONS_IS_UNAVAILABLE():
    r = rs.ratio_row("X/Y", [1.0] * 5, [1.0] * 5, "x leading")
    assert r["available"] is False and "paired sessions" in r["reason"]


def test_A_ZERO_DENOMINATOR_IS_REFUSED_NOT_DIVIDED():
    r = rs.ratio_row("X/Y", [1.0] * 30, [0.0] * 30, "x leading")
    assert r["available"] is False and "denominator" in r["reason"]


def test_EVERY_RATIO_SAYS_WHAT_RISING_MEANS():
    """Nobody should have to remember which way up COPPER/GOLD is."""
    for name, _a, _b, means in rs.LEADERSHIP:
        assert means and len(means) > 8, name
    closes = {s: [100.0 + i * 0.1 for i in range(40)]
              for _, a, b, _ in rs.LEADERSHIP for s in (a, b)}
    blk = rs.leadership_block(closes)
    assert blk["available"] is True
    assert all(r["rising_means"] for r in blk["rows"])


# ── section 3, Zweig as a proxy ───────────────────────────────────────────

def test_THE_ZWEIG_FLAG_IS_LABELLED_A_PROXY_AND_NAMES_BOTH_ERRORS():
    """R-IV.1246(b)7. The hub stores no advance/decline line, so sector breadth stands in --
    slower and broader, so it will MISS a fast thrust and can register one the real measure
    would not. The note states both directions of that error, not just the word "proxy"."""
    z = rs.zweig_proxy([35.0] * 5 + [65.0] * 6)
    assert z["fired"] is True
    assert "PROXY" in z["note"]
    assert "will miss a fast thrust" in z["note"]
    assert "can register one the real measure would not" in z["note"]
    assert "40" in z["note"] and "61.5" in z["note"]


def test_NOT_FIRED_AND_NOT_MEASURABLE_ARE_DIFFERENT_FACTS():
    """`fired: False` with history and `available: False` without it must not share a
    rendering: one is a reading, the other is the absence of one."""
    no_thrust = rs.zweig_proxy([50.0] * 12)
    assert no_thrust["available"] is True and no_thrust["fired"] is False
    assert "no thrust" in no_thrust["reason"]
    thin = rs.zweig_proxy([50.0] * 3)
    assert thin["available"] is False and thin["fired"] is None
    assert "fewer than" in thin["reason"]


# ── section 6, auction ────────────────────────────────────────────────────

def test_THE_AUCTION_SECTION_IS_UNAVAILABLE_WHEN_IT_HAS_NO_STATE():
    """MEASURED LIVE: the stored PYTHIA snapshot for SPY exists but carries no price, VAH or
    VAL. The first version returned `available: True` with a blank headline -- a section
    reporting itself present while having nothing to say."""
    b = rs.auction_block({"data": {"ib_high": 764.0}})
    assert b["available"] is False
    assert "VAH" in b["reason"]
    assert b["ib_high"] == 764.0, "whatever IS recorded stays visible"


def test_INSIDE_VALUE_IS_NEVER_COMPUTED_AGAINST_A_MISSING_EDGE():
    assert rs._where_in_value(763.0, None, 758.0, 761.0)[0] is None
    assert rs._where_in_value(763.0, 765.0, None, 761.0)[0] is None
    assert rs._where_in_value(None, 765.0, 758.0, 761.0)[0] is None
    where, basis = rs._where_in_value(763.0, 765.0, 758.0, 761.0)
    assert where == "INSIDE VALUE" and "above the POC" in basis
    assert rs._where_in_value(770.0, 765.0, 758.0, 761.0)[0] == "ABOVE VALUE"
    assert rs._where_in_value(750.0, 765.0, 758.0, 761.0)[0] == "BELOW VALUE"


def test_THE_BRACKET_COUNTER_IS_WITHHELD_WITH_ITS_REASON():
    """Board 8 asked for it greyed under 10 sessions. The hub keeps only the latest snapshot
    per ticker, so there is no count to grey -- and a figure built from one row would be a
    number about nothing."""
    b = rs.auction_block({"data": {"price": 763.0, "vah": 765.0, "val": 758.0}})
    assert b["available"] is True
    bc = b["bracket_counter"]
    assert bc["available"] is False
    assert "no per-session bracket history" in bc["reason"]


# ── section 8, lamps ──────────────────────────────────────────────────────

def test_AN_OVERLAY_LAMP_WITH_NO_FEED_IS_NOT_A_DARK_LAMP():
    """A dark lamp reads as "checked, nothing firing", which is a claim. The rules file's own
    sentence is quoted instead."""
    b = rs.lamps_block(kill_state=None)
    assert b["overlays"]["available"] is False
    assert b["overlays"]["reason"] == "overlays are a judgement input, not computed in v1"
    assert "would read as" in b["basis"]
    armed = rs.lamps_block(kill_state="armed")
    assert armed["kill"]["available"] is True and armed["kill"]["state"] == "armed"
