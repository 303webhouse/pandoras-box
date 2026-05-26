"""hub_get_options_chain — live options chain + Greeks + IV rank + max pain.

DAEDALUS's primary data tool. Closes the documented "qualitative-IV-mode"
caveat by exposing per-contract Greeks, IV rank, and max pain in a single
envelope. See Task 2 spec (docs/codex-briefs/hub-get-options-chain-task2-
schema-2026-05-26.md) for the full schema contract.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.options_chain import get_options_chain

DESCRIPTION = (
    "Returns the live options chain for a single ticker + expiry from the "
    "Pandora's Box hub via Unusual Whales: per-contract strike, type, bid, "
    "ask, mid, bid_ask_spread_pct (liquidity flag), volume, open interest, "
    "implied volatility, and the four Greeks (delta, gamma, theta, vega). "
    "Plus chain-level aggregates: spot, IV rank (0-100), max pain (filtered "
    "to the requested expiry), total call/put open interest, and the UW "
    "server timestamp + source flag.\n\n"
    "This is DAEDALUS's PRIMARY data tool — call after `hub_get_quote` "
    "whenever building or evaluating an options structure (spread selection, "
    "strike picking, liquidity check, theta/vega budget, IV-regime read). "
    "Also call when the user asks about \"the chain,\" \"the Greeks at X,\" "
    "\"what's IV rank,\" \"where's max pain,\" or any equivalent.\n\n"
    "`expiry` is REQUIRED — pass YYYY-MM-DD. UW's /option-contracts endpoint "
    "caps results at 500; without an expiry filter, multi-expiry chains "
    "truncate silently. `option_type` defaults to \"both\" (returns calls + "
    "puts); pass \"call\" or \"put\" to narrow.\n\n"
    "Do NOT call this for general flow (use `hub_get_flow_radar`). Do NOT "
    "call this for historical option pricing (out of v1 scope).\n\n"
    "Returns envelope with `status`: `ok` (chain present), `degraded` "
    "(chain present but one or more chain-level aggregates missing — see "
    "`data.aggregates_errors[]`), or `unavailable` (UW errored or returned "
    "no contracts for this ticker/expiry). When `degraded`, DAEDALUS should "
    "proceed with the per-contract data and surface the missing aggregate "
    "in the DATA NOTE."
)


def _summary(data: Dict[str, Any]) -> str:
    tkr = data.get("ticker", "?")
    exp = data.get("expiry", "?")
    n = data.get("contract_count", 0)
    spot = data.get("spot")
    iv_rank = data.get("iv_rank")
    max_pain = data.get("max_pain")

    spot_str = f"${spot:.2f}" if isinstance(spot, (int, float)) else "—"
    iv_str = f"{iv_rank:.0f}" if isinstance(iv_rank, (int, float)) else "—"
    mp_str = f"${max_pain:.2f}" if isinstance(max_pain, (int, float)) else "—"

    return (
        f"{tkr} {exp}: {n} contracts, spot {spot_str}, "
        f"IV rank {iv_str}, max pain {mp_str}."
    )


@mcp_tool(name="hub_get_options_chain", description=DESCRIPTION)
async def hub_get_options_chain(
    ticker: str,
    expiry: str,
    option_type: str = "both",
) -> dict:
    """Return the live options chain envelope for `ticker` + `expiry`."""
    if not ticker or not isinstance(ticker, str):
        return make_response(
            status="unavailable",
            error="ticker is required (non-empty string).",
            summary="hub_get_options_chain: ticker required.",
        )

    if not expiry or not isinstance(expiry, str):
        return make_response(
            status="unavailable",
            error="expiry is required (YYYY-MM-DD string).",
            summary="hub_get_options_chain: expiry required.",
        )

    # Light shape validation; full parsing is deferred to UW.
    exp_trim = expiry.strip()[:10]
    if len(exp_trim) != 10 or exp_trim[4] != "-" or exp_trim[7] != "-":
        return make_response(
            status="unavailable",
            error="expiry must be YYYY-MM-DD.",
            summary="hub_get_options_chain: invalid expiry format.",
        )

    ot = (option_type or "both").lower()
    if ot not in ("both", "call", "put"):
        return make_response(
            status="unavailable",
            error='option_type must be one of "both", "call", "put".',
            summary="hub_get_options_chain: invalid option_type.",
        )

    try:
        data: Optional[Dict[str, Any]] = await get_options_chain(ticker, exp_trim, ot)
    except Exception as exc:
        return make_response(
            status="unavailable",
            error=f"options chain fetch raised: {type(exc).__name__}",
            summary=f"hub_get_options_chain: upstream error for {ticker.upper()}.",
        )

    if data is None or not data.get("contracts"):
        return make_response(
            status="unavailable",
            error="UW /option-contracts returned no data for this ticker/expiry.",
            summary=(
                f"hub_get_options_chain: no contracts for "
                f"{ticker.upper()} {exp_trim}."
            ),
        )

    envelope_status = "degraded" if data.get("aggregates_errors") else "ok"

    return make_response(
        status=envelope_status,
        data=data,
        summary=_summary(data),
    )
