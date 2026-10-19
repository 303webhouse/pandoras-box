"""B7's Book Reality Check: what the book is worth if SPY moves. R-IV.1239(e).

EVERY NUMBER THIS PRODUCES IS A MODEL ESTIMATE, and that phrase is not decoration. The chain
is: a beta measured over 60 sessions, a volatility SOLVED from the position's own mark, a
European Black-Scholes price with no dividends, and a sticky-strike assumption that the vol
does not move when spot does. Four approximations compounded. The output is labelled
"model estimate" on every cell (R-IV.1239(e)3), the vol mode is stated on screen
(R-IV.1239(e)2), and the whole surface ships behind a flag that is OFF (R-IV.1239(e)4) until
QUERY has recomputed three rows independently and SPINE has ruled (R-IV.1239(e)5-6).

SITTCKY-STRIKE IS THE RULED ASSUMPTION AND IT IS THE CONSERVATIVE ONE TO STATE, NOT TO BELIEVE.
Holding IV constant while SPY falls 10% understates a long put's gain and overstates a short
put's loss, because in a real 10% fall implied vol rises. The mock's "VOL REACTS" mode is
therefore NOT implemented: R-IV.1239(e)2 rules sticky-strike, so the screen says
"VOL HELD (sticky-strike)" and the absent mode is named rather than left as a toggle that does
nothing.

PURE. Positions, spots, betas and a rate in; cells out. No vendor, no database, no flag.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.options_math import bs_price, implied_vol

#: R-IV.1194(g)'s columns, as SPY percentage moves.
SCENARIOS: Tuple[float, ...] = (-10.0, -5.0, -3.0, 3.0, 5.0)

#: R-IV.1194(g)'s rows. The account names in the book map onto these three plus a total.
ACCOUNT_ROWS = ("RH", "ROTH", "401A", "TOTAL")
ACCOUNT_MAP = {
    "robinhood": "RH",
    "fidelity_roth": "ROTH",
    "fidelity_401a": "401A",
}

#: The ruled label, on every cell.
MODEL_LABEL = "model estimate"
#: The ruled vol mode, stated on screen.
VOL_MODE = "VOL HELD (sticky-strike)"
VOL_MODE_BASIS = (
    "implied volatility is held constant as spot moves (R-IV.1239(e)2). In a real 10% fall "
    "implied vol rises, so this UNDERSTATES a long put's gain and OVERSTATES a short put's "
    "loss. The mock's 'VOL REACTS' mode is not implemented")

#: An option contract covers 100 shares. Stated as a constant because a missing multiplier is
#: a 100x error, which is the largest single mistake available in this file.
CONTRACT_MULTIPLIER = 100

#: Two-leg debit/credit spreads this module can price, and the leg types they are built from.
#: A structure NOT in here is reported unavailable rather than guessed at.
SPREADS = {
    "put_debit_spread": ("put", +1, "put", -1),      # long higher strike, short lower
    "call_debit_spread": ("call", +1, "call", -1),
    "put_credit_spread": ("put", -1, "put", +1),
    "call_credit_spread": ("call", -1, "call", +1),
    "bull_put_spread": ("put", -1, "put", +1),
    "bear_call_spread": ("call", -1, "call", +1),
}
SINGLES = {"long_put": ("put", +1), "long_call": ("call", +1),
           "short_put": ("put", -1), "short_call": ("call", -1)}
STOCK = {"stock", "shares", "equity"}


def account_row(account: Optional[str]) -> Optional[str]:
    """The display row for a book account. None when it is not one of the three.

    Exact-name identity, lower-cased -- never a prefix match. A prefix would fold a future
    `fidelity_roth_ira` into ROTH silently, and this repo has a filed rule that parked money is
    held out by exact name and not by spelling.
    """
    return ACCOUNT_MAP.get(str(account or "").strip().lower())


def years_to_expiry(expiry: Any, today: Optional[_dt.date] = None) -> Optional[float]:
    """Calendar days / 365, as `bs_greeks_from_iv` documents. None when there is no expiry."""
    if expiry is None:
        return None
    today = today or _dt.date.today()
    d = expiry.date() if isinstance(expiry, _dt.datetime) else expiry
    if not isinstance(d, _dt.date):
        try:
            d = _dt.date.fromisoformat(str(expiry)[:10])
        except ValueError:
            return None
    return (d - today).days / 365.0


def underlying_move(spy_pct: float, beta: Optional[float]) -> Optional[float]:
    """The ticker's move for a given SPY move, as a fraction. None without a beta.

    No beta means NO CELL for that position, and the row says which position is missing. A
    beta defaulted to 1.0 would quietly model SQQQ as SPY.
    """
    if beta is None:
        return None
    return (spy_pct / 100.0) * beta


def price_structure(structure: Optional[str], *, spot: float, long_strike: Optional[float],
                    short_strike: Optional[float], T: Optional[float], r: float,
                    iv: Optional[float]) -> Tuple[Optional[float], str]:
    """(value per unit, basis). Shares price per share; options per CONTRACT (x100).

    A structure this does not know returns None with its name in the reason. Guessing at a
    composite -- which this book holds -- would produce a number for a thing nobody priced.
    """
    s = str(structure or "").strip().lower()
    if not s:
        return None, "no structure recorded"
    if "+" in s:
        return None, ("structure %r is a COMPOSITE: its net mark cannot be split across legs, "
                      "so no single volatility identifies it (same reason TA-168 holds "
                      "composites in the B2 cut)" % s)
    if s in STOCK:
        return spot, "shares, priced at spot"
    if T is None:
        return None, "an option with no expiry cannot be priced"
    if s in SINGLES:
        kind, sign = SINGLES[s]
        strike = long_strike if sign > 0 else short_strike or long_strike
        if strike is None:
            return None, "no strike recorded for %r" % s
        p = bs_price(spot, strike, T, r, iv, kind)
        if p is None:
            return None, "the pricer could not value %r at iv=%r" % (s, iv)
        return sign * p * CONTRACT_MULTIPLIER, "%s %s, Black-Scholes" % (
            "long" if sign > 0 else "short", kind)
    if s in SPREADS:
        k1, s1, k2, s2 = SPREADS[s]
        if long_strike is None or short_strike is None:
            return None, "a spread needs both strikes; %r has %r/%r" % (
                s, long_strike, short_strike)
        p1 = bs_price(spot, long_strike, T, r, iv, k1)
        p2 = bs_price(spot, short_strike, T, r, iv, k2)
        if p1 is None or p2 is None:
            return None, "the pricer could not value both legs of %r at iv=%r" % (s, iv)
        return (s1 * p1 + s2 * p2) * CONTRACT_MULTIPLIER, "%s, both legs at one vol" % s
    return None, "structure %r is not one this module prices" % s


def can_price(structure: Optional[str]) -> Tuple[bool, Optional[str]]:
    """(priceable, reason it is not). Asked BEFORE the volatility solve.

    THE ORDER MATTERS FOR WHAT NICK READS. Solving first meant a composite failed inside the
    solver and surfaced as "the pricer could not value this structure at the bracket's ends" --
    true, generic, and useless -- instead of "its net mark cannot be split across legs, so no
    single volatility identifies it". The specific reason exists; the wrong order hid it.
    """
    st = str(structure or "").strip().lower()
    if not st:
        return False, "no structure recorded"
    if "+" in st:
        return False, ("structure %r is a COMPOSITE: its net mark cannot be split across "
                       "legs, so no single volatility identifies it (same reason TA-168 "
                       "holds composites in the B2 cut)" % st)
    if st in STOCK or st in SINGLES or st in SPREADS:
        return True, None
    return False, "structure %r is not one this module prices" % st


def solve_iv(position: Dict[str, Any], *, spot: float, r: float,
             today: Optional[_dt.date] = None) -> Tuple[Optional[float], str]:
    """The vol implied by the position's OWN current mark. (iv, basis).

    FROM THE MARK, NOT FROM A VENDOR'S IV FIELD. This repo has already been bitten by a
    plan-tier gated `implied_volatility` arriving as null; a mark is a price that exists
    whenever the position is marked at all. For a spread the solve finds ONE shared vol, which
    is all a net mark can identify.
    """
    s = str(position.get("structure") or "").lower()
    if s in STOCK:
        return None, "shares need no volatility"
    T = years_to_expiry(position.get("expiry"), today)
    if T is None:
        return None, "no expiry, so no volatility can be solved"
    mark = position.get("current_price")
    if mark is None:
        return None, "no current mark, so no volatility can be solved from it"

    def price_at(iv: float) -> Optional[float]:
        v, _ = price_structure(s, spot=spot, long_strike=_f(position.get("long_strike")),
                              short_strike=_f(position.get("short_strike")), T=T, r=r, iv=iv)
        # Back to a PER-UNIT price in the same units as the mark: the book's marks are per
        # share/contract, and the x100 multiplier belongs to the position's value, not to the
        # quoted price. Getting this backwards is a 100x error in the solved vol's input.
        return None if v is None else v / CONTRACT_MULTIPLIER

    try:
        target = abs(float(mark))
    except (TypeError, ValueError):
        return None, "the mark %r is not a number" % (mark,)
    return implied_vol(target, price_at)


def _f(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def position_cells(position: Dict[str, Any], *, spot: float, beta: Optional[float],
                   r: float, scenarios: Sequence[float] = SCENARIOS,
                   today: Optional[_dt.date] = None) -> Dict[str, Any]:
    """One position's P&L CHANGE in each scenario, or its reason for having none.

    THE CELL IS A CHANGE, NOT A VALUE: value-at-scenario minus value-now, both priced by the
    SAME model. Differencing two model prices cancels most of the model's own bias, where
    comparing a model price against the broker's mark would report the model's error as a
    scenario P&L.
    """
    qty = _f(position.get("quantity")) or _f(position.get("open_quantity")) or 0.0
    s = str(position.get("structure") or "").lower()
    ok, why = can_price(s)
    if not ok:
        return {"ticker": position.get("ticker"), "cells": None, "reason": why}
    T = years_to_expiry(position.get("expiry"), today)
    iv, iv_basis = solve_iv(position, spot=spot, r=r, today=today)
    if s not in STOCK and iv is None:
        return {"ticker": position.get("ticker"), "cells": None,
                "reason": "no volatility: %s" % iv_basis}
    if beta is None:
        return {"ticker": position.get("ticker"), "cells": None,
                "reason": "no beta measured for %s, so its move cannot be mapped from SPY"
                          % position.get("ticker")}
    now, basis = price_structure(s, spot=spot, long_strike=_f(position.get("long_strike")),
                                short_strike=_f(position.get("short_strike")), T=T, r=r, iv=iv)
    if now is None:
        return {"ticker": position.get("ticker"), "cells": None, "reason": basis}

    cells: List[Optional[float]] = []
    for spy in scenarios:
        mv = underlying_move(spy, beta)
        shocked = spot * (1.0 + mv)
        # STICKY-STRIKE: the same iv at the shocked spot. T is unchanged -- these are
        # instantaneous shocks, not a passage of time.
        then, _ = price_structure(s, spot=shocked, long_strike=_f(position.get("long_strike")),
                                 short_strike=_f(position.get("short_strike")), T=T, r=r,
                                 iv=iv)
        cells.append(None if then is None else (then - now) * qty)
    return {"ticker": position.get("ticker"), "cells": cells, "qty": qty, "iv": iv,
            "iv_basis": iv_basis, "beta": beta, "value_now": now * qty, "basis": basis,
            "reason": None}


def grid(positions: Sequence[Dict[str, Any]], *, spots: Dict[str, float],
         betas: Dict[str, Optional[float]], r: float,
         scenarios: Sequence[float] = SCENARIOS,
         today: Optional[_dt.date] = None) -> Dict[str, Any]:
    """The whole table: per-account rows, a TOTAL, the worst cell and what is not modelled.

    A position that cannot be modelled is EXCLUDED FROM THE TOTAL and listed in
    `not_modelled`. Silently treating it as zero would make the total read as complete.
    """
    rows: Dict[str, List[float]] = {k: [0.0] * len(scenarios) for k in ACCOUNT_ROWS[:-1]}
    total = [0.0] * len(scenarios)
    not_modelled: List[Dict[str, Any]] = []
    modelled = 0

    for p in positions:
        ticker = str(p.get("ticker", "")).upper()
        row = account_row(p.get("account"))
        spot = spots.get(ticker)
        if row is None:
            not_modelled.append({"ticker": ticker,
                                 "reason": "account %r is not one of the three book accounts"
                                           % p.get("account")})
            continue
        if spot is None:
            not_modelled.append({"ticker": ticker, "reason": "no spot price available"})
            continue
        got = position_cells(p, spot=spot, beta=betas.get(ticker), r=r,
                             scenarios=scenarios, today=today)
        if got["cells"] is None:
            not_modelled.append({"ticker": ticker, "reason": got["reason"]})
            continue
        if any(c is None for c in got["cells"]):
            not_modelled.append({"ticker": ticker,
                                 "reason": "at least one scenario could not be priced"})
            continue
        modelled += 1
        for i, c in enumerate(got["cells"]):
            rows[row][i] += c
            total[i] += c

    out_rows = [{"key": k, "cells": [round(c, 0) for c in rows[k]], "total": False}
                for k in ACCOUNT_ROWS[:-1]]
    out_rows.append({"key": "TOTAL", "cells": [round(c, 0) for c in total], "total": True})
    return {
        "columns": ["%+d%%" % s for s in scenarios],
        "rows": out_rows,
        "worst": worst_cell(out_rows, scenarios),
        "not_modelled": not_modelled,
        "modelled_positions": modelled,
        "vol_mode": VOL_MODE,
        "vol_mode_basis": VOL_MODE_BASIS,
        "label": MODEL_LABEL,
        "caption": "%s · beta-mapped · Black-Scholes reprice · %s" % (MODEL_LABEL, VOL_MODE),
    }


def worst_cell(rows: Sequence[Dict[str, Any]], scenarios: Sequence[float]) -> Dict[str, Any]:
    """The most negative cell across the ACCOUNT rows, never the TOTAL.

    The total's worst cell is a netted figure and hides the account that is actually exposed;
    the point of this cell is to name where the damage lands.
    """
    worst = None
    for r in rows:
        if r.get("total"):
            continue
        for i, c in enumerate(r["cells"]):
            if c is None:
                continue
            if worst is None or c < worst[0]:
                worst = (c, r["key"], scenarios[i])
    if worst is None:
        return {"value": None, "where": None,
                "basis": "no account row has a modelled cell"}
    value, key, spy = worst
    # format(), NOT %-formatting: "%,.0f" is not valid Python. SECOND TIME THIS TURN -- the
    # same mistake was in crowd_b6 an hour ago, which makes it a habit rather than a slip, so
    # it is written down here: a thousands separator only exists in format-spec syntax.
    return {"value": ("-$" if value < 0 else "+$") + format(abs(value), ",.0f"),
            "amount": round(value, 0),
            "where": "%s @ SPY %+d%%" % (key, spy),
            "basis": "the most negative ACCOUNT cell; the total nets accounts and would hide "
                     "which one is exposed"}
