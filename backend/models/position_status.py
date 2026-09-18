"""What a position's status means, and which rows count (R-IV.449(a)).

A status is read two ways in this codebase: by naming the one you want (`status = 'OPEN'`) and
by naming the one you don't (`status != 'OPEN'`). The second form treats every non-open value
as a completed trade, which was harmless while the only other values were CLOSED and EXPIRED —
and stops being harmless the moment a row exists that is neither open nor a result.

A duplicate and an absence present identically, and the remedies are opposite: one wants
a row written, the other wants a row stopped from counting, and both read as an empty
result from the wrong query. DUPLICATE_OF is exactly such a row. It records a trade the book already holds under another
position_id: the fills happened once, so its money must be counted once. Retiring the duplicate
by deletion would destroy the evidence of the duplication, and leaving it CLOSED would double
every figure computed from it. It is kept, marked, and pointed at its keeper.

So the vocabulary is written down once, with the question every consumer actually has --
"does this row's money count?" -- answered here rather than re-derived at each call site.
"""

from __future__ import annotations

from typing import Optional

OPEN = "OPEN"
CLOSED = "CLOSED"
EXPIRED = "EXPIRED"
DUPLICATE_OF = "DUPLICATE_OF"

STATUSES = (OPEN, CLOSED, EXPIRED, DUPLICATE_OF)

# Rows whose realized result is the book's. A duplicate's result belongs to its keeper, and
# counting both is the double-count this status exists to prevent.
REALIZED_STATUSES = frozenset({CLOSED, EXPIRED})
# Rows that are neither open nor a result: retired, kept for evidence, counted nowhere.
RETIRED_STATUSES = frozenset({DUPLICATE_OF})


def normalize(status: Optional[str]) -> str:
    return (status or "").strip().upper()


def is_open(status: Optional[str]) -> bool:
    return normalize(status) == OPEN


def counts_as_realized(status: Optional[str]) -> bool:
    """True when this row's realized figure is the book's own.

    Deliberately NOT `not is_open(status)`. That form is what makes a retired duplicate read
    as a completed trade, and it is the reason this function exists at all.
    """
    return normalize(status) in REALIZED_STATUSES


def is_retired(status: Optional[str]) -> bool:
    """True when the row is kept as evidence and counted nowhere."""
    return normalize(status) in RETIRED_STATUSES
