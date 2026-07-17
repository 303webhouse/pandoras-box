"""hub_get_stable_regime — market-wide regime label + breadth + dominant/emerging/fading themes."""

from __future__ import annotations

from ..decorators import mcp_tool
from ..envelope import make_response
from ..stable_envelope import map_stable_status, flatline_error, theme_warnings
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
    "IMPORTANT DATA QUALITY CAVEAT: the Robotics theme's score is currently "
    "known-corrupted (a delisted/recycled ticker, LAZR, pins it near 100.0) "
    "and can appear in dominant[] at a high rank -- do NOT treat a high "
    "Robotics score as genuine momentum. Check data_quality_warnings on "
    "every response; if non-empty, discount that theme wherever it appears "
    "in dominant/emerging/fading.\n\n"
    "Status ok/degraded/stale/unavailable follows the freshness of the "
    "underlying nightly Stable Engine recompute. unavailable means the feed "
    "has gone dead past its SLO (~26h) -- the last-known data is still "
    "returned, flagged, not hidden."
)


def _summary(data: dict, status: str, warnings: list) -> str:
    if status == "unavailable" and not data.get("regime_label"):
        return "Stable regime: unavailable, no data ever computed."
    label = data.get("regime_label", "UNKNOWN")
    breadth = data.get("breadth") or {}
    p50 = breadth.get("pct_above_50dma")
    p50_str = f"{p50}%" if p50 is not None else "n/a"
    dom = data.get("dominant") or []
    dom_str = ", ".join(d["theme"] for d in dom[:3]) or "none"
    tag = " (FLATLINE)" if status == "unavailable" else ""
    warn = f" DATA QUALITY WARNING on {len(warnings)} theme(s)." if warnings else ""
    return f"Regime: {label}{tag}. {p50_str} above 50dma. Dominant: {dom_str}.{warn}"


@mcp_tool(name="hub_get_stable_regime", description=DESCRIPTION)
async def hub_get_stable_regime() -> dict:
    """Return the current market regime label, breadth, and dominant/emerging/fading themes."""
    data = await get_regime()
    status, staleness_seconds = map_stable_status(data, feed="nightly")

    # Micro-fix 2026-07-16 (Fable): Robotics/LAZR guard now also covers the
    # dominant/emerging/fading theme lists surfaced here -- previously only
    # hub_get_stable_themes carried this warning, but this tool is THALES's
    # PRIMARY macro/regime read and was serving Robotics=100.0 unflagged at
    # rank 1 in dominant[].
    theme_names = [
        t.get("theme")
        for t in (data.get("dominant") or []) + (data.get("emerging") or []) + (data.get("fading") or [])
    ]
    warnings = theme_warnings(theme_names)
    out_data = {**data, "data_quality_warnings": warnings}

    error = flatline_error("nightly") if status == "unavailable" and data.get("flatline") else None
    return make_response(
        status=status,
        data=out_data,
        summary=_summary(out_data, status, warnings),
        staleness_seconds=staleness_seconds,
        error=error,
    )
