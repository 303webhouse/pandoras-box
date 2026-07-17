"""Shared REST-to-MCP status mapping for the hub_get_stable_*/hub_get_board_state tools
(Brief 3, 2026-07-15).

The REST "house labeling contract" (as_of/data_age_seconds/anchor/degraded[/flatline])
and the MCP envelope (status/data/summary/staleness_seconds/schema_version/error) are
structurally different shapes. This module is the ONE place that bridges them, so all
6 tools apply the exact same precedence instead of drifting into 6 slightly different
interpretations.

`flatline` (when present -- regime/themes/movers/rates/fx, via
stable_engine.job_status.feed_flatline against SLO_SECONDS) is trusted directly rather
than recomputed here -- the REST layer already does that math correctly; reimplementing
it a second time would risk exactly the kind of duplicated-logic drift this whole brief
exists to avoid. theme_members and board_state's tide/kill-switch carry no flatline
field (no SLO baseline for them), so the "stale" tier is skipped for those -- they only
ever resolve to unavailable/degraded/ok.
"""

from __future__ import annotations

from typing import Optional

# Known-corrupted theme scores -- tool-output guard ONLY, does not fix the
# upstream computation (that's a separate, not-yet-written brief; orphaned
# P3 backlog item, scoped 7/10, never built). Shared here (not duplicated
# per-tool) so a future addition/removal only happens in one place --
# every hub_get_stable_* tool that surfaces a theme name checks this dict.
# Micro-fix 2026-07-16 (Fable): originally only wired into hub_get_stable_themes;
# hub_get_stable_regime's dominant/emerging/fading lists also surface theme
# names (Robotics was serving unflagged at rank 1 in dominant[], THALES's
# primary regime read) and needed the same guard.
KNOWN_BAD_THEMES = {
    "Robotics": "Robotics score is known-corrupted (delisted-ticker LAZR bug), do not treat as genuine momentum.",
}


def theme_warnings(theme_names: list) -> list:
    """Return data_quality_warnings for any known-bad theme name present in theme_names."""
    seen = []
    out = []
    for name in theme_names:
        if name in KNOWN_BAD_THEMES and name not in seen:
            seen.append(name)
            out.append(KNOWN_BAD_THEMES[name])
    return out


def map_stable_status(data: dict, feed: Optional[str] = None) -> tuple[str, Optional[int]]:
    """Map a services/read_only/stable.py or board.py envelope dict to (mcp_status, staleness_seconds).

    Precedence (first match wins):
      1. as_of is None (nothing ever fetched)          -> "unavailable"
      2. data["flatline"] is True (feed dead past SLO)  -> "unavailable" (data NOT nulled)
      3. data["degraded"] is True (REST-native)          -> "degraded"
      4. feed has a known SLO and age > 0.5x it          -> "stale"
      5. otherwise                                       -> "ok"

    anchor="provisional" alone is never treated as degradation -- it's the normal
    steady-state for movers/rates/fx/index-strip and the RTH state for theme_members.
    """
    age = data.get("data_age_seconds")
    staleness_seconds = int(round(age)) if age is not None else None

    if data.get("as_of") is None:
        return "unavailable", staleness_seconds

    if data.get("flatline"):
        return "unavailable", staleness_seconds

    if data.get("degraded"):
        return "degraded", staleness_seconds

    if feed and age is not None:
        try:
            from stable_engine.job_status import SLO_SECONDS
            slo = SLO_SECONDS.get(feed)
            if slo and age > 0.5 * slo:
                return "stale", staleness_seconds
        except Exception:
            pass

    return "ok", staleness_seconds


def worst_status(statuses: list) -> str:
    """Worst-of-N for multi-block tools (rates_fx, board_state). unavailable > degraded > stale > ok."""
    rank = {"unavailable": 3, "degraded": 2, "stale": 1, "ok": 0}
    return max(statuses, key=lambda s: rank.get(s, 0)) if statuses else "unavailable"


def flatline_error(feed: str) -> str:
    return f"feed_flatline:{feed}"
