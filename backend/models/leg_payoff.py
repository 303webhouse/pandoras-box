"""What a set of option legs is, and what it can make or lose (R-IV.460). Pure.

N LEGS, NO CEILING, NO ALLOWLIST. Any set of legs is analysed the same way: the expiration payoff
of every leg summed, which is a piecewise-linear function of the underlying whose corners sit at
the strikes. So the extremes are at a strike or at the two ends, and a breakeven is where a segment
crosses zero. That holds for a vertical, a butterfly, a condor, a ratio, or anything the principal
invents -- nothing here branches on the structure's name.

WHAT CANNOT BE COMPUTED IS SAID, NOT GUESSED:
  * legs on DIFFERENT expiries (calendars, diagonals) have no single expiration payoff -- the
    far leg still carries time value when the near one expires -- so max profit, max loss and
    breakevens are reported as not computable at one expiry. The net premium still is.
  * a leg with no price makes the net premium unknown, so the dollar extremes are unknown too;
    the SHAPE (strikes, slopes, whether a side is unlimited) is still reported.

The name is a courtesy. recognize() names the structure where the legs match a known shape and
returns CUSTOM where they do not -- and a CUSTOM position is enterable, priced and marked exactly
like a named one.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

CONTRACT = 100
CUSTOM = "custom"


def _sign(leg) -> int:
    return 1 if str(leg.get("side", "")).upper() == "LONG" else -1


def _type(leg) -> str:
    return str(leg.get("option_type", "")).upper()


def _q(leg) -> float:
    return abs(float(leg.get("qty") or leg.get("quantity") or 1))


def _ratios(legs: Sequence[Dict[str, Any]]) -> List[float]:
    """Each leg's quantity per ONE structure: divide by the smallest leg quantity."""
    qs = [_q(l) for l in legs]
    base = min(qs) if qs else 1.0
    return [q / base for q in qs]


