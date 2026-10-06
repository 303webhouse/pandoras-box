"""What an option row is worth at the underlying's current price — R-IV.657(d).

A limit set slightly low is safe; one that never publishes limits nothing. The sleeve ceiling
had stopped publishing because Robinhood — the options sleeve the ceiling governs — holds rows
the hub cannot quote: there is no options pricer, so `mark_status` reads `UNAVAILABLE` and the
account's value stays PARTIAL indefinitely. Not a transient mark delay; a capability gap.

So an unquoted option row counts at its INTRINSIC value: what its legs are worth if the
underlying never moved again. **Zero when out of the money**, which is the common case for the
far-dated protection in this book and is the conservative direction for a cap.

THIS IS A FLOOR ON THE ROW'S VALUE, NEVER AN ESTIMATE OF ITS PRICE. An option is worth
intrinsic plus time value, and time value is exactly what cannot be computed without a pricer.
Everything here therefore UNDERSTATES, deliberately and in one direction — which is why it is
safe to size a cap against and would be wrong to publish as a mark.

WHAT IT READS, in order of preference:

  1. `legs` — the structure as recorded, each leg's own side, type, strike and ratio;
  2. the row's `long_strike` / `short_strike` plus its `structure`, when legs are absent (the
     live XLF row has none);
  3. nothing readable → **0.00 with a reason**, never a guess. Zero understates, and the row
     is named on the face either way.

A COMPOSITE IS READ BY ITS FIRST COMPONENT and said so. `put_debit_spread+long_put` carries
only two strikes, so the extra long put cannot be valued from the row alone; the figure covers
the spread and the reason records what was left out. Silence there would publish a number that
looks whole.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

OPTION_MULTIPLIER = 100

PUT = "put"
CALL = "call"

# Which way a two-strike structure runs, and which option type it is made of. The vertical's
# value is bounded by its width, so a spread cannot be worth more than (long - short) either
# way -- the bound is what makes this a floor rather than an unbounded number.
_VERTICALS = {
    "put_debit_spread": (PUT, "long"),
    "bear_put_spread": (PUT, "long"),
    "put_credit_spread": (PUT, "short"),
    "bull_put_spread": (PUT, "short"),
    "call_debit_spread": (CALL, "long"),
    "bull_call_spread": (CALL, "long"),
    "call_credit_spread": (CALL, "short"),
    "bear_call_spread": (CALL, "short"),
}
_SINGLES = {
    "long_put": (PUT, "long"),
    "short_put": (PUT, "short"),
    "long_call": (CALL, "long"),
    "short_call": (CALL, "short"),
}


def _num(v) -> Optional[float]:
    """A finite float, or None. NaN passes every `if not x` guard, so it is caught here."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def first_component(structure: Optional[str]) -> Optional[str]:
    """`put_debit_spread+long_put` -> `put_debit_spread`. A composite is read by its first."""
    if not structure:
        return None
    return str(structure).strip().lower().split("+")[0].strip()


def leg_intrinsic_per_unit(option_type: str, side: str, strike: float,
                           underlying: float) -> float:
    """One leg's intrinsic per share, signed by side. Zero when out of the money.

    A SHORT leg is NEGATIVE: it is an obligation, and a spread's value is the long leg's
    intrinsic less the short leg's. Treating a short leg as zero would value every credit
    spread at its long leg alone, which is the wrong direction for a cap.
    """
    if option_type == PUT:
        raw = max(0.0, strike - underlying)
    else:
        raw = max(0.0, underlying - strike)
    return -raw if side == "short" else raw


def intrinsic_value(row: Dict[str, Any], underlying: Optional[float]) -> Tuple[Optional[float],
                                                                              str]:
    """`(value, basis)` — the row's intrinsic at `underlying`, and how it was read.

    Returns `(None, reason)` only when the UNDERLYING is unknown: with no price there is no
    intrinsic, and 0.00 would assert the row is worthless rather than unread. An unreadable
    STRUCTURE returns `(0.0, reason)` — zero understates, which is safe for a cap, and the
    reason travels with it.
    """
    px = _num(underlying)
    if px is None or px <= 0:
        return None, "no underlying price, so intrinsic cannot be computed"

    qty = abs(_num(row.get("quantity")) or 0.0)
    if qty == 0:
        return 0.0, "quantity is zero"

    mult = OPTION_MULTIPLIER
    legs = row.get("legs")

    # ── 1. the legs, when the row has them
    if isinstance(legs, list) and legs:
        per_unit, unreadable = 0.0, 0
        for leg in legs:
            if not isinstance(leg, dict):
                unreadable += 1
                continue
            strike = _num(leg.get("strike"))
            otype = str(leg.get("option_type") or "").strip().lower()
            side = str(leg.get("side") or "long").strip().lower()
            ratio = _num(leg.get("ratio"))
            if strike is None or otype not in (PUT, CALL):
                unreadable += 1
                continue
            per_unit += leg_intrinsic_per_unit(otype, side, strike, px) * (ratio or 1.0)
        value = round(max(0.0, per_unit) * mult * qty, 2)
        basis = f"from {len(legs)} recorded leg(s) at underlying {px:g}"
        if unreadable:
            basis += f"; {unreadable} leg(s) unreadable and counted as zero"
        return value, basis

    # ── 2. the strikes and the structure
    comp = first_component(row.get("structure"))
    long_k = _num(row.get("long_strike"))
    short_k = _num(row.get("short_strike"))
    composite = bool(row.get("structure") and "+" in str(row["structure"]))

    if comp in _VERTICALS and long_k is not None and short_k is not None:
        otype, side = _VERTICALS[comp]
        per_unit = (leg_intrinsic_per_unit(otype, "long", long_k, px)
                    + leg_intrinsic_per_unit(otype, "short", short_k, px))
        if side == "short":
            per_unit = -per_unit
        # A vertical cannot be worth more than its width, whichever way it runs.
        per_unit = max(0.0, min(abs(per_unit), abs(long_k - short_k)))
        value = round(per_unit * mult * qty, 2)
        basis = (f"from the {comp} strikes {long_k:g}/{short_k:g} at underlying {px:g}"
                 f" (no legs recorded)")
        if composite:
            basis += ("; the row is a COMPOSITE and only its first component is valued — "
                      "the rest is not readable from two strikes, so this understates")
        return value, basis

    if comp in _SINGLES and long_k is not None:
        otype, side = _SINGLES[comp]
        per_unit = leg_intrinsic_per_unit(otype, side, long_k, px)
        value = round(max(0.0, per_unit) * mult * qty, 2)
        return value, (f"from the {comp} strike {long_k:g} at underlying {px:g} "
                       f"(no legs recorded)")

    # ── 3. nothing readable
    return 0.0, (f"structure {row.get('structure')!r} carries neither legs nor usable "
                 f"strikes, so it is counted as ZERO — which understates")
