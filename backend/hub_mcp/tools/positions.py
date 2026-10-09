"""hub_get_positions — unified_positions accessor."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.position_economics import capital_at_risk_from_derived
from services.read_only.positions import list_positions

from models.accounts import CANONICAL_ACCOUNTS as _CANONICAL_TUPLE
from models.accounts import account_choices as _account_choices
from models.accounts import describe_accounts as _describe_accounts

DESCRIPTION = (
    "Returns positions from the unified_positions table — the canonical source "
    "of truth for Nick's trading book across " + _describe_accounts() +
    ", plus Breakout Prop (untracked). Optionally filtered by account or "
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
    "account assignment.\n\n"
    # R-IV.780(e)1. Named in the DESCRIPTION, not only in the payload: a committee seat decides
    # whether it can enforce a bucket limit from what this text promises, and until now the text
    # promised nothing about classification because the field was being dropped.
    "**`strategy_tag` MIXES CLASSIFICATION, SLEEVE TAG AND BUCKET. NO CAP, GATE OR FILTER MAY "
    "BE COMPUTED FROM IT** (TA-123, R-IV.794(b)). It is a DISPLAY STRING only. One column holds "
    "three independent taxonomies, so each row shows whichever was written last and the other "
    "two are simply gone. That is not a presentation nuisance, it under-reads a hard cap: "
    "filtering it for the Roth's 20% tactical cap returned SOXS alone at 8.26% against the truth "
    "of SOXS + TSLQ at 19.50%, because TSLQ's `TACTICAL` had been overwritten by its bucket "
    "`B2`. A limit read off this field is a limit read off the last edit.\n\n"
    "**Read `classification` (`STRATEGIC`/`TACTICAL`), `sleeve_tag` (`TAIL`/`CONVEXITY`) and "
    "`bucket` (`B1`/`B2`/`B3`) instead.** Three independent nullable fields, served on every "
    "row. `classification` is what the hard cap depends on.\n\n"
    "**AND CHECK `classification_backfilled` BEFORE ENFORCING ANYTHING.** While it is false the "
    "three fields are present but NOT yet populated, so a `null` there means \"not yet "
    "migrated\", NOT \"this row has no classification\". Reading the first as the second is how "
    "an unenforced cap reports itself as a satisfied one. Values are the principal's and are "
    "never inferred (R-IV.730(a)); an absent value is unknown, never a default.\n\n"
    "SIZE: TWO FIELDS, AND THEY ANSWER DIFFERENT QUESTIONS (convention #29, "
    "R-IV.660). `quantity` is the size the position was OPENED at, including any "
    "adds -- it does NOT shrink when part of the position is closed, because the "
    "cost basis and every percentage computed from it belong to the trade as "
    "taken. `open_quantity` is what is STILL OPEN: the sum of the position's lot "
    "quantities, with closes subtracted. For how much exposure the book carries "
    "right now -- sizing, risk, concentration, an add-to-position decision, or "
    "anything multiplied by a price -- READ `open_quantity`. Reading `quantity` "
    "for that overstates any position that has been partially closed. "
    "`open_quantity_basis` says where the figure came from: `lots` means "
    "measured; a null `open_quantity` means the position has no lots and its "
    "remainder is UNKNOWN -- that is not zero, and it must not be treated as a "
    "flat position. `open_remainder` is an older name for `open_quantity` and "
    "carries the identical value."
)

# R-IV.638(b)4: BUILT from the registry, not typed. `brokerage_link_401k` is GONE from the
# offered values -- it is the retired merged snapshot of the parked 401(a)+403(b) under a
# disputed label, and offering it beside the traded accounts is how a committee member sizes
# off $11,642.35 that is in neither of them. `breakout_prop` stays: it is a real, separate,
# deliberately untracked account, not the retired snapshot.
Account = Literal[tuple(_account_choices() + ["breakout_prop"])]  # type: ignore[misc]
Status = Literal["OPEN", "CLOSED", "ALL"]

_VALID_ACCOUNTS = set(_account_choices()) | {"breakout_prop"}
_VALID_STATUS = {"OPEN", "CLOSED", "ALL"}


def _normalize_account(value: str) -> str:
    """Map our normalized snake_case account names to DB account column values."""
    mapping = {a.lower(): a for a in _CANONICAL_TUPLE}
    mapping["breakout_prop"] = "BREAKOUT_PROP"
    return mapping.get(value, value.upper())


def _classification_backfilled(positions: List[Dict[str, Any]]) -> bool:
    """Has R-IV.794(b)3's backfill run.

    DERIVED FROM THE DATA, deliberately: true as soon as any row carries a classification, so it
    flips by itself the moment the backfill writes its first row and cannot be left stale by a
    constant nobody remembered to bump.

    Its limit, stated rather than discovered: on an empty or fully-ambiguous selection it reads
    false, which is the safe direction — "cannot enforce" rather than "nothing to enforce".
    """
    return any(p.get("classification") for p in positions)


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
        # Both arrive already derived from the lots (R-IV.526(b)). The old
        # `max_loss or cost_basis` fallback is gone: it put a stored figure back
        # under a lot-derived name for exactly the rows that have no lots, which is
        # the substitution the ruling removes. A row that cannot state its own
        # basis says None, and `basis_reason` says why.
        "unrealized_pnl": row.get("unrealized_pnl"),
        "max_loss": row.get("max_loss"),
        # R-IV.660(b)2. TWO FIGURES, NEVER ONE. `quantity` above is the size OPENED;
        # `open_quantity` is what is still held. `open_remainder` is the older key for the
        # same figure, kept so nothing reading it breaks -- same author, not a second answer.
        "open_quantity": row.get("open_quantity"),
        "open_quantity_basis": row.get("open_quantity_basis"),
        "open_remainder": row.get("open_remainder"),
        "basis_reason": (row.get("derived") or {}).get("basis_reason"),
        "long_strike": row.get("long_strike"),
        "short_strike": row.get("short_strike"),
        "expiry": expiry,
        "dte": dte,
        "stop_loss": row.get("stop_loss"),
        "target": row.get("target") or row.get("target_price"),
        "opened_at": row.get("entry_date") or row.get("created_at"),
        "closed_at": row.get("closed_at"),
        "trade_outcome": outcome,
        # R-IV.780(e)1: SERVED AS STORED. `read_only/positions.py` selects * so the column was
        # always in the row -- it was THIS projection that dropped it, which is why no agent could
        # read a bucket and X4, X10 and B3's limits were unenforceable from the hub.
        #
        # One column, FOUR vocabularies (measured 2026-10-09 across 32 open rows):
        #   classification  STRATEGIC (8, rows 968-975), TACTICAL (1, row 976), CORE (1)
        #   sleeve          TAIL (10), CONVEXITY (8)
        #   TA buckets      B1 (7), B2 (6)
        # Served raw and UNINTERPRETED on purpose. A reader asking "is this tactical?" must not be
        # answered by this lane guessing that TAIL means tactical -- classification is the
        # principal's and is never inferred (R-IV.730(a)). The split into its own column comes
        # with the classification column; until then a consumer sees exactly what is stored.
        "strategy_tag": row.get("strategy_tag"),
        # TA-123 / R-IV.794(b)2: the three independent taxonomies, served separately. A cap is
        # computed from `classification`; `strategy_tag` above is a display string with no
        # authority, because it only ever kept whichever of the three was written last.
        "classification": row.get("classification"),
        "sleeve_tag": row.get("sleeve_tag"),
        "bucket": row.get("bucket"),
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

    # R-IV.207(d) / R-IV.526(b): THIS LINE NO LONGER SUMS max_loss.
    #
    # It used to read `max_loss or cost_basis` across every open row, which was not
    # one number: a row with a max_loss contributed a worst case while its
    # neighbour contributed a cost. And max_loss itself carried the wrong contract
    # scope on ten of the seventeen lotted open rows -- WEAT 367 at six-contract
    # scope on three, GUSH frozen at its first lot -- so the published total was
    # understated by $632.08, 13.7%, when measured on 2026-09-24.
    #
    # What is published instead is cost-derived at the open remainder and says so.
    # Rows without lots are excluded and counted, never estimated: the figure is
    # labelled incomplete rather than quietly dropping five positions.
    risk = capital_at_risk_from_derived(rows)
    total_at_risk = risk["capital_at_risk_cost_basis"] or 0.0

    # R-IV.780(e)1: serving the field is not the same as the book being classified. Measured
    # 2026-10-09: 4 of 32 open rows carry NO strategy_tag (ABNB 379, HYG 516, META 527, XLF 978 --
    # all ROBINHOOD options), and for those four X4, X10 and B3 remain unenforceable no matter
    # what this payload carries. Published as a count and a list, because "the field is served"
    # and "every row can be classified" are different claims and only the second enforces a rule.
    untagged = [p["position_id"] for p in positions if not p.get("strategy_tag")]
    data = {
        "account": account,
        "status": status,
        "ticker": ticker.upper() if ticker else None,
        "positions": positions,
        "position_count": len(positions),
        "strategy_tag_basis": (
            "DISPLAY STRING ONLY -- strategy_tag mixes classification, sleeve tag and bucket; "
            "no cap, gate or filter may be computed from it (TA-123, R-IV.794(b)). One column "
            "held three independent taxonomies, so each row kept only whichever was written "
            "last: filtering it for the Roth's 20% tactical cap gave SOXS alone at 8.26% "
            "against the truth of SOXS + TSLQ at 19.50%, TSLQ's TACTICAL having been "
            "overwritten by its bucket B2. Read classification / sleeve_tag / bucket instead. "
            "Never inferred (R-IV.730(a))."),
        # The state flag, so a null in the three fields is not read as a decision. While this
        # is false they are present but unpopulated: null means "not yet migrated", NOT "this
        # row has no classification". Treating the first as the second is how an unenforced cap
        # reports itself as a satisfied one.
        "classification_backfilled": _classification_backfilled(positions),
        "positions_without_classification": sum(
            1 for p in positions if not p.get("classification")),
        "position_ids_without_classification": [
            p["position_id"] for p in positions if not p.get("classification")],
        "cap_enforceable": _classification_backfilled(positions) and not any(
            not p.get("classification") for p in positions),
        "positions_without_strategy_tag": len(untagged),
        "untagged_position_ids": untagged,
        **risk,
    }
    # R-IV.548(b): when the caller asked for CLOSED or ALL, say out loud that the
    # risk figure counted the open rows only. A bare "$0 capital at risk" against a
    # CLOSED filter reads as "the book carries no risk", which is a different claim.
    summary = (
        f"{len(positions)} {status.lower()} positions, "
        f"${total_at_risk:,.0f} capital at risk (cost at the open remainder"
        + (f"; {risk['positions_not_open']} closed or expired rows carry realized P&L "
           f"only and are not risk" if risk.get("positions_not_open") else "")
        + ("" if risk["complete"]
           else f"; {risk['positions_excluded']} excluded for want of lots")
        + ")."
        # R-IV.780(e)1: said in the summary too, because a committee seat enforcing a bucket
        # limit reads this line and needs to know the limit cannot be applied to every row.
        + (f" {len(untagged)} of {len(positions)} carry no strategy_tag, so a bucket limit "
           f"cannot be applied to them." if untagged else "")
    )
    if ticker:
        summary = f"{ticker.upper()}: " + summary
    return make_response(status="ok", data=data, summary=summary, staleness_seconds=60)
