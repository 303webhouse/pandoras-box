"""hub_get_market_profile — latest TradingView Market Profile levels (B4 Chunk A).

Read-only. Exposes the already-flowing PYTHIA webhook data (pythia_events) to the
Olympus committee. Session-based staleness; fail-loud on missing data; selected
fields only (never raw_payload — B4 amendment 2).
"""

from __future__ import annotations

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.market_profile import get_market_profile

DESCRIPTION = (
    "Returns the latest TradingView Market Profile levels for a ticker from the "
    "Pandora's Box hub — POC, VAH, VAL, prior-session value area (prev_poc/vah/val), "
    "initial balance (ib_high/ib_low), poor highs/lows, value-area migration, and "
    "volume quality — as computed by the PYTHIA Pine indicator and pushed via webhook.\n\n"
    "Call this when PYTHIA needs structural levels for a committee pass, or when the "
    'user asks about "value area," "POC," "VAH/VAL," "initial balance," "day '
    'structure," "the 80% rule," "value-area migration," or "is this a fade or a '
    'chase." `single_prints` and `day_type` are NOT yet computed by the Pine feed '
    "and are returned as null — never inferred.\n\n"
    "Status semantics: `ok` = levels from the current session; `stale` = levels from "
    "a prior session (still returned, with session_date + event_age_seconds — the "
    "feed has been quiet this session); `unavailable` = no levels exist for this "
    "ticker (PYTHIA should fall back to her framework-only disclaimer, never "
    "fabricate levels).\n\n"
    "Do NOT use this for options structure (DAEDALUS / hub_get_options_chain) or "
    "trend reads (PYTHAGORAS). Do NOT call for general flow (hub_get_flow_radar)."
)


@mcp_tool(name="hub_get_market_profile", description=DESCRIPTION)
async def hub_get_market_profile(ticker: str) -> dict:
    """Return the latest Market Profile snapshot for one ticker."""
    if not ticker or not ticker.strip():
        return make_response(
            status="unavailable",
            error="ticker is required",
            summary="Missing ticker.",
        )

    try:
        result = await get_market_profile(ticker)
    except Exception as exc:
        return make_response(
            status="unavailable",
            error=f"Market Profile read failed: {exc}",
            summary="MCP: market profile unavailable.",
        )

    if result is None:
        return make_response(
            status="unavailable",
            data=None,
            summary=f"No Market Profile data for {ticker.upper()}.",
            staleness_seconds=None,
        )

    status = result["status"]
    data = result["data"]
    age = result.get("staleness_seconds")
    tkr = data["ticker"]

    if status == "stale":
        summary = (
            f"{tkr} MP (PRIOR session {data['session_date']}): "
            f"POC {data['poc']}, VAH {data['vah']}, VAL {data['val']}. "
            f"Feed quiet this session ({age}s old)."
        )
    else:
        summary = (
            f"{tkr} MP: POC {data['poc']}, VAH {data['vah']}, VAL {data['val']} "
            f"(VA {data['va_migration']}, {data['volume_quality']} vol)."
        )

    return make_response(status=status, data=data, summary=summary, staleness_seconds=age)
