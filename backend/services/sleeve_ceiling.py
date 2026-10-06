"""The Robinhood sleeve ceiling, summed over the registry — R-IV.644(d) / TA-070.

WHAT IT IS. The Robinhood options-and-convexity sleeve is governed by a ceiling of **10% of
all tracked accounts combined**, with **$200 always in cash**. Trade Analysis ruled the base in
TA-070, which follows the principal's own rule of Fidelity plus Robinhood.

WHY THIS MODULE EXISTS. The hub did not compute it anywhere. It lived twice as prose —
`docs/committee-training-parameters.md` said *"about 10% of FIDELITY_ROTH + ROBINHOOD
combined"* — and once as a **mock** in `frontend/v2.js`, whose own note says *"sleeve ceiling
and cash floor have no read endpoint (figures here are mock)"* with a hardcoded `ceiling: 968`.
A number the committee sizes against, that nothing computes, is a number that silently stops
being true.

AND IT WAS ABOUT TO STOP BEING TRUE. Both written forms name **two accounts**. A third tracked
account arrived on 2026-10-01 (R-IV.632(c)), so a base of named keys now omits it — and would
omit the fourth as well, with nothing to notice. **The base is therefore the REGISTRY'S tracked
accounts, never a list of names.** That is the whole point of this module: adding an account to
`models.accounts.CANONICAL_ACCOUNTS` moves the ceiling, by construction.

AN ACCOUNT WITH NO FIGURE IS NOT ZERO. A tracked account whose balance is unknown makes the
base PARTIAL, and a partial base is reported as partial rather than quietly summed as if the
missing account held nothing — understating the base understates the ceiling, which reads as
less headroom than the principal has, and he would size down against a number nobody checked.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.accounts import CANONICAL_ACCOUNTS, DISPLAY_NAMES
# money_in, not money: `money` takes a Decimal, and every figure arriving here is a
# float or a DB numeric. money_in quantizes any numeric HALF-UP (convention #27) and
# returns None for None or NaN rather than a number.
from services.position_economics import money_in as money

# TA-070. The fraction and the floor are the ruling's, in one place each.
CEILING_FRACTION = 0.10
CASH_FLOOR_USD = 200.00

# The sleeve the ceiling governs. Not a base — the base is every tracked account.
SLEEVE_ACCOUNT = "ROBINHOOD"


def ceiling_from_balances(balances: Dict[str, Any],
                          understated: Optional[set] = None) -> Dict[str, Any]:
    """The sleeve ceiling from `{account_key: value}`.

    `balances` carries each account's value AS THE BALANCES SERVICE DERIVES IT — cash from
    the ledger plus that account's open positions at their marks (R-IV.647(b)) — never the
    retired stored total. A missing key or None is UNKNOWN, never zero. Only keys the
    registry tracks contribute, so a row under a retired or disputed label —
    `BROKERAGE_LINK_401K`, the parked 401(a)+403(b) snapshot — cannot enter the base however
    it is spelled.

    `understated` names accounts whose value is PRESENT but incomplete, which the service
    reports as `balance_partial` when an open position has no mark. Such a value may not be
    summed into the published ceiling as though it were whole, but it IS a valid input to the
    lower bound, because it can only be too small.
    """
    understated = set(understated or ())
    included: Dict[str, Optional[float]] = {}
    missing = []
    base = 0.0

    for key in CANONICAL_ACCOUNTS:
        raw = balances.get(key)
        if raw is None:
            missing.append(key)
            included[key] = None
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            missing.append(key)
            included[key] = None
            continue
        # NaN passes float() and every `if not v` guard -- `not nan` is False and
        # `nan <= 0` is False -- and one NaN in the sum makes the whole base NaN, so the
        # ceiling becomes NaN and serialises as a number. Caught explicitly, as UNKNOWN.
        if v != v or v in (float("inf"), float("-inf")):
            missing.append(key)
            included[key] = None
            continue
        included[key] = money(v)
        base += v

    # Present-but-incomplete counts toward the lower bound and blocks the figure.
    incomplete = sorted(a for a in understated if included.get(a) is not None)
    partial = bool(missing) or bool(incomplete)
    return {
        "sleeve_account": SLEEVE_ACCOUNT,
        "sleeve_display": DISPLAY_NAMES.get(SLEEVE_ACCOUNT),
        "rule": f"{int(CEILING_FRACTION * 100)}% of all tracked accounts combined (TA-070)",
        "base_accounts": list(CANONICAL_ACCOUNTS),
        "base_balances": included,
        "base_total": money(base),
        # None, not a number, when the base is incomplete: a ceiling computed off a base
        # that is missing an account is not this ceiling, and publishing it anyway is how
        # a figure nobody checked becomes the one everybody sizes against.
        "ceiling": None if partial else money(base * CEILING_FRACTION),
        "cash_floor": money(CASH_FLOOR_USD),
        # A CAP UNDERSTATED IS THE SAFE DIRECTION — R-IV.647(b), and this is my addition
        # rather than the ruling's, flagged for SPINE to keep or drop.
        #
        # `ceiling` stays None on a partial base: no confident figure off an incomplete one.
        # But the balances service reports PARTIAL whenever any open position lacks a mark,
        # which is often, and a cap nobody can read is a cap nobody honours. A partial value
        # UNDERSTATES its account, so a ceiling computed from it is a LOWER BOUND on the real
        # ceiling — and for a cap, too low is the conservative error: it restricts more.
        #
        # Served under a name that cannot be mistaken for the figure, with the accounts that
        # are merely understated counted and the ones that are UNKNOWN excluded entirely —
        # an unknown account contributes nothing to a lower bound either.
        "ceiling_at_least": (money(base * CEILING_FRACTION)
                             if partial and base > 0 else None),
        "ceiling_at_least_basis": (
            "a LOWER BOUND, not the ceiling: computed from the accounts that returned a "
            "value, each of which understates its account when partial. The real ceiling is "
            "at least this. Not a licence to size to it."
        ) if partial and base > 0 else None,
        "partial": partial,
        "partial_reason": "; ".join(
            ([("no value for " + ", ".join(missing) + " — a tracked account with no figure "
               "is UNKNOWN, not zero, so no ceiling is published")] if missing else [])
            + ([("the value for " + ", ".join(incomplete) + " is PARTIAL — an open position "
                 "has no mark, so it understates that account and no ceiling is published")]
               if incomplete else [])
        ) or None,
        "understated_accounts": incomplete or None,
    }


def headroom(ceiling: Optional[float], at_risk: Optional[float]) -> Optional[float]:
    """What is left under the ceiling, or None when either side is unknown.

    None in, None out. A headroom computed against an unknown ceiling, or against unknown
    risk, is the shape of answer that gets acted on.
    """
    if ceiling is None or at_risk is None:
        return None
    return money(ceiling - float(at_risk))
