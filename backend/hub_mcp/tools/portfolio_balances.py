"""hub_get_portfolio_balances — live account balances."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.balances import get_account_balances

DESCRIPTION = (
    "Returns live account balances across all four trading accounts — total "
    "balance, cash, buying power, margin. Use this whenever sizing "
    "recommendations need real account values (replaces the prior practice of "
    "hardcoding dollar amounts in skill files), when TORO/URSA/DAEDALUS/PIVOT "
    "is producing a sizing recommendation, when PYTHAGORAS is computing per-"
    "position risk parameters against account size, when PYTHIA is sizing a "
    "B3 scalp trigger, when THALES is flagging sector concentration as a % of "
    'account, when the user asks about "my balance," "how much cash," "buying '
    'power," or any equivalent, when evaluating whether a proposed trade fits '
    "within three-bucket sizing rules.\n\n"
    "Do NOT call this for position-level data (use `hub_get_positions`). Do "
    "NOT call this for historical balance changes (v2 candidate).\n\n"
    "Returns per-account balance, cash, buying power, margin, last-updated "
    "timestamp."
)

Account = Literal[
    "robinhood", "fidelity_roth", "brokerage_link_401k", "breakout_prop"
]

_VALID_ACCOUNTS = {"robinhood", "fidelity_roth", "brokerage_link_401k", "breakout_prop"}

_DB_TO_NORMAL = {
    "ROBINHOOD": "robinhood",
    "FIDELITY_ROTH": "fidelity_roth",
    "BROKERAGE_LINK_401K": "brokerage_link_401k",
    "BREAKOUT_PROP": "breakout_prop",
}

# breakout_prop is intentionally NOT balance-tracked (DESCOPED 2026-07-23): no row
# exists in account_balances by design. We surface it EXPLICITLY as untracked
# (honest-absence) rather than omitting it silently, so a committee reader sees it
# exists but is unmistakably non-sizable — declining to size it is correct behavior,
# not a data gap. Kept OUT of `accounts` (the sizable set) and out of every total.
_BREAKOUT_PROP_UNTRACKED = {
    "account": "breakout_prop",
    "broker": "breakout",
    "tracked": False,
    "status": "untracked",
    "balance": None,
    "cash": None,
    "buying_power": None,
    "margin_total": None,
    "updated_at": None,
    "is_stale": False,
    "note": (
        "breakout_prop is intentionally not balance-tracked (DESCOPED 2026-07-23); "
        "no balance row exists by design. Committee must NOT size against it — "
        "declining to size it is designed behavior, not a data gap (honest-absence)."
    ),
}


def _is_stale(updated_iso: Optional[str], hours: int = 24) -> bool:
    if not updated_iso:
        return True
    try:
        ts = datetime.fromisoformat(updated_iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    delta_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    return delta_hours > hours


def _build_account(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_name = (row.get("account_name") or "").upper()
    name = _DB_TO_NORMAL.get(raw_name, raw_name.lower())
    return {
        "account": name,
        "broker": row.get("broker") or "",
        # R-IV.559(c)2/3. `balance` is derived cash plus this account's open
        # positions at their marks, and `None` where there is no anchor -- the old
        # `or 0` turned an unknowable account into a $0 one, which a committee sizes
        # against as confidently as a real figure. `buying_power` is the broker's
        # own number and the hub cannot derive it, so it is None with a reason.
        "balance": (float(row["balance"]) if row.get("balance") is not None else None),
        "balance_partial": row.get("balance_partial"),
        "balance_reason": row.get("balance_reason"),
        "cash": float(row.get("cash") or 0) if row.get("cash") is not None else None,
        "cash_source": row.get("cash_source"),
        "cash_difference": row.get("cash_difference"),
        "buying_power": None,
        "buying_power_reason": row.get("buying_power_reason"),
        "margin_total": float(row.get("margin_total") or 0)
        if row.get("margin_total") is not None
        else None,
        "trailing_drawdown_floor": None,
        "high_water_mark": None,
        "updated_at": row.get("updated_at"),
        "is_stale": _is_stale(row.get("updated_at")),
    }


@mcp_tool(name="hub_get_portfolio_balances", description=DESCRIPTION)
async def hub_get_portfolio_balances(account: Optional[Account] = None) -> dict:
    """Return per-account balance data."""
    if account is not None and account not in _VALID_ACCOUNTS:
        return make_response(
            status="unavailable",
            error=f"Invalid account '{account}'.",
            summary="Invalid account filter.",
        )

    rows = await get_account_balances(account=account.upper() if account else None)
    if rows is None:
        return make_response(
            status="unavailable",
            error="Account balances source unavailable.",
            summary="MCP: balances data unavailable.",
        )

    accounts: List[Dict[str, Any]] = [_build_account(r) for r in rows]

    # ── T4 (R-IV.394): AGGREGATES EXCLUDE OUT_OF_SCOPE BY VOCABULARY ──────
    # Measured live 2026-09-05: total_balance 21,320.13 against 9,677.78 true
    # (+120%), total_cash 16,862.47 against 5,220.12 (+223%) — because this sum
    # counted EVERY row, and the parked 401A+403B money sits in the table under
    # `BROKERAGE_LINK_401K`.
    #
    # EXCLUDED BY SCOPE, NOT BY STALENESS, and the distinction is the fix
    # (R-IV.284): that row is not an old reading of the traded account, it is a
    # DIFFERENT POT under a misleading name. A staleness-based exclusion would be
    # "refreshed" by a diligent maintainer who found an old row and updated it. A
    # scope-based one cannot be, because there is nothing to refresh it to.
    #
    # The rows are still RETURNED — never deleted, never hidden — so a reader sees
    # the money exists and sees that it is not spendable. Only the TOTALS change.
    from config.accounts import is_in_scope
    for a in accounts:
        a["in_scope"] = is_in_scope(a.get("account") or a.get("name"))
    tradeable = [a for a in accounts if a["in_scope"]]

    # A total over figures that are not all knowable is not a total. Accounts whose
    # balance could not be derived are EXCLUDED and named, the same shape the
    # capital-at-risk figure already uses -- summing them as zero would understate
    # the book by exactly the accounts nobody has anchored yet.
    valued = [a for a in tradeable if a["balance"] is not None]
    unvalued = [a["account"] for a in tradeable if a["balance"] is None]
    total_balance = sum(a["balance"] for a in valued)
    total_cash = sum(a["cash"] or 0 for a in tradeable)
    total_bp = None          # buying power is the broker's; the hub does not total it
    total_partial = bool(unvalued) or any(a.get("balance_partial") for a in valued)
    excluded = [a.get("account") or a.get("name") for a in accounts if not a["in_scope"]]
    # Envelope-level staleness ignores zero-balance dormant accounts: a Feb-dated
    # $0 account (e.g. IBKR) must not drag the whole envelope 'stale' and demote
    # PIVOT conviction on otherwise-fresh balances. Per-account is_stale flags are
    # unchanged — a consumer can still see which specific accounts are old.
    funded = [a for a in tradeable if a["balance"]]
    any_stale = any(a["is_stale"] for a in funded)

    data = {
        "accounts": accounts,
        # Named, not silently dropped: a total that excludes money should say
        # which money, or the next reader reconciles it against the account list
        # and finds a gap with no explanation attached.
        "excluded_out_of_scope": excluded,
        "total_balance": round(total_balance, 2),
        "total_balance_partial": total_partial,
        "total_balance_excluded": unvalued,
        "total_cash": round(total_cash, 2),
        "total_buying_power": None,
        "total_buying_power_reason": (
            "buying power is the broker's own figure and the hub cannot derive it"),
    }
    # Additive: list breakout_prop as explicitly untracked (never in `accounts`, never
    # in a total) when unfiltered or explicitly filtered to it. No scoring/sizing logic.
    if account is None or account == "breakout_prop":
        data["untracked_accounts"] = [dict(_BREAKOUT_PROP_UNTRACKED)]
    untracked_note = (
        " breakout_prop: untracked (no balance row — not sizable)."
        if "untracked_accounts" in data else ""
    )
    status = "stale" if any_stale else "ok"
    summary = (
        f"Total ${total_balance:,.0f} across {len(valued)} of {len(accounts)} accounts"
        + (f" ({len(unvalued)} not derivable: {', '.join(unvalued)})" if unvalued else "")
        + (" - PARTIAL, some positions could not be valued" if total_partial and not unvalued
           else "")
        + f". Cash ${total_cash:,.0f}. Buying power is the broker's figure and is not served. "
        + ("Some balances >24h old." if any_stale else "All balances recent.")
        + untracked_note
    )
    return make_response(
        status=status,
        data=data,
        summary=summary,
        staleness_seconds=3600 if any_stale else 60,
    )
