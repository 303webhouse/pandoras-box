"""hub_get_board_state — market tide (net options-flow direction) + circuit-breaker
kill-switch state.

Bundled but NOT named hub_get_stable_* -- different router/provenance than the
Stable Engine (tide is a UW-cache-only read, kill-switch is circuit-breaker
process state; backend/api/board_state.py, not backend/api/stable.py).

Worst-of-two status (via stable_envelope.worst_status) naturally makes a
kill-switch read failure dominate a healthy tide read -- both sub-blocks use
the same status vocabulary and rank, so the more severe one always wins
regardless of which side it came from. No separate asymmetric logic needed
to satisfy "kill-switch failure must dominate": max-rank-wins already does.
"""

from __future__ import annotations

from ..decorators import mcp_tool
from ..envelope import make_response
from ..stable_envelope import map_stable_status, worst_status
from services.read_only.board import get_tide, get_kill_switch

DESCRIPTION = (
    "Returns two pieces of live board state: (1) market tide -- net "
    "options-flow direction (BULLISH/BEARISH/NEUTRAL) from UW's aggregate "
    "flow cache, and (2) the circuit-breaker kill-switch state -- whether a "
    "market-risk breaker is currently active, and if so its bias cap/floor "
    "and scoring modifier. PIVOT (primary user) should check kill_switch."
    "active BEFORE synthesizing a final recommendation -- an active breaker "
    "caps or floors the bias regardless of what other signals say.\n\n"
    "Do NOT call this for per-ticker options flow (use hub_get_flow_radar). "
    "Do NOT call this for regime/breadth (use hub_get_stable_regime -- a "
    "different data source, despite both feeding the same dashboard regime "
    "band).\n\n"
    "Tide is read-only from an existing UW cache -- this tool never "
    "triggers a new UW request. Kill-switch is a live process state read "
    "(always fresh, degraded=False unless the read itself fails)."
)


def _summary(data: dict, status: str) -> str:
    tide = data.get("tide") or {}
    kill = data.get("kill_switch") or {}
    tide_dir = tide.get("direction") or "unknown"
    kill_active = kill.get("active")
    kill_str = "ACTIVE" if kill_active else ("inactive" if kill_active is not None else "unknown")
    tag = " (DEGRADED)" if status in ("degraded", "unavailable") else ""
    return f"Board state{tag}: tide {tide_dir}. Kill-switch {kill_str}."


@mcp_tool(name="hub_get_board_state", description=DESCRIPTION)
async def hub_get_board_state() -> dict:
    """Return market tide + kill-switch state, bundled with worst-of-two status."""
    tide_data = await get_tide()
    kill_data = await get_kill_switch()

    tide_status, tide_staleness = map_stable_status(tide_data)
    kill_status, kill_staleness = map_stable_status(kill_data)

    status = worst_status([tide_status, kill_status])
    staleness_candidates = [s for s in (tide_staleness, kill_staleness) if s is not None]
    staleness_seconds = max(staleness_candidates) if staleness_candidates else None

    out_data = {"tide": tide_data.get("tide"), "kill_switch": kill_data.get("kill_switch")}

    error = None
    if kill_status == "unavailable":
        error = "kill_switch_read_failed"
    elif tide_status == "unavailable":
        error = "tide_unavailable"

    return make_response(
        status=status,
        data=out_data,
        summary=_summary(out_data, status),
        staleness_seconds=staleness_seconds,
        error=error,
    )
