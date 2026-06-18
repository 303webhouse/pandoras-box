"""
UW API Redis Caching Layer

Configurable TTL per endpoint type, daily request counter with budget alerts,
cache hit/miss rate tracking.
"""

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("uw_api")

# TTLs by endpoint type (seconds)
CACHE_TTLS = {
    "flow": 300,          # 5 min (Phase A.4a fix 2026-05-27) — was 30s, but flow poller runs every 300s so every poller tick was a guaranteed miss → ~6,900 UW calls/day forced. Cache TTL now aligns with poller cadence.
    "flow_per_expiry": 300,  # L1.0 Path A: get_flow_per_expiry response cache, renamed off the "flow" namespace so it no longer collides with the committee uw:flow:* summary key. Same 300s as before (poller cadence).
    "gex": 3600,          # 1 hr — UW /greek-exposure is a DAILY snapshot (updates once/day,
                          # not intraday). 300s was burning 12 UW calls/hr for stale data.
                          # NOTE: B3/0DTE regime routing (C2) needs an intraday GEX source —
                          # this endpoint is too coarse for same-day scalp gating.
    "greeks": 300,        # 5 min
    "darkpool": 300,      # 5 min
    "market_tide": 60,    # 1 min
    "quote": 60,          # 60s (P1.7 fix 2026-04-28) — was 15s, hammered UW /state, tripped breaker. Heatmap+macro polls every 10s, served from cache 4x.
    "info": 86400,        # 24 hours (P1.6 fix 2026-04-28) — metadata changes quarterly, was 15s causing UW rate limit cascade
    "option_contracts": 300,  # 5 min
    "iv_rank": 300,       # 5 min
    "earnings": 3600,     # 1 hr (F.3)
    "calendar": 1800,     # 30 min — was 1 hr, economic data changes intraday (F.3)
    "news": 1800,         # 30 min (F.3 / B.7)
    "short_interest": 3600,  # 1 hr
    "ohlc": 300,          # 5 min (Phase A.3 fix 2026-05-22) — daily bars don't change minute-to-minute; the prior 60s TTL forced the refresh job to re-pull every tick, contributing to UW budget overdraw.
    "technical_indicator": 300,  # 5 min (Phase A.3 fix 2026-05-22) — RSI(14) moves slowly; 60s TTL was unnecessary minute-fresh.
    "option_chain_live": 25,     # hub_get_options_chain — short TTL for live-market chain display
}

DAILY_BUDGET = 20000     # UW Basic plan limit
BUDGET_ALERT_THRESHOLDS = [0.50, 0.70, 0.85, 0.90]  # Alert at each crossing — 90% is CRITICAL ceiling (drops 95% in favor of earlier-firing CRITICAL)

# In-memory stats (reset on deploy)
_stats = {"hits": 0, "misses": 0}


async def _get_redis():
    try:
        from database.redis_client import get_redis_client
        return await get_redis_client()
    except Exception:
        return None


async def cache_get(endpoint_type: str, key: str) -> Optional[Any]:
    """Get cached data. Returns None on miss."""
    redis = await _get_redis()
    if not redis:
        return None
    try:
        cache_key = f"uw:{endpoint_type}:{key}"
        raw = await redis.get(cache_key)
        if raw:
            _stats["hits"] += 1
            return json.loads(raw)
    except Exception as e:
        logger.debug("Cache get failed for %s: %s", key, e)
    _stats["misses"] += 1
    return None


async def cache_set(endpoint_type: str, key: str, data: Any) -> None:
    """Store data in cache with endpoint-specific TTL."""
    redis = await _get_redis()
    if not redis:
        return
    try:
        cache_key = f"uw:{endpoint_type}:{key}"
        ttl = CACHE_TTLS.get(endpoint_type, 300)
        await redis.set(cache_key, json.dumps(data, default=str), ex=ttl)
    except Exception as e:
        logger.debug("Cache set failed for %s: %s", key, e)


async def increment_daily_counter(caller: str = "untagged") -> int:
    """Increment daily request counter. Returns current count.

    Phase A.4a 2026-05-27: also writes a per-caller hash counter
    `uw:daily_requests_by_caller:{date}` via HINCRBY so the daily total
    can be attributed to specific UW-calling code paths. `caller` is an
    endpoint-grain tag (e.g. "snapshot", "flow_per_expiry", "ohlc")
    passed from each _uw_request call site. Untagged callers bucket as
    "untagged" — that bucket should trend toward zero as tag coverage
    fills in. The legacy global counter (`uw:daily_requests:{date}`) is
    preserved unchanged so /api/uw/health and budget-alert logic keep
    working identically.
    """
    redis = await _get_redis()
    if not redis:
        return 0
    try:
        from datetime import date
        today_str = date.today().isoformat()
        day_key = f"uw:daily_requests:{today_str}"
        caller_key = f"uw:daily_requests_by_caller:{today_str}"
        count = await redis.incr(day_key)
        # Per-caller attribution (Phase A.4a). Failure here must NOT break
        # the global counter / budget alerts — wrap defensively.
        try:
            await redis.hincrby(caller_key, caller, 1)
        except Exception as e:
            logger.debug("HINCRBY for caller %s failed: %s", caller, e)
        # Set expiry on first increment (48h to survive timezone edge)
        if count == 1:
            await redis.expire(day_key, 172800)
            try:
                await redis.expire(caller_key, 172800)
            except Exception:
                pass

        # Budget alerts at multiple thresholds (50/70/85/95%)
        # Use Redis flag per threshold per day to ensure each fires only once.
        for threshold_pct in BUDGET_ALERT_THRESHOLDS:
            threshold_count = int(DAILY_BUDGET * threshold_pct)
            if count >= threshold_count:
                flag_key = f"uw:budget_alert_fired:{today_str}:{int(threshold_pct * 100)}"
                already_fired = await redis.get(flag_key)
                if not already_fired:
                    await redis.setex(flag_key, 172800, "1")  # 48h TTL
                    logger.warning("UW API daily budget at %d%% (%d/%d requests)",
                                   int(threshold_pct * 100), count, DAILY_BUDGET)
                    await _post_budget_alert(count, int(threshold_pct * 100))

        return count
    except Exception:
        return 0


