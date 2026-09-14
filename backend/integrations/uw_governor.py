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
QUOTA_SAFETY_BUFFER = 2000  # headroom under the HUB budget, not the account limit

# ── RETUNED 2026-09-14 AGAINST MEASURED DEMAND (R-IV.379(c)) ────────────
# The previous table called itself "STARTING VALUES to tune against the first
# post-reset session's telemetry". That telemetry now exists, and it showed the
# table would have blocked three live callers on sight -- including `ohlc_quote`,
# a FOREGROUND caller, which is the tier the tiering exists to protect.
#
# Each quota below is max(observed Friday 09-11, projected Monday 09-14) x ~1.2.
# Friday's figures are inflated by retries under 429 and Monday's are a partial
# day projected to 24 h; taking the MAXIMUM of the two is deliberate -- a quota
# sized to the smaller sighting blocks on the day the larger recurs.
#
# TWO FINDINGS FELL OUT OF THE MEASUREMENT AND ARE RECORDED HERE:
#   * `outcome_resolver` was NOT IN THIS TABLE AT ALL and ran on DEFAULT_QUOTA
#     500 while spending 2,764 by mid-session -- the single largest hub caller
#     on Monday, governed by a default meant for unknown code paths.
#   * `flow_per_expiry` is commented "uw_flow_poller (deactivated)" and spent
#     1,640 on Friday. A caller documented as off is the fifth-largest consumer;
#     the comment is stale or the poller is not off, and which one is UNREAD.
QUOTAS: Dict[str, Tuple[int, str]] = {
    # ── FOREGROUND (live trading — protected, never clock-gated) ──
    "snapshot": (1100, TIER_FOREGROUND),          # live prices: MTM, quote, macro strip
    "ohlc_quote": (2300, TIER_FOREGROUND),        # measured 1,929 projected — was 800
    "option_contracts": (2100, TIER_FOREGROUND),  # DAEDALUS options chains
    "iv_rank": (250, TIER_FOREGROUND),
    "max_pain": (200, TIER_FOREGROUND),
    "greek_exposure": (500, TIER_FOREGROUND),     # GEX — small, and decision-critical
    "flow_recent": (400, TIER_FOREGROUND),        # Flow Radar + wh_accumulation
    "market_tide": (300, TIER_FOREGROUND),
    "chart_indicators": (700, TIER_FOREGROUND),
    # ── STANDARD (scanners / factors) ──
    "outcome_resolver": (4500, TIER_STANDARD),    # NEWLY LISTED — was on the 500 default
    "ohlc_bars": (2500, TIER_STANDARD),
    "flow_per_expiry": (2000, TIER_STANDARD),     # "deactivated" and spending: see above
    "darkpool_ticker": (500, TIER_STANDARD),
    "stock_info": (400, TIER_STANDARD),           # +/info backfill headroom for T5b Phase C
    "news_headlines": (300, TIER_STANDARD),
    "short_interest": (200, TIER_STANDARD),
    "congressional": (100, TIER_STANDARD),
    "insider_ticker": (100, TIER_STANDARD),
    "insider_all": (100, TIER_STANDARD),
    "economic_calendar": (100, TIER_STANDARD),
    "earnings_premarket": (100, TIER_STANDARD),
    "earnings_afterhours": (100, TIER_STANDARD),
    "earnings_dates": (100, TIER_STANDARD),
    # ── BACKGROUND (cut first; afternoon staleness is acceptable) ──
    # Sized to Monday's projection x1.3, NOT to Friday's 4,069 / 3,894. Friday was
    # measured under 429s, so those counts are inflated by retries that cannot
    # recur once this gate is live -- sizing a BACKGROUND tier to a retry storm
    # would reserve budget for a failure mode being removed in the same change.
    # If they do hit the ceiling the heatmap goes visibly stale, which is the
    # trade this tier was created to make.
    "ohlc_sector": (2500, TIER_BACKGROUND),       # sector WK% — heatmap
    "technical_indicator": (2500, TIER_BACKGROUND),  # sector RSI
    "sector_etfs": (300, TIER_BACKGROUND),
    "darkpool_recent": (100, TIER_BACKGROUND),
    "triton_flow_shadow": (450, TIER_BACKGROUND),
}
# Sum is asserted against the HUB budget by a test, not by a comment that can go
# stale — the previous table's arithmetic comment survived two edits to the
# numbers it described.

# Unknown / untagged callers: small STANDARD allowance so a new code path can't
# silently blow the budget, but isn't instantly blocked either.
DEFAULT_QUOTA = 500
DEFAULT_TIER = TIER_STANDARD
UNTAGGED_QUOTA = 200  # "untagged" should trend to zero as tag coverage fills in


