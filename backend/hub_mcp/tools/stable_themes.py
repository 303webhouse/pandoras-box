"""hub_get_stable_themes — ranked theme table from the Pandora's Box Stable Engine."""

from __future__ import annotations

from ..decorators import mcp_tool
from ..envelope import make_response
from ..stable_envelope import map_stable_status, flatline_error
from services.read_only.stable import get_themes

DESCRIPTION = (
    "Returns the ranked theme table from the Pandora's Box Stable Engine: "
    "theme name, rank, score, 1-day score delta, status (DOMINANT/EMERGING/"
    "FADING/etc), and member count, for every tracked theme (~20-30 "
    "typically). Use this whenever assessing which themes are leading or "
    "fading, when THALES (primary user) needs theme-rotation context, or "
    "when the user asks \"what's hot,\" \"which themes are leading,\" or "
    "any equivalent.\n\n"
    "Do NOT call this for a single theme's member tickers -- use "
    "hub_get_stable_theme_members(theme) for that drill-down. Do NOT call "
    "this for sector-ETF-specific rotation (use hub_get_sector_strength, a "
    "different data source and universe).\n\n"
    "IMPORTANT DATA QUALITY CAVEAT: the Robotics theme's score is currently "
    "known-corrupted (a delisted/recycled ticker, LAZR, pins it near 100.0) "
    "-- do NOT treat a high Robotics score as genuine momentum. Check "
    "data_quality_warnings on every response; if non-empty for a theme "
    "you're about to reason from, discount that theme's score."
)

_KNOWN_BAD_THEMES = {
    "Robotics": "Robotics score is known-corrupted (delisted-ticker LAZR bug), do not treat as genuine momentum.",
}


def _curate(theme_row: dict) -> dict:
    return {
        "theme": theme_row.get("theme"),
        "rank": theme_row.get("rank"),
        "score": theme_row.get("score"),
        "score_1d_delta": theme_row.get("score_1d_delta"),
        "status": theme_row.get("status"),
        "n_names": theme_row.get("n_names"),
    }


def _summary(data: dict, status: str, warnings: list) -> str:
    themes = data.get("themes") or []
    if status == "unavailable" and not themes:
        return "Stable themes: unavailable, no data ever computed."
    top = sorted((t for t in themes if t.get("score") is not None), key=lambda t: t["rank"] or 999)[:3]
    top_str = ", ".join(f"{t['theme']} ({t['score']})" for t in top) or "none"
    tag = " (FLATLINE)" if status == "unavailable" else ""
    warn = f" DATA QUALITY WARNING on {len(warnings)} theme(s)." if warnings else ""
    return f"Stable themes{tag}: {len(themes)} tracked. Top: {top_str}.{warn}"


@mcp_tool(name="hub_get_stable_themes", description=DESCRIPTION)
async def hub_get_stable_themes() -> dict:
    """Return the ranked theme table (curated fields), with a data-quality guard on known-bad themes."""
    data = await get_themes()
    status, staleness_seconds = map_stable_status(data, feed="nightly")

    raw_themes = data.get("themes") or []
    curated_themes = [_curate(t) for t in raw_themes]

    warnings = [
        _KNOWN_BAD_THEMES[t["theme"]]
        for t in curated_themes
        if t.get("theme") in _KNOWN_BAD_THEMES
    ]

    out_data = {
        "date": data.get("date"),
        "count": len(curated_themes),
        "themes": curated_themes,
        "as_of": data.get("as_of"),
        "anchor": data.get("anchor"),
        "degraded": data.get("degraded"),
        "flatline": data.get("flatline", False),
        "data_quality_warnings": warnings,
    }

    error = flatline_error("nightly") if status == "unavailable" and data.get("flatline") else None
    return make_response(
        status=status,
        data=out_data,
        summary=_summary(out_data, status, warnings),
        staleness_seconds=staleness_seconds,
        error=error,
    )
