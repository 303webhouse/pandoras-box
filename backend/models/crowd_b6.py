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


def short_interest_row(si: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The FINRA short-interest row. LIVE since R-IV.1318(b); a stated refusal without data.

    IT WAS A MOCK ON THREE REASONS AND ALL THREE ARE NOW ANSWERED, two of them by measurement
    that contradicted what this docstring previously asserted:

      1. "days to cover is not a documented field in FINRA's own file" -- FALSE. The free
         twice-monthly file carries `daysToCoverQuantity` AND `averageDailyVolumeQuantity`.
         Measured AAPL 2026-09-30: short 120,763,539, ADV 39,858,260, days to cover 3.03. The
         figure comes from FINRA, not from a volume series borrowed elsewhere, so
         R-IV.1239(d)3's wording is satisfiable exactly as written.
      2. "no verifiable licence for automated download" -- ANSWERED by R-IV.1318(a): the
         Equity Data terms allow non-commercial personal or professional use, require FINRA to
         be named as owner and source, and forbid charging for the data. Nothing is
         redistributed and nothing is charged for, and the attribution is asserted below.
      3. "short interest is not served by the API at all" -- WRONG IN DETAIL and it did not
         matter. `Equity/consolidatedShortInterest` answers 401, not 404, so the dataset is
         real and merely token-gated; and the route actually used is not the API at all but
         the free CDN file, which needs no credential and no account.

    TWICE MONTHLY, NEVER REAL-TIME, AND BOTH DATES TRAVEL WITH THE VALUE. The newest file is
    typically the previous settlement -- today's is 2026-09-30, published 2026-10-12, while
    2026-10-15 is still 403 -- so the number on the card can be three weeks old BY DESIGN. A
    positioning figure without its settlement date would read as current, which is the fault
    this tile's siblings were built to avoid.

    `pct` STAYS None, DELIBERATELY. A percentile needs a history, and this route serves one
    settlement per 2.7MB file; building a distribution would mean dozens of downloads for a
    single line. So the row carries a real VALUE and no percentile, and `headline()` already
    refuses to count a row without one -- the row displays, and it does not vote.

    #42: display only. The CROWDED SHORT flag is a label on the same line, not a gate.
    """
    if not (si or {}).get("available"):
        return {
            "key": "SHORT INT",
            "sub": "FINRA · DAYS TO COVER",
            "value": "—",
            "pct": None,
            "pct_label": None,
            "extreme": False,
            "thin": True,
            "mock": False,
            "crowded_short": None,
            "crowded_short_at": CROWDED_SHORT_DTC,
            "settlement_date": None,
            "publish_date": None,
            "attribution": (si or {}).get("attribution") or "Source: FINRA",
            "cadence": (si or {}).get("cadence"),
            # UNAVAILABLE IS NOT A MOCK AND NOT A ZERO. The reason travels so a reader learns
            # which of the two it is.
            "source": ("FINRA equity short interest, unavailable this read: %s"
                       % ((si or {}).get("reason") or "not fetched")),
        }

    dtc = si.get("days_to_cover")
    return {
        "key": "SHORT INT",
        "sub": "FINRA · DAYS TO COVER",
        "value": ("—" if dtc is None else "%.2f" % dtc),
        "pct": None,
        "pct_label": None,
        "extreme": False,
        # THIN, because one settlement is one observation. The word is honest about what this
        # row can support, and it is what keeps the row out of the headline.
        "thin": True,
        "mock": False,
        "crowded_short": crowded_short(dtc),
        "crowded_short_at": CROWDED_SHORT_DTC,
        "symbol": si.get("symbol"),
        "settlement_date": si.get("settlement_date"),
        "publish_date": si.get("publish_date"),
        "attribution": si.get("attribution") or "Source: FINRA",
        "cadence": si.get("cadence"),
        "current_short": si.get("current_short"),
        "average_daily_volume": si.get("average_daily_volume"),
        "source": ("FINRA equity short interest, free twice-monthly file "
                   "(cdn.finra.org/equity/otcmarket/biweekly). %s settlement, published %s. "
                   "Days to cover is FINRA’s own field, not computed here."
                   % (si.get("settlement_date"), si.get("publish_date"))),
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