async def increment_429_counter(caller: str = "untagged") -> None:
    """Increment per-caller 429 counter (Phase A.4a instrumentation).

    Best-effort write to `uw:daily_429s_by_caller:{date}` via HINCRBY.
    Failure is silent — 429 attribution is observability, not control flow.
    """
    redis = await _get_redis()
    if not redis:
        return
    try:
        from datetime import date
        today_str = date.today().isoformat()
        key = f"uw:daily_429s_by_caller:{today_str}"
        await redis.hincrby(key, caller, 1)
        # Expire is idempotent in Redis — setting it on every increment is
        # cheap and avoids the "first-increment" coordination from
        # increment_daily_counter (where global INCR returns 1 on cold key).
        await redis.expire(key, 172800)
    except Exception:
        pass


async def get_caller_count(caller: str) -> int:
    """Today's request count for a single caller tag (B2 governor quota check).

    Single HGET on the per-caller hash maintained by increment_daily_counter.
    Fail-open: returns 0 when Redis is unavailable so the governor never blocks
    a UW call because of an infra blip.
    """
    redis = await _get_redis()
    if not redis:
        return 0
    try:
        from datetime import date
        key = f"uw:daily_requests_by_caller:{date.today().isoformat()}"
        v = await redis.hget(key, caller)
        return int(v) if v else 0
    except Exception:
        return 0


async def get_counts_by_caller() -> dict:
    """Return today's per-caller request + 429 counts.

    Used by `GET /api/uw/health/by_caller` (Phase A.4a). Returns empty
    dicts when Redis is unavailable so the route never errors.
    """
    empty = {"requests_by_caller": {}, "rate_limited_by_caller": {}}
    redis = await _get_redis()
    if not redis:
        return empty
    try:
        from datetime import date
        today_str = date.today().isoformat()
        req_key = f"uw:daily_requests_by_caller:{today_str}"
        err_key = f"uw:daily_429s_by_caller:{today_str}"
        req = await redis.hgetall(req_key) or {}
        err = await redis.hgetall(err_key) or {}

        def _coerce(d: dict) -> dict:
            out = {}
            for k, v in d.items():
                ks = k.decode() if isinstance(k, (bytes, bytearray)) else k
                try:
                    vs = int(v.decode() if isinstance(v, (bytes, bytearray)) else v)
                except (ValueError, TypeError):
                    continue
                out[ks] = vs
            return out

        return {
            "requests_by_caller": _coerce(req),
            "rate_limited_by_caller": _coerce(err),
        }
    except Exception:
        return empty


async def get_daily_count() -> int:
    """Get current daily request count."""
    redis = await _get_redis()
    if not redis:
        return 0
    try:
        from datetime import date
        day_key = f"uw:daily_requests:{date.today().isoformat()}"
        val = await redis.get(day_key)
        return int(val) if val else 0
    except Exception:
        return 0


def get_cache_stats() -> dict:
    """Return cache hit/miss stats."""
    total = _stats["hits"] + _stats["misses"]
    hit_rate = round(_stats["hits"] / total * 100, 1) if total > 0 else 0
    return {
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "total": total,
        "hit_rate_pct": hit_rate,
    }


async def _post_budget_alert(count: int, threshold_pct: int) -> None:
    """Post budget alert to Discord webhook with explicit threshold tier."""
    try:
        import os
        import httpx
        webhook = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")
        if not webhook:
            return
        # Severity dispatch — CRITICAL now fires at 90% (was 95%) so Nick has
        # ~2K requests / ~10 min headroom instead of 1K / ~5 min.
        if threshold_pct >= 90:
            emoji = "\U0001F6A8"  # rotating light
            severity = "CRITICAL"
            body = "only ~2K requests remaining — throttle now or expect 429s within ~10 min of normal usage."
        elif threshold_pct >= 85:
            emoji = "\U000026A0\uFE0F"  # warning
            severity = "WARNING"
            body = "only ~3K requests remaining — reduce non-critical calls."
        elif threshold_pct >= 70:
            emoji = "\U0001F4CA"  # bar chart
            severity = "ELEVATED"
            body = "usage is heavier than typical — monitor."
        else:
            emoji = "\U0001F4CB"  # clipboard
            severity = "INFO"
            body = "informational, on track for normal day."
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(webhook, json={
                "content": f"{emoji} **UW API Budget [{severity}]** — {count}/{DAILY_BUDGET} requests "
                           f"({threshold_pct}% crossed) — {body}"
            })
    except Exception:
        pass
