"""Lots, and the position figures DERIVED from them. Pure -- no database, no network.

The position row is the AGGREGATE. Entry price, cost basis and everything computed from them
derive from the lot set and are never maintained independently of it (R-IV.310(b)); a stored
aggregate that is separately maintained drifts from the lots it claims to summarise, and every
figure over it is then defensible and unverifiable at the same time.

Three rules live here because all three are arithmetic, and arithmetic is testable without a
database:

  PROVENANCE IS INHERITED, NEVER DEFAULTED (T6d).  A lot's provenance answers "how do we know
  this?", which is not the same question as "is it open?". A new lot takes its value from how
  it arrived; a backfilled lot takes it from the parent position row. Nothing here ever returns
  BROKER_VERIFIED -- that value is reachable only by matching a broker record, and a stamp
  nothing checked is an assertion about an assertion.

  AN UNKNOWN PRICE MAKES ITS AGGREGATE UNKNOWN.  A lot with no price still moves quantity. Its
  cost is not zero (a zero price claims the shares were free and flows into every derived
  figure as a number nobody can distinguish from a measurement) and it is not absent (a
  position whose lots do not sum to its quantity is a broken aggregate). So the quantity stays
  known and the basis reads UNKNOWN until the price arrives.

  BASIS IS GROSS, AND THE MULTIPLIER IS THE ASSET'S.  Fees are summed and reported beside the
  basis, never folded into the per-unit price -- the book's convention is gross (R-IV.312(a)),
  and the fee delta is the one measurement the gross/net normalization depends on. Contracts
  are 100 shares: measured on the book itself, 176 of 264 OPTION rows and 15 of 16 SPREAD rows
  carry cost_basis == qty x entry x 100, and no EQUITY row does.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

# --- vocabulary ---------------------------------------------------------------------------
PRINCIPAL_REPORTED = "PRINCIPAL_REPORTED"
BROKER_VERIFIED = "BROKER_VERIFIED"
IMPORTED = "IMPORTED"
UNKNOWN = "UNKNOWN"
PROVENANCE_VALUES = (PRINCIPAL_REPORTED, BROKER_VERIFIED, IMPORTED, UNKNOWN)

# Parent-position sources that mean "this row landed through an import path". Measured over the
# live book 2026-09-17; the mapping is mirrored in migrations/037_position_lots_ruled_shape.sql,
# which applies it once to the rows that predate this module.
IMPORT_PARENT_SOURCES = frozenset({
    "IMPORTED_HISTORICAL", "CSV_IMPORT", "CSV_SYNC", "CSV_RECONCILE", "fidelity_confirm",
})
# Lot sources the write path accepts. LEGACY-SINGLE-LOT is the 2026-08-26 backfill's and is not
# writable through the API.
LOT_SOURCE_PROVENANCE = {"MANUAL": PRINCIPAL_REPORTED, "IMPORT": IMPORTED}

CONTRACT_MULTIPLIER = 100
CONTRACT_ASSET_TYPES = frozenset({"OPTION", "SPREAD"})


def multiplier(asset_type: Optional[str]) -> int:
    """Shares per unit of quantity. 100 for contracts, 1 for shares."""
    return CONTRACT_MULTIPLIER if (asset_type or "").upper() in CONTRACT_ASSET_TYPES else 1


def provenance_for_parent(parent_source: Optional[str], price: Any = 0) -> str:
    """The value a lot INHERITS from its parent position row.

    An unpriced lot is UNKNOWN whatever the parent says. An unmapped parent source falls to
    PRINCIPAL_REPORTED deliberately: it is the weakest claim in the vocabulary, and an unknown
    origin is exactly "the principal said so, and nothing checked it".
    """
    if price is None:
        return UNKNOWN
    return IMPORTED if (parent_source or "") in IMPORT_PARENT_SOURCES else PRINCIPAL_REPORTED


def provenance_for_lot(lot_source: Optional[str], price: Any = 0) -> str:
    """The value a NEW lot carries, from how it arrived. Never BROKER_VERIFIED."""
    if price is None:
        return UNKNOWN
    return LOT_SOURCE_PROVENANCE.get(lot_source or "", PRINCIPAL_REPORTED)


def _f(v: Any) -> float:
    return float(v or 0)


def derive_aggregate(lots: Iterable[Mapping[str, Any]], asset_type: Optional[str] = None
                     ) -> Dict[str, Any]:
    """The position figures implied by a lot set.

    Returns quantity (always known), the gross blended entry price over PRICED lots, the cost
    basis when -- and only when -- every lot carries a price, the summed fees, and the reason
    the basis is unknown when it is.
    """
    lots = list(lots)
    qty = sum(_f(l.get("qty")) for l in lots)
    priced = [l for l in lots if l.get("price") is not None]
    unpriced = len(lots) - len(priced)
    priced_qty = sum(_f(l.get("qty")) for l in priced)
    fees = sum(_f(l.get("fees")) for l in lots)

    entry_price = None
    if priced and priced_qty:
        entry_price = sum(_f(l.get("qty")) * _f(l.get("price")) for l in priced) / priced_qty

    cost_basis = None
    reason = None
    if not lots:
        reason = "no lots"
    elif unpriced:
        reason = f"{unpriced} lot(s) carry no price"
    elif entry_price is None or not qty:
        reason = "quantity nets to zero"
    else:
        cost_basis = entry_price * qty * multiplier(asset_type)

    return {"qty": qty, "priced_qty": priced_qty, "unpriced_lots": unpriced,
            "fees": fees, "entry_price": entry_price, "cost_basis": cost_basis,
            "basis_known": cost_basis is not None, "unknown_reason": reason,
            "multiplier": multiplier(asset_type)}


def integral_qty(qty: float) -> Optional[int]:
    """The quantity as an integer, or None when it is not one.

    unified_positions.quantity is INTEGER. A fractional lot sum cannot be stored there, and
    int() would silently drop the fraction -- shares disappearing from the book without an
    event. The caller refuses the write instead.
    """
    return int(round(qty)) if abs(qty - round(qty)) < 1e-9 else None
