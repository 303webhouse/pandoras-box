"""hub_get_sector_strength — 11-sector relative strength + rotation regime."""

from __future__ import annotations

from typing import Any, Dict, List

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.sectors import get_sector_rotation

DESCRIPTION = (
    "Returns cross-sectional sector relative strength and rotation regime tags "
    "from the Pandora's Box hub. Identifies leading and lagging sectors, narrow "
    "vs broad leadership, and the current rotation state (concentrated "
    "leadership / rotation / regime-agnostic). Use this whenever evaluating "
    "sector context for a trade, when THALES (primary user) needs sector-"
    "rotation input, when TORO is hunting sector-RS-leader patterns, when URSA "
    "is flagging crowded sector positioning, when PYTHAGORAS is mapping "
    "structural trends to sector backdrop, when DAEDALUS is reading sector-"
    "level options pricing context, when PIVOT is assembling sector context for "
    'synthesis, or when the user asks about "sector leadership," "rotation," '
    '"which sectors are leading," "narrow vs broad," or any equivalent.\n\n'
    "Do NOT call this for company-specific fundamentals within a sector (use "
    "`hub_get_hermes_alerts`). Do NOT call this for general directional bias "
    "(use `hub_get_bias_composite`).\n\n"
    "Returns 11 sector ETFs (XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLU, XLB, "
    "XLRE, XLC) with rolling 10-day and 20-day RS vs SPY, plus the current "
    "rotation regime classification."
)


def _classify_regime(sectors: List[Dict[str, Any]]) -> str:
    """Heuristic rotation-regime label from per-sector RS readings."""
    leaders = [s for s in sectors if s["state"] in ("LEADING", "ROTATING_IN")]
    laggards = [s for s in sectors if s["state"] in ("LAGGING", "ROTATING_OUT")]
    if len(leaders) <= 2:
        return "CONCENTRATED_LEADERSHIP"
    if len(leaders) >= 5 and len(laggards) <= 3:
        return "BROAD_ROTATION"
    if len(laggards) >= 6:
        return "ACTIVE_DISTRIBUTION"
    return "REGIME_AGNOSTIC"


def _map_status(status: str, rs_20d: float) -> str:
    s = (status or "").upper()
    if s == "SURGING":
        return "LEADING" if rs_20d >= 0 else "ROTATING_IN"
    if s == "DUMPING":
        return "LAGGING" if rs_20d <= 0 else "ROTATING_OUT"
    return "NEUTRAL"


@mcp_tool(name="hub_get_sector_strength", description=DESCRIPTION)
async def hub_get_sector_strength() -> dict:
    """Return per-sector RS + rotation regime."""
    raw = await get_sector_rotation()
    if not raw:
        return make_response(
            status="unavailable",
            error="Sector rotation cache empty. Run sector momentum refresh.",
            summary="MCP: sector strength data unavailable.",
        )

    sectors: List[Dict[str, Any]] = []
    by_rs_10d: List[Dict[str, Any]] = []
    by_rs_20d: List[Dict[str, Any]] = []
    for name, entry in raw.items():
        rs_10d = entry.get("relative_strength_10d") or entry.get("rs_10d") or 0.0
        rs_20d = entry.get("relative_strength_20d") or entry.get("rs_20d") or 0.0
        sector = {
            "etf": entry.get("etf") or entry.get("ticker"),
            "name": name,
            "rs_10d": rs_10d,
            "rs_20d": rs_20d,
            "rank_10d": entry.get("rank_10d"),
            "rank_20d": entry.get("rank_20d"),
            "state": _map_status(entry.get("status"), rs_20d),
        }
        sectors.append(sector)
        by_rs_10d.append(sector)
        by_rs_20d.append(sector)

    by_rs_10d.sort(key=lambda s: s["rs_10d"], reverse=True)
    by_rs_20d.sort(key=lambda s: s["rs_20d"], reverse=True)
    for rank, s in enumerate(by_rs_10d, start=1):
        if s["rank_10d"] is None:
            s["rank_10d"] = rank
    for rank, s in enumerate(by_rs_20d, start=1):
        if s["rank_20d"] is None:
            s["rank_20d"] = rank

    regime = _classify_regime(sectors)
    leaders_count = sum(1 for s in sectors if s["state"] in ("LEADING", "ROTATING_IN"))
    breadth_score = round(leaders_count / max(len(sectors), 1), 2)
    narrow = breadth_score < 0.35

    data = {
        "rotation_regime": regime,
        "sectors": sectors,
        "narrow_leadership_flag": narrow,
        "leadership_breadth_score": breadth_score,
    }

    top = sorted(sectors, key=lambda s: s["rs_20d"], reverse=True)[:3]
    bottom = sorted(sectors, key=lambda s: s["rs_20d"])[:2]
    top_str = ", ".join(f"{s['etf']} ({s['rs_20d']:+.1f}%)" for s in top)
    bot_str = ", ".join(f"{s['etf']} ({s['rs_20d']:+.1f}%)" for s in bottom)
    summary = (
        f"Sector regime: {regime}. Leading: {top_str}. Lagging: {bot_str}. "
        f"Leadership breadth {breadth_score}."
    )
    return make_response(status="ok", data=data, summary=summary, staleness_seconds=600)
