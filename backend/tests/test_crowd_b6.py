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


# ── 3. the FINRA row is LIVE, and both dates travel with it ──────────

def test_THE_SHORT_INTEREST_ROW_IS_LIVE_AND_BOTH_REASONS_ARE_ANSWERED():
    """INVERTED BY R-IV.1318(b). It shipped as a mock on two findings, and MEASUREMENT
    CONTRADICTED BOTH:

      1. "FINRA's catalogue documents neither days to cover nor average daily volume" --
         FALSE. The free twice-monthly file carries `daysToCoverQuantity` AND
         `averageDailyVolumeQuantity`. Measured AAPL 2026-09-30: short 120,763,539, ADV
         39,858,260, days to cover 3.03. So R-IV.1239(d)3's wording is satisfiable exactly as
         written -- the figure is FINRA's, not one computed against another source's volume.
      2. "no licence for automated download this lane could verify" -- ANSWERED by
         R-IV.1318(a): the Equity Data terms permit non-commercial personal or professional
         use, require FINRA to be named as owner and source, and forbid charging for the data.

    The reasons were honestly held and honestly recorded; they were also wrong, which is why
    the docstring that carried them is replaced rather than deleted.
    """
    si = {"available": True, "symbol": "SPY", "days_to_cover": 2.02,
          "settlement_date": "2026-09-30", "publish_date": "2026-10-12",
          "attribution": "Source: FINRA",
          "cadence": "twice-monthly settlement data, published about 7 business days after "
                     "each settlement date - not real-time"}
    row = cb.short_interest_row(si)
    assert row["mock"] is False
    assert row["value"] == "2.02"
    assert row["crowded_short_at"] == 5.0
    # BOTH DATES, R-IV.1318(b). A positioning figure without its settlement date reads as
    # current, and this one can be three weeks old by design.
    assert row["settlement_date"] == "2026-09-30"
    assert row["publish_date"] == "2026-10-12"
    assert row["attribution"] == "Source: FINRA"
    assert "not real-time" in row["cadence"]
    assert "cdn.finra.org" in row["source"]


def test_AN_UNAVAILABLE_READ_IS_NOT_A_MOCK_AND_NOT_A_ZERO():
    """The third state. A failed fetch must not resurrect the mock and must not print a number;
    it prints an em dash and says why."""
    row = cb.short_interest_row({"available": False, "reason": "no file read"})
    assert row["mock"] is False
    assert row["value"] == "—"
    assert row["crowded_short"] is None
    assert "unavailable this read" in row["source"]

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
    # R-IV.1369(f)6 gave each row its OWN direction, so a row must now name itself to
    # vote. These fixtures omitted `key` because it did not matter before. The test is
    # about the MOCK row being excluded, not about direction, so they gain a key and
    # the assertion stands: PUT/CALL high is bears crowded.
    live_extreme = {"key": "PUT/CALL", "pct": 95, "extreme": True,
                    "extreme_end": "high", "mock": False}
    mock_extreme = {"key": "PUT/CALL", "pct": 95, "extreme": True,
                    "extreme_end": "high", "mock": True}
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


# ── R-IV.1369(f)6: each row's high end means its own thing ──────────────────

def _ex(key, end="high"):
    """An extreme live row for `key`. `pct` is only there to make the row live."""
    return {"key": key, "pct": 95 if end == "high" else 5, "extreme": True,
            "extreme_end": end, "mock": False}


def test_FUTURES_at_95_is_BULLS_CROWDED():
    """THE DEFECT, named. A high leveraged-money net is the crowd positioned LONG. The old
    headline counted every "high" extreme as BEARS CROWDED, so a week with funds at a
    95th-percentile net long published the exact opposite of what the data said -- on the tile
    whose whole point is which side is already full."""
    word, lean, basis = cb.headline([_ex("FUTURES")])
    assert word == "BULLS CROWDED", basis
    assert lean == "notable"


def test_PUT_CALL_at_95_is_BEARS_CROWDED():
    """The case the old code got right, kept as a control: a high ratio is a lot of puts."""
    word, lean, basis = cb.headline([_ex("PUT/CALL")])
    assert word == "BEARS CROWDED", basis
    assert lean == "notable"


def test_ONE_OF_EACH_is_CROWD_MIXED():
    """Both sides crowded is a real, readable state. Picking the larger count would turn a
    one-row margin into a confident call."""
    word, lean, basis = cb.headline([_ex("FUTURES"), _ex("PUT/CALL")])
    assert word == "CROWD MIXED", basis
    assert "extremes disagree" in basis


def test_the_LOW_end_flips_each_row_too():
    """The map names the HIGH end; the low end is its opposite, per row."""
    assert cb.headline([_ex("FUTURES", "low")])[0] == "BEARS CROWDED"
    assert cb.headline([_ex("PUT/CALL", "low")])[0] == "BULLS CROWDED"


def test_a_row_with_NO_DECLARED_SIDE_does_not_vote():
    """SHORT INT has no percentile and no side -- "shown, not counted". Guessing a direction
    for an undeclared row would be the same error in a new place."""
    word, _lean, basis = cb.headline([_ex("SHORT INT")])
    assert word == "CROWD MIXED"
    assert "declares a side" in basis


def test_BOTH_crowded_headlines_are_NOTABLE_not_bear_or_bull():
    """R-IV.1369(f)7. A crowded side is contrarian fuel: painting "BEARS CROWDED" in the bear
    colour invites the wrong read, since a crowded short side is what a squeeze runs on."""
    assert cb.headline([_ex("FUTURES")])[1] == "notable"
    assert cb.headline([_ex("PUT/CALL")])[1] == "notable"
    assert cb.HEADLINE_LEAN_CROWDED == "notable"
