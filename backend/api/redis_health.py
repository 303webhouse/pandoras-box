"""
Redis Health Endpoint
Exposes last-known Redis health without issuing new Redis commands.
"""

from fastapi import APIRouter

from database.redis_client import get_redis_status

router = APIRouter()


@router.get("/redis/health")
async def redis_health():
    return get_redis_status()
