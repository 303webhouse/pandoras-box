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
    return await get_health()


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
