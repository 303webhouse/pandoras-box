"""hub_get_flow_radar — options flow imprint."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.flow import get_flow_radar as _read_flow

DESCRIPTION = (
    "Returns the current options flow imprint from the Pandora's Box hub — "
    "recent unusual options activity, net call/put premium direction, biggest "
    "sweeps, sector aggregations. Optionally filtered to a specific ticker. "
    "Use this whenever evaluating directional conviction on a trade idea, when "
    "TORO needs to confirm bullish positioning is flowing in, when URSA needs "
    "to confirm distribution, when DAEDALUS is reading options-specific "
    "positioning for structure recommendations, when PYTHIA is checking volume "
    "imprint at her key auction levels, when PIVOT is synthesizing committee "
    'output, or when the user asks about "the flow," "options imprint," "what\'s '
    'the smart money doing," "unusual activity," or any equivalent.\n\n'
    "Do NOT call this for general bias context (use `hub_get_bias_composite` "
    "instead). Do NOT call this for fundamentals or catalyst awareness (use "
    "`hub_get_hermes_alerts`). For squeeze setup scoring specifically, use "
    "`hub_get_hydra_scores`.\n\n"
    "Returns ranked list of recent flow events with premium, direction (calls "
    "vs puts), unusual-vs-baseline ratio, and timestamp. Includes net premium "
    "aggregation for the lookback window."
)


def _format_events(raw: Dict[str, Any], ticker: Optional[str]) -> List[Dict[str, Any]]:
    """Extract flow events from the flow-radar payload into the canonical shape."""
    events: List[Dict[str, Any]] = []
    watchlist = raw.get("watchlist_unusual") or []
    position_flow = raw.get("position_flow") or []
    for source in (watchlist, position_flow):
        for entry in source:
            tkr = (entry.get("ticker") or "").upper()
            if ticker and tkr != ticker.upper():
                continue
            events.append(
                {
                    "ticker": tkr,
                    "strike": entry.get("top_strike") or entry.get("strike"),
                    "expiry": entry.get("top_expiry") or entry.get("expiry"),
                    "option_type": entry.get("top_option_type")
                    or entry.get("option_type"),
                    "side": entry.get("side") or entry.get("flow_direction"),
                    "premium_usd": entry.get("net_premium") or entry.get("premium"),
                    "size": entry.get("size") or entry.get("contracts"),
                    "unusual_ratio": entry.get("unusual_ratio"),
                    "timestamp": entry.get("last_alert_at") or entry.get("timestamp"),
                    "type": entry.get("type") or entry.get("alert_type") or "FLOW",
                }
            )
    return events


def _summary(
    ticker: Optional[str],
    lookback_hours: int,
    net_calls: float,
    net_puts: float,
    direction: str,
    event_count: int,
) -> str:
    scope = ticker.upper() if ticker else "Global"
    return (
        f"{scope} flow last {lookback_hours}h: net {direction} "
        f"(calls ${net_calls:,.0f}, puts ${net_puts:,.0f}). "
        f"{event_count} events tracked."
    )


@mcp_tool(name="hub_get_flow_radar", description=DESCRIPTION)
async def hub_get_flow_radar(
    ticker: Optional[str] = None,
    lookback_hours: int = 4,
) -> dict:
    """Return options flow imprint for a ticker or global top-N."""
    if not isinstance(lookback_hours, int) or not (1 <= lookback_hours <= 24):
        return make_response(
            status="unavailable",
            error="lookback_hours must be an int between 1 and 24",
            summary="Invalid lookback_hours.",
        )

    raw = await _read_flow()
    if raw is None:
        return make_response(
            status="unavailable",
            error="Flow radar source unavailable.",
            summary="MCP: flow data unavailable.",
        )

    market_pulse = raw.get("market_pulse") or {}
    net_calls = float(market_pulse.get("net_premium_calls_usd", 0) or 0)
    net_puts = float(market_pulse.get("net_premium_puts_usd", 0) or 0)
    direction = (market_pulse.get("direction") or "NEUTRAL").upper()

    events = _format_events(raw, ticker)

    data = {
        "ticker": ticker.upper() if ticker else None,
        "lookback_hours": lookback_hours,
        "net_premium_calls_usd": net_calls,
        "net_premium_puts_usd": net_puts,
        "net_premium_direction": direction,
        "events": events,
        "event_count": len(events),
    }
    return make_response(
        status="ok",
        data=data,
        summary=_summary(ticker, lookback_hours, net_calls, net_puts, direction, len(events)),
        staleness_seconds=300,
    )
