"""hub_get_stable_movers — top gainers/losers from the Pandora's Box Stable Engine."""

from __future__ import annotations

from ..decorators import mcp_tool
from ..envelope import make_response
from ..stable_envelope import map_stable_status, flatline_error
from services.read_only.stable import get_movers

DESCRIPTION = (
    "Returns the latest gainers/losers snapshot (15 each) from the Pandora's "
    "Box Stable Engine screener: ticker, % move, price, theme where "
    "applicable. Use this whenever assessing today's tape leaders/laggards, "
    "or when the user asks \"what's moving today,\" \"top gainers,\" \"top "
    "losers,\" or any equivalent.\n\n"
    "Do NOT call this for a single ticker's price (use hub_get_quote). Do "
    "NOT call this for options flow (use hub_get_flow_radar).\n\n"
    "Serves the last stored snapshot even when the underlying screener has "
    "stalled -- status flips degraded/unavailable rather than silently "
    "going empty, so a stale tape is always distinguishable from a healthy one."
)


def _summary(data: dict, status: str) -> str:
    gainers = data.get("gainers") or []
    losers = data.get("losers") or []
    if status == "unavailable" and not gainers and not losers:
        return "Stable movers: unavailable, no data ever computed."
    top_g = ", ".join(f"{g['ticker']} (+{g['pct']:.1f}%)" for g in gainers[:3]) or "none"
    top_l = ", ".join(f"{l['ticker']} ({l['pct']:.1f}%)" for l in losers[:3]) or "none"
    tag = " (FLATLINE)" if status == "unavailable" else ""
    return f"Movers{tag}: top gainers {top_g}. Top losers {top_l}."


@mcp_tool(name="hub_get_stable_movers", description=DESCRIPTION)
async def hub_get_stable_movers() -> dict:
    """Return the latest gainers/losers snapshot."""
    data = await get_movers()
    status, staleness_seconds = map_stable_status(data, feed="movers")

    error = flatline_error("movers") if status == "unavailable" and data.get("flatline") else None
    return make_response(
        status=status,
        data=data,
        summary=_summary(data, status),
        staleness_seconds=staleness_seconds,
        error=error,
    )
