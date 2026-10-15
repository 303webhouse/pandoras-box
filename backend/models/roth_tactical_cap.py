"""The 20% tactical reminder for FIDELITY_ROTH / FIDELITY_401A — R-IV.1033(e).

THE PRINCIPAL'S RULING, and every clause of it is load-bearing:

  * MARKET VALUE, not cost basis. A position that has doubled occupies twice the share of the
    account it did at entry, and the cap is about what the account is exposed to now.
  * REMINDER-LEVEL. It NEVER blocks a write. Nothing in this module raises on a breach; the
    only thing it can do is return a verdict and push a notification.
  * A NULL CLASSIFICATION COUNTS AS TACTICAL, PROVISIONALLY, and the push says "provisional".
    Reading NULL as "not tactical" would under-report the very cap this exists to watch --
    that is exactly how `strategy_tag` under-read it before (SOXS alone at 8.26% against the
    truth of SOXS + TSLQ at 19.50%). Reading it as tactical without saying so would overstate
    a figure the principal may act on. So it is counted AND flagged.
  * PERCENT ONLY. The push carries no dollar figure, because ntfy is a third-party relay
    (R-IV.901(b)2). The percentage is the whole message.

THE COMPUTATION IS PURE AND SEPARATE FROM THE PUSH. `tactical_share()` takes rows and an
account value and returns a verdict; nothing in it reads a clock, a database or an env var. The
delivery decision lives in `should_push()` and the I/O in the caller. A reminder whose
arithmetic can only be tested through a webhook is a reminder nobody tests.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: R-IV.1033(e): the same rule for both. Named rather than spelled at each site, and compared
#: case-insensitively because `is_in_scope` once answered differently for FIDELITY_401A and
#: fidelity_401a (R-IV.849(d)).
CAP_ACCOUNTS = frozenset({"FIDELITY_ROTH", "FIDELITY_401A"})

#: The reminder level. NOT a limit: nothing here refuses anything.
REMINDER_THRESHOLD_PCT = Decimal("20.0")

TACTICAL = "TACTICAL"

#: A row counted as tactical only because its classification is absent.
PROVISIONAL = "provisional"


def _dec(v: Any) -> Optional[Decimal]:
    """Decimal(str(x)) or None. Decimal(0.19) is 0.1900000000000000078..."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return Decimal(str(v))
    except Exception:                                               # noqa: BLE001
        return None


def _multiplier(structure: Any) -> int:
    """100 for contracts, 1 for shares.

    Deliberately NOT the orientation whitelist: this asks "how much money does one unit
    represent", which is knowable for every structure including the ones whose orientation is
    held (TA-168). Collapsing the two would make an unclassifiable row unpriceable.
    """
    whole = (structure or "").strip().lower()
    if not whole or whole == "stock":
        return 1
    return 100


def market_value(row: Dict[str, Any]) -> Tuple[Optional[Decimal], Optional[str]]:
    """(market value, reason it is unknown). open_quantity x price x multiplier.

    `open_quantity`, NEVER `quantity` (convention #29): `quantity` is the size the position was
    OPENED at and does not shrink on a partial exit, so a cap computed from it would overstate
    every partially-closed position. A NULL `open_quantity` is UNKNOWN, not zero.
    """
    qty = _dec(row.get("open_quantity"))
    if qty is None:
        return None, "open_quantity is NULL (unknown remainder, not zero)"
    if qty <= 0:
        return Decimal("0"), None
    px = _dec(row.get("current_price"))
    if px is None:
        return None, "no current_price (position unvalued)"
    return (qty * px * Decimal(_multiplier(row.get("structure")))), None


def is_tactical(row: Dict[str, Any]) -> Tuple[bool, bool]:
    """(counts as tactical, is that only provisionally?).

    `classification` is the field the cap depends on -- never `strategy_tag`, which mixes three
    taxonomies and under-read this very cap (TA-123).
    """
    c = (row.get("classification") or "").strip().upper()
    if c == TACTICAL:
        return True, False
    if not c:
        # NULL counts, and the caller is told it was a provisional count.
        return True, True
    return False, False


def in_scope(row: Dict[str, Any]) -> bool:
    return (row.get("account") or "").strip().upper() in CAP_ACCOUNTS


def tactical_share(rows: Iterable[Dict[str, Any]], account: str,
                   account_value: Any) -> Dict[str, Any]:
    """Tactical market value as a percentage of the account total. PURE — no clock, no I/O.

    Returns `pct = None` when the account value is unusable; a percentage of an unknown total
    is not a number, and a zero would read as "nothing tactical".
    """
    acct = (account or "").strip().upper()
    av = _dec(account_value)
    mine = [r for r in rows
            if (r.get("account") or "").strip().upper() == acct]

    tac = Decimal("0")
    provisional_ids: List[str] = []
    unvalued: List[str] = []
    counted = 0
    for r in mine:
        tactical, prov = is_tactical(r)
        if not tactical:
            continue
        mv, why = market_value(r)
        if mv is None:
            unvalued.append("%s (%s)" % (r.get("position_id") or "?", why))
            continue
        if mv == 0:
            continue
        counted += 1
        tac += mv
        if prov:
            provisional_ids.append(str(r.get("position_id") or "?"))

    out: Dict[str, Any] = {
        "account": acct,
        "tactical_market_value": str(tac),
        "positions_counted": counted,
        "provisional_position_ids": provisional_ids,
        "provisional": bool(provisional_ids),
        "unvalued": unvalued,
        "threshold_pct": str(REMINDER_THRESHOLD_PCT),
        "pct": None,
        "at_or_over": False,
        "reason": "",
    }
    if av is None or av <= 0:
        out["reason"] = ("account value unusable (%r), so a percentage cannot be computed -- "
                         "NOT reported as zero" % (account_value,))
        return out

    pct = (tac / av * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    out["pct"] = str(pct)
    out["at_or_over"] = pct >= REMINDER_THRESHOLD_PCT
    out["reason"] = ("tactical %s of account %s = %s%% (reminder at %s%%)%s"
                     % (tac, av, pct, REMINDER_THRESHOLD_PCT,
                        "; counted provisionally for %d row(s) with no classification"
                        % len(provisional_ids) if provisional_ids else ""))
    if unvalued:
        # Understates, and says so. An unvalued tactical row can only push the true figure UP.
        out["reason"] += ("; %d tactical row(s) unvalued, so this UNDERSTATES"
                          % len(unvalued))
    return out


def push_text(verdict: Dict[str, Any]) -> str:
    """The phone line. PERCENT ONLY — no dollars, by construction (R-IV.901(b)2)."""
    prov = " provisional" if verdict.get("provisional") else ""
    return "tactical at %s%% (%s%% reminder)%s" % (
        verdict.get("pct"), verdict.get("threshold_pct"), prov)


def should_push(verdict: Dict[str, Any], last_pushed_pct: Any) -> bool:
    """Push once, and again only when the figure MOVES — R-IV.1033(e)'s "push once".

    "Once" cannot mean "once ever": a book that goes 20% -> 31% is news the principal wants.
    So it fires on the first crossing and thereafter only when the rounded percentage changes,
    which is quiet while the figure sits still and speaks when it moves. Never fires below the
    threshold, and never when the percentage is unknown.
    """
    if not verdict.get("at_or_over") or verdict.get("pct") is None:
        return False
    prev = _dec(last_pushed_pct)
    if prev is None:
        return True
    return _dec(verdict["pct"]) != prev
