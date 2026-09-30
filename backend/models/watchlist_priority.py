"""What `watchlist_tickers.priority` means, and how it orders. R-IV.610(c).

THE DEFECT. The collector ordered its watchlist with

    ORDER BY COALESCE(priority, 999), symbol ASC

and that query **fails outright** — `COALESCE types character varying and integer cannot be
matched`. The column is `character varying`, holding the labels `'low'` and `'normal'`, and it is
`NOT NULL`, so the COALESCE was both type-invalid and pointless. Its author had assumed a numeric
priority.

The failure was invisible because the call site wraps it in `except Exception: logger.debug(...)`
— at DEBUG, so in production the watchlist silently contributed **nothing** to the collector and
nothing anywhere said so. A query that has never once succeeded looked exactly like a watchlist
with no rows in it.

FIXED AT THE CAUSE, which is that a label has no natural order. The rank lives here, once, and
the SQL is generated from it. A third label added to the column without being added here sorts
LAST rather than arbitrarily, and `test_watchlist_priority` fails against the live table — so it
is caught rather than silently mis-ordered, which is the failure mode this replaces.
"""

from __future__ import annotations

from typing import Optional

HIGH = "high"
NORMAL = "normal"
LOW = "low"

# Lower sorts first. `high` is not in the column today but is the obvious next label, and leaving
# it out would mean the first row to use it sorted last.
RANK: dict = {HIGH: 0, NORMAL: 1, LOW: 2}

# Anything unknown sorts after everything known, rather than in an order nobody chose.
UNKNOWN_RANK = 99

PRIORITIES = tuple(sorted(RANK, key=lambda k: RANK[k]))


def rank(priority: Optional[str]) -> int:
    """The sort position of a label. Unknown and NULL both sort last."""
    return RANK.get((priority or "").strip().lower(), UNKNOWN_RANK)


def order_by_sql(column: str = "priority") -> str:
    """A CASE expression ordering the labels, GENERATED from `RANK` rather than retyped.

    Retyping it in the query is how the two come apart, and a mis-ordered watchlist is the kind
    of wrong that never raises.
    """
    whens = " ".join("WHEN '%s' THEN %d" % (label, RANK[label]) for label in PRIORITIES)
    return "CASE lower(%s) %s ELSE %d END" % (column, whens, UNKNOWN_RANK)
