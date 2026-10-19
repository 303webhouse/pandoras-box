"""`GET /api/yield-curve` — B3's tenor table, spreads, labels and measured fire rates.

Every served figure names its source, its universe and its as-of IN THE SAME SENTENCE as the
figure (Convention #37 as clarified by R-IV.1224(g)), because these are exactly the numbers
that get quoted onward without their caption.

DISPLAY ONLY (#42). Nothing gates on a yield-curve label; the regime engine's own BREADTH and
STRUCTURE families are a separate, already-ratified input and this route does not feed them.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from integrations import fred_series as fred
from models import yield_curve_b3 as yc

logger = logging.getLogger("api_yield_curve")

router = APIRouter(prefix="/yield-curve", tags=["yield-curve"])
# Included with prefix="/api" in main.py, so declaring "/api/..." here would double it.

#: Sparkline length, in sessions. B3's spec: 60-day sparklines on the two headline spreads.
SPARK_SESSIONS = 60


def _tenor_block(tenor: str, series_id: str) -> Dict[str, Any]:
    points = fred.fetch_series(series_id)
    as_of, level = fred.latest(points)
    values = [v for _, v in points]
    changes = yc.diffs(values)
    z = yc.zscore(changes)
    change_bp = changes[-1] if changes else None
    stats = yc.fires_per_year(changes)
    stats["as_of"] = as_of.isoformat() if as_of else "unknown"
    label = yc.label_for(z)
    return {
        "tenor": tenor,
        "series": series_id,
        "level_pct": level,
        "as_of": as_of.isoformat() if as_of else None,
        "change_bp": round(change_bp, 1) if change_bp is not None else None,
        "z": round(z, 2) if z is not None else None,
        "label": label,
        # EXTREME pulses; UNUSUAL does not. R-IV.1220(b).
        "pulse": label == yc.EXTREME,
        "fires": stats,
        "tooltip": yc.tooltip(tenor, stats),
        "unavailable_reason": None if level is not None else (
            "FRED returned no usable observation for %s (FRED_API_KEY present: %s)"
            % (series_id, fred.key_present())),
    }


def _spread_block(name: str, series_id: str) -> Dict[str, Any]:
    points = fred.fetch_series(series_id)
    as_of, level_pct = fred.latest(points)
    values = [v for _, v in points]
    # T10Y2Y / T10Y3M are published in PERCENTAGE POINTS, so the spread in bp is x100. Stated
    # because mixing the two units is how a 0.42 spread gets displayed as 0.4bp.
    bp = None if level_pct is None else level_pct * 100.0
    changes = yc.diffs(values)
    z = yc.zscore(changes)
    stats = yc.fires_per_year(changes)
    stats["as_of"] = as_of.isoformat() if as_of else "unknown"
    label = yc.label_for(z)
    spark = [round(v * 100.0, 1) for v in values if v is not None][-SPARK_SESSIONS:]
    bp_series = [None if v is None else v * 100.0 for v in values]
    return {
        "name": name,
        "series": series_id,
        "bp": round(bp, 1) if bp is not None else None,
        "as_of": as_of.isoformat() if as_of else None,
        "change_bp": round(changes[-1], 1) if changes else None,
        "z": round(z, 2) if z is not None else None,
        "label": label,
        "pulse": label == yc.EXTREME,
        "spark": spark,
        "spark_sessions": len(spark),
        "fires": stats,
        "tooltip": yc.tooltip(name, stats),
        "un_inverted": yc.un_inverted(bp_series),
        "inverted": None if bp is None else bp < 0,
    }


def payload() -> Dict[str, Any]:
    tenors = [_tenor_block(t, s) for t, s in yc.SERIES.items()]
    spreads = {n: _spread_block(n, s) for n, s in yc.SPREAD_SERIES.items()}
    word, why = yc.shape_word(spreads.get("2s10s", {}).get("bp"),
                              spreads.get("3m10s", {}).get("bp"))
    as_ofs = [t["as_of"] for t in tenors if t["as_of"]] + [
        s["as_of"] for s in spreads.values() if s["as_of"]]
    return {
        "live": True,
        "source": fred.SOURCE,
        "terms": fred.TERMS,
        "key_present": fred.key_present(),
        "as_of": max(as_ofs) if as_ofs else None,
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "tenors": tenors,
        "spreads": spreads,
        "shape": {"word": word, "basis": why, "vocabulary": list(yc.SHAPE_WORDS),
                  "vocabulary_author": "BUILD (R-IV.1220(b) requires a shape word and does "
                                       "not enumerate the words)"},
        "labels": {"unusual_z": yc.UNUSUAL_Z, "extreme_z": yc.EXTREME_Z,
                   "z_window_sessions": yc.Z_WINDOW,
                   "retired": ["RARE (R-IV.1220(b))",
                               "the 10Y >= 10bp route to EXTREME (R-IV.1239(b))"]},
        "field_origin": {"tenors": "derived", "spreads": "derived", "shape": "derived",
                         "fires": "derived", "as_of": "stored"},
    }


@router.get("")
async def get_yield_curve() -> Dict[str, Any]:
    """The curve. On failure it says so and serves no number at all.

    The import and the whole body are inside the try, which is the fix carried over from B2's
    route: a deferred import that cannot resolve raises at REQUEST time, and when it sits
    outside the handler's own error path the result is a bare 500 with no log line of its own.
    """
    try:
        import asyncio

        return await asyncio.to_thread(payload)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[yield-curve] failed: %s", type(exc).__name__)
        return {"live": True, "error": "%s" % type(exc).__name__, "tenors": [], "spreads": {},
                "note": "the FRED read failed; no cached or substituted figure is served"}
