"""hub_get_quote — real-time spot + OHLCV + UW timestamp for a single ticker."""

from __future__ import annotations

from typing import Any, Dict

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.quote import get_quote

DESCRIPTION = (
    "Returns the current real-time quote for a single ticker from the "
    "Pandora's Box hub via Unusual Whales: spot price, intraday OHLCV, "
    "prior-session close, percent change, 30-day average volume, 52-week "
    "high/low, market state (pre_market / open / post_market / closed), "
    "and — critically — the UW server timestamp for the data. Use this "
    "MANDATORILY before any output that cites a specific spot price, "
    "today's intraday level, or anchors analysis to 'today's tape.' Every "
    "Olympus agent (TORO, URSA, PYTHAGORAS, PYTHIA, THALES, DAEDALUS, "
    "PIVOT) calls this as the first data tool after `mcp_ping` so the "
    "UW timestamp becomes the authoritative anchor for the rest of the "
    'pass. Also call when the user asks about "current price," "today\'s '
    'range," "where is X trading right now," or any equivalent.\n\n'
    "Do NOT call this for historical OHLCV bars (out of v1 scope; v2 "
    "candidate). Do NOT call this for options chain data (use the "
    "DAEDALUS path / future `hub_get_options_chain`).\n\n"
    "Returns a single quote envelope with `status` field: `live` (UW "
    "data is fresh per its own timestamp), `stale` (UW timestamp is more "
    "than 5 minutes old during market hours), or `unavailable` (UW errored "
    "or rate-limited). When status is `stale` or `unavailable`, agents "
    "must degrade conviction and surface the staleness in their DATA NOTE."
)


def _summary(data: Dict[str, Any]) -> str:
    if data.get("status") == "unavailable":
        return f"{data.get('ticker','?')}: quote unavailable (UW error or rate limit)."
    tkr = data.get("ticker", "?")
    spot = data.get("spot")
    pct = data.get("pct_change")
    mstate = data.get("market_state", "closed")
    uw_ts = data.get("uw_timestamp", "—")
    spot_str = f"${spot:.2f}" if isinstance(spot, (int, float)) else "—"
    pct_str = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "—"
    return (
        f"{tkr}: {spot_str} ({pct_str}) — market {mstate}, UW {uw_ts}."
    )


@mcp_tool(name="hub_get_quote", description=DESCRIPTION)
async def hub_get_quote(ticker: str) -> dict:
    """Return real-time quote for `ticker`."""
    if not ticker or not isinstance(ticker, str):
        return make_response(
            status="unavailable",
            error="ticker is required (non-empty string).",
            summary="hub_get_quote: ticker required.",
        )

    data = await get_quote(ticker)
    if data is None:
        return make_response(
            status="unavailable",
            error="Invalid ticker input.",
            summary="hub_get_quote: invalid input.",
        )

    inner_status = data.get("status", "unavailable")
    if inner_status == "unavailable":
        return make_response(
            status="unavailable",
            data=data,
            summary=_summary(data),
            error="UW /stock-state did not return data.",
        )

    # Map the source status to envelope status. Both "live" and "stale" carry
    # data; "stale" propagates so downstream agents degrade conviction.
    envelope_status = "stale" if inner_status == "stale" else "ok"
    staleness_seconds = None
    if envelope_status == "stale":
        # Best-effort age in seconds (already past 5m during market hours).
        staleness_seconds = 300

    return make_response(
        status=envelope_status,
        data=data,
        summary=_summary(data),
        staleness_seconds=staleness_seconds,
    )
