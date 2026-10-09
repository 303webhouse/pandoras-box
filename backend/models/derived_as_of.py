"""R-IV.775(f) and R-IV.792(b) — a derived figure carries its OWN as-of.

THE DEFECT. The balances payload showed the stored row's `updated_at` beside a live-derived
value, so Trade Analysis read POSITIONS' Roth cash — 7,847.90, derived and current — as a
2026-09-24 figure. One timestamp sat next to two figures of different ages and was taken to
describe both. Nothing was wrong with either number; the payload simply did not say which
instant belonged to which.

THE SHAPE, copied from `/api/abacus/summary`, which already does this correctly: an as-of PER
BLOCK, not one per payload, and the blocks are expected to disagree. There, `scope` and `equity`
carry the current instant while `leaks` and `strategies` stay frozen at 2026-09-17 because they
are still mock — and that disagreement is the information.

R-IV.792(b), drift. A difference between a stored figure and a live one measures drift only when
BOTH sides are fresh. Measured on the live book: `account_balance` was 14.3 days old while
`computed_balance` was computed on request, and the payload published their difference —
2,782.43 — under the name `drift_dollars`. Most of that is staleness, not drift. Past 24 hours
the figure is withheld and the reason is published in its place.

AN UNKNOWN AGE IS NOT FRESHNESS. A missing `stored_as_of` makes the stored side stale here, not
eligible. Reading an absent fact as a satisfied condition is this register's recurring failure,
and it is the whole mechanism of the defect above.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

# R-IV.792(b). Stated once: the route, the reason string and the tests all read it from here.
STORED_STALE_AFTER_SECONDS = 24 * 3600

# The name the payload uses for a figure computed on request, kept distinct from the stored
# row's `updated_at` so the two can never again be read as one instant.
DERIVED_KEY = "computed_at"
STORED_KEY = "updated_at"


def _iso(instant: Any) -> Optional[str]:
    if instant is None:
        return None
    try:
        return instant.isoformat()
    except AttributeError:
        return str(instant)


def stored_age_seconds(stored_as_of: Any, now: Any) -> Optional[float]:
    """How old the stored row is, or None when that cannot be established."""
    if stored_as_of is None or now is None:
        return None
    try:
        return (now - stored_as_of).total_seconds()
    except TypeError:
        # A naive timestamp against an aware one. This module never adjudicates clocks: reading
        # one through the wrong offset invents six hours and a day boundary.
        return None


def is_stored_stale(stored_as_of: Any, now: Any,
                    window_seconds: int = STORED_STALE_AFTER_SECONDS) -> bool:
    """Older than the window, or of unknown age. Unknown counts as stale, deliberately."""
    age = stored_age_seconds(stored_as_of, now)
    if age is None:
        return True
    return age > window_seconds


def drift_between(stored: Any, computed: Any, *, stored_as_of: Any, now: Any,
                  window_seconds: int = STORED_STALE_AFTER_SECONDS
                  ) -> Tuple[Optional[float], str]:
    """`(drift_dollars, drift_basis)`. The value is None whenever it would not mean drift.

    The basis is returned alongside and is never optional: a withheld figure with no reason is
    indistinguishable from a figure of zero, and the one reader of this field treats a falsy
    value as "nothing to report" — which would turn a two-week staleness into silence.
    """
    if stored is None or computed is None:
        return None, "drift needs both a stored and a computed balance"
    age = stored_age_seconds(stored_as_of, now)
    if age is None:
        return None, "stored balance stale (as-of unknown)"
    if age > window_seconds:
        return None, "stored balance stale (as-of %s)" % _iso(stored_as_of)
    return round(float(stored) - float(computed), 2), \
        "both sides fresh (stored as-of %s)" % _iso(stored_as_of)


def as_of_block(*, derived_at: Any, stored_as_of: Any, now: Any,
                derived_fields: Optional[Tuple[str, ...]] = None,
                stored_fields: Optional[Tuple[str, ...]] = None,
                window_seconds: int = STORED_STALE_AFTER_SECONDS) -> dict:
    """The per-block as-of, naming WHICH fields each instant describes.

    Listing the fields is the point. The defect was not an absent timestamp — there was one —
    but a timestamp whose scope nobody had written down, so a reader attached it to the figure
    it happened to sit beside.
    """
    age = stored_age_seconds(stored_as_of, now)
    return {
        "derived": {
            DERIVED_KEY: _iso(derived_at),
            "basis": "computed on request from the live book",
            "fields": list(derived_fields or ()),
        },
        "stored": {
            STORED_KEY: _iso(stored_as_of),
            "basis": "as the principal last recorded it",
            "fields": list(stored_fields or ()),
            "age_seconds": None if age is None else round(age, 1),
            "stale": is_stored_stale(stored_as_of, now, window_seconds),
            "stale_after_seconds": window_seconds,
        },
    }