def _mode() -> str:
    """Governor mode from env, empty-safe. 'observe' (default) | 'enforce'."""
    return (os.getenv("UW_GOVERNOR_MODE") or "observe").strip().lower()


# ── R-IV.379(c): SHED BY ACCOUNT STATE, NOT ONLY BY OUR OWN COUNT ───────
# Per-caller quotas govern THIS process. They cannot see the other client on the
# key, and on 2026-09-11 that client spent 23,417 of the account's 40,000 while
# every hub caller sat inside its quota. The account was exhausted and the
# governor had nothing to say, because it was measuring the wrong thing.
#
# So the gate is now two-sided:
#   1. per-caller quota  — stops ONE caller running away (unchanged)
#   2. ACCOUNT SHED      — stops the hub adding to an account already near its
#                          limit, whoever filled it
#
# Tiers shed in order, so the account's last requests belong to the callers a
# trading decision depends on. FOREGROUND holds until 92%: gex, tide, flow
# alerts and /info keep working while the heatmap goes visibly stale, which is
# the trade this tiering existed for.
ACCOUNT_SHED_AT = {
    TIER_BACKGROUND: 0.55,
    TIER_STANDARD: 0.75,
    TIER_FOREGROUND: 0.92,
}
ACCOUNT_EXHAUSTED = "ACCOUNT_NEAR_LIMIT"

# ── Market-hours gate, AT THE CHOKEPOINT ────────────────────────────────
# R-IV.368(b)(2) asks for a gate on every UW poller. Putting it here instead of
# in each poller is deliberate and stronger: one place, it catches every caller
# including ones not written yet, and it cannot be forgotten by a new poller —
# which is exactly how DEF-UW-CLIENT-BYPASS happened.
#
# Holidays come from the ONE calendar (market_calendar), not a weekday test, so
# a Thanksgiving poll is gated the same as a Sunday one.
NON_RTH_QUOTA_FACTOR = {
    TIER_BACKGROUND: 0.0,    # a sector heatmap has nothing to refresh at 03:00
    TIER_STANDARD: 0.25,
    TIER_FOREGROUND: 1.0,    # never gated: a live read is a live read
}


def _is_rth(now_et=None) -> bool:
    """True during a regular trading session. Fail-OPEN: an unreadable calendar
    returns True, because gating a live caller on a calendar error would turn a
    data problem into an outage."""
    try:
        from datetime import datetime as _dt, time as _time
        from zoneinfo import ZoneInfo
        from stable_engine.market_calendar import is_trading_day
        now = now_et or _dt.now(ZoneInfo("America/New_York"))
        if not is_trading_day(now.date()):
            return False
        return _time(9, 30) <= now.time() <= _time(16, 0)
    except Exception:
        return True


def effective_quota(caller: str, now_et=None) -> Tuple[int, str]:
    """Per-caller quota after the market-hours factor. Never below 1 for
    FOREGROUND — a tier that can reach zero is a tier that can be starved by a
    rounding rule."""
    quota, tier = quota_for(caller)
    if _is_rth(now_et):
        return quota, tier
    factor = NON_RTH_QUOTA_FACTOR.get(tier, 0.25)
    return max(0, int(quota * factor)), tier


async def account_shed(tier: str) -> Optional[str]:
    """Should this tier be shed on ACCOUNT state? Returns a reason or None.

    Fail-OPEN on every unknown: no header seen yet, unreadable Redis, missing
    limit. An unmeasured account must not block traffic — that would make the
    instrument an outage of its own, which is the failure this whole register
    keeps finding.
    """
    try:
        from integrations.uw_api import account_quota
        q = await account_quota()
        used, limit = q.get("used"), q.get("limit")
        if not isinstance(used, int) or not isinstance(limit, int) or limit <= 0:
            return None
        pct = used / limit
        threshold = ACCOUNT_SHED_AT.get(tier, 0.75)
        if pct >= threshold:
            return "account %d/%d = %.0f%% >= %.0f%% for %s" % (
                used, limit, pct * 100, threshold * 100, tier)
    except Exception:
        return None
    return None


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
    quota, tier = effective_quota(caller)
    count = await get_caller_count(caller)

    # Gate 2: the ACCOUNT, whoever filled it. Checked even when this caller is
    # inside its own quota — that is the case the 2026-09-11 exhaustion was.
    shed = await account_shed(tier)
    if shed is not None:
        if _mode() == "enforce":
            logger.warning("UW governor BLOCK caller=%s tier=%s reason=account_shed %s",
                           caller, tier, shed)
            return UWUnavailable(ACCOUNT_EXHAUSTED, caller=caller, tier=tier, detail=shed)
        logger.info("UW governor WOULD-BLOCK caller=%s tier=%s reason=account_shed %s "
                    "mode=observe", caller, tier, shed)

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
