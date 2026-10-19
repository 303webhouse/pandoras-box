"""B6's Crowd gauge: who is positioned which way, and how unusual that is.

PURE. Numbers in, rows out.

THREE SOURCES, THREE DIFFERENT STANDINGS, and the tile has to keep them apart:

  * CFTC Traders in Financial Futures -- US government, public domain, WIRED LIVE under
    R-IV.1239(d)1. Weekly, as of the prior Tuesday, so it is three days stale by construction
    and the row says so rather than looking current.
  * PUT/CALL -- NOT the CBOE market-wide equity series, which R-IV.1239(d)2 declines to scrape
    on unverified terms. It is derived from `flow_events`, which the hub ALREADY pulls from UW,
    aggregated over the poller's own universe. That is a different quantity from CBOE's and is
    labelled as one: a proxy served under a CBOE label would be the wrong-source fault.
  * FINRA short interest -- MOCK in this deploy, per R-IV.1239(d)3's "ship the mock first".

PERCENTILES, NOT Z-SCORES, on all three: positioning series are bounded and skewed, and a
thin history is STARRED rather than quietly ranked (R-IV.1194(f)).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: CFTC contract names, verified against the portal's own data rather than guessed.
#: "NASDAQ MINI" is the E-mini Nasdaq-100; a "NASDAQ-100 Consolidated" series also exists and
#: is NOT used -- the choice is stated because the two carry different open interest
#: (294,776 vs 279,515 on 2026-10-13) and a silent switch between them would move the figure.
CFTC_CONTRACTS = {"ES": "E-MINI S&P 500", "NQ": "NASDAQ MINI"}

#: A history shorter than this gets the starred, amber "cannot confirm" treatment.
THIN_HISTORY = 52
#: What a full percentile window is, in weekly observations for CFTC and sessions elsewhere.
FULL_WINDOW = 52

#: R-IV.1239(d)3: the days-to-cover flag.
CROWDED_SHORT_DTC = 5.0

#: An extreme reading, in percentile terms, at either end.
EXTREME_LOW, EXTREME_HIGH = 10, 90


def percentile(value: Optional[float], history: Sequence[Optional[float]]) -> Optional[int]:
    """Rank of `value` within `history`, 0-100. None when there is nothing to rank against.

    Needs only TWO observations to produce a rank, because a thin history is reported as thin
    rather than withheld -- but see `thin`, which is what makes the difference visible.
    """
    vals = sorted(v for v in history if v is not None)
    if value is None or len(vals) < 2:
        return None
    below = sum(1 for v in vals if v < value)
    return int(round(100.0 * below / len(vals)))


def thin(history: Sequence[Optional[float]], full: int = THIN_HISTORY) -> bool:
    """Is this percentile drawn from too little history to be trusted? R-IV.1194(f)."""
    return len([v for v in history if v is not None]) < full


def label(pct: Optional[int]) -> Tuple[bool, Optional[str]]:
    """(extreme, which end). A percentile at either tail is extreme; the middle is not."""
    if pct is None:
        return False, None
    if pct >= EXTREME_HIGH:
        return True, "high"
    if pct <= EXTREME_LOW:
        return True, "low"
    return False, None


def cftc_net(long_: Optional[float], short_: Optional[float]) -> Optional[float]:
    """Leveraged-money NET position. None when either leg is missing, never a one-sided net."""
    if long_ is None or short_ is None:
        return None
    return long_ - short_


def cftc_row(nets: Dict[str, Optional[float]], history: Sequence[Optional[float]],
             as_of: Optional[_dt.date]) -> Dict[str, Any]:
    """The futures row: ES + NQ leveraged-money net, its percentile, and its OWN as-of.

    THE AS-OF IS PART OF THE READING. The TFF report is published Friday for the prior
    Tuesday, so this row is at least three days old the moment it is correct, and more than
    that by the following week. A positioning figure read as current is a positioning figure
    read wrong.
    """
    have = [v for v in nets.values() if v is not None]
    total = sum(have) if have else None
    pct = percentile(total, history)
    is_extreme, end = label(pct)
    missing = [k for k, v in nets.items() if v is None]
    return {
        "key": "FUTURES",
        "sub": "CFTC · " + "+".join(CFTC_CONTRACTS),
        # format(), not %-formatting: "%,d" is not valid Python and raised ValueError on the
        # first run. A thousands separator belongs in format spec syntax.
        "value": None if total is None else "net %s" % format(total, "+,.0f"),
        "net": total,
        "components": dict(nets),
        "pct": pct,
        "pct_label": None if pct is None else "%dth" % pct,
        "extreme": is_extreme,
        "extreme_end": end,
        "thin": thin(history),
        "as_of": as_of.isoformat() if as_of else None,
        "staleness_note": (
            "CFTC publishes the TFF report on Friday as of the prior Tuesday, so this reading "
            "is at least three days old when it is correct"),
        "missing": missing or None,
        "source": "CFTC Traders in Financial Futures, futures only (public domain)",
        "mock": False,
    }


def put_call_row(ratio: Optional[float], history: Sequence[Optional[float]], *,
                 universe_size: Optional[int], sessions: int,
                 as_of: Optional[str]) -> Dict[str, Any]:
    """The put/call row, from UW flow the hub already pulls -- NOT CBOE's equity series.

    THE LABEL IS THE POINT. R-IV.1239(d)2 declined to scrape CBOE on terms that could not be
    verified, and said to use a stored put/call "labelled with its source" if one exists. One
    does, but it is an aggregate over the flow poller's own universe, which is a different
    quantity from the market-wide equity ratio: a narrower, large-cap-heavy sample. Serving it
    under "EQUITY · 5D" -- the mock's label, which means CBOE's series -- would be the
    wrong-source fault, so the row names its universe in its own subtitle.
    """
    pct = percentile(ratio, history)
    is_extreme, end = label(pct)
    return {
        "key": "PUT/CALL",
        "sub": "UW FLOW · %dD · %s" % (sessions,
                                       ("%d tickers" % universe_size) if universe_size
                                       else "universe unknown"),
        "value": None if ratio is None else "%.2f" % ratio,
        "ratio": ratio,
        "pct": pct,
        "pct_label": None if pct is None else "%dth" % pct,
        "extreme": is_extreme,
        "extreme_end": end,
        "thin": thin(history),
        "as_of": as_of,
        "source": ("UW flow_events, which the hub already pulls, summed over the flow "
                   "poller's universe. NOT the CBOE market-wide equity put/call: a narrower "
                   "sample and therefore a different quantity (R-IV.1239(d)2)"),
        "mock": False,
    }


def short_interest_row(*, mock: bool = True) -> Dict[str, Any]:
    """The FINRA short-interest row. MOCK in this deploy, R-IV.1239(d)3.

    AND IT STAYS MOCK UNTIL SPINE RULES, for two reasons found while researching the source
    rather than assumed:

      1. R-IV.1239(d)3 asks for days to cover "from FINRA's own file". FINRA's own equity
         short interest catalogue page documents NEITHER a days-to-cover field NOR an average
         daily volume one. If the figure has to be computed as short interest divided by
         average daily volume from some other source, it is no longer from FINRA's file and
         the ruling's own wording stops being satisfiable as written.
      2. FINRA Data describes "non-commercial use of data" and publishes no licence for
         automated file download that this lane could verify. R-IV.1239(d)2's own standard --
         "we don't scrape sites whose terms we can't verify" -- therefore applies here too.

    So the row ships with the mock's shape and an explicit `mock: true`, and the tile shows it
    as a mock while its two siblings are live.
    """
    return {
        "key": "SHORT INT",
        "sub": "FINRA · DAYS TO COVER",
        "value": "—",
        "pct": None,
        "pct_label": None,
        "extreme": False,
        "thin": True,
        "mock": mock,
        "crowded_short": None,
        "crowded_short_at": CROWDED_SHORT_DTC,
        "source": ("FINRA equity short interest. NOT WIRED: days to cover is not a documented "
                   "field in FINRA's own file, and FINRA Data's terms say non-commercial use "
                   "with no verifiable licence for automated download (R-IV.1239(d)3)"),
    }


def crowded_short(days_to_cover: Optional[float]) -> Optional[bool]:
    """R-IV.1239(d)3's flag: CROWDED SHORT at days to cover >= 5. None when it is unknown."""
    if days_to_cover is None:
        return None
    return days_to_cover >= CROWDED_SHORT_DTC


def headline(rows: Sequence[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str], str]:
    """(word, lean, basis). Counts only the rows that ARE live and DO have a percentile.

    A mock row never votes. A headline that counted one would be a claim about the market made
    partly from a fixture.
    """
    live = [r for r in rows if not r.get("mock") and r.get("pct") is not None]
    if not live:
        return None, None, "no live positioning row has a percentile"
    extremes = [r for r in live if r.get("extreme")]
    n = "%d of %d live rows" % (len(extremes), len(live))
    if not extremes:
        return "CROWD MIXED", "neutral", "no live row at an extreme, %s" % n
    highs = [r for r in extremes if r.get("extreme_end") == "high"]
    lows = [r for r in extremes if r.get("extreme_end") == "low"]
    if len(highs) >= len(lows):
        return "BEARS CROWDED", "bear", "%s at a high extreme, %s" % (len(highs), n)
    return "BULLS CROWDED", "bull", "%s at a low extreme, %s" % (len(lows), n)
