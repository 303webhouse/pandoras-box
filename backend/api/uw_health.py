"""
UW API Health Check Endpoint
GET /api/uw/health — returns circuit breaker status, daily request count, cache hit rate.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/uw", tags=["uw-health"])


@router.get("/health")
async def uw_health():
    """Return UW API health status."""
    from integrations.uw_api import get_health
    return await get_health()
