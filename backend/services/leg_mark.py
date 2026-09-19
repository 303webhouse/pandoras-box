"""Mark a position from its legs (R-IV.458(a), R-IV.460(b)).

ANY position with legs in position_legs is marked from those legs. No structure allowlist: a
condor, a butterfly, a calendar, a ratio, or a name the principal invents are all priced the same
way -- leg by leg -- because the legs, not the name, say what is held.

THE DEFECT THIS ENDS. The mark path chose its method from the STRUCTURE NAME. A name on the
multi-leg allowlist read a legacy JSONB column; a name containing "spread" priced two strikes;
anything else priced ONE option. NVDA 415 (put_butterfly, three legs) was not on the list and so
was priced as its 100P alone -- +21.00 of unrealized on a structure with no fill behind it. XLF 300
(three legs, stored as a put debit spread) was priced as two. The census found exactly those two
among the twenty open positions with legs; the other eighteen were 2-leg verticals and single legs
the name-based path happened to price correctly.

WHAT "CANNOT BE PRICED" MEANS HERE, and why it is UNAVAILABLE rather than a retained number:
  * the legs disagree with the row (legs hold 10 structures, the row says 8) -- the scale of the
    position is not known, so no per-position figure is either;
  * a leg has no quote -- a net built from some legs is a different structure's price.
A prior mark is retained through a failed cycle when it is a GOOD value: legs produced it, or the
two-strike path priced exactly the contracts the legs hold (a vertical or a single leg -- the
census's correct class). A prior from the name-based path on any other leg set priced a different
structure, and keeping it would keep the invented number. A negative prior is never good: no
vertical or single leg the two-strike path priced is worth less than nothing.

Pure apart from the injected pricer, so every rule is testable without a vendor.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional

LEGS_MARK_PREFIX = "priced from "

Pricer = Callable[[str, List[Dict[str, Any]], str], Awaitable[Optional[Dict[str, Any]]]]


def structure_ratios(legs: List[Dict[str, Any]], row_qty) -> Optional[List[int]]:
    """Each leg's quantity per ONE structure, or None when the legs and the row disagree."""
    try:
        q = float(row_qty or 0)
    except (TypeError, ValueError):
        return None
    if q <= 0:
        return None
    out = []
    for leg in legs:
        r = abs(float(leg.get("qty") or 0)) / q
        if r <= 0 or abs(r - round(r)) > 1e-9:
            return None
        out.append(int(round(r)))
    return out


async def mark_from_legs(ticker: str, legs: List[Dict[str, Any]], row_qty,
                         structure: Optional[str], pricer: Pricer) -> Dict[str, Any]:
    """{"ok", "net_mark", "reason", "details"} for one position. Never raises."""
    n = len(legs)
    if not legs:
        return {"ok": False, "net_mark": None, "reason": "no legs", "details": []}
    ratios = structure_ratios(legs, row_qty)
    if ratios is None:
        held = sorted({abs(float(l.get("qty") or 0)) for l in legs})
        return {"ok": False, "net_mark": None, "details": [],
                "reason": (f"legs hold {', '.join(f'{h:g}' for h in held)} contracts; the row "
                           f"says quantity {row_qty} -- the position's scale is not known")}

    by_expiry: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for leg, ratio in zip(legs, ratios):
        by_expiry[str(leg.get("expiry"))[:10]].append({
            "action": "BUY" if str(leg.get("side")).upper() == "LONG" else "SELL",
            "option_type": str(leg.get("option_type") or "").lower(),
            "strike": float(leg.get("strike")),
            "quantity": ratio,
        })

    net = 0.0
    details: List[Any] = []
    for expiry, group in sorted(by_expiry.items()):
        try:
            res = await pricer(ticker, group, expiry)
        except Exception as exc:
            res = None
            err = type(exc).__name__
        else:
            err = None
        if not res or res.get("net_mark") is None:
            strikes = ", ".join(f"{g['strike']:g}{g['option_type'][:1].upper()}" for g in group)
            return {"ok": False, "net_mark": None, "details": details,
                    "reason": (f"no quote for the {expiry} leg(s) {strikes}"
                               + (f" ({err})" if err else "")
                               + " -- a net built from the remaining legs would price a "
                                 "different structure")}
        net += float(res["net_mark"])
        details.extend(res.get("leg_details") or [])
    return {"ok": True, "net_mark": net, "details": details,
            "reason": f"{LEGS_MARK_PREFIX}{n} leg(s) ({structure or 'CUSTOM'})"}


def prior_mark_came_from_legs(mark_reason: Optional[str]) -> bool:
    """A legs-derived prior survives a failed legs cycle."""
    return bool(mark_reason) and str(mark_reason).startswith(LEGS_MARK_PREFIX)


def name_path_priced_same_legs(legs: List[Dict[str, Any]], structure: Optional[str], expiry,
                               long_strike, short_strike, row_qty, prior_mark) -> bool:
    """True when the two-strike path priced exactly the contracts these legs hold.

    Such a prior is a GOOD value under the mark guard's rule and survives a failed cycle as STALE.
    Mirrors the two-strike path's own choices: the option type from the NAME, the spread branch
    when a short strike exists and the name says spread/credit/debit, else the single leg at the
    long strike. Anything wider than that path could see -- three legs, two expiries, a ratio, a
    type the name did not say -- priced a different structure and is not good.
    """
    try:
        if prior_mark is None or float(prior_mark) < 0:
            return False
    except (TypeError, ValueError):
        return False
    if not legs or len(legs) > 2 or expiry is None or long_strike is None:
        return False
    if structure_ratios(legs, row_qty) != [1] * len(legs):
        return False
    if any(str(l.get("expiry"))[:10] != str(expiry)[:10] for l in legs):
        return False
    s = (structure or "").lower()
    kind = "PUT" if "put" in s else "CALL"
    if any(str(l.get("option_type") or "").upper() != kind for l in legs):
        return False
    spread_branch = bool(short_strike) and ("spread" in s or "credit" in s or "debit" in s)
    if spread_branch:
        if len(legs) != 2:
            return False
        by_side = {str(l.get("side") or "").upper(): float(l["strike"]) for l in legs}
        return by_side == {"LONG": float(long_strike), "SHORT": float(short_strike)}
    return len(legs) == 1 and float(legs[0]["strike"]) == float(long_strike)
