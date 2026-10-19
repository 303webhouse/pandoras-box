"""B3's yield-curve reads: z-scores, the shape word, the un-inverted flag, and the one thing
every label here owes — ITS MEASURED FIRE RATE.

R-IV.1220(b): the labels are UNUSUAL (|z| >= 2) and EXTREME (|z| >= 3, or a 10Y daily move of
at least 10bp). "RARE" is retired. EXTREME still pulses. AND EVERY TOOLTIP STATES THAT LABEL'S
MEASURED FIRES PER YEAR -- measured from the same history the z-score is computed on, never
asserted from a normal distribution. A threshold whose frequency is not stated is a threshold
nobody can calibrate against, and the Gaussian answer (|z|>=2 about 11 times a year) is wrong
for rates, whose daily changes are fat-tailed.

PURE. No key, no vendor, no database, so every rule here is testable from a list of numbers.

ONE VOCABULARY CHOICE IS MINE AND IS FLAGGED AS SUCH: R-IV.1220(b) and B3's spec require a
"shape word" without enumerating the words. `SHAPE_WORDS` below is the standard curve
vocabulary with its thresholds stated. The labels UNUSUAL / EXTREME and the retirement of RARE
are the ruling's; the shape words are this lane's and are reported for correction.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: R-IV.1220(b)'s two labels. There is no third, and there is no "RARE".
UNUSUAL = "UNUSUAL"
EXTREME = "EXTREME"

#: |z| at or above these. Stated once, used everywhere, because two numbers for one threshold
#: is a fault this lane has shipped before.
UNUSUAL_Z = 2.0
EXTREME_Z = 3.0
#: R-IV.1220(b)'s second route to EXTREME: a 10Y daily move of 10bp or more, whatever its z.
#: A 10bp day in the 10Y is a market event even in a year whose vol makes it a 1.8-sigma one.
EXTREME_10Y_BP = 10.0

#: The trailing window, in sessions, that a z-score is measured against. ~1 year of sessions.
Z_WINDOW = 252

#: Sessions in a year, for turning a count of fires into a rate.
SESSIONS_PER_YEAR = 252

#: The FRED series B3 reads. Keys are the display tenors.
SERIES = {
    "3M": "DGS3MO",
    "2Y": "DGS2",
    "10Y": "DGS10",
    "30Y": "DGS30",
}
SPREAD_SERIES = {
    "2s10s": "T10Y2Y",
    "3m10s": "T10Y3M",
}

#: This lane's vocabulary, with the thresholds that pick each word, in basis points of 2s10s.
#: Reported under R-IV.925(b) as BUILD's wording rather than a ruling's.
SHAPE_WORDS = ("INVERTED", "FLAT", "NORMAL", "STEEP")
FLAT_BP = 25.0
STEEP_BP = 150.0


def diffs(values: Sequence[Optional[float]]) -> List[float]:
    """Session-over-session changes in BASIS POINTS, skipping gaps.

    FRED's daily series carry None on holidays. A None is SKIPPED rather than carried forward:
    a repeated value would add a zero change and shrink the standard deviation, which would
    push more days over the z threshold -- a quiet inflation of every label.
    """
    out: List[float] = []
    prev: Optional[float] = None
    for v in values:
        if v is None:
            continue
        if prev is not None:
            out.append((v - prev) * 100.0)
        prev = v
    return out


def zscore(changes: Sequence[float], window: int = Z_WINDOW) -> Optional[float]:
    """The z of the LATEST change against the `window` changes before it.

    None when there is not enough history, never 0.0 -- a zero z reads as "a perfectly ordinary
    day", which is a claim, and this lane has a standing rule that an unavailable factor is
    None and never zero.
    """
    if len(changes) < 2:
        return None
    latest = changes[-1]
    hist = list(changes[-(window + 1):-1])
    if len(hist) < 30:
        return None
    mean = sum(hist) / len(hist)
    var = sum((x - mean) ** 2 for x in hist) / (len(hist) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return None
    return (latest - mean) / sd


def label_for(z: Optional[float], *, tenor: Optional[str] = None,
              change_bp: Optional[float] = None) -> Optional[str]:
    """UNUSUAL, EXTREME or None. R-IV.1220(b).

    The 10bp route applies to the 10Y ONLY, as ruled -- not to every tenor. Applying it to the
    3M, whose daily moves are smaller, would mark almost nothing; applying it to a spread would
    be a different quantity entirely.
    """
    if tenor == "10Y" and change_bp is not None and abs(change_bp) >= EXTREME_10Y_BP:
        return EXTREME
    if z is None:
        return None
    if abs(z) >= EXTREME_Z:
        return EXTREME
    if abs(z) >= UNUSUAL_Z:
        return UNUSUAL
    return None


def fires_per_year(changes: Sequence[float], *, tenor: Optional[str] = None,
                   window: int = Z_WINDOW) -> Dict[str, Any]:
    """MEASURED fires per year for each label, by replaying the rule over the history.

    Every day with enough history behind it is re-tested with EXACTLY the published rule --
    the same `zscore` and `label_for` the live reading uses, not a closed-form approximation.
    If the rule changes, this number changes with it, which is the only way a tooltip's
    frequency stays true.

    Returns the counts, the rates, and the span measured, because a rate without its span is
    the figure Convention #37 exists to prevent.
    """
    n = len(changes)
    counts = {UNUSUAL: 0, EXTREME: 0}
    tested = 0
    for i in range(n):
        slice_ = changes[: i + 1]
        z = zscore(slice_, window)
        if z is None:
            continue
        tested += 1
        lab = label_for(z, tenor=tenor, change_bp=slice_[-1])
        if lab in counts:
            counts[lab] += 1
    if not tested:
        return {"sessions_tested": 0, "unusual_per_year": None, "extreme_per_year": None,
                "basis": "not enough history to measure a rate"}
    years = tested / float(SESSIONS_PER_YEAR)
    return {
        "sessions_tested": tested,
        "unusual_count": counts[UNUSUAL],
        "extreme_count": counts[EXTREME],
        "unusual_per_year": round(counts[UNUSUAL] / years, 1),
        "extreme_per_year": round(counts[EXTREME] / years, 1),
        "basis": ("measured by replaying the published rule over %d sessions (%.1f years) of "
                  "this series' own history" % (tested, years)),
    }


def shape_word(spread_2s10s_bp: Optional[float],
               spread_3m10s_bp: Optional[float]) -> Tuple[Optional[str], str]:
    """(word, why). BUILD's vocabulary, with the threshold that picked it.

    INVERTED wins on EITHER spread being negative, not on both: a 3m10s inversion with a
    positive 2s10s is still an inverted curve at the front, and that is the part the recession
    literature reads. Reporting NORMAL there would be the comfortable answer, not the true one.
    """
    if spread_2s10s_bp is None and spread_3m10s_bp is None:
        return None, "neither spread is available"
    vals = [v for v in (spread_2s10s_bp, spread_3m10s_bp) if v is not None]
    if any(v < 0 for v in vals):
        which = []
        if spread_3m10s_bp is not None and spread_3m10s_bp < 0:
            which.append("3m10s %.0fbp" % spread_3m10s_bp)
        if spread_2s10s_bp is not None and spread_2s10s_bp < 0:
            which.append("2s10s %.0fbp" % spread_2s10s_bp)
        return "INVERTED", "inverted at " + " and ".join(which)
    ref = spread_2s10s_bp if spread_2s10s_bp is not None else vals[0]
    if ref < FLAT_BP:
        return "FLAT", "2s10s %.0fbp, under the %.0fbp flat threshold" % (ref, FLAT_BP)
    if ref >= STEEP_BP:
        return "STEEP", "2s10s %.0fbp, at or over the %.0fbp steep threshold" % (ref, STEEP_BP)
    return "NORMAL", "2s10s %.0fbp, between %.0f and %.0fbp" % (ref, FLAT_BP, STEEP_BP)


#: How recently a sign flip still counts as news.
UNINVERT_WINDOW = 20


def un_inverted(spread_bp: Sequence[Optional[float]],
                window: int = UNINVERT_WINDOW) -> Optional[Dict[str, Any]]:
    """The UN-INVERTED flag: the spread was negative and is now not, within `window` sessions.

    None when it has not happened, never False -- "it did not un-invert" and "it was never
    inverted" are different facts, and the second one is most of history.

    The crossing is found on the SIGN, and a value of exactly 0.0 counts as NOT inverted: a
    curve at zero has stopped being inverted, and treating 0 as still-negative would hold the
    flag back a day on precisely the day it matters.
    """
    vals = [v for v in spread_bp if v is not None]
    if len(vals) < 2 or vals[-1] < 0:
        return None
    recent = vals[-(window + 1):]
    for i in range(len(recent) - 1, 0, -1):
        if recent[i] >= 0 > recent[i - 1]:
            return {"flag": "UN-INVERTED",
                    "sessions_ago": len(recent) - 1 - i,
                    "from_bp": round(recent[i - 1], 1),
                    "to_bp": round(recent[i], 1),
                    "basis": ("crossed from %.1fbp to %.1fbp %d session(s) ago"
                              % (recent[i - 1], recent[i], len(recent) - 1 - i))}
    return None


def tooltip(tenor_or_spread: str, stats: Dict[str, Any]) -> str:
    """The tooltip line R-IV.1220(b) requires: the label, its rule AND its measured frequency.

    Source, universe and as-of in one sentence (Convention #37 as clarified by R-IV.1224(g)),
    because this string is exactly the kind that gets quoted onward without its caption.
    """
    u = stats.get("unusual_per_year")
    e = stats.get("extreme_per_year")
    if u is None:
        return "%s: not enough history to state a fire rate" % tenor_or_spread
    return ("%s · UNUSUAL at |z| >= %.0f fires %.1f times a year, EXTREME at |z| >= %.0f fires "
            "%.1f times a year — %s (FRED daily series, as of %s)"
            % (tenor_or_spread, UNUSUAL_Z, u, EXTREME_Z, e, stats.get("basis", ""),
               stats.get("as_of", "unknown")))
