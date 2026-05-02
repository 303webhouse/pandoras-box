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
    "flow": 30,           # Near-real-time polling
    "gex": 300,           # 5 min
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


async def increment_daily_counter() -> int:
    """Increment daily request counter. Returns current count."""
    redis = await _get_redis()
    if not redis:
        return 0
    try:
        from datetime import date
        day_key = f"uw:daily_requests:{date.today().isoformat()}"
        count = await redis.incr(day_key)
        # Set expiry on first increment (48h to survive timezone edge)
        if count == 1:
            await redis.expire(day_key, 172800)

        # Budget alerts at multiple thresholds (50/70/85/95%)
        # Use Redis flag per threshold per day to ensure each fires only once.
        from datetime import date as _date
        today_str = _date.today().isoformat()
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
