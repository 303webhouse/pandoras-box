"""Gap 1 — a position's money, computed from the lots that are still open.

R-IV.526(b), sharpened by R-IV.522(a): every derived money field — `max_loss`,
`unrealized_pnl`, and anything summed from them — is computed from the OPEN
REMAINDER (SUM of lot qty, convention #29) and, where a mark is needed, from a
live mark. Never from a stored money column.

WHY THIS MODULE EXISTS RATHER THAN A FIX IN EACH CALLER. Trade Analysis found the
same scope fault in three different shapes, and the census found it in ten rows of
seventeen:

  * `max_loss` frozen at an earlier lot prefix — GUSH's $694.65 is the first lot's
    15 shares of a 25-share remainder, to the cent.
  * `max_loss` at double scope — WEAT 367 carries six-contract scope on a
    three-contract remainder, while its closed roll sibling carries the right $15.
  * a basis taken from `max_loss` itself — ABNB 379's stored P&L reproduces as
    `(mark - max_loss/100/quantity) x 100 x 1`: a one-contract scope AND a basis
    that is not `entry_price`. R-IV.522(a) names that one explicitly: **ABNB's
    basis comes from its lots, never from max_loss / 100 / quantity.**

Three shapes of one fault is what a missing single author looks like. Every figure
below is derived here, in one place, from the lots.

DECIMAL, NOT FLOAT. Convention #27: money is computed in `Decimal` and rounded
HALF-UP at the edge. A cent of float drift is not a rounding opinion when the
figure is compared against a stored one to decide whether the ledger disagrees
with itself.

WHAT IS RETURNED WHEN IT CANNOT BE COMPUTED. Nothing is substituted. A row with no
lots has no open remainder, so its derived money is `None` and `basis_reason` says
why — the same refusal the loss alert makes, and for the same reason: a figure
standing in for a missing one is the fault this replaces, not a courtesy.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple

OPTION_MULTIPLIER = Decimal("100")
CENT = Decimal("0.01")

NO_LOTS = "this row holds no lots, so it has no open remainder"
NO_OPEN_REMAINDER = "the lots net to nothing open"
NO_MARK = "no live mark"


def _d(x: Any) -> Optional[Decimal]:
    """Decimal, or None. A non-finite value is None — never a number.

    The same rule the Triton grader needed (R-IV.522): `float("nan")` succeeds and
    then passes every `if not x` guard downstream, because `not nan` is False.
    """
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x if x.is_finite() else None
    try:
        v = Decimal(str(x))
    except Exception:
        return None
    return v if v.is_finite() else None


def money(x: Optional[Decimal]) -> Optional[float]:
    """A money figure at the edge: HALF-UP to the cent (convention #27)."""
    if x is None:
        return None
    return float(x.quantize(CENT, rounding=ROUND_HALF_UP))


def _sorted_lots(lots: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Oldest fill first; a lot with no fill_time sorts last, never silently first."""
    def key(l):
        ft = l.get("fill_time")
        if ft is None:
            return (1, datetime.max.replace(tzinfo=None), l.get("id") or 0)
        naive = ft.replace(tzinfo=None) if getattr(ft, "tzinfo", None) else ft
        return (0, naive, l.get("id") or 0)
    return sorted(lots or [], key=key)


def open_remainder(lots: Sequence[Dict[str, Any]]) -> Optional[Decimal]:
    """SUM(lot qty) — convention #29's open remainder. None when there are no lots.

    None and zero are different answers: no lots means the size is unknown, an
    empty remainder means the position is closed. Collapsing them is how a
    never-lotted row came to be read as a flat one.
    """
    if not lots:
        return None
    total = Decimal("0")
    for l in lots:
        q = _d(l.get("qty"))
        if q is None:
            return None
        total += q
    return total


def surviving_cost(lots: Sequence[Dict[str, Any]]) -> Optional[Decimal]:
    """The cost of the lots STILL OPEN, FIFO: a disposal consumes the oldest first.

    For a position that has never sold anything this is just SUM(qty x price) — and
    that is every lotted open row in the book today. FIFO is here because it is
    right the first time a partial close lands, not because it changes a number now.
    """
    ordered = _sorted_lots(lots)
    if not ordered:
        return None
    open_lots: List[List[Decimal]] = []          # [qty, price] still held
    for l in ordered:
        q, p = _d(l.get("qty")), _d(l.get("price"))
        if q is None or p is None:
            return None
        if q > 0:
            open_lots.append([q, p])
            continue
        take = -q
        while take > 0 and open_lots:
            head = open_lots[0]
            used = head[0] if head[0] <= take else take
            head[0] -= used
            take -= used
            if head[0] == 0:
                open_lots.pop(0)
        if take > 0:
            # Sold more than was ever acquired. Not a cost this can state.
            return None
    total = Decimal("0")
    for q, p in open_lots:
        total += q * p
    return total


def close_date_from_lots(
    lots: Sequence[Dict[str, Any]],
) -> Tuple[Optional[date], Optional[int], Optional[str]]:
    """(close date, the lot id it came from, reason) — R-IV.517(e).

    THE CLOSE DATE IS THE `fill_time` OF THE DISPOSAL THAT TOOK THE REMAINDER TO
    ZERO. Never `created_at`: every one of the 24 disposal lots in this book was
    created on 2026-09-24, in one backfill, so `created_at` would date two years of
    closures to a single Thursday morning. And never the LAST disposal by itself —
    a partial sale is a disposal too, and the one that closes the position is the
    one after which nothing is held.

    No new column: this is derived on read, from rows that already exist.
    """
    ordered = _sorted_lots(lots)
    if not ordered:
        return None, None, NO_LOTS
    running = Decimal("0")
    closer = None
    for l in ordered:
        q = _d(l.get("qty"))
        if q is None:
            return None, None, "a lot carries no readable quantity"
        running += q
        if q < 0 and running == 0:
            closer = l
    if closer is None:
        return None, None, "no disposal takes this position to zero"
    ft = closer.get("fill_time")
    if ft is None:
        return None, closer.get("id"), "the closing disposal carries no fill_time"
    return (ft.date() if hasattr(ft, "date") else ft), closer.get("id"), None


def economics(
    row: Dict[str, Any],
    lots: Sequence[Dict[str, Any]],
    mark: Optional[Any] = None,
) -> Dict[str, Any]:
    """Every derived money figure for one position, from its lots and a mark.

    `mark` is the per-unit price — per share, or per contract/structure. It is the
    caller's live mark; this module never reaches for one, so there is exactly one
    place that decides what counts as live.
    """
    is_option = (row.get("asset_type") or "").upper() == "OPTION"
    mult = OPTION_MULTIPLIER if is_option else Decimal("1")
    status = (row.get("status") or "").upper()

    out: Dict[str, Any] = {
        "open_remainder": None,
        "cost_at_remainder": None,
        "unit_cost": None,
        "market_value": None,
        "unrealized_pnl": None,
        "max_loss": None,
        "basis_source": None,
        "basis_reason": None,
        "multiplier": int(mult),
    }

    # R-IV.548(b): A CLOSED ROW HOLDS NO RISK, WHATEVER ITS LOTS SAY.
    #
    # Most closures in this book were booked without a disposal lot -- 308 of them --
    # so `SUM(lot qty)` stays POSITIVE on a position that is over. The arithmetic
    # below is correct and the question was wrong: asking a closed row for its open
    # remainder at all. POSITIONS measured what that cost: 301 non-OPEN rows carrying
    # a positive remainder, $88,016.87 of risk that does not exist, published to four
    # committee seats for sizing by a tool whose own description sends them there.
    #
    # A closed position carries REALIZED P&L only. No remainder, no max_loss, no
    # unrealized -- and the reason says which status refused it, so a reader is never
    # left wondering whether the lots were simply missing.
    if status and status != "OPEN":
        out["status"] = status
        out["basis_reason"] = (
            "this row is %s; a position that is over carries realized P&L only, and "
            "no open remainder, max_loss or unrealized figure" % status)
        return out

    rem = open_remainder(lots)
    if rem is None:
        out["basis_reason"] = NO_LOTS
        return out
    out["open_remainder"] = float(rem)
    if rem <= 0:
        out["basis_reason"] = NO_OPEN_REMAINDER
        return out

    cost = surviving_cost(lots)
    if cost is None:
        out["basis_reason"] = "the lots do not state a cost for what is still open"
        return out

    cost_total = cost * mult
    unit = cost / rem
    out["cost_at_remainder"] = money(cost_total)
    out["unit_cost"] = float(unit)
    out["basis_source"] = "lots"

    # max_loss for long premium and for stock IS the cost of what is still held.
    # A defined-risk structure whose worst case is narrower than its debit is not
    # decided here -- that is gap 3's stop/invalidation work -- but it can never
    # again be WIDER than the position actually held, which is the whole fault.
    out["max_loss"] = money(cost_total)

    m = _d(mark)
    if m is None:
        out["basis_reason"] = NO_MARK
        return out
    value = m * rem * mult
    out["market_value"] = money(value)
    out["unrealized_pnl"] = money(value - cost_total)
    return out


def capital_at_risk(
    rows: Sequence[Dict[str, Any]],
    lots_by_position: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """The book's capital at risk, COST-DERIVED at the open remainder.

    R-IV.207(d) forbids summing `max_loss`, and R-IV.526(b) says so again: the
    published figure is cost-derived and labelled as such, or there is none.

    Two reasons the old sum was not a number. It read `max_loss or cost_basis`, so
    one row contributed a worst case while its neighbour contributed a cost — a
    mixed unit, added up. And `max_loss` itself carried the wrong scope on ten of
    the seventeen lotted open rows, understating the total by $632.08 (13.7%) when
    measured on 2026-09-24.

    Rows without lots are EXCLUDED and counted, never estimated: the figure is
    labelled partial when any row is missing, because a total that quietly drops
    five positions is worse than one that says it did.
    """
    return capital_at_risk_from_derived([
        dict(r, derived=economics(r, lots_by_position.get(r.get("position_id")) or []))
        for r in rows
    ])


def account_value(cash: Any, rows: Sequence[Dict[str, Any]],
                  account: Optional[str] = None,
                  cash_reason: Optional[str] = None) -> Dict[str, Any]:
    """An account's value: its cash plus its OPEN positions at their marks.

    R-IV.551(c) and R-IV.559(c)2, in one place. The loss alert's threshold and the
    balances tool's `balance` are the same question asked twice, and two arithmetics
    answering it is how a committee sizing off one figure and an alert firing off
    another come to disagree about the same account.

    PARTIAL RATHER THAN GUESSED. A position with no market value -- no lots, or no
    live mark -- contributes nothing and is NAMED. The total is still returned,
    deliberately: an understated account makes a 2%% trigger smaller, which errs
    toward alerting, and a sizing figure that is too small is the safe direction too.
    What it must never do is fill the hole with a number.

    NO CASH, NO VALUE. With no derived cash there is no account value and the reason
    travels with the None. Inventing zero cash would make the figure the positions
    alone, which is not the account.
    """
    c = _d(cash)
    positions = Decimal("0")
    missing: List[Any] = []
    counted = 0
    for r in rows:
        if account and (r.get("account") or "").upper() != account.upper():
            continue
        if (r.get("status") or "OPEN").upper() != "OPEN":
            continue
        mv = (r.get("derived") or {}).get("market_value")
        if mv is None:
            missing.append(r.get("position_id") or r.get("id"))
            continue
        positions += Decimal(str(mv))
        counted += 1

    partial = bool(missing)
    if c is None:
        return {"value": None, "cash": None, "positions_value": money(positions),
                "positions_counted": counted, "positions_unvalued": missing,
                "partial": partial,
                "reason": cash_reason or "there is no derived cash for this account"}
    return {
        "value": money(c + positions), "cash": money(c),
        "positions_value": money(positions), "positions_counted": counted,
        "positions_unvalued": missing, "partial": partial,
        "reason": ("%d position(s) could not be valued, so this figure is PARTIAL "
                   "and understates the account" % len(missing)) if partial else None,
    }


def capital_at_risk_from_derived(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The same figure, for rows that already carry their `derived` block.

    One arithmetic, two entry points: a caller that has the lots and a caller that
    has already had them attached. Summing `cost_at_remainder` in a second place
    would be exactly the duplication that let `max_loss` and the total drift apart.
    """
    total = Decimal("0")
    included: List[Any] = []
    excluded: List[Dict[str, Any]] = []
    not_open = 0
    for r in rows:
        pid = r.get("position_id")
        e = r.get("derived") or {}
        # R-IV.548(b): OPEN rows only, WHATEVER THE FILTER. A caller asking for
        # status=ALL or status=CLOSED is asking to SEE those rows, never to add them
        # to the book's risk -- and both are documented inputs to a tool four
        # committee seats size off. Skipped rather than "excluded": an excluded row
        # is one that should have counted and could not, and reporting 400 closures
        # that way would bury the handful that actually need lots.
        if (r.get("status") or "").upper() not in ("", "OPEN"):
            not_open += 1
            continue
        if e.get("cost_at_remainder") is None:
            excluded.append({"position_id": pid, "ticker": r.get("ticker"),
                             "reason": e.get("basis_reason") or NO_LOTS})
            continue
        total += Decimal(str(e["cost_at_remainder"]))
        included.append(pid)
    return {
        "positions_not_open": not_open,
        "capital_at_risk_cost_basis": money(total),
        "basis": "cost at the open remainder (SUM lot qty x price), by R-IV.526(b)",
        "positions_included": len(included),
        "positions_excluded": len(excluded),
        "excluded": excluded,
        "complete": not excluded,
    }
