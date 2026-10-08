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
# R-IV.761(b). Rows whose realized MONEY counts. This is a DIFFERENT QUESTION from whether the
# trade is complete, and conflating the two is what hid 107.48 of real gains:
#
#   "is this trade finished?"      -> REALIZED_STATUSES. Governs win rate, per-trade return,
#                                    hold time, the equity curve. A partially-exited position is
#                                    NOT a finished trade and must not enter those.
#   "does this row's money count?" -> MONEY_STATUSES. Governs the realized total. A partial exit
#                                    books real money on a row that is still OPEN, and that money
#                                    is in the account whatever the row's status says.
#
# Measured 2026-10-08: three OPEN rows carried realized (HYG 516 52.00, PDBC 953 8.48, IWM 956
# 47.00 = 107.48), and the closed-only aggregate reported 3,500.25 against a true 3,607.73.
# DUPLICATE_OF is excluded from both, for the reason this module exists.
MONEY_STATUSES = frozenset({OPEN, CLOSED, EXPIRED})


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


def realized_money_counts(status: Optional[str]) -> bool:
    """True when this row's realized MONEY belongs in the book's realized total (R-IV.761(b)).

    NOT a synonym for `counts_as_realized`. That one answers "is the trade finished?" and is
    right for win rate and per-trade return; this one answers "is this money in the account?"
    and is right for the realized total. An OPEN row with a partial exit answers no to the first
    and yes to the second, and treating the two as one question is the defect this pair replaces.

    Also NOT `not is_retired(status)`: an unrecognised status answers no here. A value this
    vocabulary has never seen is not evidence that its money counts, and the same reasoning that
    rejects `!= 'OPEN'` rejects `not is_retired` -- both read an unknown as a yes.
    """
    return normalize(status) in MONEY_STATUSES


def is_retired(status: Optional[str]) -> bool:
    """True when the row is kept as evidence and counted nowhere."""
    return normalize(status) in RETIRED_STATUSES


# ── BACKFILL EXEMPTION (R-IV.454(c)) ───────────────────────────────────────────────────────
#
# NO BLANKET BACKFILL OF "CLOSED WITH NO REALIZED" — EVER. The rows in that state are not one
# thing: some are honest absences (the record cannot support a figure), some are duplicates
# (where a backfill would count the same trade twice, for real), and some are ends nobody
# recorded. Six groups got six reads, not one remedy.
#
# A row carrying `backfill_exempt_reason` must not be written by any sweep. The mark is a
# REASON rather than a flag so the next sweep that meets it reads why it must stop.
def is_backfill_exempt(row) -> bool:
    """True when a row is marked exempt from every backfill. Accepts a mapping or a record."""
    try:
        return bool((row.get("backfill_exempt_reason") or "").strip())
    except AttributeError:
        return False
