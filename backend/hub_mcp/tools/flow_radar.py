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
    """Extract ticker-level flow imprints from the flow-radar payload.

    The `uw:flow:{ticker}` cache stores TICKER-LEVEL rollups (call/put premium,
    pc_ratio, sentiment), NOT per-contract events. So we emit one flow-imprint
    entry per ticker, using the keys that actually exist in `watchlist_unusual`
    and `position_flow`. strike / expiry / side / size are intentionally absent
    — the poll does not persist the raw per-contract flow list (out of scope).
    """
    events: List[Dict[str, Any]] = []
    watchlist = raw.get("watchlist_unusual") or []
    position_flow = raw.get("position_flow") or []

    for entry in watchlist:
        tkr = (entry.get("ticker") or "").upper()
        if ticker and tkr != ticker.upper():
            continue
        events.append(
            {
                "ticker": tkr,
                "source": "watchlist",
                "sentiment": (entry.get("sentiment") or "NEUTRAL").upper(),
                "pc_ratio": entry.get("pc_ratio"),
                "total_premium_usd": entry.get("total_premium"),
                "premium_display": entry.get("premium_display"),
                "change_pct": entry.get("change_pct"),
                "divergence": entry.get("divergence"),
                "unusual": entry.get("unusual"),
            }
        )

    for entry in position_flow:
        tkr = (entry.get("ticker") or "").upper()
        if ticker and tkr != ticker.upper():
            continue
        events.append(
            {
                "ticker": tkr,
                "source": "position",
                "sentiment": (entry.get("sentiment") or "NEUTRAL").upper(),
                "pc_ratio": entry.get("pc_ratio"),
                "total_premium_usd": entry.get("total_premium"),
                "premium_display": entry.get("premium_display"),
                "alignment": entry.get("alignment"),
                "strength": entry.get("strength"),
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
    direction = (market_pulse.get("net_premium_direction") or "NEUTRAL").upper()
    flow_data_available = bool(market_pulse.get("flow_data_available", False))

    events = _format_events(raw, ticker)

    data = {
        "ticker": ticker.upper() if ticker else None,
        "lookback_hours": lookback_hours,
        "net_premium_calls_usd": net_calls,
        "net_premium_puts_usd": net_puts,
        "net_premium_direction": direction,
        "flow_data_available": flow_data_available,
        # F1 (7/1 db_fallback contract): provenance + honest freshness end-to-end.
        # source: "redis" (normal) | "db_fallback" (Redis empty, served from
        # flow_events) | "none" (both empty). data_age_seconds null when empty, never 0.
        "source": raw.get("source"),
        "data_age_seconds": raw.get("data_age_seconds"),
        "events": events,
        "event_count": len(events),
    }
    return make_response(
        status="ok",
        data=data,
        summary=_summary(ticker, lookback_hours, net_calls, net_puts, direction, len(events)),
        # L1.0 Chunk 3: real staleness from the dashboard read-time compute (the
        # exact same value get_flow_radar emits — single source, null when unknown,
        # never the old hardcoded 300).
        staleness_seconds=raw.get("staleness_seconds"),
    )
