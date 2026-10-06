"""`open_quantity` — what is still open, served so no consumer computes it (R-IV.660(b)2).

CONVENTION #29 names two figures and they are not interchangeable:

    quantity        the size OPENED, adds included -- what the principal took on
    open_quantity   the OPEN REMAINDER, SUM(lot qty) -- what is still held

Every consumer that wants "how big is this position right now" wants the second one, and before
this module existed the only field on the payload was the first. A reader asking the row how
much it holds got the size it had been opened at, which on a partially-closed position is too
large -- and after R-IV.657(c) correctly stopped `/close` from shrinking `quantity`, that
overstatement applied to every partially-closed row in the book. Serving the remainder is what
makes that fix safe to leave in place.

The figure is NOT stored. A column would be a fourth writer of something the lots already
say, and it would be wrong for exactly as long as it took a lot to be added without it.

One query per response, never one per row: `fetch_lots_by_position` is the existing author of
the batched lot read, and the addition is `position_economics.open_remainder`, which answers
None where the lot set cannot support a figure. Nothing here re-adds anything.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from models.position_status import OPEN, normalize

# The basis travels with the figure. A consumer that gets a number and no account of where it
# came from cannot tell a measured remainder from a fallback, and the two license different
# decisions -- which is the whole lesson of the ceiling's PARTIAL mark.
BASIS_LOTS = "lots"
BASIS_NO_LOTS = "unknown: the position has no lots"
BASIS_NOT_OPEN = "0: the position is not open"


def open_quantity_of(position: Dict[str, Any],
                     lots: Optional[Iterable[Dict[str, Any]]]) -> Dict[str, Any]:
    """`{open_quantity, open_quantity_basis}` for one position and its lots.

    Three cases, each answered rather than collapsed:

    * LOTS PRESENT -- the remainder they sum to. This is the answer in every live case today:
      all 28 open rows have lots (measured 2026-10-06).
    * NO LOTS, OPEN -- None, not the row's `quantity`. Substituting `quantity` would assert a
      remainder the book has no record of, and a never-lotted row is exactly the row whose
      size is least trustworthy. None with a reason is the honest answer; zero would read as
      a flat position, which is the opposite fact.
    * NOT OPEN -- zero. A closed, expired or retired row holds nothing. Where its lots
      disagree (an expiry that was never lotted as a disposal, which 5 EXPIRED rows show
      today) the basis SAYS so instead of the contradiction being resolved silently.
    """
    from services.position_economics import open_remainder

    status = normalize(position.get("status"))
    lots = list(lots or [])
    remainder = open_remainder(lots)

    if status and status != OPEN:
        basis = BASIS_NOT_OPEN
        if remainder is not None and float(remainder) != 0.0:
            basis = (f"{BASIS_NOT_OPEN} ({status}), though its lots still sum to "
                     f"{float(remainder)} - the disposal was never lotted")
        return {"open_quantity": 0.0, "open_quantity_basis": basis}

    if remainder is None:
        return {"open_quantity": None, "open_quantity_basis": BASIS_NO_LOTS}
    return {"open_quantity": float(remainder), "open_quantity_basis": BASIS_LOTS}


def stamp_open_quantity_from_lots(positions: List[Dict[str, Any]],
                                  lots_by_position: Dict[str, List[Dict[str, Any]]]) -> None:
    """Stamp both fields where the caller ALREADY holds the lots. In place.

    Separate from the async form on purpose: a site that has just fetched the lots must not
    fetch them again, and a site that has not must not be able to forget to.
    """
    for p in positions or []:
        if isinstance(p, dict):
            p.update(open_quantity_of(p, (lots_by_position or {}).get(p.get("position_id"))))


async def stamp_open_quantity(conn, positions: List[Dict[str, Any]]
                              ) -> List[Dict[str, Any]]:
    """Stamp both fields on every position dict, in place. ONE lot query for the whole list.

    Returns the same list, so a route can wrap its serialiser in one call.
    """
    rows = [p for p in (positions or []) if isinstance(p, dict)]
    if not rows:
        return positions
    from services.read_only.positions import fetch_lots_by_position

    lots_by = await fetch_lots_by_position(
        conn, [p.get("position_id") for p in rows])
    for p in rows:
        p.update(open_quantity_of(p, lots_by.get(p.get("position_id"))))
    return positions
