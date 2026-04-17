"""
Signals API — Brief C v1.1

Nick's action tracking endpoint.
PATCH /api/signals/{id}/action — records Accept/Pass/Watch with price snapshot.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database.postgres_client import get_postgres_client
from utils.pivot_auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_ACTIONS = {"ACCEPTED", "PASSED", "WATCHING"}


class NickAction(BaseModel):
    action: str  # ACCEPTED | PASSED | WATCHING


async def _fetch_price(ticker: str) -> Optional[float]:
    """Fetch current last price via yfinance (sync → thread)."""
    def _sync():
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).fast_info
            return float(info.last_price) if info.last_price else None
        except Exception:
            return None

    return await asyncio.to_thread(_sync)


@router.patch("/signals/{signal_id}/action")
async def record_nick_action(
    signal_id: str,
    body: NickAction,
    _=Depends(require_api_key),
):
    """
    Record Nick's Accept/Pass/Watch decision on a signal.

    Writes to enrichment_data.nick_decision with current price snapshot.
    Sets user_action so the outcome resolver knows what to track.

    Called by the dashboard when Nick taps Accept/Pass/Watch on a trade idea.
    """
    action = body.action.upper().strip()
    if action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action must be one of: {', '.join(sorted(VALID_ACTIONS))}",
        )

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT signal_id, ticker, user_action FROM signals WHERE signal_id = $1",
            signal_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")

        ticker = row["ticker"]

    # Fetch current price (non-blocking — don't hold the DB connection)
    price_at_decision = await _fetch_price(ticker) if ticker else None

    nick_decision = {
        "action": action,
        "price_at_decision": price_at_decision,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }

    # Map action to user_action column value (consistent with existing convention)
    user_action_map = {
        "ACCEPTED": "SELECTED",
        "PASSED": "DISMISSED",
        "WATCHING": "WATCHING",
    }
    user_action = user_action_map[action]

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE signals
            SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb)
                                  || jsonb_build_object('nick_decision', $1::jsonb),
                user_action = $2
            WHERE signal_id = $3
            """,
            json.dumps(nick_decision),
            user_action,
            signal_id,
        )

    logger.info(
        "Nick action recorded: %s → %s (price: %s)", signal_id, action, price_at_decision
    )
    return {
        "signal_id": signal_id,
        "action": action,
        "user_action": user_action,
        "price_at_decision": price_at_decision,
    }
