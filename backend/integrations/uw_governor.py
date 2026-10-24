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

from integrations.uw_api_cache import (
    DAILY_BUDGET, get_caller_count, get_caller_count_or_none,
)

# ── R-IV.901(c)2: the degraded path when the Redis counter cannot be read ──────────────────────
#
# HOW MANY PROCESSES CALL UW: **ONE**, established rather than assumed.
#   * Procfile's web entry is `uvicorn main:app` with NO `--workers`, so a single process;
#   * `railway.json` sets no `numReplicas`, so Railway's default of 1 replica;
#   * production holds one service that calls UW (`pandoras-box`; the other is Postgres);
#   * the `worker:` entry runs run_discord_bot.py, which contains ZERO UW references, and per
#     CLAUDE.md the bot runs on the VPS only.
#
# So the divisor the ruling asks for is 1 and each caller keeps its whole quota while degraded.
# It is written as a divisor anyway, because the day a second replica appears, two processes each
# allowing a full quota would silently double the ceiling — the arithmetic should already be
# there rather than needing to be remembered.
UW_PROCESS_COUNT = 1

_DEGRADED: Dict[str, int] = {}
_DEGRADED_ALERTED: Dict[str, str] = {}      # caller -> the UW day it was alerted on


def degraded_cap(quota: int) -> int:
    """This process's share of a caller's quota while the shared counter is unreadable."""
    return max(1, int(quota) // max(1, UW_PROCESS_COUNT))


def _degraded_count(caller: str) -> int:
    return _DEGRADED.get(caller, 0)


def note_degraded_call(caller: str) -> None:
    """Count one call in this process's own tally. Called on the allow path, so the degraded
    ceiling actually fills instead of reading 0 forever."""
    _DEGRADED[caller] = _DEGRADED.get(caller, 0) + 1


def _alert_degraded_once(caller: str) -> None:
    """ONE alert per caller per UW day. A degraded gate that announced itself on every call
    would bury the fact it is degraded in the noise of saying so."""
    try:
        from integrations.uw_spend_ledger import uw_day
        today = uw_day().isoformat()
    except Exception:                                               # noqa: BLE001
        today = "unknown"
    if _DEGRADED_ALERTED.get(caller) == today:
        return
    _DEGRADED_ALERTED[caller] = today
    logger.error("UW governor DEGRADED for caller=%s: the shared counter is unreadable, so this "
                 "process is capping on its own tally at quota/%d. The ceiling is being held "
                 "locally, not globally.", caller, UW_PROCESS_COUNT)


def degraded_state() -> Dict[str, Any]:
    """For /health: which callers are being held locally rather than globally."""
    return {"process_count": UW_PROCESS_COUNT,
            "callers_degraded": dict(_DEGRADED),
            "alerted_today": dict(_DEGRADED_ALERTED)}


def reset_degraded_for_tests() -> None:
    _DEGRADED.clear()
    _DEGRADED_ALERTED.clear()
    _BREAKER.clear()


# ── R-IV.901(c)3: the daily-limit breaker ──────────────────────────────────────────────────────
#
# The ONLY exhaustion on record (2026-09-11, 23,417 requests) happened with every caller inside
# its own quota, which is the case the static table cannot catch and the account gate exists for.
# That gate is inert: UW's `x-uw-daily-req-count` header has not arrived for over 36 hours, so
# `account_shed()` can never fire because its input never comes.
#
# THIS WORKS WITHOUT THE HEADER. When UW refuses a request with HTTP 429 and a body naming
# `daily_request_limit_hit`, the account is at its cap — stated by the vendor, in the only form
# it offers when it has nothing left to give. One such refusal stops EVERY caller until the
# 20:00 ET reset.
#
# KEYED ON THE UW DAY, NOT A TIMER. The breaker records the UW day it tripped on, and clears
# because the day changes — so a restart does not forget it within the day and nothing has to
# remember to cancel it. (A sleeping timer would be lost on the next deploy, which happens
# several times a day here.)
LIMIT_BODY_MARKER = "daily_request_limit_hit"
BREAKER_TRIPPED = "ACCOUNT_DAILY_LIMIT"

_BREAKER: Dict[str, str] = {}      # "day" -> the UW day it tripped on


def _today_uw() -> str:
    try:
        from integrations.uw_spend_ledger import uw_day
        return uw_day().isoformat()
    except Exception:                                               # noqa: BLE001
        return "unknown"


def breaker_is_tripped() -> bool:
    """True while UW has told us the account is at its daily limit, for THIS UW day."""
    return _BREAKER.get("day") == _today_uw()


def trip_breaker(detail: str = "") -> None:
    """Called when UW returns 429 + the daily-limit marker. Alerts ONCE per UW day."""
    today = _today_uw()
    if _BREAKER.get("day") == today:
        return
    _BREAKER["day"] = today
    _BREAKER["detail"] = (detail or "")[:200]
    logger.error("UW governor BREAKER TRIPPED for UW day %s: the vendor refused a request with "
                 "429 %s. Every UW caller is stopped until the 20:00 ET reset. This is the "
                 "account limit, which the static quota table cannot see and the account gate "
                 "cannot read while the quota header is absent.", today, LIMIT_BODY_MARKER)


def breaker_state() -> Dict[str, Any]:
    return {"tripped": breaker_is_tripped(), "tripped_on": _BREAKER.get("day"),
            "detail": _BREAKER.get("detail"), "uw_day": _today_uw()}

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


# Reasons that mean UW ANSWERED. Everything else on the sentinel means the call never left
# this process. The distinction is the whole value of the sentinel to a consumer announcing a
# substitution: "they refused us" and "we never asked" have different causes, different
# remedies, and different owners.
VENDOR_ANSWERED = frozenset({RATE_LIMITED})


def describe_block(sentinel) -> str:
    """A phrase naming WHICH negative this was, for a substitution announcement."""
    if not is_unavailable(sentinel):
        return "no usable payload"
    if sentinel.reason in VENDOR_ANSWERED:
        return f"uw refused the call ({sentinel.reason})"
    return f"not attempted: governor block ({sentinel.reason})"


# ── Per-caller daily quota table ─────────────────────────────────────
# (quota, tier). Sum held under DAILY_BUDGET - QUOTA_SAFETY_BUFFER. These are
# STARTING VALUES to tune against the first post-reset session's telemetry
# (`GET /api/uw/health/by_caller`); the mechanism is the durable part, the
# numbers are knobs. Tags match the `caller=` strings passed at each call site
# (see the ohlc_* split in get_ohlc).
# R-IV.1265(d): CUT FROM 2,000 TO 1,950 to fund `notables_strip` at 50/day. This table already
# summed to exactly DAILY_BUDGET - buffer, so a new tag can only come from a reallocation or
# from the buffer, and the ruling chose the buffer. The arithmetic is asserted by
# `test_hub_quota_table_fits_inside_the_hub_budget`, not left to this comment -- the previous
# version of this line carried an arithmetic comment that survived two edits to the numbers it
# described, which is why the assertion exists.
# R-IV.1408(b)2: CUT FROM 1,950 TO 1,310 to fund `option_quote_grid` at 640/day. The table
# summed to exactly DAILY_BUDGET - buffer, so a new tag can only come from a reallocation or
# from the buffer, and the ruling took the buffer -- the only route that touches no caller's
# MEASURED demand. (Measured free under the table's own 1.2x sizing rule at the time: 9,594
# across daily_budget tags, but 5,000 of it sits on six `crypto_bars_*` tags whose sizing rests
# on a 2,764 sighting the ledger can no longer attribute, and four days is thinner than the ten
# UW days R-IV.886(e) required before resizing a tag.)
#
# The arithmetic is asserted by `test_hub_quota_table_fits_inside_the_hub_budget`, never by
# this comment -- the line this replaced carried arithmetic that outlived two edits to the
# numbers it described, which is why that test exists.
# R-IV.1415(c): 1,310 -> 1,290, the +20 that restores `option_quote_capture`'s 1.2x sizing
# margin. Asked for under R-IV.1408, not ruled then, ruled now. Same route as the 640 above and
# for the same reason: the table sums to exactly DAILY_BUDGET - buffer, so the buffer is the
# only source that costs no caller its measured demand.
QUOTA_SAFETY_BUFFER = 1290  # headroom under the HUB budget, not the account limit

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
    # R-IV.1058(b). THE HERMES ALARM GETS ITS OWN TAG, and this is why.
    #
    # `hermes_session_poll` shared `snapshot` and spent the tag out mid-session on two
    # consecutive days. MEASURED from uw_caller_spend_daily:
    #
    #   uw_day       snapshot  429s        quota 1100
    #   2026-10-12        458     0        (baseline: MTM + quote + strip only)
    #   2026-10-13       1106     0        OVER by 6
    #   2026-10-14       1100     0        pinned AT the ceiling
    #
    # 429s = 0 on every row: UW's own limiter never fired. The blocking was entirely this
    # governor, which is correct behaviour on an under-funded tag -- the defect is the funding.
    # On 10-14 the tag hit 1100 at 17:47:08Z and `hermes_session_poll` then failed 133 times,
    # once a minute, to the 16:00 ET close, reporting "alarm is blind".
    #
    # Demand: 3 symbols, one poll per 60 s, 390 RTH minutes = 1,170 calls. The `quote` cache
    # TTL is 60 s against a 60 s poll, so nearly every poll is a real call rather than a hit.
    # 1,170 x 1.2 = 1,404, rounded to 1,400 -- the same max(observed, projected) x ~1.2 rule
    # the rest of this table was built with.
    #
    # WHY A SEPARATE TAG RATHER THAN A BIGGER `snapshot`. Sharing made the alarm's spend
    # invisible and let it starve MTM, quote and the macro strip -- and MTM marks positions,
    # so that is the worse failure of the two. It is the same finding this table already
    # records against `outcome_resolver`, where six consumers behind one name could not be
    # told apart.
    # WHERE THE 1,400 CAME FROM. Headroom was ZERO -- this table already summed to exactly
    # 26,000 = DAILY_BUDGET 28,000 - QUOTA_SAFETY_BUFFER 2,000 -- so a new tag could only be
    # funded by reallocation, and the sum below is still exactly 26,000. Taken from four tags
    # with MEASURED slack over 2026-10-08..10-15, none left under this table's own
    # max(observed) x 1.2 rule:
    #
    #   ohlc_bars            2500 -> 1800   peak 1491   1.21x
    #   ohlc_sector          2500 -> 2220   peak 1850   1.20x
    #   technical_indicator  2500 -> 2220   peak 1848   1.20x
    #   chart_indicators      700 ->  560   peak    0   (no call in the window)
    #
    # NOT taken from `crypto_bars_outcome_resolver`, which was the obvious source at peak 0 and
    # 3,350 funded. A test rightly refuses it: that family's measured peak is 2,764 in one day,
    # and sizing the resolver under it would recreate the exact "blocks the largest consumer on
    # sight" fault the 2026-09-14 retune was filed to fix. Crypto research being closed
    # (R-IV.1058(d)3) is not evidence the resolver will never run again.
    "hermes_session": (1400, TIER_FOREGROUND),    # the session displacement alarm's marks
    "ohlc_quote": (2300, TIER_FOREGROUND),        # measured 1,929 projected — was 800
    "option_contracts": (2100, TIER_FOREGROUND),  # DAEDALUS options chains
    "iv_rank": (250, TIER_FOREGROUND),
    "max_pain": (200, TIER_FOREGROUND),
    "greek_exposure": (500, TIER_FOREGROUND),     # GEX — small, and decision-critical
    "flow_recent": (400, TIER_FOREGROUND),        # Flow Radar + wh_accumulation
    "market_tide": (300, TIER_FOREGROUND),
    "chart_indicators": (560, TIER_FOREGROUND),
    # R-IV.1265(d): the NOTABLES option strip, 50/day, carved from the safety buffer
    # (2,000 -> 1,950) rather than from another tag -- the ruling's choice, and the only one
    # available without reopening a measured sizing.
    #
    # STANDARD, NOT FOREGROUND, deliberately. FOREGROUND is "live trading -- protected, never
    # starved", and the tier exists to keep marks and quotes alive when the budget tightens.
    # The NOTABLES strip is DISPLAY ONLY (#42): nothing gates, caps or journals on it, so it
    # must not be able to compete with the reads that mark the book. It is also capped a second
    # time in `models/notables_strip.py`, because enforcement here is a MODE and a cap that
    # holds only while a global switch is in one position is not a cap.
    "notables_strip": (50, TIER_STANDARD),
    # ── STANDARD (scanners / factors) ──
    # ── crypto bars: the rename R-IV.380(b) said was owed — DONE, R-IV.624(b) ──
    # `outcome_resolver` named a JOB, not an endpoint, violating the endpoint-grain
    # convention at uw_api_cache.py:115 — which is why a table built by walking
    # endpoints never saw it and it ran on the 500 unknown-code-path default.
    # The rename was deferred because it resets the counter. It is done now, and
    # the BEFORE figure is recorded so the reset costs no measurement:
    #
    #   old tag `outcome_resolver`, measured 2026-10-01 14:40 UTC
    #     09-30 (full day)  369  — of which 333 was the two scheduled jobs
    #     10-01 (to 14:40Z) 204  — accounted for exactly by those jobs
    #
    # SIX consumers shared that one name (all via crypto_bars._fetch_uw_bars_full):
    # the resolver, tape-health, /api/crypto/state, the regime job, the MCP VP
    # tool and btc_market_structure. Measured 2026-10-01: an open Stater tab is
    # 4 calls per 30 s — 11,520/day, 41% of DAILY_BUDGET — and was indistinguishable
    # from the resolver's own traffic. Tags are declared once, in
    # jobs/crypto_bars.py::CRYPTO_BAR_CALLERS; a test proves every one appears
    # below, because an absent tag silently takes DEFAULT_QUOTA 500.
    #
    # SIZING. A first pass split the 4,500 six ways to keep the table total fixed.
    # test_uw_governor_account.py refused it, correctly: this tag's MEASURED peak is
    # **2,764 on 2026-09-14**, when it was the largest hub caller, so a sixth of
    # 4,500 would have blocked it on sight — the very fault the 09-14 retune was
    # filed to fix. The split is therefore NOT budget-neutral; it rises 500, which
    # the table's headroom carries (25,500 against the 26,000 cap).
    #
    # The 2,764 cannot be attributed to one consumer now — that is the defect being
    # fixed, and it is not retroactive. It is assigned to the resolver because
    # over-sizing a quota wastes headroom while under-sizing BLOCKS, and the table's
    # own rule is to size to the maximum of sightings, not the smaller one. The six
    # buckets separate from today, so the next tuning pass has real figures.
    "crypto_bars_outcome_resolver": (3350, TIER_STANDARD),  # measured 2,764 (09-14) x1.2
    "crypto_bars_tape_health": (700, TIER_STANDARD),        # 288/day scheduled + GET traffic
    "crypto_bars_state_api": (450, TIER_STANDARD),          # Stater /api/crypto/state
    "crypto_bars_regime": (200, TIER_STANDARD),             # 72/day scheduled
    "crypto_bars_vp_mcp": (150, TIER_STANDARD),             # on demand, Claude sessions
    "crypto_bars_market_structure": (150, TIER_STANDARD),   # on demand
    "ohlc_bars": (1800, TIER_STANDARD),
    # R-IV.380(b) READ: the poller IS running (main.py:882, every 300 s, RTH-gated)
    # and its output is consumed three ways — flow_radar's build_flow_summary,
    # board_state's uw:flow:{ticker}, and the flow_events feed. The old
    # "deactivated" comment named a DIFFERENT, genuinely-disabled loop in
    # bias_scheduler.py and sized this one's quota to 100 while it spent 1,640.
    # 2000 matches the "~1,680 UW calls/day" main.py:878 already documented.
    # R-IV.1082(b): reduced 2000 -> 1700 to fund `option_quote_capture` below, budget-neutral.
    # The 1,640-1,680 measured spend cited above still fits; the cut takes only the headroom.
    "flow_per_expiry": (1700, TIER_STANDARD),
    # R-IV.1082(b): the forward option bid/ask capture, 8 names x 0-3 DTE x 12 intraday slots.
    # Carved from flow_per_expiry by exactly this amount, so QUOTAS still sums to 26,000.
    # MEASURED from the expiry calendar before the job was written: 144/204/168/132/132 calls
    # Mon-Fri, worst day 204, mean 156 -- but 384 on Mon/Tue if all eight names turn out to
    # carry daily expiries. The job budgets ITSELF to 288/session rather than relying on which
    # case holds, because the governor sheds the calls that arrive LAST and those are the 15:00
    # and 15:30 slots. NO off-hours entry below: its window is 10:00-15:30 ET, entirely RTH,
    # so the STANDARD haircut never applies to it and an exemption would be a licence it has
    # no use for.
    # R-IV.1415(c): 300 -> 320. Measured peak 244, whose safe ceiling under this table's own
    # 1.2x rule is 250 -- so at 300 the tag was already AT its sizing limit before the 15:59
    # close slot (b1b75134) added ~14-20 calls a day. 320/1.2 = 266 restores the margin.
    # Funded from QUOTA_SAFETY_BUFFER above, so no caller gives up measured demand.
    "option_quote_capture": (320, TIER_STANDARD),
    # R-IV.1408(b)2: the 5-minute ATM-vertical grid, TRITON-R2 Stage A. 640/day, funded from
    # QUOTA_SAFETY_BUFFER above (1,950 -> 1,310), so no caller gives up measured demand.
    #
    # MEASURED BEFORE A CALL WAS SPENT, which is what the ruling required first: 75 slots
    # (09:45-15:55 ET, every 5 minutes) x 8 names x 1 nearest expiry = 600 fixed, plus
    # first-slot expiry discovery -- wasted probes only -- at ~20 on a Monday with Friday-only
    # names and 40 as an absolute bound. 640 is that bound, not a guess.
    #
    # NO off-hours entry below: the window is entirely RTH, so the STANDARD haircut never
    # applies and an exemption would be a licence it has no use for. STANDARD, not FOREGROUND:
    # a forward collection should be shed before a live quote, and FOREGROUND would buy
    # immunity from shedding that this does not need.
    "option_quote_grid": (640, TIER_STANDARD),
    "darkpool_ticker": (500, TIER_STANDARD),
    # R-IV.867(e): the daily ATM implied-volatility snapshot. Runs ONCE a session at 16:45 ET,
    # one /option-contracts call per universe ticker. 250 covers the universe with headroom and
    # is paired with a per-caller off-hours factor of 1.0 below -- without that, STANDARD's 25%
    # cut would leave it 62 calls for a job whose entire purpose happens after the close.
    "iv_snapshot": (250, TIER_STANDARD),
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
    # R-IV.886(d), INTERIM: 250/day, which is exactly the room the table has. 3,000 was ruled
    # (R-IV.839(c)) and does NOT fit -- the table sums to 26,000 against a 26,000 ceiling at 250,
    # and 28,750 at 3,000, while UW_GOVERNOR_MODE is `enforce` in production, so the overrun
    # would refuse real calls. The resize to ~3,000 waits on 10 UW days of measured spend
    # (R-IV.886(e)); this row collects FORWARD ROWS FIRST on the room available.
    #
    # The per-caller off-hours factor of 1.0 below is what makes 250 usable at all: the job runs
    # ONLY after the close, where STANDARD keeps 25%, so without it this would be 62 calls.
    # NOT promoted to FOREGROUND (R-IV.839(c)) -- that would also buy immunity from shedding,
    # and a nightly bulk collection is the first thing that should be shed, not the last.
    # The collector's own clock still stops it before 19:50 ET and the UW reset regardless.
    "darkpool_collector": (250, TIER_STANDARD),
    # R-IV.432(e): the backtest module's second-vendor check -- /ohlc/1d, only for graded
    # rows whose window spans a calendar event, at most 40 tickers a pass. It runs after the
    # close, where STANDARD keeps 25% (50/day), which is the ceiling it is sized under.
    "ohlc_grader": (200, TIER_STANDARD),
    # ── BACKGROUND (cut first; afternoon staleness is acceptable) ──
    # Sized to Monday's projection x1.3, NOT to Friday's 4,069 / 3,894. Friday was
    # measured under 429s, so those counts are inflated by retries that cannot
    # recur once this gate is live -- sizing a BACKGROUND tier to a retry storm
    # would reserve budget for a failure mode being removed in the same change.
    # If they do hit the ceiling the heatmap goes visibly stale, which is the
    # trade this tier was created to make.
    "ohlc_sector": (2220, TIER_BACKGROUND),       # sector WK% — heatmap
    "technical_indicator": (2220, TIER_BACKGROUND),  # sector RSI
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
# R-IV.867(e): PER-CALLER off-hours exemption, which takes precedence over the tier factor.
#
# The tier factor asks "how much does this KIND of caller need outside RTH?" and 25% is right
# for a scanner that has little to refresh at 03:00. It is wrong for a caller whose entire job
# IS after the close: iv_snapshot runs at 16:45 ET and would be cut to a quarter of a budget it
# needs in full, once, on the only occasion it ever runs.
#
# WHY NOT PROMOTE IT TO FOREGROUND, which already carries a 1.0 factor. Because the tier does
# two jobs: it sets the off-hours factor AND it sets what gets shed first under pressure.
# FOREGROUND is never shed -- "a live read is a live read" -- and a nightly snapshot is exactly
# the thing that SHOULD be shed before a live quote. A per-caller factor buys the off-hours
# quota without buying the shedding immunity, which is the only part it needs.
OFF_HOURS_FACTOR_BY_CALLER = {
    "iv_snapshot": 1.0,          # 16:45 ET, once a session
    "darkpool_collector": 1.0,   # 16:30 ET, nightly; R-IV.839(c) "do NOT promote to FOREGROUND"
    # R-IV.940(b): the backfill is DESIGNED to run after the close, so the 0.25 off-hours
    # haircut turned the ruled 2,500/day allowance into 625 and blocked the run after ~600
    # calls on its first night. Measured, not inferred: the vendor block read
    # "QUOTA_EXCEEDED detail=625/625", and 2500 x 0.25 is 625. Same exemption as the
    # collector beside it, for the same reason: a job whose whole window is off-hours cannot
    # be budgeted as though off-hours were its idle time.
    "darkpool_backfill_triton": 1.0,
    # R-IV.1073(c)'s backfill hit the IDENTICAL haircut, and the entry above predicted it.
    # MEASURED, not inferred: the governor logged
    #   "BLOCK caller=iv_term_backfill count=41 limit=41 tier=STANDARD mode=enforce"
    # and 165 x 0.25 is 41.25 -> 41. The ruled 136-call allowance was unspendable at 03:00 MT,
    # which is exactly when a calibration backfill over past sessions wants to run.
    #
    # This grants the OFF-HOURS QUOTA ONLY. The quota stays 165 and the tier stays STANDARD, so
    # the backfill is still the first thing shed under account pressure -- which is right: it
    # reads sessions that already happened and can always wait, unlike a live quote.
    "iv_term_backfill": 1.0,
}

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
    # A per-caller exemption wins over the tier's factor. `.get` with the tier factor as the
    # default keeps every unlisted caller on exactly the behaviour it had before.
    factor = OFF_HOURS_FACTOR_BY_CALLER.get(caller, NON_RTH_QUOTA_FACTOR.get(tier, 0.25))
    return max(0, int(quota * factor)), tier


# R-IV.380(a): AN INSTRUMENT THAT FAILS OPEN MUST NOT FAIL SILENTLY.
# Every open-on-unknown path below records WHY it opened, and /health.uw_quota
# publishes it as `gate_state`. Without this, "the governor is not shedding" and
# "the governor cannot see the account" are the same observation from outside —
# which is the absent-vs-neutral collapse this register has filed four times.
GATE_STATE_KEY = "uw:governor_gate_state"
_LAST_GATE_STATE = {"state": "unknown", "detail": "no precheck yet", "at": None}


def _set_gate_state(state: str, detail: str) -> None:
    """Record the gate's own condition. Logs only on TRANSITION, so a steady
    open state does not fill the log while a new one is still visible."""
    prev = _LAST_GATE_STATE.get("state")
    if prev != state:
        log = logger.warning if state.startswith("open:") else logger.info
        log("UW governor gate_state %s -> %s (%s)", prev, state, detail)
    from datetime import datetime as _dt, timezone as _tz
    _LAST_GATE_STATE.update({"state": state, "detail": detail,
                             "at": _dt.now(_tz.utc).isoformat()})


def gate_state() -> dict:
    """The gate's own condition, for /health.uw_quota."""
    return dict(_LAST_GATE_STATE)


def _reading_predates_reset(at_iso, now=None) -> bool:
    """Is this quota reading from a PREVIOUS quota day? (UW resets at 00:00Z.)

    DEF-GOVERNOR-STALE-READING-LATCHES. The cache TTL is 36 h and the quota
    period is 24 h, so a reading can outlive the day it describes. A count from
    yesterday is not a small error about today -- it is a statement about a
    counter that has since been set back to zero.

    Unparseable or missing -> False. We do not invent staleness any more than we
    invent freshness; a reading we cannot age is handled by the callers' other
    guards.
    """
    if not at_iso:
        return False
    from datetime import datetime as _dt, timezone as _tz
    try:
        t = _dt.fromisoformat(str(at_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=_tz.utc)
    n = now or _dt.now(_tz.utc)
    reset = n.astimezone(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return t < reset


# ── R-IV.441(c): A SHED DECISION NEEDS A FRESH READING ──────────────────────────
#
# The cross-day rule below (a reading from before 00:00Z) closed one latch. Production then
# showed the SAME latch inside a single day: 3,717 calls attributed, FOUR account readings, and
# no attempts -- the gate shed on a reading hours old, shedding suppressed the calls whose
# responses carry `x-uw-daily-req-count`, and the reading that would clear it could not arrive.
# A latch does not need a day boundary to sustain itself; it only needs to suppress its own
# input.
#
# So age is a gate condition in its own right: past ACCOUNT_READING_MAX_AGE_S the account is
# UNMEASURED NOW, whatever it said then, and an unmeasured account opens -- the same posture
# every other unknown in this module takes. Opening lets a call through, and a 200's response
# carries the header, so the gate is self-CLEARING instead of self-sustaining.
#
# ── CORRECTION, MEASURED AGAINST THE VENDOR 2026-09-17 ──────────────────────────
# That paragraph used to end: "if the account really is exhausted the fresh reading (a 429
# carries the header too) sheds again immediately." The parenthesis was FALSE, and it was taken
# from a module comment rather than from UW. A live 429 carries `x-request-id` and nothing else
# -- no counter, no limit. An exhausted account therefore cannot produce a reading at all, and
# the design as shipped opens, calls, is refused, and learns nothing from the refusal.
#
# The refusal is still evidence; it is simply not numeric. A 429 is now stored with its
# timestamp, and for RATE_LIMIT_BACKOFF_S afterwards the two non-interactive tiers shed on THAT
# -- a measured refusal rather than a remembered percentage. FOREGROUND is never shed on it,
# both because it is what a person is waiting on and because it keeps one path open through
# which a 200, and so a real reading, can still arrive. The window is short and self-expiring:
# evidence that suppresses its own renewal indefinitely is the latch this work exists to remove.
ACCOUNT_READING_MAX_AGE_S = 1800        # 30 minutes
RATE_LIMIT_BACKOFF_S = 600              # 10 minutes after a measured refusal
RATE_LIMIT_SHED_TIERS = ("STANDARD", "BACKGROUND")


def _reading_age_s(at_iso, now=None):
    """Age of a quota reading in seconds, or None when it cannot be aged."""
    if not at_iso:
        return None
    from datetime import datetime as _dt, timezone as _tz
    try:
        t = _dt.fromisoformat(str(at_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_tz.utc)
    return ((now or _dt.now(_tz.utc)) - t).total_seconds()


async def account_shed(tier: str, now=None) -> Optional[str]:
    """Should this tier be shed on ACCOUNT state? Returns a reason or None.

    `now` is a clock seam, not a parameter callers pass in production: every age here is
    measured against a real instant, and a test that builds "three hours old" out of the
    wall clock silently changes meaning depending on the hour it runs at — which is how a
    scenario meant to sit inside one quota day starts landing on the other side of a reset.

    Fail-OPEN on every unknown: no header seen yet, unreadable Redis, missing
    limit. An unmeasured account must not block traffic — that would make the
    instrument an outage of its own, which is the failure this whole register
    keeps finding.

    EVERY open-on-unknown path sets gate_state, so the opening is observable.
    """
    try:
        from integrations.uw_api import account_quota
        q = await account_quota()
        used, limit = q.get("used"), q.get("limit")
        # A REFUSAL IS A MEASUREMENT, and it is checked before any counter, because it is the
        # most recent thing the vendor has said about the account. It carries no number, so it
        # cannot set a percentage — only a bounded back-off on the tiers nobody is waiting on.
        r429 = _reading_age_s(q.get("last_429_at"), now)
        if r429 is not None and r429 <= RATE_LIMIT_BACKOFF_S and tier in RATE_LIMIT_SHED_TIERS:
            reason = ("UW refused a call %.0f min ago (429, no counter in it) - backing %s off "
                      "for %.0f min on measured refusal" % (r429 / 60, tier,
                                                            RATE_LIMIT_BACKOFF_S / 60))
            _set_gate_state("shed:rate_limited", reason)
            return reason
        if not isinstance(used, int):
            _set_gate_state("open:no_header",
                            "no x-uw-daily-req-count in the shared cache")
            return None
        # R-IV.405(b) / R-IV.406(c): a reading from BEFORE the last 00:00Z reset
        # describes a counter that no longer exists. Treating it as current
        # LATCHES: every tier sheds at a high stale percentage, shedding
        # suppresses the calls whose responses carry the header, and the reading
        # that would clear it can never arrive. Fails OPEN, as an unmeasured
        # account must.
        if _reading_predates_reset(q.get("at"), now):
            # R-IV.407(b): its OWN state, not folded into open:no_header. "no header
            # has ever been cached" and "the cached header belongs to a spent quota
            # day" have different causes and different fixes; one name for both is
            # the collapse this register keeps filing (conventions #18).
            _set_gate_state("open:stale_reading",
                            "last header %s predates the 00:00Z reset - the "
                            "account is UNMEASURED for this quota day, not at "
                            "%s" % (q.get("at"), used))
            return None
        # R-IV.441(c): an old reading cannot justify shedding, and shedding is what keeps it
        # old. Its own state, never folded into the cross-day one: "belongs to a spent quota
        # day" and "is hours old today" have different causes and different fixes.
        age = _reading_age_s(q.get("at"), now)
        if age is None:
            _set_gate_state("open:reading_unageable",
                            "last header carries no usable timestamp (%r) - it cannot be "
                            "shown FRESH, so it does not shed" % (q.get("at"),))
            return None
        if age > ACCOUNT_READING_MAX_AGE_S:
            _set_gate_state("open:reading_too_old",
                            "last header %s is %.0f min old (limit %.0f min) - the account is "
                            "UNMEASURED NOW, not at %s" % (q.get("at"), age / 60,
                                                           ACCOUNT_READING_MAX_AGE_S / 60, used))
            return None
        if not isinstance(limit, int) or limit <= 0:
            _set_gate_state("open:no_limit",
                            "account used=%s but no usable limit — cannot compute a "
                            "percentage, so nothing is shed" % used)
            return None
        pct = used / limit
        threshold = ACCOUNT_SHED_AT.get(tier, 0.75)
        if pct >= threshold:
            reason = "account %d/%d = %.0f%% >= %.0f%% for %s" % (
                used, limit, pct * 100, threshold * 100, tier)
            _set_gate_state("shedding", reason)
            return reason
        _set_gate_state("armed", "account %d/%d = %.0f%%, below every threshold"
                        % (used, limit, pct * 100))
    except Exception as exc:
        _set_gate_state("open:read_error",
                        "account state unreadable: %s" % type(exc).__name__)
        return None
    return None


#: Callers funded from UW_FOREIGN_RESERVE (12,000), NOT from the hub's DAILY_BUDGET.
#:
#: WHY A SECOND TABLE AND NOT A ROW IN `QUOTAS`. That table sums to exactly 26,000 against a
#: 28,000 DAILY_BUDGET, and the sum is asserted by a test. Putting the backfill's 2,500 in it
#: would either break that assertion or quietly eat the 2,000 of headroom the whole governor was
#: measured around. R-IV.921(b)3 funds the backfill "from the foreign reserve", which is the
#: part of the 40,000 account limit the hub deliberately does not spend -- so it is tracked
#: here, separately, and the hub's own budget arithmetic is left exactly as it was.
#:
#: These entries are TEMPORARY by ruling: the allowance lapses after 2026-10-23 and the job
#: refuses to run past it on its own (darkpool_backfill.ALLOWANCE_THROUGH).
FOREIGN_RESERVE_QUOTAS: Dict[str, Tuple[int, str]] = {
    # LAPSED 2026-10-24 and left at its number on purpose. `darkpool_backfill.ALLOWANCE_THROUGH`
    # is 2026-10-23, and both `run()` and the nightly loop refuse past it -- the loop RETURNS --
    # so this allowance is now unspendable whatever the figure says. Its census is finished (312
    # of 312 ticker-sessions, outstanding 0). `darkpool_forward` below is the live successor.
    # Reducing this is a budget decision nobody has ruled, so the number stands and the state is
    # written down instead.
    "darkpool_backfill_triton": (5000, TIER_STANDARD),   # R-IV.983(c), raised from 2,500; through 2026-10-23
    # R-IV.1073(c): the IV term-structure calibration backfill. 8 census names x 17 sessions
    # (2026-09-01 -> 09-24) = 136 calls, x1.2 = 164, rounded to 165.
    #
    # FROM THE RESERVE, as ruled, and NOT from `iv_snapshot` (250/day, DAILY_BUDGET, measured
    # peak 208): 136 calls through that tag would have exhausted the nightly IV snapshot, which
    # is the Hermes failure exactly one tag over. Also explicitly NOT from `darkpool_collector`
    # or `triton_flow_shadow`, both of which were at their ceilings on 2026-10-14 (R-IV.1071(c)).
    #
    # The reserve is 12,000 and the only other claim on it is the 5,000 above, so this is funded
    # from genuinely unallocated room and takes nothing from anyone.
    "iv_term_backfill": (165, TIER_STANDARD),
    # R-IV.1408(b)1: the FORWARD dark-pool walk. 250 a night, from the reserve, writing
    # `darkpool_backfill_pages` for each new session per R-IV.1403(c) with
    # `darkpool_collector` untouched (R-IV.912(c)2).
    #
    # IT ADDS ALMOST NOTHING, measured: the five most recent nights that walked one new session
    # across the 8 names spent 202 / 140 / 132 / 131 / 188 -- mean 158.6, median 140, max 202.
    # That spend was already happening through `darkpool_backfill_triton` until its allowance
    # lapsed at 00:00 UTC on 2026-10-24. 250 covers the measured maximum with headroom.
    #
    # FROM THE RESERVE and not the hub table, for the reason the two entries above give: the
    # reserve is 12,000 with 5,165 claimed, so this is funded from genuinely unallocated room
    # and takes nothing from anyone. STANDARD, matching the census walk it succeeds.
    #
    # NO EXPIRY DATE, deliberately, and that is the whole reason it is a separate tag: the
    # entry above expired, its loop RETURNED rather than slept, and one date literal stopped
    # the dark-pool pages and the F: bars export together. A forward collection has no end
    # date to write.
    "darkpool_forward": (250, TIER_STANDARD),
}


def quota_for(caller: str) -> Tuple[int, str]:
    """(quota, tier) for a caller tag, with sane defaults for unknowns."""
    if caller in QUOTAS:
        return QUOTAS[caller]
    if caller in FOREIGN_RESERVE_QUOTAS:
        return FOREIGN_RESERVE_QUOTAS[caller]
    if caller == "untagged":
        return (UNTAGGED_QUOTA, DEFAULT_TIER)
    return (DEFAULT_QUOTA, DEFAULT_TIER)


async def precheck(caller: str) -> Optional[UWUnavailable]:
    """Quota gate for one UW call. Called BEFORE the token bucket / HTTP.

    Returns a UWUnavailable sentinel when the caller is over quota AND the
    governor is enforcing; returns None (allow) otherwise. In observe mode it
    LOGS a would-block but never blocks.

    DEGRADED, NOT UNLIMITED (R-IV.901(c)2). This used to say: "if the counter is unreadable
    (Redis down) the count reads 0 and the call proceeds". That made an infra blip remove the
    ceiling rather than lower it, because 0 and "unknown" were the same value. An unreadable
    counter now caps on this process's own tally at quota/UW_PROCESS_COUNT, and alerts once per
    caller per UW day.
    """
    # Gate 0 (R-IV.901(c)3): the vendor has said the ACCOUNT is done for the day. Checked first
    # and for every tier, including FOREGROUND -- "a live read is a live read" is an argument
    # about OUR priorities, and it does not buy requests UW has already refused to serve.
    if breaker_is_tripped():
        if _mode() == "enforce":
            logger.warning("UW governor BLOCK caller=%s reason=breaker %s", caller,
                           _BREAKER.get("day"))
            return UWUnavailable(BREAKER_TRIPPED, caller=caller, tier=effective_quota(caller)[1],
                                 detail="UW daily limit hit on %s" % _BREAKER.get("day"))
        logger.warning("UW governor WOULD-BLOCK caller=%s reason=breaker mode=observe", caller)

    quota, tier = effective_quota(caller)

    # R-IV.901(c)2: DEGRADED, NOT UNLIMITED. `get_caller_count` returns 0 when Redis cannot be
    # read, so "no calls yet" and "the counter is gone" were the same answer and the gate failed
    # open to unlimited — a blip removed the ceiling instead of lowering it. The _or_none variant
    # distinguishes them; an unreadable counter now falls back to this process's own tally,
    # capped at the same quota, with ONE alert per caller per UW day.
    read = await get_caller_count_or_none(caller)
    degraded = read is None
    if degraded:
        count = _degraded_count(caller)
        # THE LIMIT MOVES TOO. Comparing a local tally against the GLOBAL quota would have made
        # the divisor decorative -- computed and never applied -- so the cap is the limit here.
        limit = degraded_cap(quota)
        _alert_degraded_once(caller)
    else:
        count = read
        limit = quota
        _DEGRADED.pop(caller, None)      # the real counter is back; stop shadowing it

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

    if count < limit:
        if degraded:
            # Tally the allow, or the local ceiling reads 0 for ever and degraded becomes
            # unlimited by a slower route than the one this replaced.
            note_degraded_call(caller)
        return None

    mode = _mode()
    suffix = " DEGRADED(local tally, cap=quota/%d)" % UW_PROCESS_COUNT if degraded else ""
    if mode == "enforce":
        logger.warning(
            "UW governor BLOCK caller=%s count=%d limit=%d tier=%s mode=enforce%s",
            caller, count, limit, tier, suffix,
        )
        return UWUnavailable(QUOTA_EXCEEDED, caller=caller, tier=tier,
                             detail=f"{count}/{limit}{suffix}")

    # observe (default): log the would-block, allow the call through.
    logger.warning(
        "UW governor WOULD-BLOCK caller=%s count=%d limit=%d tier=%s mode=observe%s",
        caller, count, limit, tier, suffix,
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
