"""hub_get_hermes_alerts — active catalysts and upcoming events."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.catalysts import get_upcoming_catalysts

DESCRIPTION = (
    "Returns active catalysts and upcoming events from the Hermes alert system "
    "— earnings, FDA decisions, M&A announcements, macro data releases, "
    "geopolitical deadlines. Filtered by ticker and lookback window. Use this "
    "whenever evaluating catalyst risk for a trade, when TORO needs catalyst "
    "tailwinds, when URSA needs catalyst-asymmetry risks, when PYTHAGORAS is "
    "mapping catalysts to DTE selection, when PYTHIA is checking for catalyst-"
    "driven volume regime shifts at her key levels, when THALES (macro voice-"
    "of-reason) is evaluating macro event risk, when DAEDALUS is selecting "
    "expiry windows around catalyst risk, when PIVOT is assembling catalyst "
    'context for synthesis, or when the user asks about "catalysts," "what\'s '
    'coming up," "earnings," "FDA," "Fed meeting," or any equivalent.\n\n'
    "Do NOT call this for general macro context (use `hub_get_bias_composite` "
    "for the system's directional read). Do NOT call this for completed "
    "catalysts older than the lookback window.\n\n"
    "Returns ranked list of upcoming and recent catalysts with type, scheduled "
    "timestamp, expected impact, and any system-generated context. Includes "
    "both ticker-specific and macro events."
)


def _map_event(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a raw catalyst event into the canonical schema."""
    scheduled_iso = ev.get("date") or ev.get("scheduled_at")
    if not scheduled_iso:
        return None
    try:
        scheduled_dt = datetime.fromisoformat(str(scheduled_iso))
        if scheduled_dt.tzinfo is None:
            scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None

    now = datetime.now(timezone.utc)
    delta_hours = (scheduled_dt - now).total_seconds() / 3600.0
    is_upcoming = delta_hours > 0
    category = (ev.get("category") or "").upper()
    type_map = {
        "FOMC": "MACRO_DATA",
        "CPI": "MACRO_DATA",
        "PCE": "MACRO_DATA",
        "JOBS": "MACRO_DATA",
        "EARNINGS": "EARNINGS",
        "FDA": "FDA",
        "M_AND_A": "M_AND_A",
        "GEOPOLITICAL": "GEOPOLITICAL",
        "SECTOR_EVENT": "SECTOR_EVENT",
        "CUSTOM": "MACRO_DATA",
        "MACRO": "MACRO_DATA",
    }
    impact = (ev.get("impact") or ev.get("expected_impact") or "MEDIUM").upper()
    return {
        "id": ev.get("id") or f"{category}-{scheduled_iso}",
        "ticker": ev.get("ticker") or "MACRO",
        "type": type_map.get(category, "MACRO_DATA"),
        "title": ev.get("name") or ev.get("title") or category or "Catalyst",
        "scheduled_at": scheduled_dt.isoformat(),
        "is_upcoming": is_upcoming,
        "hours_until": round(delta_hours, 1) if is_upcoming else None,
        "hours_since": round(-delta_hours, 1) if not is_upcoming else None,
        "expected_impact": impact if impact in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "MEDIUM",
        "context_note": ev.get("note") or ev.get("context_note"),
    }


@mcp_tool(name="hub_get_hermes_alerts", description=DESCRIPTION)
async def hub_get_hermes_alerts(
    ticker: Optional[str] = None,
    lookback_hours: int = 24,
    forward_days: int = 14,
) -> dict:
    """Return catalyst alerts within the requested windows."""
    if not isinstance(forward_days, int) or forward_days < 0:
        return make_response(
            status="unavailable",
            error="forward_days must be a non-negative int",
            summary="Invalid forward_days.",
        )
    if not isinstance(lookback_hours, int) or lookback_hours < 0:
        return make_response(
            status="unavailable",
            error="lookback_hours must be a non-negative int",
            summary="Invalid lookback_hours.",
        )

    raw = await get_upcoming_catalysts(days=forward_days)
    if raw is None:
        return make_response(
            status="unavailable",
            error="Catalyst calendar source unavailable.",
            summary="MCP: catalyst data unavailable.",
        )

    events_raw = raw.get("events") or []
    mapped: List[Dict[str, Any]] = []
    cutoff_back = lookback_hours
    ticker_filter = ticker.upper() if ticker else None
    for ev in events_raw:
        normalized = _map_event(ev)
        if normalized is None:
            continue
        if ticker_filter and normalized["ticker"] not in (ticker_filter, "MACRO"):
            continue
        if not normalized["is_upcoming"]:
            hs = normalized.get("hours_since") or 0
            if hs > cutoff_back:
                continue
        mapped.append(normalized)

    critical = sum(1 for e in mapped if e["expected_impact"] == "CRITICAL")
    high = sum(1 for e in mapped if e["expected_impact"] == "HIGH")

    data = {
        "ticker": ticker_filter,
        "lookback_hours": lookback_hours,
        "forward_days": forward_days,
        "alerts": mapped,
        "critical_count": critical,
        "high_count": high,
    }

    scope = ticker_filter or "All"
    summary = (
        f"{scope} catalysts: {len(mapped)} events ({critical} critical, "
        f"{high} high). Forward window {forward_days}d, lookback {lookback_hours}h."
    )
    return make_response(status="ok", data=data, summary=summary, staleness_seconds=900)
