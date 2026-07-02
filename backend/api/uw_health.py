"""
UW API Health Check Endpoint
GET /api/uw/health — returns circuit breaker status, daily request count, cache hit rate.
GET /api/uw/health/by_caller — Phase A.4a — per-caller request + 429 breakdown.
"""

from datetime import date

from fastapi import APIRouter

router = APIRouter(prefix="/uw", tags=["uw-health"])


@router.get("/health")
async def uw_health():
    """Return UW API health status."""
    from integrations.uw_api import get_health
    health = await get_health()

    # Triton Step-0 B4: surface the shadow feed's liveness so THIS feed can't
    # silently die for days like the MP feed did (191->23 decay went unseen).
    # events_today + last_event_age_seconds; fail-safe (table may not exist pre-deploy).
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        if pool:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS events_today,
                           EXTRACT(EPOCH FROM (NOW() - MAX(fired_at)))::int   AS last_event_age_seconds
                    FROM triton_flow_shadow
                    """
                )
            health["triton_shadow"] = {
                "events_today": int(row["events_today"] or 0),
                "last_event_age_seconds": row["last_event_age_seconds"],
            }
    except Exception as exc:
        health["triton_shadow"] = {"error": type(exc).__name__}

    # F2: flow-poller Redis-write liveness. The 7/1 outage (Redis writes failing
    # while Postgres stayed healthy) was invisible for a full RTH because the dark
    # radar was the only symptom. Reads survive a write-outage, so this age (from
    # the poller's uw:flow:_meta:last_write stamp) surfaces it same-day. Fail-safe.
    try:
        from datetime import datetime, timezone
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        raw = await redis.get("uw:flow:_meta:last_write") if redis else None
        if raw:
            ts = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
            age = int((datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds())
            # Poller cadence is 5 min; >15 min (3 missed cycles) is an ops concern.
            health["flow_redis"] = {
                "last_successful_write_age_seconds": age,
                "status": "ok" if age <= 900 else "stale",
            }
        else:
            health["flow_redis"] = {"last_successful_write_age_seconds": None, "status": "unknown"}
    except Exception as exc:
        health["flow_redis"] = {"error": type(exc).__name__}

    return health


@router.get("/health/by_caller")
async def uw_health_by_caller():
    """Phase A.4a 2026-05-27 — per-caller daily attribution.

    Reads the HSET counters written by `increment_daily_counter(caller)`
    and `increment_429_counter(caller)`. Use this to identify which UW
    code paths are driving daily load. Tags are endpoint-grain (snapshot,
    flow_per_expiry, ohlc, etc.). Counters reset at midnight ET (key TTL 48h).
    """
    from integrations.uw_api_cache import get_counts_by_caller, get_daily_count
    counts = await get_counts_by_caller()
    total = await get_daily_count()
    return {
        "date": date.today().isoformat(),
        "total": total,
        **counts,
    }


@router.get("/governor")
async def uw_governor_status():
    """B2/B4 — UW budget governor state: mode (observe|enforce), total quota
    allocation vs the 20k cap, and per-caller usage% (sorted hottest-first).
    Watch this during the OBSERVE rollout to confirm the quota table doesn't
    starve foreground before flipping to enforce. AEGIS-clean (no key/URL)."""
    from integrations.uw_governor import governor_status
    return {
        "date": date.today().isoformat(),
        **(await governor_status()),
    }
