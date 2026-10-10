"""R-IV.827(e) — what an expiring row settled at, and when the sweep must not guess.

THE DEFECT POSITIONS FOUND. The sweep marked IWM 956 EXPIRED at 20:05:32Z and left its lots
netting +1: 13.08 of basis still unrealized, `trade_outcome` UNKNOWN, `exit_price` NULL. The row
was terminal and its money was not. That is the state POSITIONS then fixed by hand on 562 and
518 — three rows, one cause.

A terminal status with open lots is the #29 disagreement in its worst form: the row says the
trade is over and the lots say part of it is still held, so every figure derived from the lots —
capital at risk, the open remainder, realized — keeps counting a position that ended.

THE RULE, and the second half matters more than the first:

  * every leg finished OUT of the money at the expiry close -> the options expired worthless, so
    each open lot is closed at 0 and realized is exactly minus its basis. That is not an
    estimate; it is what settlement did.

  * ANY leg in the money, OR moneyness not determinable -> write NO closure and mark the row
    NEEDS_DOCUMENT. An ITM expiry settles through assignment or exercise at a price only the
    broker document states, and a sweep inventing one would put a wrong number beyond the reach
    of the correction that notices.

"Not determinable" is deliberately broad: no legs recorded, no strike, no close for the expiry
date, a missing option type. Each is a reason to stop, and each is REPORTED rather than defaulted
— defaulting any of them to OTM would close a real position at zero.

NEEDS_DOCUMENT IS NOT A STATUS. `unified_positions.status` is (OPEN, CLOSED, EXPIRED,
DUPLICATE_OF) and every reader is written against that set, so a fifth value would break them.
The contract really did end, so the row still becomes EXPIRED; the flag is a separate column
saying the MONEY is outstanding. Status answers "is it over"; the flag answers "do we know what
it was worth".
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

# Written into `needs_document` — a reason, never a bare boolean, because "this row needs the
# broker document" and "this row needs it BECAUSE no leg strike was recorded" send POSITIONS to
# different places.
NEEDS_DOCUMENT = "NEEDS_DOCUMENT"

CALL = "CALL"
PUT = "PUT"

# The verdicts. OTM is the only one that may write money.
ALL_OTM = "all_otm"
ANY_ITM = "any_itm"
UNDETERMINABLE = "undeterminable"


def _dec(value: Any) -> Optional[Decimal]:
    """A Decimal carrying the value as written, not a float's tail (#27)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def leg_moneyness(option_type: Any, strike: Any, underlying_close: Any) -> Optional[bool]:
    """True when the leg finished OUT of the money, False when IN, None when undeterminable.

    AT the strike counts as OUT: a contract exactly at the money expires worthless, and that is
    the whole reason the boundary has to be stated rather than left to a `<` somebody writes
    from memory.

    Side is deliberately NOT a parameter. Moneyness is a property of the CONTRACT against the
    settlement price; whether the position was long or short decides who pays, not whether the
    option finished in the money. Mixing the two is how a short OTM leg gets read as ITM.
    """
    k, s = _dec(strike), _dec(underlying_close)
    if k is None or s is None:
        return None
    t = (str(option_type).strip().upper() if option_type is not None else "")
    if t == CALL:
        return s <= k
    if t == PUT:
        return s >= k
    return None


def settle(legs: Sequence[Mapping[str, Any]], underlying_close: Any
           ) -> Tuple[str, Optional[str]]:
    """`(verdict, reason)` for one expiring row.

    `reason` is None only for ALL_OTM. Every other outcome carries the sentence that will be
    stored, so the row says why it is waiting rather than merely that it is.
    """
    if underlying_close is None:
        return UNDETERMINABLE, ("no close recorded for the expiry date, so moneyness cannot be "
                                "established")
    if not legs:
        return UNDETERMINABLE, ("no legs recorded, so there is nothing to test against the "
                                "expiry close")
    for leg in legs:
        otm = leg_moneyness(leg.get("option_type"), leg.get("strike"), underlying_close)
        if otm is None:
            return UNDETERMINABLE, (
                "leg %s has no usable option_type/strike (%r/%r), so moneyness cannot be "
                "established" % (leg.get("leg_seq"), leg.get("option_type"), leg.get("strike")))
        if not otm:
            return ANY_ITM, (
                "leg %s (%s %s) finished IN the money against a %s close; settlement price "
                "comes from the broker document"
                % (leg.get("leg_seq"), leg.get("option_type"), leg.get("strike"),
                   underlying_close))
    return ALL_OTM, None


def closes_at_zero(verdict: str) -> bool:
    """May the sweep write money for this verdict. ONLY the all-OTM case."""
    return verdict == ALL_OTM


def realized_for_worthless_expiry(lot_qty: Any, lot_price: Any, multiplier: int,
                                  fees: Any = 0) -> Optional[Decimal]:
    """Realized on a lot that expired worthless: minus its basis, fees included.

    Proceeds are exactly zero, so this is not a P&L model — it is the definition. Returns None
    when the basis cannot be computed, because a lot with no price has no known basis and
    writing 0 would claim it cost nothing.
    """
    q, p, f = _dec(lot_qty), _dec(lot_price), _dec(fees) or Decimal(0)
    if q is None or p is None:
        return None
    return -((abs(q) * abs(p) * Decimal(int(multiplier))) + f)


def summarise(results: Iterable[Mapping[str, Any]]) -> dict:
    """What the sweep reports: how many it settled, how many wait, and which.

    The waiting rows are LISTED, not merely counted. A count tells POSITIONS that work exists; a
    list tells them where it is.
    """
    rows = list(results)
    settled = [r for r in rows if r.get("verdict") == ALL_OTM]
    waiting = [r for r in rows if r.get("verdict") != ALL_OTM]
    return {
        "expired": len(rows),
        "settled_worthless": len(settled),
        "needs_document": len(waiting),
        "needs_document_rows": [
            {"position_id": r.get("position_id"), "ticker": r.get("ticker"),
             "verdict": r.get("verdict"), "reason": r.get("reason")}
            for r in waiting
        ],
        "basis": ("a row is settled at 0 only when EVERY leg finished out of the money at the "
                  "expiry close; anything in the money or undeterminable waits for the broker "
                  "document (R-IV.827(e))"),
    }
