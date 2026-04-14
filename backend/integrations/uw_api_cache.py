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
    "quote": 15,          # 15s
    "info": 15,           # 15s
    "option_contracts": 300,  # 5 min
    "iv_rank": 300,       # 5 min
    "earnings": 3600,     # 1 hr
    "calendar": 3600,     # 1 hr
    "short_interest": 3600,  # 1 hr
}

DAILY_BUDGET = 20000     # UW Basic plan limit
BUDGET_ALERT_PCT = 0.50  # Alert at 50%

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

        # Budget alert at threshold
        alert_threshold = int(DAILY_BUDGET * BUDGET_ALERT_PCT)
        if count == alert_threshold:
            logger.warning("UW API daily budget at %d%% (%d/%d requests)",
                           int(BUDGET_ALERT_PCT * 100), count, DAILY_BUDGET)
            await _post_budget_alert(count)

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


async def _post_budget_alert(count: int) -> None:
    """Post budget alert to Discord webhook."""
    try:
        import os
        import httpx
        webhook = os.getenv("DISCORD_WEBHOOK_SIGNALS", "")
        if not webhook:
            return
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(webhook, json={
                "content": f"**UW API Budget Alert:** {count}/{DAILY_BUDGET} requests "
                           f"({int(count/DAILY_BUDGET*100)}%) — monitor usage"
            })
    except Exception:
        pass
