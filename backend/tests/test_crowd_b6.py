"""B6's Crowd gauge: three sources with three different standings, kept apart.

What is tested here is mostly the KEEPING APART. The numbers are percentile ranks, which are
simple; the harm would come from a proxy served under the label of the series it is standing in
for, a mock row voting in a live headline, or a weekly figure read as current.
"""
from __future__ import annotations

import datetime as _dt

from models import crowd_b6 as cb


# ── 1. the CFTC row ───────────────────────────────────────────────────────

def test_THE_CONTRACT_NAMES_ARE_THE_ONES_THE_PORTAL_PUBLISHES():
    """Read from CFTC's own API, not guessed. "NASDAQ MINI" is the E-mini Nasdaq-100;
    "NASDAQ-100 Consolidated" is a DIFFERENT series with different open interest (294,776 vs
    279,515 on 2026-10-13), so picking one is a choice and it is recorded."""
    assert cb.CFTC_CONTRACTS == {"ES": "E-MINI S&P 500", "NQ": "NASDAQ MINI"}


def test_A_ONE_SIDED_NET_IS_NOT_A_NET():
    assert cb.cftc_net(121404.0, 530130.0) == -408726.0
    assert cb.cftc_net(121404.0, None) is None
    assert cb.cftc_net(None, 530130.0) is None


def test_THE_FUTURES_ROW_CARRIES_ITS_OWN_AS_OF_AND_SAYS_IT_IS_STALE():
    """The TFF report is published Friday as of the prior Tuesday. A positioning figure read as
    current is a positioning figure read wrong, so the staleness is IN THE ROW, not in a doc."""
    row = cb.cftc_row({"ES": -408726.0, "NQ": -11593.0},
                      [-300000.0, -250000.0, -100000.0], _dt.date(2026, 10, 13))
    assert row["as_of"] == "2026-10-13"
    assert "prior Tuesday" in row["staleness_note"]
    assert "three days old" in row["staleness_note"]
    assert row["net"] == -420319.0
    assert row["mock"] is False
    assert "CFTC" in row["source"] and "public domain" in row["source"]


def test_A_MISSING_CONTRACT_IS_NAMED_NOT_SILENTLY_DROPPED():
    """ES + NQ with NQ missing is not "ES+NQ". The row still reports, and says what is absent,
    because a total drawn from one leg under a two-leg label is the wrong figure."""
    row = cb.cftc_row({"ES": -408726.0, "NQ": None}, [-300000.0, -250000.0], None)
    assert row["missing"] == ["NQ"]
    assert row["net"] == -408726.0


# ── 2. the put/call row is a PROXY and says so ────────────────────────────

def test_THE_PUT_CALL_ROW_NEVER_CLAIMS_TO_BE_CBOE():
    """R-IV.1239(d)2 declined to scrape CBOE on terms that could not be verified and said to
    use a stored put/call LABELLED WITH ITS SOURCE. The stored one is an aggregate over the UW
    flow poller's universe -- a narrower, large-cap-heavy sample, which is a DIFFERENT quantity
    from the market-wide equity ratio. The mock's label "EQUITY · 5D" means CBOE's series, so
    using it here would be the wrong-source fault."""
    row = cb.put_call_row(0.78, [0.6] * 60, universe_size=120, sessions=5, as_of="2026-10-16")
    assert "CBOE" not in row["sub"]
    assert "UW FLOW" in row["sub"] and "120 tickers" in row["sub"]
    assert "NOT the CBOE" in row["source"]
    assert row["value"] == "0.78"


def test_AN_UNKNOWN_UNIVERSE_SAYS_SO_RATHER_THAN_IMPLYING_BREADTH():
    row = cb.put_call_row(0.78, [0.6] * 60, universe_size=None, sessions=5, as_of=None)
    assert "universe unknown" in row["sub"]


# ── 3. the FINRA row is a mock, and the reason is in the row ──────────────

def test_THE_SHORT_INTEREST_ROW_IS_A_MOCK_AND_CARRIES_BOTH_REASONS():
    """R-IV.1239(d)3 said ship the mock first. It stays a mock on two findings from reading the
    source rather than assuming it:

      1. FINRA's own equity short interest catalogue documents NEITHER days to cover NOR
         average daily volume, so "days to cover from FINRA's own file" is not satisfiable as
         written -- computing it from another source's volume makes it not FINRA's figure.
      2. FINRA Data states non-commercial use with no licence for automated download that this
         lane could verify, so (d)2's own standard applies.
    """
    row = cb.short_interest_row()
    assert row["mock"] is True
    assert row["crowded_short_at"] == 5.0
    assert "not a documented field" in row["source"]
    assert "non-commercial" in row["source"]


def test_THE_CROWDED_SHORT_FLAG_IS_THE_RULED_THRESHOLD():
    assert cb.crowded_short(5.0) is True
    assert cb.crowded_short(7.2) is True
    assert cb.crowded_short(4.9) is False
    assert cb.crowded_short(None) is None, "unknown is not uncrowded"


# ── 4. percentiles, thin history, and the headline ────────────────────────

def test_A_THIN_HISTORY_IS_STILL_RANKED_BUT_MARKED_THIN():
    """R-IV.1194(f): a short history shows amber with the percentile starred. Withholding the
    rank entirely would hide the reading; presenting it unmarked would overstate it."""
    row = cb.cftc_row({"ES": 100.0, "NQ": 0.0}, [50.0] * 9, _dt.date(2026, 10, 13))
    assert row["pct"] is not None and row["thin"] is True
    full = cb.cftc_row({"ES": 100.0, "NQ": 0.0}, [50.0] * 60, _dt.date(2026, 10, 13))
    assert full["thin"] is False


def test_EXTREME_IS_EITHER_TAIL_AND_THE_MIDDLE_IS_NOT():
    assert cb.label(95) == (True, "high")
    assert cb.label(5) == (True, "low")
    assert cb.label(50) == (False, None)
    assert cb.label(None) == (False, None)


def test_A_MOCK_ROW_NEVER_VOTES_IN_THE_HEADLINE():
    """A headline partly drawn from a fixture is a claim about the market made from a fixture.
    The mock row is on the tile and out of the count."""
    live_extreme = {"pct": 95, "extreme": True, "extreme_end": "high", "mock": False}
    mock_extreme = {"pct": 95, "extreme": True, "extreme_end": "high", "mock": True}
    word, lean, basis = cb.headline([live_extreme, mock_extreme])
    assert word == "BEARS CROWDED"
    assert "1 of 1 live rows" in basis, basis
    # And with only a mock to go on, there is no headline at all.
    none_word, none_lean, none_basis = cb.headline([mock_extreme])
    assert none_word is None and none_lean is None
    assert "no live positioning row" in none_basis


def test_MIXED_IS_ITS_OWN_ANSWER():
    live = {"pct": 50, "extreme": False, "mock": False}
    word, lean, basis = cb.headline([live, live])
    assert word == "CROWD MIXED" and lean == "neutral"
    assert "no live row at an extreme" in basis


def test_A_ROW_WITH_NO_PERCENTILE_DOES_NOT_COUNT_AS_AGREEMENT():
    """An unrankable row is not a vote for "mixed" -- it is not a vote."""
    live_na = {"pct": None, "extreme": False, "mock": False}
    assert cb.headline([live_na])[0] is None
