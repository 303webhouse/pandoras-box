"""hub_get_trade_ideas — active scored trade ideas feed."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..decorators import mcp_tool
from ..envelope import make_response

DESCRIPTION = (
    "Returns the hub's active scored trade ideas — the grouped Insights feed "
    "ranked by composite score. Each group represents a unique ticker + "
    "direction setup: highest-scoring signal as primary, confluence tier "
    "(CONVICTION / CONFIRMED / STANDALONE), display_score (base + confirmation "
    "bonus, capped 100), supporting strategies, and trade parameters.\n\n"
    "Regime-aware: in a TORO (bull) regime, LONG signals get a -15pt score "
    "relaxation; in a URSA (bear) regime, SHORT signals get the same. Redis "
    "suppression hides groups already acted on (accepted or rejected in the "
    "dashboard) for 24 hours. When Redis is unavailable, status=degraded but "
    "the feed is still functional — suppression and regime adjustment are "
    "skipped and the response says so plainly.\n\n"
    "Call this at the start of every committee pass to seed the ticker list — "
    "it tells the committee what the hub's own engine considers the highest-"
    "conviction setups right now. Also call when the user asks 'what are the "
    "top ideas', 'what does the hub like', 'show me the insights', or any "
    "equivalent.\n\n"
    "Do NOT call this for bias context (use hub_get_bias_composite). "
    "Do NOT call this for options flow (use hub_get_flow_radar). "
    "Returns status=unavailable when the signals DB is unreachable."
)


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _serialize_group(g: Dict[str, Any], now: datetime, include_related: bool) -> Dict[str, Any]:
    """Explicit allow-list serialization — curated fields only, no jsonb blobs."""
    p = g["primary_signal"]

    age_minutes: Optional[float] = None
    newest = g.get("newest_at")
    if newest:
        try:
            newest_str = str(newest).replace("Z", "+00:00")
            if "+00:00" not in newest_str and "+" not in newest_str[10:]:
                newest_dt = datetime.fromisoformat(newest_str)
            else:
                newest_dt = datetime.fromisoformat(newest_str.replace("+00:00", ""))
            age_minutes = round((now - newest_dt).total_seconds() / 60, 1)
        except Exception:
            pass

    base_score = _safe_float(p.get("score_v2") or p.get("score")) or 0.0
    confirmation_bonus = g.get("confirmation_bonus", 0)

    out: Dict[str, Any] = {
        "signal_id": p.get("signal_id"),
        "group_key": g.get("group_key"),
        "ticker": g.get("ticker"),
        "direction": g.get("direction"),
        "display_score": g.get("display_score"),
        "confluence_tier": g.get("confluence_tier"),
        "feed_tier": p.get("feed_tier"),
        "gate_type": p.get("gate_type"),
        "signal_count": g.get("signal_count"),
        "distinct_strategy_count": g.get("distinct_strategy_count"),
        "strategies": g.get("strategies"),
        "signal_type": p.get("signal_type"),
        "signal_category": p.get("signal_category"),
        "entry_price": _safe_float(p.get("entry_price")),
        "stop_loss": _safe_float(p.get("stop_loss")),
        "target_1": _safe_float(p.get("target_1")),
        "target_2": _safe_float(p.get("target_2")),
        "risk_reward": _safe_float(p.get("risk_reward")),
        "timeframe": p.get("timeframe"),
        "bias_alignment": p.get("bias_alignment"),
        "newest_at": str(newest) if newest else None,
        "age_minutes": age_minutes,
        "score_components": {
            "base_score": base_score,
            "confirmation_bonus": confirmation_bonus,
        },
    }

    if include_related:
        out["related_signals"] = [
            {
                "signal_id": rs.get("signal_id"),
                "strategy": rs.get("strategy"),
                "score": _safe_float(rs.get("score")),
                "timestamp": str(rs.get("timestamp")) if rs.get("timestamp") else None,
                "confluence_tier": rs.get("confluence_tier"),
            }
            for rs in g.get("related_signals", [])
        ]

    return out


@mcp_tool(name="hub_get_trade_ideas", description=DESCRIPTION)
async def hub_get_trade_ideas(
    limit: int = 15,
    min_score: Optional[float] = 65.0,
    direction: Optional[str] = None,
    include_related: bool = False,
) -> dict:
    """Return the active grouped trade ideas feed."""
    if not isinstance(limit, int) or not (1 <= limit <= 25):
        return make_response(
            status="unavailable",
            error="limit must be an integer between 1 and 25",
            summary="Invalid limit parameter.",
        )
    if min_score is not None and (
        not isinstance(min_score, (int, float)) or not (0 <= min_score <= 100)
    ):
        return make_response(
            status="unavailable",
            error="min_score must be a number between 0 and 100",
            summary="Invalid min_score parameter.",
        )
    if direction is not None and direction.upper() not in ("LONG", "SHORT", "BUY", "SELL"):
        return make_response(
            status="unavailable",
            error="direction must be LONG, SHORT, BUY, or SELL",
            summary="Invalid direction parameter.",
        )

    try:
        from database.postgres_client import get_postgres_client
        from signals.feed_service import get_active_trade_ideas
        pool = await get_postgres_client()
    except Exception as exc:
        return make_response(
            status="unavailable",
            error=f"DB unavailable: {exc}",
            summary="hub_get_trade_ideas: database unavailable.",
        )

    try:
        groups_all, redis_ok = await get_active_trade_ideas(
            pool,
            min_score=min_score,
            direction=direction,
        )
    except Exception as exc:
        return make_response(
            status="unavailable",
            error=f"Feed query failed: {exc}",
            summary="hub_get_trade_ideas: query error.",
        )

    now = datetime.utcnow()
    limited: List[Dict[str, Any]] = groups_all[:limit]
    serialized = [_serialize_group(g, now, include_related) for g in limited]

    status = "degraded" if not redis_ok else "ok"
    redis_note = " Redis degraded — suppression and regime adjustment unavailable." if not redis_ok else ""

    data = {
        "ideas": serialized,
        "returned_count": len(serialized),
        "total_qualifying": len(groups_all),
        "min_score_applied": min_score,
        "direction_filter": direction.upper() if direction else None,
        "redis_degraded": not redis_ok,
    }

    if not serialized:
        return make_response(
            status=status,
            data=data,
            summary=f"No active trade ideas above threshold.{redis_note}",
            staleness_seconds=60,
        )

    top_str = ", ".join(
        f"{g['ticker']} {g['direction']} ({g['display_score']:.0f})"
        for g in serialized[:3]
    )
    summary = f"{len(serialized)} idea(s) returned. Top: {top_str}.{redis_note}"

    return make_response(
        status=status,
        data=data,
        summary=summary,
        staleness_seconds=60,
    )
