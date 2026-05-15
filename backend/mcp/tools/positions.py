"""hub_get_positions — unified_positions accessor."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.positions import list_positions

DESCRIPTION = (
    "Returns positions from the unified_positions table — the canonical source "
    "of truth for Nick's trading book across Robinhood, Fidelity Roth IRA, "
    "401k BrokerageLink, and Breakout Prop. Optionally filtered by account or "
    "status. Use this whenever evaluating portfolio coherence (URSA's "
    "mandatory check), when a trade idea touches an existing position, when "
    "sizing recommendations need awareness of current exposure, when TORO is "
    "evaluating an \"add to existing position\" decision, when PYTHAGORAS is "
    "checking structural risk concentration, when PYTHIA is checking which "
    "positions sit at her key auction levels, when THALES is flagging sector "
    "concentration risk, when DAEDALUS is computing per-account exposure for "
    "sizing math, when PIVOT is pulling existing book context for synthesis, "
    'or when the user asks about "my positions," "open trades," "what am I '
    'holding," or any equivalent.\n\n'
    "Do NOT call this to check live account balances (use "
    "`hub_get_portfolio_balances` for cash/buying power). Do NOT call this "
    "for closed trade outcomes prior to position close (those live in "
    "`signal_outcomes`, a v2 tool).\n\n"
    "Returns full position records including structure, strikes, expiry, "
    "quantity, entry price, current value, unrealized PnL, stop loss, and "
    "account assignment."
)

Account = Literal[
    "robinhood", "fidelity_roth", "brokerage_link_401k", "breakout_prop"
]
Status = Literal["OPEN", "CLOSED", "ALL"]

_VALID_ACCOUNTS = {"robinhood", "fidelity_roth", "brokerage_link_401k", "breakout_prop"}
_VALID_STATUS = {"OPEN", "CLOSED", "ALL"}


def _normalize_account(value: str) -> str:
    """Map our normalized snake_case account names to DB account column values."""
    mapping = {
        "robinhood": "ROBINHOOD",
        "fidelity_roth": "FIDELITY_ROTH",
        "brokerage_link_401k": "BROKERAGE_LINK_401K",
        "breakout_prop": "BREAKOUT_PROP",
    }
    return mapping.get(value, value.upper())


def _build_position(row: Dict[str, Any]) -> Dict[str, Any]:
    expiry = row.get("expiry")
    dte = None
    if isinstance(expiry, str) and expiry:
        try:
            dte = (date.fromisoformat(expiry) - date.today()).days
        except ValueError:
            dte = None

    status = (row.get("status") or "").upper()
    outcome = "OPEN"
    if status == "CLOSED":
        unrealized = row.get("realized_pnl") or row.get("unrealized_pnl")
        if unrealized is None:
            outcome = "OPEN"
        elif unrealized > 0:
            outcome = "WIN"
        elif unrealized < 0:
            outcome = "LOSS"
        else:
            outcome = "BREAKEVEN"

    return {
        "position_id": row.get("position_id") or row.get("id"),
        "ticker": row.get("ticker"),
        "account": (row.get("account") or "").lower(),
        "structure": row.get("structure"),
        "quantity": row.get("quantity"),
        "entry_price": row.get("entry_price"),
        "current_price": row.get("current_price"),
        "current_value": row.get("current_value"),
        "unrealized_pnl": row.get("unrealized_pnl"),
        "max_loss": row.get("max_loss") or row.get("cost_basis"),
        "long_strike": row.get("long_strike"),
        "short_strike": row.get("short_strike"),
        "expiry": expiry,
        "dte": dte,
        "stop_loss": row.get("stop_loss"),
        "target": row.get("target") or row.get("target_price"),
        "opened_at": row.get("entry_date") or row.get("created_at"),
        "closed_at": row.get("closed_at"),
        "trade_outcome": outcome,
    }


@mcp_tool(name="hub_get_positions", description=DESCRIPTION)
async def hub_get_positions(
    account: Optional[Account] = None,
    status: Status = "OPEN",
    ticker: Optional[str] = None,
) -> dict:
    """Return positions matching the requested filters."""
    if account is not None and account not in _VALID_ACCOUNTS:
        return make_response(
            status="unavailable",
            error=f"Invalid account '{account}'.",
            summary="Invalid account filter.",
        )
    if status not in _VALID_STATUS:
        return make_response(
            status="unavailable",
            error=f"Invalid status '{status}'. Use OPEN, CLOSED, or ALL.",
            summary="Invalid status filter.",
        )

    rows = await list_positions(
        status=status,
        ticker=ticker,
        account=_normalize_account(account) if account else None,
    )
    if rows is None:
        return make_response(
            status="unavailable",
            error="Positions source unavailable.",
            summary="MCP: positions data unavailable.",
        )

    positions: List[Dict[str, Any]] = [_build_position(r) for r in rows]
    total_at_risk = sum(
        float(p.get("max_loss") or 0)
        for p in positions
        if p.get("max_loss") is not None
    )

    data = {
        "account": account,
        "status": status,
        "ticker": ticker.upper() if ticker else None,
        "positions": positions,
        "position_count": len(positions),
        "total_capital_at_risk": round(total_at_risk, 2),
    }
    summary = (
        f"{len(positions)} {status.lower()} positions, "
        f"${total_at_risk:,.0f} capital at risk."
    )
    if ticker:
        summary = f"{ticker.upper()}: " + summary
    return make_response(status="ok", data=data, summary=summary, staleness_seconds=60)
