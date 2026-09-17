"""Read-only sector strength / rotation accessors.

Sources cached 11-sector rotation data computed by the bias_filters
scheduler. Read-only — the writer (`refresh_sector_rotation`) is owned
by the scheduler and never invoked from this module.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from bias_filters.sector_momentum import get_cached_rotation

logger = logging.getLogger(__name__)


async def get_sector_rotation() -> Optional[Dict[str, Dict[str, Any]]]:
    """Return per-sector rotation data keyed by sector name, or None."""
    try:
        return await get_cached_rotation()
    except Exception as exc:
        logger.warning("sector rotation read failed: %s", exc)
        return None


# ── The rotation regime: ONE definition (R-IV.422) ──────────────────────────
# Moved here from hub_mcp/tools/sector_strength.py so the MCP tool and the signal
# enrichment join label a regime by the same rule. Two copies of a classifier drift, and
# then "positive expectancy in both sector regimes" is measured against a label nobody else
# uses. The vocabulary is the MCP tool's, unchanged.

LEADER_STATES = ("LEADING", "ROTATING_IN")
LAGGARD_STATES = ("LAGGING", "ROTATING_OUT")


def map_sector_state(status: Optional[str], rs_20d: Optional[float]) -> str:
    """Per-sector state from the rotation writer's status + 20d RS."""
    if rs_20d is None:
        return "NEUTRAL"
    s = (status or "").upper()
    if s == "SURGING":
        return "LEADING" if rs_20d >= 0 else "ROTATING_IN"
    if s == "DUMPING":
        return "LAGGING" if rs_20d <= 0 else "ROTATING_OUT"
    return "NEUTRAL"


def classify_rotation_regime(sectors: List[Dict[str, Any]]) -> str:
    """Heuristic rotation-regime label from per-sector states (each dict has "state")."""
    leaders = [s for s in sectors if s["state"] in LEADER_STATES]
    laggards = [s for s in sectors if s["state"] in LAGGARD_STATES]
    if len(leaders) <= 2:
        return "CONCENTRATED_LEADERSHIP"
    if len(leaders) >= 5 and len(laggards) <= 3:
        return "BROAD_ROTATION"
    if len(laggards) >= 6:
        return "ACTIVE_DISTRIBUTION"
    return "REGIME_AGNOSTIC"


def _rs(entry: Dict[str, Any], window: str) -> Optional[float]:
    v = entry.get(f"relative_strength_{window}")
    return entry.get(f"rs_{window}") if v is None else v


def rotation_snapshot(raw: Optional[Dict[str, Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """{regime, states: {etf: state}, as_of} from the cached rotation, or None.

    `as_of` is the OLDEST per-sector updated_at: the snapshot is only as fresh as its
    stalest input, and an intermittent source carries its as-of (observation-instrument law).
    """
    if not raw:
        return None
    states: Dict[str, str] = {}
    rows = []
    stamps = []
    for name, entry in raw.items():
        etf = entry.get("etf") or entry.get("ticker") or name
        state = map_sector_state(entry.get("status"), _rs(entry, "20d"))
        states[etf] = state
        rows.append({"state": state})
        if entry.get("updated_at"):
            stamps.append(str(entry["updated_at"]))
    return {
        "regime": classify_rotation_regime(rows),
        "states": states,
        "as_of": min(stamps) if stamps else None,
        "n_sectors": len(rows),
    }


async def resolve_sector_etf(conn, ticker: str) -> Optional[str]:
    """Ticker -> SPDR sector ETF. The static 3-10 map first (its "INDEX" sentinel means
    deliberately sector-agnostic -> None), then the sector_constituents table. No new source."""
    tkr = (ticker or "").upper()
    try:
        from indicators.sector_rotation_3_10 import _DEFAULT_SECTOR_MAP
        etf = _DEFAULT_SECTOR_MAP.get(tkr)
    except Exception:
        etf = None
    if etf == "INDEX":
        return None
    if etf:
        return etf
    try:
        return await conn.fetchval(
            "SELECT sector_etf FROM sector_constituents WHERE ticker = $1 LIMIT 1", tkr)
    except Exception as exc:
        logger.debug("sector_constituents lookup failed for %s: %s", tkr, exc)
        return None
