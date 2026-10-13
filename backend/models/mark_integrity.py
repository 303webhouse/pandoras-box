"""What a stored mark is WORTH as evidence — R-IV.935(c)1, gated by TA-152.

THE THREE THINGS THE PRINCIPAL SAW. WEAT's displayed mark was 13 days old; KRE's and HYG's were
fresh but computed from books 3-4x wide; ORCL's came from a contract with ZERO volume and no
last trade at all. None of those is a wrong number in the arithmetic sense — each is the correct
mid of something. The defect is that all four cases looked identical on the surface.

FOUR WORDS, NOT A NUMBER (R-IV.935(e)): `ok`, `stale`, `wide`, `unknown`, each with a reason
string. A page cannot be asked to decide what 0.46 means; it can be asked to show a word.

CONVENTION #38, ADOPTED BY TA-152: a freshness guard belongs to the DECISION, not the data
store. So this module reports `stale` as a DISPLAY verdict on the 26-hour bound, and the B2 gate
does not use it: that gate needs a mark at or after its own cut session's close, which is a
stricter and different question. Each consumer states the freshness its own decision needs, and
nothing here decides on anyone's behalf.

WHY `wide` EXISTS AT ALL. `compute_mark` accepts ANY two-sided quote, however far apart the two
sides are -- so ORCL's 0.11/0.46 book on a contract that had not traded once that day produced
a confident 0.285. `compute_bid_ask_spread_pct` already lived in utils/options_math.py, used by
DAEDALUS's liquidity flag, and was simply never wired into the mark rule.

EVERY THRESHOLD IS HERE (R-IV.935(e)3). One place in the backend, so the page never picks one
and no second copy can drift.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

OK = "ok"
STALE = "stale"
WIDE = "wide"
UNKNOWN = "unknown"

#: The DISPLAY freshness bound. Deliberately generous: this is a "the feed died" bound, not a
#: tick-level rule, and it is the same 26 hours `mark_guard.MARK_MAX_AGE` already uses -- that
#: constant is the one author and this module reads it rather than restating the number.
from api.mark_guard import MARK_MAX_AGE  # noqa: E402

#: A book wider than this, measured as (ask - bid) / mid, is not a price anyone could trade at.
#:
#: 50% CHOSEN, AND REPORTED. The measured cases it must catch: ORCL 65P at 0.11/0.46 is 123% of
#: mid, KRE 60P at 0.40/1.13 is 95%, HYG 76P at 0.20/0.57 is 96%. The case it must NOT catch:
#: IBIT 43P at 0.06/0.07 is 15%, on 2,175 contracts traded. 50% sits with a wide margin on both
#: sides of that gap, and well above the 10% DAEDALUS uses for a liquidity WARNING -- a mark is
#: allowed to be less liquid than an entry before it stops being evidence.
WIDE_SPREAD_PCT = 50.0

#: ...AND the book must be wider than this in absolute terms before `wide` is returned.
#:
#: WHY BOTH. A percentage alone is meaningless at tick-level prices: a 0.01/0.02 quote is the
#: TIGHTEST book obtainable and still reads as 67% of its 1.5-cent mid. IBIT 980's short leg is
#: exactly that, and a percentage-only rule flagged the spread `wide` -- holding the one cut
#: TA-152's own fallback calls valid. Measured separation: the three real offenders are 0.35,
#: 0.73 and 0.37 wide; the tick-level cases are 0.01. This sits 7x below the narrowest offender
#: and 5x above the tick cases.
WIDE_SPREAD_MIN_ABS = 0.05

REASON_NO_MARK = "no mark recorded"
REASON_NO_TIMESTAMP = "mark has no timestamp, so its age cannot be established"
REASON_NAIVE = "mark timestamp has no timezone -- refusing to assume one"


def _aware(ts: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """(aware datetime, error). A naive timestamp is REFUSED, not assumed into UTC: guessing a
    zone here is how a mark taken at 16:47 ET reads as fresh at 16:47 UTC, six hours early."""
    if ts is None:
        return None, REASON_NO_TIMESTAMP
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None, "mark timestamp %r is not a timestamp" % (ts,)
    if not isinstance(ts, datetime):
        return None, "mark timestamp %r is not a timestamp" % (ts,)
    if ts.tzinfo is None:
        return None, REASON_NAIVE
    return ts, None


def spread_pct(bid: Any, ask: Any) -> Optional[float]:
    """(ask - bid) / mid, as a percentage, or None when it cannot be computed.

    None is returned rather than 0.0 whenever either side is missing: a one-sided book has no
    width, and calling that zero would report the tightest possible market.
    """
    try:
        b, a = float(bid), float(ask)
    except (TypeError, ValueError):
        return None
    if b <= 0 or a <= 0 or a < b:
        return None
    mid = (a + b) / 2.0
    if mid <= 0:
        return None
    return (a - b) / mid * 100.0


def abs_spread(bid: Any, ask: Any) -> Optional[float]:
    """ask - bid, or None when it cannot be computed."""
    try:
        b, a = float(bid), float(ask)
    except (TypeError, ValueError):
        return None
    if b <= 0 or a <= 0 or a < b:
        return None
    return round(a - b, 6)


def is_wide(width_pct: Optional[float], abs_width: Optional[float]) -> bool:
    """BOTH bounds must be breached. The one author for this question, so the job's worst-leg
    check and this module's own check cannot drift apart."""
    if width_pct is None or abs_width is None:
        return False
    return width_pct > WIDE_SPREAD_PCT and abs_width > WIDE_SPREAD_MIN_ABS


