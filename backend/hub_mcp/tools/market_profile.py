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
    "Status semantics: `ok` = levels from the session under analysis; `stale` = ONE "
    "session behind, returned with session_date and sessions_behind; `dark` = TWO OR "
    "MORE sessions behind — the feed is NOT ARRIVING and the levels DO NOT describe "
    "the current market, so do not reason from them without confirming the feed. "
    "This surface CANNOT distinguish an upstream outage from a quiet market and does "
    "not try; it reports the observation, never the cause. (was: `stale` = "
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

    sb = data.get("sessions_behind")

    if status == "dark":
        # Never assert a market condition here. From the pipe end a delivery
        # outage and a quiet market are the same observation, so this states
        # the observation and refuses the cause.
        summary = (
            f"{tkr} MP IS DARK — NO EVENTS SINCE {data['session_date']} "
            f"({sb} sessions). These levels are from that date and DO NOT "
            f"describe the current market. The feed is not arriving; whether "
            f"the cause is upstream or delivery is not knowable from here. "
            f"Do not trade or reason from these levels without confirming the "
            f"feed. POC {data['poc']}, VAH {data['vah']}, VAL {data['val']}."
        )
    elif status == "stale":
        summary = (
            f"{tkr} MP from PRIOR session {data['session_date']} "
            f"({sb} session behind): POC {data['poc']}, VAH {data['vah']}, "
            f"VAL {data['val']}. No events yet in the session under analysis — "
            f"cause not determinable from this surface."
        )
    else:
        summary = (
            f"{tkr} MP: POC {data['poc']}, VAH {data['vah']}, VAL {data['val']} "
            f"(VA {data['va_migration']}, {data['volume_quality']} vol)."
        )

    return make_response(status=status, data=data, summary=summary, staleness_seconds=age)