def net_premium(legs: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Net paid per structure: positive = DEBIT, negative = CREDIT. None if any leg is unpriced."""
    total = 0.0
    for leg, r in zip(legs, _ratios(legs)):
        if leg.get("price") is None:
            return None
        total += _sign(leg) * r * float(leg["price"])
    return round(total, 6)


def _payoff_at(legs, ratios, s: float) -> float:
    v = 0.0
    for leg, r in zip(legs, ratios):
        k = float(leg["strike"])
        intrinsic = max(0.0, s - k) if _type(leg) == "CALL" else max(0.0, k - s)
        v += _sign(leg) * r * intrinsic
    return v


def analyze(legs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Net premium, max profit, max loss and breakevens, per structure and per contract set."""
    legs = list(legs)
    if not legs:
        return {"legs": 0, "computable": False, "reason": "no legs"}
    expiries = {str(l.get("expiry"))[:10] for l in legs}
    net = net_premium(legs)
    out: Dict[str, Any] = {
        "legs": len(legs),
        "net_premium": net,
        "debit_or_credit": (None if net is None else "DEBIT" if net > 0
                            else "CREDIT" if net < 0 else "EVEN"),
        "multi_expiry": len(expiries) > 1,
    }
    if len(expiries) > 1:
        out.update(computable=False, max_profit=None, max_loss=None, breakevens=None,
                   reason=("legs expire on different dates; the far leg still carries time value "
                           "when the near one expires, so no single expiration payoff exists"))
        return out

    ratios = _ratios(legs)
    strikes = sorted({float(l["strike"]) for l in legs})
    points = [0.0] + strikes
    values = [_payoff_at(legs, ratios, s) for s in points]
    # Slope beyond the highest strike: only calls move there.
    upper_slope = sum(_sign(l) * r for l, r in zip(legs, ratios) if _type(l) == "CALL")

    cost = net if net is not None else 0.0
    pnl = [v - cost for v in values]
    unlimited_profit = upper_slope > 1e-12
    unlimited_loss = upper_slope < -1e-12
    max_profit = None if unlimited_profit else max(pnl)
    max_loss = None if unlimited_loss else min(pnl)

    breakevens: List[float] = []
    for (s0, p0), (s1, p1) in zip(zip(points, pnl), zip(points[1:], pnl[1:])):
        if p0 == 0:
            breakevens.append(round(s0, 4))
        elif (p0 < 0 < p1) or (p1 < 0 < p0):
            breakevens.append(round(s0 + (0 - p0) * (s1 - s0) / (p1 - p0), 4))
    if pnl and pnl[-1] == 0:
        breakevens.append(round(points[-1], 4))
    if upper_slope and pnl:
        tail = points[-1] - pnl[-1] / upper_slope
        if tail > points[-1] and ((pnl[-1] < 0 < upper_slope) or (pnl[-1] > 0 > upper_slope)):
            breakevens.append(round(tail, 4))

    known = net is not None
    out.update(
        computable=True,
        max_profit=("UNLIMITED" if unlimited_profit else
                    (round(max_profit * CONTRACT, 2) if known else None)),
        max_loss=("UNLIMITED" if unlimited_loss else
                  (round(-max_loss * CONTRACT, 2) if known else None)),
        breakevens=sorted(set(breakevens)) if known else None,
        reason=None if known else "a leg has no price, so the net premium and the dollar "
                                  "extremes are unknown; the shape is reported",
        per="one structure (x100 per contract)",
    )
    return out


def recognize(legs: Sequence[Dict[str, Any]]) -> str:
    """The structure's name where the legs match a known shape; CUSTOM otherwise."""
    legs = list(legs)
    n = len(legs)
    if n == 0:
        return CUSTOM
    types = [_type(l) for l in legs]
    signs = [_sign(l) for l in legs]
    ratios = _ratios(legs)
    expiries = {str(l.get("expiry"))[:10] for l in legs}
    strikes = [float(l["strike"]) for l in legs]

    if n == 1:
        return f"{'long' if signs[0] > 0 else 'short'}_{types[0].lower()}"

    if len(expiries) > 1:
        if n == 2 and types[0] == types[1] and signs[0] != signs[1]:
            return "calendar" if strikes[0] == strikes[1] else "diagonal"
        return CUSTOM

    if n == 2:
        if types[0] == types[1] and signs[0] != signs[1]:
            if ratios[0] != ratios[1]:
                return f"{types[0].lower()}_ratio_spread"
            long_k = strikes[signs.index(1)]
            short_k = strikes[signs.index(-1)]
            kind = types[0].lower()
            debit = (long_k < short_k) if kind == "call" else (long_k > short_k)
            return f"{kind}_{'debit' if debit else 'credit'}_spread"
        if set(types) == {"CALL", "PUT"} and signs[0] == signs[1]:
            side = "long" if signs[0] > 0 else "short"
            return f"{side}_straddle" if strikes[0] == strikes[1] else f"{side}_strangle"
        return CUSTOM

    if n == 3 and len(set(types)) == 1:
        order = sorted(range(3), key=lambda i: strikes[i])
        s = [signs[i] * ratios[i] for i in order]
        k = [strikes[i] for i in order]
        if s[0] == s[2] and s[1] == -2 * s[0] and abs((k[1] - k[0]) - (k[2] - k[1])) < 1e-9:
            return f"{types[0].lower()}_butterfly"
        return CUSTOM

    if n == 4 and sorted(types) == ["CALL", "CALL", "PUT", "PUT"] and len(set(ratios)) == 1:
        puts = sorted([(strikes[i], signs[i]) for i in range(4) if types[i] == "PUT"])
        calls = sorted([(strikes[i], signs[i]) for i in range(4) if types[i] == "CALL"])
        # long wing below, short body, short body, long wing above
        if puts[0][1] > 0 and puts[1][1] < 0 and calls[0][1] < 0 and calls[1][1] > 0:
            if puts[1][0] == calls[0][0]:
                return "iron_butterfly"
            if puts[1][0] < calls[0][0]:
                return "iron_condor"
        return CUSTOM

    return CUSTOM


def display_strikes(legs: Sequence[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """long_strike / short_strike DERIVED for display (R-IV.460(d)) -- never a source.

    The first long leg's strike and the first short leg's strike, in leg order. For a vertical
    that is exactly what the two columns used to hold; for anything wider it is a summary, and a
    reader who needs the structure reads the legs.
    """
    long_k = next((float(l["strike"]) for l in legs if _sign(l) > 0), None)
    short_k = next((float(l["strike"]) for l in legs if _sign(l) < 0), None)
    return {"long_strike": long_k, "short_strike": short_k}
