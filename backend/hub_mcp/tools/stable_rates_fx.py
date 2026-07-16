"""hub_get_stable_rates_fx — Treasury yield curve + DXY/USDJPY from the Stable Engine."""

from __future__ import annotations

from ..decorators import mcp_tool
from ..envelope import make_response
from ..stable_envelope import map_stable_status, worst_status, flatline_error
from services.read_only.stable import get_rates, get_fx

DESCRIPTION = (
    "Returns the current Treasury yield curve (3M/5Y/10Y/30Y + a ~5-session-"
    "ago ghost curve for comparison, plus the 10y-3m spread) and DXY/USDJPY "
    "levels with day change, from the Pandora's Box Stable Engine. Use this "
    "whenever assessing macro/rates backdrop, dollar strength, or curve "
    "shape for a trade thesis.\n\n"
    "Do NOT call this for equity-specific data (use hub_get_stable_regime "
    "or hub_get_quote). Response has two independently-timed sub-blocks "
    "(data.rates, data.fx) -- each carries its own as_of/anchor/degraded; "
    "the top-level status is the WORSE of the two, so a healthy rates read "
    "can still report degraded/unavailable if fx is down, and vice versa."
)


def _summary(data: dict, status: str) -> str:
    rates = data.get("rates") or {}
    fx = data.get("fx") or {}
    spread = rates.get("spread") or {}
    spread_str = f"{spread.get('value')}" if spread.get("value") is not None else "n/a"
    fx_list = fx.get("fx") or []
    fx_str = ", ".join(f"{f['symbol']} {f.get('level')}" for f in fx_list) or "n/a"
    tag = " (FLATLINE)" if status == "unavailable" else ""
    return f"Rates/FX{tag}: 10y-3m spread {spread_str}. FX: {fx_str}."


@mcp_tool(name="hub_get_stable_rates_fx", description=DESCRIPTION)
async def hub_get_stable_rates_fx() -> dict:
    """Return the Treasury yield curve + DXY/USDJPY, bundled with worst-of-two status."""
    rates_data = await get_rates()
    fx_data = await get_fx()

    rates_status, rates_staleness = map_stable_status(rates_data, feed="strip")
    fx_status, fx_staleness = map_stable_status(fx_data, feed="strip")

    status = worst_status([rates_status, fx_status])
    staleness_candidates = [s for s in (rates_staleness, fx_staleness) if s is not None]
    staleness_seconds = max(staleness_candidates) if staleness_candidates else None

    out_data = {"rates": rates_data, "fx": fx_data}

    error = None
    if status == "unavailable":
        if rates_data.get("flatline"):
            error = flatline_error("strip:rates")
        elif fx_data.get("flatline"):
            error = flatline_error("strip:fx")

    return make_response(
        status=status,
        data=out_data,
        summary=_summary(out_data, status),
        staleness_seconds=staleness_seconds,
        error=error,
    )
