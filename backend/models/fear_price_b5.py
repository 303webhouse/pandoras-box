"""B5's Fear Price: implied minus realized, the VIX term curve, SKEW's percentile, and the
expected move.

PURE. Numbers in, reads out.

THE HEADLINE IS A COMPARISON OF TWO THINGS MEASURED THE SAME WAY, and that is the only reason
it means anything. An index like VIX is an annualised 30-day implied volatility in percentage
points; a realized figure computed as a 20-day standard deviation of daily returns is neither
annualised nor in those units until it is made so. Subtracting them without that step is the
single easiest way to produce a confident, wrong "premium rich" call, so `realized_vol` does
the annualising and says so in its name and its docstring.

WHAT IS NOT HERE: any claim that a rich premium is a reason to sell it. The tile is display
only (#42); the words are a description of the spread, not a recommendation.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Trading days in a year, for annualising.
ANNUALISE = 252
#: The realized window B5's spec names.
REALIZED_DAYS = 20

#: Each implied index and the underlying whose realized vol it is compared with.
PAIRS = (("SPY", "^VIX"), ("QQQ", "^VXN"), ("IWM", "^RVX"))

#: The VIX term structure, shortest first. Nine days to six months.
CURVE = (("9D", "^VIX9D"), ("1M", "^VIX"), ("3M", "^VIX3M"), ("6M", "^VIX6M"))

#: SKEW's percentile window, in sessions. Five years: long enough that a percentile means
#: something, short enough that it is this market's distribution and not the 2008 one.
SKEW_WINDOW = 252 * 5

#: Headline words. The spread they describe is implied minus realized, in vol points.
RICH_AT = 2.0
CHEAP_AT = -2.0


def returns(closes: Sequence[Optional[float]]) -> List[float]:
    """Log returns, skipping holes. A None is a missing session, not a flat one."""
    out: List[float] = []
    prev: Optional[float] = None
    for c in closes:
        if c is None or c <= 0:
            continue
        if prev is not None:
            out.append(math.log(c / prev))
        prev = c
    return out


def realized_vol(closes: Sequence[Optional[float]], days: int = REALIZED_DAYS) -> Optional[float]:
    """ANNUALISED realized volatility in PERCENTAGE POINTS, over the last `days` returns.

    Annualised and in percent, so it is the same unit as VIX. A 20-day standard deviation of
    daily returns is about 0.008; VIX is about 18. Subtracting the first from the second is how
    a tile reports a 17-point premium every single day and nobody notices for a month.
    """
    r = returns(closes)
    if len(r) < days:
        return None
    window = r[-days:]
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
    return math.sqrt(var) * math.sqrt(ANNUALISE) * 100.0


def gap(implied: Optional[float], closes: Sequence[Optional[float]],
        days: int = REALIZED_DAYS) -> Tuple[Optional[float], str]:
    """(implied - realized, basis). None when either side is missing, never 0.0."""
    rv = realized_vol(closes, days)
    if implied is None:
        return None, "the implied index has no reading"
    if rv is None:
        return None, "fewer than %d returns are available for realized vol" % days
    return implied - rv, ("implied %.1f minus %d-day annualised realized %.1f"
                          % (implied, days, rv))


def headline(gaps: Sequence[Optional[float]]) -> Tuple[Optional[str], Optional[str], str]:
    """(word, lean, basis) from the available gaps. Describes; does not advise.

    The AVERAGE of the gaps that exist, and the basis says how many that was: a headline drawn
    from one index when three were expected is a different claim from the same words drawn
    from three.
    """
    have = [g for g in gaps if g is not None]
    if not have:
        return None, None, "no implied-minus-realized gap is available"
    avg = sum(have) / len(have)
    n = "%d of %d indices" % (len(have), len(gaps))
    if avg >= RICH_AT:
        return "PREMIUM RICH", "bear", "implied over realized by %.1f points, %s" % (avg, n)
    if avg <= CHEAP_AT:
        return "PREMIUM CHEAP", "bull", "implied under realized by %.1f points, %s" % (-avg, n)
    return "PREMIUM FAIR", "neutral", "implied within %.1f points of realized, %s" % (
        abs(avg), n)


def curve_label(values: Sequence[Optional[float]]) -> Tuple[Optional[str], str]:
    """INVERTED / FLAT / UPWARD on the VIX term structure, shortest tenor first.

    INVERTED means the front is ABOVE the back, which is stress -- the opposite sense from the
    yield curve, where inverted means the front is BELOW. The two tiles sit on the same screen,
    so the word is defined here against its own curve and the basis states the direction.
    """
    have = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(have) < 2:
        return None, "fewer than two tenors are available"
    front, back = have[0][1], have[-1][1]
    spread = front - back
    if spread > 0.5:
        return "INVERTED", ("front %.1f above back %.1f: near-term fear above longer-dated"
                            % (front, back))
    if abs(spread) <= 0.5:
        return "FLAT", "front %.1f and back %.1f within half a point" % (front, back)
    return "UPWARD", ("front %.1f below back %.1f: the usual shape" % (front, back))


def percentile(value: Optional[float], history: Sequence[Optional[float]]) -> Optional[int]:
    """The percentile rank of `value` within `history`, 0-100. None when it cannot be ranked.

    Rank, not a z-score, because SKEW is bounded and skewed: a z would imply a symmetry the
    series does not have.
    """
    vals = sorted(v for v in history if v is not None)
    if value is None or len(vals) < 30:
        return None
    below = sum(1 for v in vals if v < value)
    return int(round(100.0 * below / len(vals)))


def ordinal(n: Optional[int]) -> Optional[str]:
    if n is None:
        return None
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "%d%s" % (n, suf)


def expected_move(spot: Optional[float], call_mid: Optional[float], put_mid: Optional[float],
                  *, days: Optional[int] = None,
                  label: Optional[str] = None) -> Dict[str, Any]:
    """The ATM straddle as an expected move, in dollars and percent.

    THE STRADDLE PRICE IS THE EXPECTED MOVE, to a good approximation, and that approximation is
    named in the payload rather than buried: the market's own price for "either direction by
    expiry". It is NOT derived from an implied volatility here, because a plan-tier gated
    `implied_volatility` field has already been a null in this repo and a straddle's two mids
    are prices that are always there when the chain is.

    An unavailable leg returns an UNAVAILABLE block with its reason -- never a one-sided
    estimate doubled, which would read as a measurement.
    """
    if spot is None or call_mid is None or put_mid is None:
        missing = [n for n, v in (("spot", spot), ("ATM call", call_mid), ("ATM put", put_mid))
                   if v is None]
        return {"available": False, "label": label,
                "reason": "no expected move: %s unavailable" % ", ".join(missing)}
    dollars = call_mid + put_mid
    return {
        "available": True,
        "label": label,
        "dollars": round(dollars, 2),
        "pct": round(100.0 * dollars / spot, 2),
        "value": "±$%.0f · ±%.1f%%" % (dollars, 100.0 * dollars / spot),
        "days": ("%dd" % days) if days is not None else None,
        "approx": True,
        "basis": ("the ATM straddle's two mid prices (call %.2f + put %.2f) against spot "
                  "%.2f: the market's own price for a move either way by expiry, which is an "
                  "approximation of the expected move and is labelled one"
                  % (call_mid, put_mid, spot)),
    }
