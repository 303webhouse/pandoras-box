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
        "balance": float(row.get("balance") or 0),
        "cash": float(row.get("cash") or 0) if row.get("cash") is not None else None,
        "buying_power": float(row.get("buying_power") or 0)
        if row.get("buying_power") is not None
        else None,
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
    total_balance = sum(a["balance"] for a in accounts)
    total_cash = sum(a["cash"] or 0 for a in accounts)
    total_bp = sum(a["buying_power"] or 0 for a in accounts)
    any_stale = any(a["is_stale"] for a in accounts)

    data = {
        "accounts": accounts,
        "total_balance": round(total_balance, 2),
        "total_cash": round(total_cash, 2),
        "total_buying_power": round(total_bp, 2),
    }
    status = "stale" if any_stale else "ok"
    summary = (
        f"Total ${total_balance:,.0f} across {len(accounts)} accounts. "
        f"Cash ${total_cash:,.0f}, BP ${total_bp:,.0f}. "
        + ("Some balances >24h old." if any_stale else "All balances recent.")
    )
    return make_response(
        status=status,
        data=data,
        summary=summary,
        staleness_seconds=3600 if any_stale else 60,
    )
