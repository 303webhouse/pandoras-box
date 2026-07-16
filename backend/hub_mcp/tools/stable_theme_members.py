"""hub_get_stable_theme_members — theme drill-down (top/bottom movers) with a
live RTH price overlay, rate-bounded to once/minute/theme.

Separate tool from hub_get_stable_themes (not a param) -- this one carries a
different freshness contract: during RTH it live-fetches prices for the
returned slice (AEGIS fix, Brief 3: slice-then-fetch, not full-roster-then-
slice -- see services/read_only/stable.py::get_theme_members), flipping
anchor from 'close' to 'provisional'. The base themes snapshot never does
that. In-process 60s cache keyed by (theme, top, bottom, minute-bucket)
caps the live-fetch rate to once/minute/theme regardless of how many
committee members ask about the same theme in a burst -- the MCP rate
limiter is global-per-token across all tools, not per-tool, so nothing
else bounds this.
"""

from __future__ import annotations

import time

from ..decorators import mcp_tool
from ..envelope import make_response
from ..stable_envelope import map_stable_status
from services.read_only.stable import get_theme_members

DESCRIPTION = (
    "Returns a theme's top and bottom movers (ticker, name, 1d/5d return, RS "
    "vs QQQ, above 20/50dma, ATR extension, last price) from the Pandora's "
    "Box Stable Engine. During regular trading hours the returned slice gets "
    "a LIVE price overlay (anchor flips 'close' -> 'provisional'); outside "
    "RTH it's the last close. Use this as a deliberate drill-down after "
    "hub_get_stable_themes flags a theme worth investigating -- NOT as a "
    "routine per-theme poll.\n\n"
    "RATE GUIDANCE: live overlay only fires during RTH; do not call this "
    "more than once per minute per theme -- responses are cached "
    "server-side for 60s per (theme, top, bottom), so repeated calls within "
    "that window return the same cached read anyway. Outside that cadence, "
    "or outside RTH, hub_get_stable_themes' snapshot is cheaper and "
    "sufficient.\n\n"
    "Do NOT call this for a ticker outside the theme's own roster. Do NOT "
    "assume `top`/`bottom` sort the WHOLE theme -- only the top N and "
    "bottom N by 1d return are returned, matching the requested top/bottom "
    "sizes (default 5/5, max 50/50)."
)

_MEMBERS_CACHE: dict = {}
_CACHE_TTL_S = 60


def _summary(data: dict, status: str, theme: str) -> str:
    if status == "unavailable":
        return f"Theme members ({theme}): unavailable, no data for this theme."
    top = data.get("top") or []
    top_str = ", ".join(f"{m['ticker']} ({m.get('ret_1d', 0)*100:+.1f}%)" for m in top[:3]) or "none"
    anchor = data.get("anchor")
    live_tag = " [LIVE]" if anchor == "provisional" else ""
    return f"Theme {theme}{live_tag}: {data.get('member_count', 0)} members. Top: {top_str}."


@mcp_tool(name="hub_get_stable_theme_members", description=DESCRIPTION)
async def hub_get_stable_theme_members(theme: str, top: int = 5, bottom: int = 5) -> dict:
    """Return a theme's top/bottom movers, with a rate-bounded RTH live overlay."""
    if not theme or not isinstance(theme, str):
        return make_response(
            status="unavailable",
            error="theme is required (non-empty string).",
            summary="hub_get_stable_theme_members: theme required.",
        )
    top = max(1, min(int(top), 50))
    bottom = max(1, min(int(bottom), 50))

    minute_bucket = int(time.time() // 60)
    cache_key = (theme, top, bottom, minute_bucket)
    cached = _MEMBERS_CACHE.get(cache_key)
    if cached is not None:
        data = cached
    else:
        data = await get_theme_members(theme, top=top, bottom=bottom)
        _MEMBERS_CACHE[cache_key] = data
        # Bound memory: drop any entries from a prior minute bucket.
        stale_keys = [k for k in _MEMBERS_CACHE if k[3] != minute_bucket]
        for k in stale_keys:
            del _MEMBERS_CACHE[k]

    status, staleness_seconds = map_stable_status(data)

    return make_response(
        status=status,
        data=data,
        summary=_summary(data, status, theme),
        staleness_seconds=staleness_seconds,
    )
