"""
Committee Bridge API — Phase 4D

Endpoints for VPS committee to poll and submit results:
- GET /api/committee/queue — signals awaiting committee review
- POST /api/committee/results — submit committee analysis
- GET /api/committee/history — recent committee-reviewed signals
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.pivot_auth import require_api_key
from pydantic import BaseModel

from database.postgres_client import get_postgres_client, serialize_db_row

logger = logging.getLogger(__name__)
router = APIRouter()


class CommitteeResult(BaseModel):
    """Result payload from VPS committee run."""
    signal_id: str
    committee_run_id: str  # Unique ID for this committee run
    action: str  # TAKE, PASS, WATCHING
    conviction: str  # HIGH, MEDIUM, LOW
    toro_analysis: Optional[str] = None
    ursa_analysis: Optional[str] = None
    risk_params: Optional[dict] = None  # entry, stop, target, size
    pivot_synthesis: Optional[str] = None
    cost_usd: Optional[float] = None  # LLM cost for this run
    run_duration_ms: Optional[float] = None


@router.get("/committee/queue")
async def get_committee_queue(
    limit: int = Query(default=10, le=20),
):
    """
    Get signals explicitly requested for committee review via dashboard.
    VPS polls this every 3 minutes during market hours.
    Only returns COMMITTEE_REVIEW (manual Analyze clicks), NOT PENDING_REVIEW
    (auto-flagged by pipeline). This ensures committee only runs when Nick asks.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id, ticker, direction, strategy, entry_price,
                   stop_loss, target_1, target_2, score, score_v2,
                   bias_alignment, enrichment_data, triggering_factors,
                   score_v2_factors, timeframe, asset_class, source,
                   created_at, committee_requested_at
            FROM signals
            WHERE status = 'COMMITTEE_REVIEW'
            ORDER BY committee_requested_at ASC NULLS LAST, created_at ASC
            LIMIT $1
            """,
            limit,
        )

    return {
        "queue": [serialize_db_row(dict(row)) for row in rows],
        "count": len(rows),
    }


@router.post("/committee/results")
async def submit_committee_results(body: CommitteeResult, _=Depends(require_api_key)):
    """
    Submit committee analysis results from VPS.
    Stores in signals.committee_data and transitions signal back to ACTIVE.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        # Verify signal exists and is in COMMITTEE_REVIEW
        current = await conn.fetchrow(
            "SELECT status FROM signals WHERE signal_id = $1", body.signal_id
        )

        if not current:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Allow results even if signal moved past COMMITTEE_REVIEW
        # (e.g., user accepted while committee was running)
        if current["status"] not in ("PENDING_REVIEW", "COMMITTEE_REVIEW", "ACTIVE"):
            logger.warning(
                f"Committee results for {body.signal_id} arrived but signal is "
                f"{current['status']} — storing results anyway"
            )

        # Build committee_data JSON
        committee_data = {
            "committee_run_id": body.committee_run_id,
            "action": body.action,
            "conviction": body.conviction,
            "toro": body.toro_analysis,
            "ursa": body.ursa_analysis,
            "risk": body.risk_params,
            "pivot": body.pivot_synthesis,
            "cost_usd": body.cost_usd,
            "run_duration_ms": body.run_duration_ms,
            "completed_at": datetime.utcnow().isoformat(),
        }

        # Store results and transition back to ACTIVE
        await conn.execute(
            """
            UPDATE signals
            SET committee_data = $2,
                committee_run_id = $3,
                committee_completed_at = NOW(),
                status = CASE
                    WHEN status IN ('PENDING_REVIEW', 'COMMITTEE_REVIEW') THEN 'ACTIVE'
                    ELSE status
                END
            WHERE signal_id = $1
            """,
            body.signal_id,
            json.dumps(committee_data),
            body.committee_run_id,
        )

    logger.info(
        f"🧠 Committee result stored: {body.signal_id} → "
        f"{body.action} ({body.conviction})"
    )

    return {
        "signal_id": body.signal_id,
        "committee_run_id": body.committee_run_id,
        "action": body.action,
        "conviction": body.conviction,
        "status": "stored",
    }


@router.get("/committee/history")
async def get_committee_history(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
):
    """Recent signals that have been through committee review."""
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id, ticker, direction, strategy, score_v2,
                   committee_data, committee_run_id,
                   committee_requested_at, committee_completed_at,
                   status, user_action, created_at
            FROM signals
            WHERE committee_run_id IS NOT NULL
            ORDER BY committee_completed_at DESC NULLS LAST
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    return {
        "signals": [serialize_db_row(dict(row)) for row in rows],
        "count": len(rows),
    }
