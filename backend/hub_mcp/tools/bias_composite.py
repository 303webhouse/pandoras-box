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


#: Factor weights, read from the engine's own config so there is one author for them. A copy
#: pasted here would be a second place for a weight to drift, and the weights are the thing
#: convention #42's original defect was about.
try:
    from bias_engine.composite import FACTOR_CONFIG as _FC

    _FACTOR_WEIGHTS = {k: v.get("weight") for k, v in _FC.items()}
except Exception:                                                   # noqa: BLE001
    # A weight that cannot be read is served as None, never as 0.0 -- a zero weight is a
    # statement that the factor does not count, which is a different claim from "unknown".
    _FACTOR_WEIGHTS = {}


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
                # TA-193 R1: THE WEIGHT, which was hard-coded None. Without it a reader has a
                # list of scores and no way to see which of them the blend actually rests on,
                # so a -0.9 reading at 2% weight looks like a -0.9 reading at 12%.
                "weight": _FACTOR_WEIGHTS.get(name),
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
        # R-IV.99 item 2. Counts alone are misleading: six active factors carry
        # anywhere from 19% to 40% of the intended weight depending on WHICH six,
        # and the composite renormalises over survivors so the score reads identical
        # either way. coverage_ratio is the fraction of intended evidence the score
        # actually rests on. None = unknown (pre-fix cached payload), never 0.0.
        "coverage_ratio": composite.get("coverage_ratio"),
        "excluded_factors": composite.get("excluded_factors") or [],
        # TA-193 R1 — HOW composite_score WAS REACHED, so the question "why does my recompute
        # disagree" is answerable from the payload instead of from the source.
        #
        # `raw_score` is the weighted blend BEFORE any modifier: the figure
        # SUM(score x weight / active_weight_sum) reproduces. `score_modifiers` is every stage
        # that touched it afterwards, in order, each with its name, its value and the score
        # either side. Two different stages can produce the same 1.3x -- the velocity
        # multiplier, and the circuit breaker's `2.0 - scoring_modifier` on an already-bearish
        # score -- so the name is the only thing that distinguishes them.
        "raw_score": composite.get("raw_score"),
        "score_modifiers": composite.get("score_modifiers") or [],
        # The engine's per-timeframe sub-scores, each with the active weight it was normalised
        # over. NUMBERS ONLY, as ruled: a sub-score carries no bias label, because the call is
        # the composite's to make and a labelled sub-score reads as a second opinion.
        "sub_scores": composite.get("timeframe_scores") or {},
    }


def _bias_label(level: Optional[str]) -> str:
    if not level:
        return "UNKNOWN"
    return level.replace("_", " ")


def _summary(payload: Dict[str, Any], override: Optional[Dict[str, Any]]) -> str:
    # TA-193 R1: ONE LABEL, ONCE. This printed the same label and the same score three times
    # -- "Swing: URSA MINOR (-0.11). Daily: URSA MINOR (-0.11). Intraday: URSA MINOR (-0.11)"
    # -- because all three slots are one reading. Three identical clauses read as three
    # independent horizons agreeing, which is the strongest-looking and emptiest claim the
    # tool could make.
    blocks = [payload["timeframes"][tf] for tf in ("swing", "daily", "intraday")
              if payload["timeframes"].get(tf) is not None]
    parts: List[str] = []
    if blocks:
        b = blocks[0]
        score = b.get("composite_score")
        score_str = f"{score:+.2f}" if isinstance(score, (int, float)) else "n/a"
        parts.append(f"{_bias_label(b.get('bias_level'))} ({score_str}), one reading across "
                     f"{len(blocks)} timeframe slot(s)")
        raw = b.get("raw_score")
        moved = [m for m in (b.get("score_modifiers") or []) if m.get("applied")]
        if isinstance(raw, (int, float)) and isinstance(score, (int, float)):
            if moved:
                parts.append("blend %+.3f moved by %s" % (
                    raw, ", ".join("%s %s" % (m.get("name"), m.get("value")) for m in moved)))
            else:
                parts.append("blend %+.3f, unmodified" % raw)
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
    # TA-193 R1: SAID IN THE PAYLOAD, not only in the comment above. These three slots are the
    # SAME reading -- one object assigned three times -- so a reader comparing "swing" against
    # "intraday" is comparing a number with itself and will find agreement that means nothing.
    # The engine's real per-horizon figures are in `sub_scores` on each slot, and they are
    # keyed intraday / swing / MACRO, which is a third vocabulary again: `daily` here has no
    # counterpart there.
    timeframes_basis = (
        "THE THREE SLOTS ARE ONE READING. The v1 engine emits a single composite, and it is "
        "assigned to swing/daily/intraday unchanged, so they are identical by construction "
        "and their agreement carries no information. Per-horizon numbers live in "
        "`sub_scores` (keyed intraday/swing/macro -- note `daily` has no counterpart)."
    )

    override = await get_manual_override()
    data = {
        "timeframes": timeframes,
        "timeframes_basis": timeframes_basis,
        "manual_override_active": bool(override and override.get("level")),
        "override_level": (override or {}).get("level"),
        # B1 GEX regime — daily series, identical across timeframes; surfaced once.
        # "FADE" (+GEX, dealers long gamma), "MOMENTUM" (-GEX, dealers short gamma),
        # "NEUTRAL" (absent/stale/degenerate). Layer 3 (hub_get_regime) deferred.
        "gex_regime": composite.get("gex_regime"),
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