def evaluate(mark: Any, *, mark_as_of: Any = None, bid: Any = None, ask: Any = None,
             now: Optional[datetime] = None) -> Tuple[str, str]:
    """(verdict, reason). Pure, and NEVER raises.

    Order is absent -> unmeasurable -> wide -> stale -> ok, because an absent mark has no width
    and no age, and a mark from an untradeable book is not rescued by being recent.
    """
    if mark is None:
        return UNKNOWN, REASON_NO_MARK
    try:
        if float(mark) <= 0:
            return UNKNOWN, "mark %r is not a positive price" % (mark,)
    except (TypeError, ValueError):
        return UNKNOWN, "mark %r is not a number" % (mark,)

    width = spread_pct(bid, ask)
    if width is not None and is_wide(width, abs_spread(bid, ask)):
        return WIDE, ("the book is %.0f%% of mid wide and %s wide absolutely (bid %s / ask %s), "
                      "over the %.0f%% / %s bounds -- not a price anyone could trade at"
                      % (width, abs_spread(bid, ask), bid, ask, WIDE_SPREAD_PCT,
                         WIDE_SPREAD_MIN_ABS))

    ts, err = _aware(mark_as_of)
    if err:
        # Unknown, NOT ok: "I could not establish the age" and "it is fresh" are different
        # facts, and the whole defect this closes was the two looking identical.
        return UNKNOWN, err
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now - ts
    if age > MARK_MAX_AGE:
        return STALE, ("the mark is %.1f hours old (%s), past the %.0f-hour display bound"
                       % (age.total_seconds() / 3600.0, ts.isoformat(),
                          MARK_MAX_AGE.total_seconds() / 3600.0))
    if age < -timedelta(minutes=5):
        return UNKNOWN, "the mark is timestamped %s, in the future" % ts.isoformat()
    return OK, "mark %s as of %s" % (mark, ts.isoformat())


def is_gateable(verdict: Optional[str]) -> bool:
    """May a DECISION be taken on a mark carrying this verdict?

    `wide` and `unknown` are refused: the first is not a tradeable price, the second is not a
    measurement. `stale` is NOT refused here -- it is a display verdict, and a consumer that
    needs recency states its own requirement (TA-152, Convention #38). The B2 gate does exactly
    that, and its requirement is stricter than 26 hours.
    """
    return verdict not in (WIDE, UNKNOWN)


def describe(verdict: Optional[str], reason: Optional[str], mark: Any,
             mark_as_of: Any) -> str:
    """One line for an alert body: the mark, its timestamp and its flag (R-IV.935(c)3)."""
    stamp = mark_as_of.isoformat() if isinstance(mark_as_of, datetime) else (mark_as_of or "no timestamp")
    return "mark %s as of %s [%s%s]" % (
        mark if mark is not None else "none", stamp, verdict or UNKNOWN,
        ": %s" % reason if reason else "")


def payload(mark: Any, *, mark_as_of: Any = None, bid: Any = None, ask: Any = None,
            now: Optional[datetime] = None) -> Dict[str, Any]:
    """The serving shape (R-IV.935(d)/(e)): an exact instant, a word, and a reason."""
    verdict, reason = evaluate(mark, mark_as_of=mark_as_of, bid=bid, ask=ask, now=now)
    ts, _ = _aware(mark_as_of)
    return {
        "mark": mark,
        "mark_as_of": ts.astimezone(timezone.utc).isoformat() if ts else None,
        "mark_integrity": verdict,
        "mark_integrity_reason": reason,
    }
