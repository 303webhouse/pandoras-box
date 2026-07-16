"""hub_get_stable_regime — market-wide regime label + breadth + dominant/emerging/fading themes."""

from __future__ import annotations

from ..decorators import mcp_tool
from ..envelope import make_response
from ..stable_envelope import map_stable_status, flatline_error
from services.read_only.stable import get_regime

DESCRIPTION = (
    "Returns the current market regime from the Pandora's Box Stable Engine: a "
    "RISK-ON/RISK-OFF/NEUTRAL label derived from % of the ~690-ticker universe "
    "above its 50-day moving average, full breadth counts (above 20/50/200dma, "
    "new highs/lows), and the dominant/emerging/fading theme lists (up to 8 "
    "each). Use this whenever assessing overall market regime or breadth "
    "context, when THALES (primary user) needs macro/regime input for a "
    "trade thesis, or when the user asks about \"market regime,\" \"breadth,\" "
    "\"risk-on or risk-off,\" or \"what's leading the market.\"\n\n"
    "Do NOT call this for a single ticker's price or technicals (use "
    "hub_get_quote or hub_get_chart_indicators). Do NOT call this for "
    "sector-level rotation specifically (use hub_get_sector_strength, a "
    "different data source). This tool is yfinance-sourced end-of-day/"
    "provisional data, not real-time.\n\n"
    "Status ok/degraded/stale/unavailable follows the freshness of the "
    "underlying nightly Stable Engine recompute. unavailable means the feed "
    "has gone dead past its SLO (~26h) -- the last-known data is still "
    "returned, flagged, not hidden."
)


def _summary(data: dict, status: str) -> str:
    if status == "unavailable" and not data.get("regime_label"):
        return "Stable regime: unavailable, no data ever computed."
    label = data.get("regime_label", "UNKNOWN")
    breadth = data.get("breadth") or {}
    p50 = breadth.get("pct_above_50dma")
    p50_str = f"{p50}%" if p50 is not None else "n/a"
    dom = data.get("dominant") or []
    dom_str = ", ".join(d["theme"] for d in dom[:3]) or "none"
    tag = " (FLATLINE)" if status == "unavailable" else ""
    return f"Regime: {label}{tag}. {p50_str} above 50dma. Dominant: {dom_str}."


@mcp_tool(name="hub_get_stable_regime", description=DESCRIPTION)
async def hub_get_stable_regime() -> dict:
    """Return the current market regime label, breadth, and dominant/emerging/fading themes."""
    data = await get_regime()
    status, staleness_seconds = map_stable_status(data, feed="nightly")

    error = flatline_error("nightly") if status == "unavailable" and data.get("flatline") else None
    return make_response(
        status=status,
        data=data,
        summary=_summary(data, status),
        staleness_seconds=staleness_seconds,
        error=error,
    )
