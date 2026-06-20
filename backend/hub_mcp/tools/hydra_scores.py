"""hub_get_hydra_scores — squeeze setup candidate scores."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.squeezes import get_squeeze_scores

DESCRIPTION = (
    "Returns the current Hydra squeeze setup scores from the Pandora's Box "
    "hub — composite scoring on squeeze-trade candidates based on short "
    "interest, days-to-cover, options positioning, gamma flip levels, and "
    "price compression. Filtered by ticker or returns top-N candidates "
    "globally. Use this whenever evaluating squeeze potential for a trade, "
    "when TORO is checking the \"Squeeze setup\" pattern (per references/"
    "equities.md), when URSA is grading whether a previously squeezed name is "
    "fading, when PYTHAGORAS is mapping squeeze candidates to structural "
    "breakout setups, when DAEDALUS is sizing options exposure on a squeeze "
    "candidate, when PIVOT is assembling the synthesis around a squeeze "
    'thesis, or when the user asks about "squeezes," "short squeeze," "Hydra," '
    "or any equivalent.\n\n"
    "Do NOT call this for general flow analysis (use `hub_get_flow_radar`). "
    "Do NOT call this for bias context (use `hub_get_bias_composite`).\n\n"
    "Returns ranked squeeze scores with component breakdown (short interest, "
    "options skew, gamma positioning, price compression)."
)


def _build_candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    components = {
        "short_interest_score": row.get("short_interest_score"),
        "days_to_cover_score": row.get("days_to_cover_score"),
        "options_skew_score": row.get("options_skew_score"),
        "gamma_positioning_score": row.get("gamma_positioning_score"),
        "price_compression_score": row.get("price_compression_score"),
    }
    return {
        "ticker": row.get("ticker"),
        "composite_score": row.get("composite_score"),
        "components": components,
        "short_interest_pct": row.get("short_interest_pct"),
        "days_to_cover": row.get("days_to_cover"),
        "gamma_flip_level": row.get("gamma_flip_level"),
        "current_price": row.get("current_price") or row.get("last_price"),
    }


HYDRA_STALE_SECONDS = 86_400  # 1 day; no rescan cron exists, so older = stale


def _compute_staleness(rows: List[Dict[str, Any]]):
    """Return (age_seconds, last_scan_iso) from the freshest row's updated_at.

    Rows from services.read_only.squeezes carry updated_at as an ISO string.
    Missing/unparseable timestamps -> (None, None); callers treat that as stale.
    """
    freshest = None
    for r in rows:
        ts = r.get("updated_at")
        if ts is None:
            continue
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if freshest is None or ts > freshest:
            freshest = ts
    if freshest is None:
        return None, None
    age = int((datetime.now(timezone.utc) - freshest).total_seconds())
    return age, freshest.isoformat()


@mcp_tool(name="hub_get_hydra_scores", description=DESCRIPTION)
async def hub_get_hydra_scores(
    ticker: Optional[str] = None,
    min_score: float = 50.0,
) -> dict:
    """Return ranked squeeze candidates."""
    if not isinstance(min_score, (int, float)) or not (0 <= min_score <= 100):
        return make_response(
            status="unavailable",
            error="min_score must be a number between 0 and 100",
            summary="Invalid min_score.",
        )

    rows = await get_squeeze_scores(
        ticker=ticker, min_score=float(min_score), limit=10 if not ticker else 5
    )
    if rows is None:
        return make_response(
            status="unavailable",
            error="Squeeze score source unavailable.",
            summary="MCP: hydra data unavailable.",
        )

    candidates: List[Dict[str, Any]] = [_build_candidate(r) for r in rows]

    if not candidates:
        # Empty result is honest as-is: nothing found, freshness N/A.
        scope = ticker.upper() if ticker else "global"
        data = {
            "ticker": ticker.upper() if ticker else None,
            "min_score": float(min_score),
            "candidates": [],
            "candidate_count": 0,
            "stale": False,
            "data_age_seconds": None,
            "last_scan_at": None,
        }
        summary = f"No squeeze candidates ({scope}) above threshold {min_score}."
        return make_response(
            status="ok", data=data, summary=summary, staleness_seconds=None
        )

    # FLOOR: derive honest staleness from the freshest row's updated_at. No
    # rescan cron exists, so April-1 data must NOT be served as if live. This
    # replaces the previously hardcoded staleness_seconds=1800 (fake-healthy).
    age_seconds, last_scan_at = _compute_staleness(rows)
    is_stale = age_seconds is None or age_seconds > HYDRA_STALE_SECONDS

    data = {
        "ticker": ticker.upper() if ticker else None,
        "min_score": float(min_score),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "stale": is_stale,
        "data_age_seconds": age_seconds,
        "last_scan_at": last_scan_at,
    }
    status = "stale" if is_stale else "ok"

    if ticker:
        top = candidates[0]
        body = (
            f"{ticker.upper()} Hydra: {top.get('composite_score')}/100. "
            f"SI {top.get('short_interest_pct')}%, DTC {top.get('days_to_cover')}, "
            f"price ${top.get('current_price')}."
        )
    else:
        top_str = ", ".join(
            f"{c['ticker']} ({c.get('composite_score')})" for c in candidates[:5]
        )
        body = f"Top squeeze candidates: {top_str}."

    if is_stale:
        days = round(age_seconds / 86_400, 1) if age_seconds is not None else "?"
        summary = (
            f"⚠ STALE: Hydra last scanned {days}d ago — scores unreliable, "
            f"no rescan cron. {body}"
        )
    else:
        summary = body

    return make_response(
        status=status, data=data, summary=summary, staleness_seconds=age_seconds
    )
