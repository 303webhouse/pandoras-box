"""
Accept Flow API — Phase 4E

Two-step accept:
  1. POST /api/accept/{signal_id} — create pending trade from signal
  2. POST /api/accept/{pending_id}/fill — fill pending trade → create position

Also:
  GET /api/pending-trades — list pending trades
  POST /api/pending-trades/expire — auto-expire stale pending trades
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database.postgres_client import (
    get_postgres_client,
    serialize_db_row,
    create_pending_trade,
    get_pending_trades,
    fill_pending_trade,
    expire_pending_trades,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Request Models ---

class OptionLegInput(BaseModel):
    action: str  # BUY or SELL
    option_type: str  # CALL or PUT
    strike: float
    expiration: str  # YYYY-MM-DD
    quantity: int = 1
    premium: float = 0.0


class AcceptAsStocksRequest(BaseModel):
    planned_entry: Optional[float] = None  # Override signal entry_price
    planned_stop: Optional[float] = None  # Override signal stop_loss
    planned_target: Optional[float] = None  # Override signal target_1
    planned_quantity: Optional[float] = None
    notes: Optional[str] = None


class AcceptAsOptionsRequest(BaseModel):
    options_structure: str  # LONG_CALL, BULL_CALL_SPREAD, etc.
    options_legs: List[OptionLegInput]
    options_net_premium: Optional[float] = None
    options_max_loss: Optional[float] = None
    options_expiry: Optional[str] = None  # YYYY-MM-DD
    notes: Optional[str] = None


class FillStocksRequest(BaseModel):
    actual_entry_price: float
    quantity: float
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    notes: Optional[str] = None


class FillOptionsRequest(BaseModel):
    underlying: str
    strategy_type: str
    direction: str  # BULLISH, BEARISH
    legs: List[OptionLegInput]
    net_premium: float
    contracts: int = 1
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    breakeven: Optional[List[float]] = None
    thesis: Optional[str] = None
    notes: Optional[str] = None


# --- Step 1: Accept ---

@router.post("/accept/{signal_id}/stocks")
async def accept_as_stocks(signal_id: str, body: AcceptAsStocksRequest):
    """
    Accept a trade idea as a stocks trade. Creates a pending trade
    and transitions signal to ACCEPTED_STOCKS.

    Nick can override entry/stop/target from signal defaults.
    Pending trade expires after 5 calendar days if not filled.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        signal = await conn.fetchrow("SELECT * FROM signals WHERE signal_id = $1", signal_id)

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal = dict(signal)
    current_status = signal.get("status") or "ACTIVE"
    if current_status not in ("ACTIVE", "COMMITTEE_REVIEW"):
        raise HTTPException(status_code=409, detail=f"Signal in {current_status}, cannot accept")

    # Build pending trade params (override from signal defaults)
    params = {
        "planned_entry": body.planned_entry or signal.get("entry_price"),
        "planned_stop": body.planned_stop or signal.get("stop_loss"),
        "planned_target": body.planned_target or signal.get("target_1"),
        "planned_quantity": body.planned_quantity,
        "notes": body.notes,
    }

    pending_id = await create_pending_trade(signal_id, "STOCKS", params)

    # Transition signal status
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE signals
            SET status = 'ACCEPTED_STOCKS', user_action = 'SELECTED',
                selected_at = NOW(), decided_at = NOW(),
                decision_source = 'dashboard', pending_trade_id = $2
            WHERE signal_id = $1
            """,
            signal_id,
            str(pending_id),
        )

    logger.info(f"✅ Signal {signal_id} accepted as STOCKS → pending_trade {pending_id}")

    return {
        "signal_id": signal_id,
        "pending_trade_id": pending_id,
        "trade_type": "STOCKS",
        "planned_entry": params["planned_entry"],
        "planned_stop": params["planned_stop"],
        "planned_target": params["planned_target"],
        "status": "PENDING",
    }


@router.post("/accept/{signal_id}/options")
async def accept_as_options(signal_id: str, body: AcceptAsOptionsRequest):
    """
    Accept a trade idea as an options trade. Creates a pending trade
    and transitions signal to ACCEPTED_OPTIONS.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        signal = await conn.fetchrow("SELECT * FROM signals WHERE signal_id = $1", signal_id)

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal = dict(signal)
    current_status = signal.get("status") or "ACTIVE"
    if current_status not in ("ACTIVE", "COMMITTEE_REVIEW"):
        raise HTTPException(status_code=409, detail=f"Signal in {current_status}, cannot accept")

    params = {
        "options_structure": body.options_structure,
        "options_legs": [leg.dict() for leg in body.options_legs],
        "options_net_premium": body.options_net_premium,
        "options_max_loss": body.options_max_loss,
        "options_expiry": body.options_expiry,
        "notes": body.notes,
    }

    pending_id = await create_pending_trade(signal_id, "OPTIONS", params)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE signals
            SET status = 'ACCEPTED_OPTIONS', user_action = 'SELECTED',
                selected_at = NOW(), decided_at = NOW(),
                decision_source = 'dashboard', pending_trade_id = $2
            WHERE signal_id = $1
            """,
            signal_id,
            str(pending_id),
        )

    logger.info(f"✅ Signal {signal_id} accepted as OPTIONS → pending_trade {pending_id}")

    return {
        "signal_id": signal_id,
        "pending_trade_id": pending_id,
        "trade_type": "OPTIONS",
        "options_structure": body.options_structure,
        "status": "PENDING",
    }


# --- Step 2: Fill ---

@router.post("/accept/{pending_id}/fill-stocks")
async def fill_stocks(pending_id: int, body: FillStocksRequest):
    """
    Fill a pending stocks trade — creates an actual position via
    the existing accept_signal() flow in positions.py.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        pending = await conn.fetchrow(
            "SELECT * FROM pending_trades WHERE id = $1", pending_id
        )

    if not pending:
        raise HTTPException(status_code=404, detail="Pending trade not found")

    pending = dict(pending)
    if pending["status"] != "PENDING":
        raise HTTPException(status_code=409, detail=f"Pending trade is {pending['status']}")

    signal_id = pending["signal_id"]

    # Call existing accept_signal() flow
    from api.positions import accept_signal, AcceptSignalRequest

    accept_req = AcceptSignalRequest(
        signal_id=signal_id,
        actual_entry_price=body.actual_entry_price,
        quantity=body.quantity,
        stop_loss=body.stop_loss or pending.get("planned_stop"),
        target_1=body.target_1 or pending.get("planned_target"),
        notes=body.notes,
    )

    result = await accept_signal(signal_id, accept_req)
    position_id = result.get("position_id")

    # Mark pending trade as filled
    await fill_pending_trade(pending_id, position_id)

    logger.info(f"🎯 Pending trade {pending_id} filled → position {position_id}")

    return {
        "pending_trade_id": pending_id,
        "position_id": position_id,
        "status": "FILLED",
        "signal_id": signal_id,
    }


