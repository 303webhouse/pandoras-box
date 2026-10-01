"""What a structure REQUIRES, and the legs its strikes imply. R-IV.613(c)1 and (c)2.

THE ROW THIS EXISTS BECAUSE OF. The add form wrote `564 QQQ` as a `put_debit_spread` with **no
legs, no expiry and no direction**, and reported success. Three separate silences:

  * the expiry was swallowed by a bare `except: pass` (fixed under R-IV.610(d));
  * nothing required an expiry or strikes for a structure that cannot exist without them;
  * `legs` went into a jsonb column only when the form happened to send an array, and the form
    sends STRIKES. Nothing built the legs from them, so a spread's legs were simply absent.

ONE AUTHOR FOR BOTH HALVES, because they are the same fact read twice: a structure that needs
two strikes needs them to validate AND to build its legs. Two lists would disagree the first
time a structure was added to one of them.

WHAT IS DELIBERATELY NOT REQUIRED. `entry_price` is optional and stays so: the principal books
rows he has not priced yet, and `position_economics` already reports a missing basis honestly
rather than inventing one. `direction` is inferred from the structure
(`models/position_direction`), so demanding it would be asking for something already known.

AN UNKNOWN STRUCTURE IS NOT REFUSED. It requires nothing and implies no legs, so a structure
nobody has mapped is bookable and simply carries no synthesised legs — the same answer as
before. Refusing it would turn "we have not described this shape" into "you may not record your
own trade", which is not a trade-off to make on the principal's behalf.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

# Required fields per structure family. `strikes` is how many of long/short the shape needs.
#
#   expiry   an option contract has an expiry; a share does not.
#   strikes  2 -> a vertical needs both legs' strikes; 1 -> a single option needs one.
SPREAD = "spread"
SINGLE = "single"
SHARES = "shares"

# Structure name (lower, each `+`-component checked separately) -> family.
_FAMILY: Dict[str, str] = {
    # shares — neither an expiry nor a strike
    "stock": SHARES, "equity": SHARES, "etf": SHARES, "shares": SHARES,
    "long_stock": SHARES, "short_stock": SHARES, "stock_long": SHARES, "stock_short": SHARES,
    # a single option — an expiry and one strike
    "long_call": SINGLE, "long_put": SINGLE, "short_call": SINGLE, "short_put": SINGLE,
    # a vertical — an expiry and both strikes
    "call_debit_spread": SPREAD, "put_debit_spread": SPREAD,
    "call_credit_spread": SPREAD, "put_credit_spread": SPREAD,
    "bull_call_spread": SPREAD, "bear_put_spread": SPREAD,
    "bull_put_spread": SPREAD, "bear_call_spread": SPREAD,
}

REQUIRES: Dict[str, Dict[str, Any]] = {
    SPREAD: {"expiry": True, "strikes": 2},
    SINGLE: {"expiry": True, "strikes": 1},
    SHARES: {"expiry": False, "strikes": 0},
}

# Which option type and which side each spread's two legs are. The long leg first.
_SPREAD_LEGS: Dict[str, tuple] = {
    "call_debit_spread":  (("call", "long"), ("call", "short")),
    "bull_call_spread":   (("call", "long"), ("call", "short")),
    "put_debit_spread":   (("put", "long"), ("put", "short")),
    "bear_put_spread":    (("put", "long"), ("put", "short")),
    "call_credit_spread": (("call", "short"), ("call", "long")),
    "bear_call_spread":   (("call", "short"), ("call", "long")),
    "put_credit_spread":  (("put", "short"), ("put", "long")),
    "bull_put_spread":    (("put", "short"), ("put", "long")),
}
_SINGLE_LEGS: Dict[str, tuple] = {
    "long_call": ("call", "long"), "long_put": ("put", "long"),
    "short_call": ("call", "short"), "short_put": ("put", "short"),
}


def _components(structure: Optional[str]) -> List[str]:
    """A composite structure, component by component. `a+b` is two shapes in one row."""
    return [p.strip() for p in (structure or "").strip().lower().split("+") if p.strip()]


def family_of(structure: Optional[str]) -> Optional[str]:
    """`spread`, `single`, `shares`, or None when the structure is not mapped.

    A composite takes the family of its FIRST mapped component for validation purposes: a
    `put_debit_spread+long_put` still needs an expiry and both spread strikes, and its extra leg
    is the principal's business rather than something to demand up front.
    """
    for part in _components(structure):
        fam = _FAMILY.get(part)
        if fam is not None:
            return fam
    return None


def missing_fields(structure: Optional[str], expiry: Any,
                   long_strike: Any, short_strike: Any) -> List[str]:
    """Which required fields a structure is missing. Empty when it is bookable.

    A strike of 0 or a negative one counts as MISSING, not as a strike. A zero-strike option is
    not a thing, and accepting it would put an unusable number where a reader expects a price.
    """
    fam = family_of(structure)
    if fam is None:
        return []                       # unmapped: nothing is required, nothing is refused
    need = REQUIRES[fam]
    out: List[str] = []
    if need["expiry"] and not expiry:
        out.append("expiry")

    def _ok(v) -> bool:
        try:
            return v is not None and float(v) > 0
        except (TypeError, ValueError):
            return False

    if need["strikes"] >= 1 and not _ok(long_strike):
        out.append("long_strike")
    if need["strikes"] >= 2 and not _ok(short_strike):
        out.append("short_strike")
    return out


def refusal_message(structure: Optional[str], missing: List[str]) -> str:
    """What to tell the principal: what is missing, for which shape, and that nothing was saved."""
    fam = family_of(structure)
    shape = {SPREAD: "a spread", SINGLE: "a single option", SHARES: "shares"}.get(fam, structure)
    need = ", ".join(missing)
    return ("%s needs %s. Add %s and send it again — nothing was saved."
            % (structure or "this structure", need, need)) if fam is None else (
        "%s is %s, which needs %s. Nothing was saved."
        % (structure or "this structure", shape, need))


def legs_from_strikes(structure: Optional[str], expiry: Optional[date],
                      long_strike: Any, short_strike: Any,
                      quantity: float) -> Optional[List[Dict[str, Any]]]:
    """The legs a structure's strikes imply, or None when they imply none.

    Shaped exactly like `_validated_legs` returns, so a synthesised set and a form-supplied set
    are indistinguishable downstream — a second shape would be a second thing to keep in step.

    None (not `[]`) when the shape is unmapped or a strike is absent: an empty list would assert
    "this position has no legs", which for a spread is false rather than unknown.
    """
    parts = _components(structure)
    if not parts or expiry is None:
        return None
    key = parts[0]

    def _f(v):
        try:
            return float(v) if v is not None and float(v) > 0 else None
        except (TypeError, ValueError):
            return None

    lo, sh = _f(long_strike), _f(short_strike)
    qty = float(quantity or 0) or 1.0

    def _leg(option_type: str, side: str, strike: float) -> Dict[str, Any]:
        return {"option_type": option_type, "side": side, "strike": strike,
                "expiry": expiry, "qty": qty, "ratio": 1.0, "price": None}

    if key in _SPREAD_LEGS and lo is not None and sh is not None:
        (t1, s1), (t2, s2) = _SPREAD_LEGS[key]
        # The LONG leg carries the long_strike the form sent, whichever side comes first.
        by_side = {"long": lo, "short": sh}
        return [_leg(t1, s1, by_side[s1]), _leg(t2, s2, by_side[s2])]

    if key in _SINGLE_LEGS and lo is not None:
        t, s = _SINGLE_LEGS[key]
        return [_leg(t, s, lo)]

    return None
