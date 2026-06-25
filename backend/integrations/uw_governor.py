"""UW budget governor — Parts B2 + D (2026-06-16 UW budget rework).

Enforces per-caller daily quotas at the single UW chokepoint (`_uw_request`).
When a caller exhausts its daily quota the call is BLOCKED before it hits UW,
and a typed, FALSY sentinel (`UWUnavailable`) is returned instead of a silent
`None`. This kills the fake-healthy anti-pattern (a silent `None` on throttle
looks identical to "no data", which is exactly why the 2026-06-16 outage was
invisible until a human noticed stale cells). Consumers that want to surface
"stale / quota exhausted" can `isinstance(resp, UWUnavailable)`; consumers that
only do `if not resp:` keep their existing degrade-to-cache/fallback behavior
because the sentinel is falsy.

Reserved foreground headroom (Part D): quotas are PER-CALLER and INDEPENDENT.
Background callers (sector refresh) get tight quotas; foreground live-trading
callers (quotes, option chains, flow) get generous quotas. Because each caller
draws only its own counter, background can NEVER consume foreground's
allocation — foreground headroom is structurally reserved, not advisory. The
2026-06-16 outage was background sector refresh starving foreground (quotes /
chains / flow went dark mid-selloff); this makes that structurally impossible.
The sum of all quotas is held under DAILY_BUDGET minus a safety buffer, so the
aggregate also cannot blow the daily cap.

Tiering: BACKGROUND is sized to be exhausted FIRST under pressure (intended —
e.g. the heatmap goes visibly stale in the afternoon rather than starving live
trade reads). B3 throttles the sector loop at the source to stretch its
BACKGROUND quota across the session and render visible staleness when blocked.

Rollout (staged, like the webhook hardening): `UW_GOVERNOR_MODE` env, default
"observe". In observe mode the governor LOGS would-block decisions but does NOT
block — a one-session shakedown to confirm the quota table doesn't starve
foreground. Flip to "enforce" only after a post-reset session validates it.

AEGIS: governor logs carry only {caller, count, quota, tier, mode} — never the
API key, URL, or params. Matches the existing clean log precedent in uw_api.py.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Tuple

from integrations.uw_api_cache import DAILY_BUDGET, get_caller_count

logger = logging.getLogger("uw_governor")

# ── Tiers ────────────────────────────────────────────────────────────
TIER_FOREGROUND = "FOREGROUND"  # live-trading reads — protected, never starved
TIER_STANDARD = "STANDARD"      # scanners / factor data
TIER_BACKGROUND = "BACKGROUND"  # sector refresh etc. — cut first

# ── UWUnavailable reason codes (returned to consumers) ───────────────
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
RATE_LIMITED = "RATE_LIMITED"      # UW returned 429
CIRCUIT_OPEN = "CIRCUIT_OPEN"
NO_API_KEY = "NO_API_KEY"


class UWUnavailable:
    """Falsy typed sentinel for a blocked/unavailable UW call.

    Falsy (`__bool__` -> False) so existing `if not resp:` fallback paths fire
    unchanged. Typed so governor-aware consumers (sector heatmap, B3) can render
    visible staleness instead of faking fresh data. NEVER carries response data
    — it is only returned on a control-flow block (quota / 429 / circuit / no
    key), never in place of a real 200 body.
    """

    __slots__ = ("reason", "caller", "tier", "detail")

    def __init__(self, reason: str, caller: Optional[str] = None,
                 tier: Optional[str] = None, detail: Optional[str] = None):
        self.reason = reason
        self.caller = caller
        self.tier = tier
        self.detail = detail

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"UWUnavailable(reason={self.reason}, caller={self.caller}, detail={self.detail})"


def is_unavailable(obj) -> bool:
    """True if obj is a governor sentinel (vs a real None / dict)."""
    return isinstance(obj, UWUnavailable)


# ── Per-caller daily quota table ─────────────────────────────────────
# (quota, tier). Sum held under DAILY_BUDGET - QUOTA_SAFETY_BUFFER. These are
# STARTING VALUES to tune against the first post-reset session's telemetry
# (`GET /api/uw/health/by_caller`); the mechanism is the durable part, the
# numbers are knobs. Tags match the `caller=` strings passed at each call site
# (see the ohlc_* split in get_ohlc).
QUOTA_SAFETY_BUFFER = 2000  # leave >=2k/day headroom under the 20k UW cap

QUOTAS: Dict[str, Tuple[int, str]] = {
    # ── FOREGROUND (live trading — generous, structurally reserved) ──
    "snapshot": (3000, TIER_FOREGROUND),          # live prices: MTM, quote, macro strip
    "option_contracts": (2000, TIER_FOREGROUND),  # DAEDALUS options chains
    "ohlc_quote": (800, TIER_FOREGROUND),         # regular-session daily-change (quote path)
    "iv_rank": (700, TIER_FOREGROUND),            # chain IV rank
    "max_pain": (700, TIER_FOREGROUND),           # chain max pain
    "greek_exposure": (500, TIER_FOREGROUND),     # GEX
    "flow_recent": (1500, TIER_FOREGROUND),       # Flow Radar + wh_accumulation (committee-facing)
    "market_tide": (300, TIER_FOREGROUND),
    "chart_indicators": (700, TIER_FOREGROUND),   # PYTHAGORAS daily technical feed (one ohlc/1d pull/call)
    # ── STANDARD (scanners / factors) ──
    "ohlc_bars": (1500, TIER_STANDARD),           # factor/indicator daily bars (bars.py + get_bars)
    "darkpool_ticker": (800, TIER_STANDARD),
    "flow_per_expiry": (100, TIER_STANDARD),      # uw_flow_poller (deactivated) — standby reclaimed 500->100 to fund chart_indicators
    "news_headlines": (300, TIER_STANDARD),
    "stock_info": (300, TIER_STANDARD),
    "short_interest": (200, TIER_STANDARD),
    "congressional": (100, TIER_STANDARD),
    "insider_ticker": (100, TIER_STANDARD),
    "insider_all": (100, TIER_STANDARD),
    "economic_calendar": (100, TIER_STANDARD),
    "earnings_premarket": (100, TIER_STANDARD),
    "earnings_afterhours": (100, TIER_STANDARD),
    "earnings_dates": (100, TIER_STANDARD),
    # ── BACKGROUND (cut first; afternoon staleness is acceptable) ──
    "ohlc_sector": (1500, TIER_BACKGROUND),       # sector WK% — heatmap, glanceable tier
    "technical_indicator": (1500, TIER_BACKGROUND),  # sector RSI
    "sector_etfs": (300, TIER_BACKGROUND),
    "darkpool_recent": (100, TIER_BACKGROUND),    # reclaimed 300->100 to fund chart_indicators
}
# QUOTAS sum = 17,500 (was 17,400; +700 chart_indicators, -400 flow_per_expiry,
# -200 darkpool_recent). <= 18,000 cap, and <= 20,000 - QUOTA_SAFETY_BUFFER. ✓

# Unknown / untagged callers: small STANDARD allowance so a new code path can't
# silently blow the budget, but isn't instantly blocked either.
DEFAULT_QUOTA = 500
DEFAULT_TIER = TIER_STANDARD
UNTAGGED_QUOTA = 200  # "untagged" should trend to zero as tag coverage fills in


def _mode() -> str:
    """Governor mode from env, empty-safe. 'observe' (default) | 'enforce'."""
    return (os.getenv("UW_GOVERNOR_MODE") or "observe").strip().lower()


def quota_for(caller: str) -> Tuple[int, str]:
    """(quota, tier) for a caller tag, with sane defaults for unknowns."""
    if caller in QUOTAS:
        return QUOTAS[caller]
    if caller == "untagged":
        return (UNTAGGED_QUOTA, DEFAULT_TIER)
    return (DEFAULT_QUOTA, DEFAULT_TIER)


async def precheck(caller: str) -> Optional[UWUnavailable]:
    """Quota gate for one UW call. Called BEFORE the token bucket / HTTP.

    Returns a UWUnavailable sentinel when the caller is over quota AND the
    governor is enforcing; returns None (allow) otherwise. In observe mode it
    LOGS a would-block but never blocks. Fail-open: if the counter is
    unreadable (Redis down) the count reads 0 and the call proceeds — we never
    block UW because of an infra blip.
    """
    quota, tier = quota_for(caller)
    count = await get_caller_count(caller)
    if count < quota:
        return None

    mode = _mode()
    if mode == "enforce":
        logger.warning(
            "UW governor BLOCK caller=%s count=%d quota=%d tier=%s mode=enforce",
            caller, count, quota, tier,
        )
        return UWUnavailable(QUOTA_EXCEEDED, caller=caller, tier=tier,
                             detail=f"{count}/{quota}")

    # observe (default): log the would-block, allow the call through.
    logger.warning(
        "UW governor WOULD-BLOCK caller=%s count=%d quota=%d tier=%s mode=observe",
        caller, count, quota, tier,
    )
    return None


async def governor_status() -> dict:
    """Snapshot for observability (B4-lite, surfaced via GET /api/uw/health).

    Returns mode, total quota allocation vs budget, and per-caller usage% so
    the OBSERVE rollout can be watched and the table tuned. AEGIS-clean.
    """
    total_quota = sum(q for q, _ in QUOTAS.values())
    rows = []
    over = []
    for caller, (quota, tier) in QUOTAS.items():
        count = await get_caller_count(caller)
        pct = round(100.0 * count / quota, 1) if quota else None
        rows.append({"caller": caller, "tier": tier, "count": count,
                     "quota": quota, "usage_pct": pct})
        if count >= quota:
            over.append(caller)
    rows.sort(key=lambda r: -(r["usage_pct"] or 0))
    return {
        "mode": _mode(),
        "daily_budget": DAILY_BUDGET,
        "total_quota_allocated": total_quota,
        "safety_buffer": DAILY_BUDGET - total_quota,
        "callers_over_quota": over,
        "callers": rows,
    }