@router.post("/accept/{pending_id}/fill-options")
async def fill_options(pending_id: int, body: FillOptionsRequest):
    """
    Fill a pending options trade — creates an actual options position via
    the existing accept_signal_as_options() flow in positions.py.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        pending = await conn.fetchrow(
            "SELECT * FROM pending_trades WHERE id = $1", pending_id
        )

    if not pending:
        raise HTTPException(status_code=404, detail="Pending trade not found")

    pending = dict(pending)
    if pending["status"] != "PENDING":
        raise HTTPException(status_code=409, detail=f"Pending trade is {pending['status']}")

    signal_id = pending["signal_id"]

    # Call existing accept_signal_as_options() flow
    from api.positions import (
        accept_signal_as_options,
        AcceptSignalAsOptionsRequest,
        OptionLegRequest,
    )

    option_legs = [
        OptionLegRequest(
            action=leg.action,
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
            quantity=leg.quantity,
            premium=leg.premium,
        )
        for leg in body.legs
    ]

    options_req = AcceptSignalAsOptionsRequest(
        signal_id=signal_id,
        underlying=body.underlying,
        strategy_type=body.strategy_type,
        direction=body.direction,
        legs=option_legs,
        net_premium=body.net_premium,
        contracts=body.contracts,
        max_profit=body.max_profit,
        max_loss=body.max_loss,
        breakeven=body.breakeven,
        thesis=body.thesis,
        notes=body.notes,
    )

    result = await accept_signal_as_options(signal_id, options_req)
    position_id = result.get("position_id")

    await fill_pending_trade(pending_id, position_id)

    logger.info(f"🎯 Pending options trade {pending_id} filled → position {position_id}")

    return {
        "pending_trade_id": pending_id,
        "position_id": position_id,
        "status": "FILLED",
        "signal_id": signal_id,
    }


# --- List + Expire ---

@router.get("/pending-trades")
async def list_pending_trades(
    status: str = Query(default="PENDING"),
):
    """List pending trades, with signal data joined."""
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pt.*, s.ticker, s.direction, s.strategy, s.score, s.score_v2,
                   s.enrichment_data, s.bias_alignment
            FROM pending_trades pt
            JOIN signals s ON pt.signal_id = s.signal_id
            WHERE pt.status = $1
            ORDER BY pt.created_at DESC
            """,
            status.upper(),
        )

    return {
        "pending_trades": [serialize_db_row(dict(row)) for row in rows],
        "count": len(rows),
    }


@router.post("/pending-trades/expire")
async def expire_stale_pending_trades():
    """Auto-expire pending trades older than 5 days. Called by nightly cron."""
    count = await expire_pending_trades()

    if count > 0:
        logger.info(f"🕐 Expired {count} stale pending trades")

    # Also update the parent signals back to EXPIRED if they were still ACCEPTED_*
    if count > 0:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE signals s
                SET status = 'EXPIRED'
                FROM pending_trades pt
                WHERE pt.signal_id = s.signal_id
                AND pt.status = 'EXPIRED'
                AND s.status IN ('ACCEPTED_STOCKS', 'ACCEPTED_OPTIONS')
            """)

    return {"expired_count": count}
