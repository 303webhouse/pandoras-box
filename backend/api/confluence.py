"""
Confluence API — Query active confluence signals.
"""

from fastapi import APIRouter
from datetime import datetime, timedelta
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/confluence/active")
async def get_active_confluence():
    """Return currently active CONFIRMED/CONVICTION signals."""
    from database.postgres_client import get_postgres_client

    cutoff = datetime.utcnow() - timedelta(hours=4)

    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # Check if confluence columns exist
            col_check = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'signals' AND column_name = 'confluence_tier'
                )
            """)
            if not col_check:
                return {"confluence_signals": [], "count": 0, "message": "Confluence columns not yet created"}

            rows = await conn.fetch("""
                SELECT signal_id, ticker, direction, strategy, signal_type,
                       score, confluence_tier, confluence_count, timestamp
                FROM signals
                WHERE confluence_tier IN ('CONFIRMED', 'CONVICTION')
                  AND timestamp >= $1
                ORDER BY 
                    CASE confluence_tier WHEN 'CONVICTION' THEN 1 WHEN 'CONFIRMED' THEN 2 END,
                    confluence_count DESC
            """, cutoff)

        return {
            "confluence_signals": [dict(r) for r in rows],
            "count": len(rows),
        }
    except Exception as e:
        logger.error("Confluence API error: %s", e)
        return {"confluence_signals": [], "count": 0, "error": str(e)}


@router.get("/confluence/status")
async def get_confluence_status():
    """Return confluence engine status and recent stats."""
    from database.postgres_client import get_postgres_client

    cutoff = datetime.utcnow() - timedelta(hours=8)

    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            col_check = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'signals' AND column_name = 'confluence_tier'
                )
            """)
            if not col_check:
                return {"status": "not_initialized", "message": "Confluence columns not yet created"}

            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE confluence_tier = 'CONFIRMED') as confirmed,
                    COUNT(*) FILTER (WHERE confluence_tier = 'CONVICTION') as conviction,
                    COUNT(*) FILTER (WHERE confluence_tier = 'STANDALONE' OR confluence_tier IS NULL) as standalone,
                    MAX(confluence_updated_at) as last_scan
                FROM signals
                WHERE timestamp >= $1
            """, cutoff)

        return {
            "status": "active",
            "last_8h": dict(stats) if stats else {},
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/confluence/scan")
async def trigger_confluence_scan():
    """Manually trigger a confluence scan (for testing)."""
    try:
        from confluence.engine import run_confluence_scan
        result = await run_confluence_scan()
        return {"status": "complete", **result}
    except Exception as e:
        logger.error("Manual confluence scan failed: %s", e)
        return {"status": "error", "error": str(e)}
