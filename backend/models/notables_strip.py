"""The NOTABLES option strip: its wording and its own spending cap. R-IV.1265(c)-(d).

(c) THE IV-RANK TAG, RESOLVED BY WORDING. R-IV.1259(f) specified the tag as "cheap below 30,
neutral 30-60, rich above 60" while (g) banned the word "cheap" from every card -- so one ruling
mandated and forbade the same word on the same card. R-IV.1265(c) settles it:

    below 30      "IV LOW"
    30 to 60      "IV MID"
    above 60      "IV HIGH"

and "cheap" stays banned everywhere. The band edges are written as ONE comparison each, because
"30-60" and "below 30" could both be read to own 30 -- two numbers for one threshold is a fault
class this board has filed before. 30 and 60 both belong to MID, by the rule below, and a test
pins both edges.

(d) FIFTY CALLS A DAY, HARD-CAPPED HERE AS WELL AS IN THE GOVERNOR. The governor already refuses
a tag past its quota, and `notables_strip` is registered there at 50 with the safety buffer cut
from 2,000 to 1,950 to fund it. This module caps again, independently, for one reason: the
governor's enforcement is a MODE (`observe` / `enforce`), and a cap that only exists while a
global switch is in one position is not a cap. At the cap the strip renders
`UNAVAILABLE_TEXT` -- never a stale price presented as current, which R-IV.1259(f) rules out in
those words.

THE COUNT HAS ONE AUTHOR. This module does not keep its own tally: it asks the governor's spend
ledger for the tag's count, which is the same number `/api/uw/governor` serves and the same one
the other 38 callers are judged by. A second counter would drift from the first, and the one
that drifted would be the one nobody reconciled.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("notables_strip")

#: The governor tag. Matches the `caller=` string passed at the call site and the key in
#: `uw_governor.QUOTAS`, so the daily count is logged beside the others (R-IV.1265(d)).
UW_CALLER = "notables_strip"

#: R-IV.1265(d). Kept here as well as in the governor so the two must agree; a test asserts it.
DAILY_CALL_CAP = 50

#: R-IV.1259(f)'s words, kept verbatim. The em dash is the ruling's.
UNAVAILABLE_TEXT = "Options data unavailable — chart only"

#: R-IV.1259(f)'s other refusal state, for a liquid-enough chain whose 1x rung is too wide.
TOO_THIN_TEXT = "Options too thin — chart only"

#: The 1x rung's spread thresholds (R-IV.1259(f)): green at or below 5%, amber 5-10%, and above
#: 10% the strip collapses. One comparison per edge, same reason as the IV bands.
SPREAD_GREEN_MAX = 5.0
SPREAD_AMBER_MAX = 10.0

#: (c)'s band edges. Written as the two cut points, with the ownership of each edge decided by
#: `iv_rank_label` and nowhere else.
IV_LOW_BELOW = 30.0
IV_HIGH_ABOVE = 60.0

IV_LOW = "IV LOW"
IV_MID = "IV MID"
IV_HIGH = "IV HIGH"

#: Every label this module may put on a card. A test asserts the banned vocabulary is disjoint
#: from it, so (c)'s wording cannot drift back into (g)'s banned list.
IV_LABELS = (IV_LOW, IV_MID, IV_HIGH)


def iv_rank_label(rank: Optional[float]) -> Optional[str]:
    """(c)'s tag for an IV rank, or None when there is no rank.

    NONE IS NOT A BAND. A missing rank renders nothing rather than defaulting to MID: a card
    that says "IV MID" because it could not read the rank is a caption lying about its field,
    and MID is the band a reader is least likely to question.

    The edges: 30 and 60 both read MID. `< 30` is LOW and `> 60` is HIGH, so each edge is owned
    by exactly one comparison and the two bands cannot both claim it.
    """
    if rank is None:
        return None
    try:
        r = float(rank)
    except (TypeError, ValueError):
        return None
    if r != r:                                  # NaN, which compares false against everything
        return None
    if r < IV_LOW_BELOW:
        return IV_LOW
    if r > IV_HIGH_ABOVE:
        return IV_HIGH
    return IV_MID


def iv_rank_tone(label: Optional[str]) -> Optional[str]:
    """The card's colour token for a band. Display only; it carries no threshold of its own."""
    return {IV_LOW: "low", IV_MID: "mid", IV_HIGH: "high"}.get(label or "")


def spread_light(spread_pct: Optional[float]) -> Tuple[Optional[str], bool]:
    """(light, collapse). `collapse` is True when the strip must render TOO_THIN_TEXT instead.

    A MISSING SPREAD COLLAPSES THE STRIP. "Could not measure the spread" and "the spread is
    fine" must not render alike -- failing open on "could not tell" is a fault class this board
    has filed repeatedly, and here it would put a quote on a card whose tradeability is unknown.
    """
    if spread_pct is None:
        return None, True
    try:
        s = float(spread_pct)
    except (TypeError, ValueError):
        return None, True
    if s != s:
        return None, True
    if s <= SPREAD_GREEN_MAX:
        return "green", False
    if s <= SPREAD_AMBER_MAX:
        return "amber", False
    return "red", True


async def calls_used_today(conn=None) -> Optional[int]:
    """The tag's count today, from the governor's own ledger. None when it cannot be read.

    NONE IS NOT ZERO. An unreadable counter must not read as "nothing spent yet", because that
    is the answer that lets the strip spend without limit. `budget_state` turns None into a
    refusal.
    """
    try:
        from integrations.uw_api_cache import get_caller_count_or_none

        # `get_caller_count_or_none` is the OR_NONE variant on purpose (R-IV.901(c)2):
        # `get_caller_count` returns 0 on a failed read, which makes "no calls yet" and "Redis
        # is unreachable" the same answer and lets a cap fail open to unlimited.
        n = await get_caller_count_or_none(UW_CALLER)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[notables] caller count unreadable: %s", type(exc).__name__)
        return None
    return None if n is None else int(n)


async def budget_state(conn=None) -> Dict[str, Any]:
    """Whether the strip may make a UW call, with the reason either way.

    Three answers, and the two that are not "yes" are different facts:
      * `allowed` with the remaining count;
      * refused because the cap is reached -- the strip renders UNAVAILABLE_TEXT;
      * refused because the count could not be READ -- also UNAVAILABLE_TEXT, because a cap
        that cannot be measured is not a cap, but the reason says which it was.
    """
    used = await calls_used_today(conn)
    if used is None:
        return {"allowed": False, "used": None, "cap": DAILY_CALL_CAP, "remaining": None,
                "caller": UW_CALLER, "text": UNAVAILABLE_TEXT,
                "reason": ("the %s daily call count could not be read, so the cap cannot be "
                           "enforced; the strip refuses rather than spending unmeasured"
                           % UW_CALLER)}
    remaining = DAILY_CALL_CAP - used
    if remaining <= 0:
        return {"allowed": False, "used": used, "cap": DAILY_CALL_CAP, "remaining": 0,
                "caller": UW_CALLER, "text": UNAVAILABLE_TEXT,
                "reason": ("%s has used %d of its %d calls today (R-IV.1265(d)); no stale price "
                           "is served in place of a live one"
                           % (UW_CALLER, used, DAILY_CALL_CAP))}
    return {"allowed": True, "used": used, "cap": DAILY_CALL_CAP, "remaining": remaining,
            "caller": UW_CALLER, "text": None,
            "reason": "%d of %d calls left today" % (remaining, DAILY_CALL_CAP)}
