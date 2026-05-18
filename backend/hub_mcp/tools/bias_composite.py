"""hub_get_bias_composite — 20-factor composite bias reading."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.bias import get_composite_bias, get_manual_override

DESCRIPTION = (
    "Returns the current 20-factor composite bias reading from the Pandora's "
    "Box hub, with per-factor breakdown and staleness flags. Use this when "
    "evaluating directional context for any trade idea, when running pre-market "
    "or weekly briefing setup, when any Olympus committee member (TORO, URSA, "
    "PYTHAGORAS, PYTHIA, THALES, DAEDALUS, PIVOT) needs to confirm whether the "
    "market regime supports the proposed direction, or when the user asks about "
    '"the bias," "market regime," "directional context," "what does the system see," '
    "or any equivalent.\n\n"
    "Do NOT call this for company-specific fundamentals, single-stock catalysts, "
    "or sector rotation — those have their own tools (`hub_get_hermes_alerts`, "
    "`hub_get_sector_strength`). Do NOT call this repeatedly within a single "
    "committee pass; one call per pass is sufficient.\n\n"
    "Returns 5-level bias mapping (TORO MAJOR / TORO MINOR / NEUTRAL / URSA "
    "MINOR / URSA MAJOR), composite score (−1.0 to +1.0), per-factor scores "
    "and weights, and staleness per factor."
)

Timeframe = Literal["swing", "daily", "intraday"]
_VALID_TIMEFRAMES = {"swing", "daily", "intraday"}


def _build_timeframe_payload(composite: Dict[str, Any]) -> Dict[str, Any]:
    """Map a CompositeResult dict into the per-timeframe payload shape."""
    factors_raw = composite.get("factors", {}) or {}
    factors: List[Dict[str, Any]] = []
    active = 0
    stale = 0
    now = datetime.now(timezone.utc)

    for name, reading in factors_raw.items():
        if reading is None:
            continue
        ts_raw = reading.get("timestamp")
        staleness = None
        is_stale = False
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                staleness = int((now - ts).total_seconds())
            except (ValueError, TypeError):
                staleness = None
        in_stale = name in (composite.get("stale_factors") or [])
        in_active = name in (composite.get("active_factors") or [])
        if in_stale:
            is_stale = True
            stale += 1
        if in_active:
            active += 1
        factors.append(
            {
                "name": name,
                "score": reading.get("score"),
                "weight": None,
                "staleness_seconds": staleness,
                "is_stale": is_stale,
            }
        )

    return {
        "composite_score": composite.get("composite_score"),
        "bias_level": composite.get("bias_level"),
        "factors": factors,
        "active_factor_count": active or len(composite.get("active_factors") or []),
        "stale_factor_count": stale or len(composite.get("stale_factors") or []),
    }


def _bias_label(level: Optional[str]) -> str:
    if not level:
        return "UNKNOWN"
    return level.replace("_", " ")


def _summary(payload: Dict[str, Any], override: Optional[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for tf in ("swing", "daily", "intraday"):
        tf_block = payload["timeframes"].get(tf)
        if tf_block is None:
            continue
        score = tf_block.get("composite_score")
        label = _bias_label(tf_block.get("bias_level"))
        score_str = f"{score:+.2f}" if isinstance(score, (int, float)) else "n/a"
        parts.append(f"{tf.title()}: {label} ({score_str})")
    base = ". ".join(parts) if parts else "No bias reading available"
    if override and override.get("level"):
        base += f". Manual override active: {_bias_label(override.get('level'))}."
    else:
        base += ". No manual override active."
    return base


@mcp_tool(name="hub_get_bias_composite", description=DESCRIPTION)
async def hub_get_bias_composite(
    timeframe: Optional[Timeframe] = None,
) -> dict:
    """Return composite bias for one or all timeframes."""
    if timeframe is not None and timeframe not in _VALID_TIMEFRAMES:
        return make_response(
            status="unavailable",
            error=f"Invalid timeframe '{timeframe}'. Use swing, daily, intraday, or omit.",
            summary=f"Invalid timeframe '{timeframe}'.",
        )

    composite = await get_composite_bias()
    if composite is None:
        return make_response(
            status="unavailable",
            error="Composite bias not cached. Bias engine may not have run yet.",
            summary="MCP: bias data unavailable.",
        )

    timeframes: Dict[str, Any] = {}
    # The v1 composite engine returns a single reading. Until the engine emits
    # separate per-horizon results, populate all three slots from the single
    # reading. PYTHIA and DAEDALUS rebuilds will introduce per-timeframe.
    snapshot = _build_timeframe_payload(composite)
    for tf in ("swing", "daily", "intraday"):
        if timeframe is None or timeframe == tf:
            timeframes[tf] = snapshot

    override = await get_manual_override()
    data = {
        "timeframes": timeframes,
        "manual_override_active": bool(override and override.get("level")),
        "override_level": (override or {}).get("level"),
    }

    confidence = (composite.get("confidence") or "").upper()
    velocity = composite.get("velocity_multiplier")
    if confidence == "LOW" or (composite.get("stale_factors") and len(composite["stale_factors"]) >= 5):
        status = "stale"
        staleness = 3600
    elif confidence in ("MEDIUM", ""):
        status = "ok"
        staleness = 60
    else:
        status = "ok"
        staleness = 60
    if velocity and isinstance(velocity, (int, float)) and velocity > 1.0:
        # rate-of-change escalation reading — fresh by construction
        status = "ok"
        staleness = 60

    return make_response(
        status=status,
        data=data,
        summary=_summary(data, override),
        staleness_seconds=staleness,
    )
