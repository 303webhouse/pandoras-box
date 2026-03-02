"""
Trade Ideas API — Phase 4 Signal Lifecycle Endpoints

Provides the API surface for the Trade Ideas feed:
- GET /api/trade-ideas — active signal feed (replaces get_active_trade_ideas)
- GET /api/trade-ideas/{signal_id} — single signal detail
- PATCH /api/trade-ideas/{signal_id}/status — lifecycle transitions
- POST /api/trade-ideas/{signal_id}/dismiss — dismiss signal
- POST /api/trade-ideas/expire — cron endpoint for auto-expiry
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database.postgres_client import get_postgres_client, serialize_db_row

logger = logging.getLogger(__name__)
router = APIRouter()


class StatusUpdate(BaseModel):
    status: str  # DISMISSED, ACCEPTED_STOCKS, ACCEPTED_OPTIONS, COMMITTEE_REVIEW
    decision_source: Optional[str] = "dashboard"  # dashboard or discord
    reason: Optional[str] = None


@router.get("/trade-ideas")
async def get_trade_ideas_feed(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default="ACTIVE"),
    source: Optional[str] = Query(default=None),
    min_score: Optional[float] = Query(default=None),
):
    """
    Get the Trade Ideas feed — active signals ranked by score.

    This replaces the old get_active_trade_ideas() function with proper
    lifecycle filtering and pagination.
    """
    pool = await get_postgres_client()

    conditions = []
    params = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status.upper())
        idx += 1

    if source:
        conditions.append(f"source = ${idx}")
        params.append(source.lower())
        idx += 1

    if min_score is not None:
        conditions.append(f"COALESCE(score, 0) >= ${idx}")
        params.append(min_score)
        idx += 1

    # Exclude expired signals from ACTIVE feed
    if status and status.upper() == "ACTIVE":
        conditions.append("(expires_at IS NULL OR expires_at > NOW())")

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM signals WHERE {where_clause}", *params
        )

        params.extend([limit, offset])
        rows = await conn.fetch(
            f"""
            SELECT * FROM signals
            WHERE {where_clause}
            ORDER BY COALESCE(score, 0) DESC, created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
        )

    return {
        "signals": [serialize_db_row(dict(row)) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/trade-ideas/{signal_id}")
async def get_trade_idea_detail(signal_id: str):
    """Get full detail for a single signal including enrichment and committee data."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM signals WHERE signal_id = $1", signal_id)

    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")

    return serialize_db_row(dict(row))


@router.patch("/trade-ideas/{signal_id}/status")
async def update_trade_idea_status(signal_id: str, body: StatusUpdate):
    """
    Update signal lifecycle status with optimistic locking.

    Valid transitions:
    - ACTIVE -> DISMISSED, ACCEPTED_STOCKS, ACCEPTED_OPTIONS, COMMITTEE_REVIEW
    - COMMITTEE_REVIEW -> ACTIVE (re-evaluate), ACCEPTED_STOCKS, ACCEPTED_OPTIONS, DISMISSED

    Rejects transitions from terminal states (already DISMISSED/ACCEPTED/EXPIRED).
    """
    pool = await get_postgres_client()
    new_status = body.status.upper()

    terminal_states = {"DISMISSED", "ACCEPTED_STOCKS", "ACCEPTED_OPTIONS", "EXPIRED"}

    async with pool.acquire() as conn:
        # Optimistic lock: check current status
        current = await conn.fetchrow(
            "SELECT status, user_action FROM signals WHERE signal_id = $1", signal_id
        )
        if not current:
            raise HTTPException(status_code=404, detail="Signal not found")

        current_status = current["status"] or "ACTIVE"
        if current_status in terminal_states:
            raise HTTPException(
                status_code=409,
                detail=f"Signal already in terminal state: {current_status}",
            )

        # Map new status to legacy user_action for backward compatibility
        user_action_map = {
            "DISMISSED": "DISMISSED",
            "ACCEPTED_STOCKS": "SELECTED",
            "ACCEPTED_OPTIONS": "SELECTED",
        }
        user_action = user_action_map.get(new_status)

        # Build update
        update_fields = [
            "status = $2",
            "decided_at = $3",
            "decision_source = $4",
        ]
        update_params = [signal_id, new_status, datetime.utcnow(), body.decision_source]
        param_idx = 5

        if user_action:
            update_fields.append(f"user_action = ${param_idx}")
            update_params.append(user_action)
            param_idx += 1

            if user_action == "DISMISSED":
                update_fields.append(f"dismissed_at = ${param_idx}")
                update_params.append(datetime.utcnow())
                param_idx += 1
            elif user_action == "SELECTED":
                update_fields.append(f"selected_at = ${param_idx}")
                update_params.append(datetime.utcnow())
                param_idx += 1

        if body.reason:
            update_fields.append(f"notes = ${param_idx}")
            update_params.append(body.reason)
            param_idx += 1

        await conn.execute(
            f"UPDATE signals SET {', '.join(update_fields)} WHERE signal_id = $1",
            *update_params,
        )

    logger.info(f"📋 Signal {signal_id}: {current_status} → {new_status} (via {body.decision_source})")
    return {"signal_id": signal_id, "previous_status": current_status, "new_status": new_status}


@router.post("/trade-ideas/expire")
async def expire_stale_signals():
    """
    Auto-expire signals past their expires_at timestamp.
    Called by cron or scheduler. Safe to call frequently (idempotent).
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE signals
            SET status = 'EXPIRED', user_action = 'DISMISSED', dismissed_at = NOW()
            WHERE status = 'ACTIVE'
            AND expires_at IS NOT NULL
            AND expires_at < NOW()
        """)

    # Parse count from result string like "UPDATE 5"
    count = 0
    if result:
        parts = result.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            count = int(parts[-1])

    if count > 0:
        logger.info(f"🕐 Expired {count} stale signals")

    return {"expired_count": count}


@router.get("/enrichment/status")
async def get_enrichment_status():
    """
    Check universe enrichment cache health.
    Returns cache coverage and staleness for monitoring.
    """
    import json as _json
    from database.redis_client import get_redis_client
    from enrichment.universe_cache import UNIVERSE_CACHE_PREFIX, get_watchlist_tickers

    client = await get_redis_client()
    tickers = await get_watchlist_tickers()

    cached = 0
    stale = 0
    samples = {}

    for ticker in tickers[:20]:  # Sample first 20
        try:
            raw = await client.get(f"{UNIVERSE_CACHE_PREFIX}{ticker}")
            if raw:
                data = _json.loads(raw)
                cached += 1
                refreshed = data.get("refreshed_at", "")
                has_atr = data.get("atr_14") is not None
                has_vol = data.get("avg_volume_20d") is not None
                has_iv = data.get("iv_rank") is not None
                samples[ticker] = {
                    "refreshed_at": refreshed,
                    "atr": has_atr,
                    "volume": has_vol,
                    "iv_rank": has_iv,
                }

                # Check staleness (> 3 hours old)
                if refreshed:
                    try:
                        age = datetime.utcnow() - datetime.fromisoformat(refreshed)
                        if age.total_seconds() > 10800:
                            stale += 1
                    except (ValueError, TypeError):
                        pass
            else:
                samples[ticker] = {"status": "not_cached"}
        except Exception:
            samples[ticker] = {"status": "error"}

    return {
        "total_watchlist": len(tickers),
        "cached": cached,
        "stale": stale,
        "coverage_pct": round((cached / max(len(tickers[:20]), 1)) * 100, 1),
        "samples": samples,
    }
