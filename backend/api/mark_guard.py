"""T1 — the mark guard. R-IV.394, ordered FIRST by R-IV.271(e).

`unified_positions` recomputed `unrealized_pnl` from `current_price` with no check
that the mark was present, fresh or sane, and wrote the result unconditionally.

THE ORDER IS LOAD-BEARING. Every later task in the ledger brief reads numbers that
write produces. Fixing the account vocabulary while the marks are unguarded yields a
WELL-NAMED WRONG ANSWER, which is harder to detect than an obviously wrong one --
because the name now looks right.

THE RULE: on any failure, WRITE NOTHING to unrealized_pnl. Do not write zero.

    A zero P&L is a CLAIM: "this position is flat."
    It is indistinguishable from a real flat position on every surface downstream.
    An absent update leaves the previous value standing, stamped with the reason
    it was not refreshed -- which a reader can act on. A zero cannot be
    distinguished from a measurement, which is the absent-vs-real collapse this
    register has filed five times, landed on money.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

MARK_OK = "OK"
MARK_STALE = "STALE"
MARK_REJECTED = "REJECTED"
MARK_ABSENT = "ABSENT"

# A mark older than this cannot price a position. Deliberately generous: this is a
# "the feed died" bound, not a tick-level freshness rule, and a tight value here
# would reject good marks over a weekend.
MARK_MAX_AGE = timedelta(hours=26)

# Sanity bounds. A mark outside these is not a price.
MARK_MIN = 0.0001
MARK_MAX = 1_000_000.0
# A mark this far from the entry is far more likely a units error (cents vs
# dollars, per-share vs per-contract) than a real move. Rejecting is recoverable;
# writing a P&L computed from it is not.
MARK_MAX_RATIO = 100.0


def evaluate_mark(
    current_price: Any,
    entry_price: Any = None,
    price_asof: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Tuple[str, Optional[str]]:
    """(status, reason). NEVER raises.

    Predicates in the order present -> sane -> fresh, because an absent mark has no
    freshness and a malformed one has no magnitude worth comparing.
    """
    # ── present ──
    if current_price is None:
        return MARK_ABSENT, "no mark"
    try:
        px = float(current_price)
    except (TypeError, ValueError):
        return MARK_REJECTED, "mark not numeric: %r" % (current_price,)
    if px != px or px in (float("inf"), float("-inf")):
        return MARK_REJECTED, "mark is not finite"

    # ── sane ──
    if px <= 0:
        return MARK_REJECTED, "mark <= 0 (%s)" % px
    if px < MARK_MIN or px > MARK_MAX:
        return MARK_REJECTED, "mark %s outside [%s, %s]" % (px, MARK_MIN, MARK_MAX)
    if entry_price is not None:
        try:
            ep = float(entry_price)
            if ep > 0:
                ratio = px / ep if px > ep else ep / px
                if ratio > MARK_MAX_RATIO:
                    return MARK_REJECTED, (
                        "mark %s is %.0fx entry %s — units error more likely than move"
                        % (px, ratio, ep))
        except (TypeError, ValueError, ZeroDivisionError):
            pass          # an unusable ENTRY does not condemn the MARK

    # ── fresh ──
    if price_asof is not None:
        n = now or datetime.now(timezone.utc)
        a = price_asof if price_asof.tzinfo else price_asof.replace(tzinfo=timezone.utc)
        age = n - a
        if age > MARK_MAX_AGE:
            return MARK_STALE, "mark is %.1f h old (max %.0f h)" % (
                age.total_seconds() / 3600, MARK_MAX_AGE.total_seconds() / 3600)
    # price_asof absent = UNKNOWN freshness, which is not STALE. Nothing here
    # invents an age; the absence of a vintage is a gap in the schema, not
    # evidence about the mark.

    return MARK_OK, None


def mark_is_writable(status: str) -> bool:
    """Only an OK mark may produce a P&L write. The one place this is decided."""
    return status == MARK_OK
