"""
Positions API
Manages selected trades and open positions with comprehensive logging for backtesting.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import json

from database.redis_client import get_signal, delete_signal, cache_signal
from database.postgres_client import (
    update_signal_action,
    create_position,
    get_open_positions,
    get_active_trade_ideas,
    get_active_trade_ideas_paginated,
    get_archived_signals,
    get_signal_by_id,
    update_signal_outcome,
    close_position_in_db,
    get_position_by_id,
    get_backtest_statistics,
    update_position_quantity,
    delete_open_position
)
from websocket.broadcaster import manager
from utils.bias_snapshot import get_bias_snapshot

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory position store (synced with database on startup)
_open_positions = []
_closed_trades = []
_position_counter = 1


def _normalize_signal_payloads(signals: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Keep only dict payloads (skip numeric counters and other primitive values)."""
    if not signals:
        return []

    return [sig for sig in signals if isinstance(sig, dict)]


# =========================================================================
# REQUEST MODELS
# =========================================================================

class SignalAction(BaseModel):
    """User action on a signal"""
    signal_id: str
    action: str  # "DISMISS" or "SELECT"

class AcceptSignalRequest(BaseModel):
    """Request to accept a signal and open a position"""
    signal_id: str
    actual_entry_price: float
    quantity: float
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    notes: Optional[str] = None

class OptionLegRequest(BaseModel):
    """Single leg of an options position"""
    action: str  # "BUY" or "SELL"
    option_type: str  # "CALL" or "PUT"
    strike: float
    expiration: str  # YYYY-MM-DD
    quantity: int = 1
    premium: float = 0.0

class AcceptSignalAsOptionsRequest(BaseModel):
    """Request to accept a signal and open an options position"""
    signal_id: str
    underlying: str
    strategy_type: str  # e.g. "LONG_CALL", "BULL_CALL_SPREAD"
    direction: str  # "BULLISH", "BEARISH", "NEUTRAL", "VOLATILITY"
    legs: List[OptionLegRequest]
    net_premium: float  # Positive = credit, Negative = debit
    contracts: int = 1
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    breakeven: Optional[List[float]] = None
    thesis: Optional[str] = None
    notes: Optional[str] = None

class DismissSignalRequest(BaseModel):
    """Request to dismiss a signal with reason"""
    signal_id: str
    reason: Optional[str] = None  # "NOT_ALIGNED", "MISSED_ENTRY", "TECHNICAL_CONCERN", "OTHER"
    notes: Optional[str] = None

class ClosePositionRequest(BaseModel):
    """Request to close a position with outcome logging"""
    position_id: int
    exit_price: float
    quantity_closed: Optional[float] = None  # If None, close entire position
    trade_outcome: str  # "WIN", "LOSS", "BREAKEVEN"
    loss_reason: Optional[str] = None  # "SETUP_FAILED", "EXECUTION_ERROR", "MARKET_CONDITIONS"
    actual_stop_hit: Optional[bool] = False
    notes: Optional[str] = None

class PositionUpdate(BaseModel):
    """Update an existing position"""
    position_id: int
    exit_price: Optional[float] = None
    status: Optional[str] = None

class OpenPositionRequest(BaseModel):
    """Request to open a new position (legacy)"""
    signal_id: str
    ticker: str
    direction: str
    entry_price: float
    quantity: float
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    strategy: Optional[str] = None
    asset_class: Optional[str] = "EQUITY"
    signal_type: Optional[str] = None
    bias_level: Optional[str] = None

class ManualPositionRequest(BaseModel):
    """Request to create a manual position (no signal required)"""
    ticker: str
    direction: str
    entry_price: float
    quantity: float
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    strategy: Optional[str] = "Manual Entry"
    asset_class: Optional[str] = "EQUITY"
    signal_type: Optional[str] = "MANUAL"
    notes: Optional[str] = None

class ArchiveFilters(BaseModel):
    """Filters for archived signals query"""
    ticker: Optional[str] = None
    strategy: Optional[str] = None
    user_action: Optional[str] = None  # "DISMISSED", "SELECTED"
    trade_outcome: Optional[str] = None  # "WIN", "LOSS", "BREAKEVEN"
    bias_alignment: Optional[str] = None  # "ALIGNED", "COUNTER_BIAS"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = 100
    offset: int = 0


async def _upsert_watchlist_for_position(ticker: str, position_id: int) -> None:
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return

    try:
        from database.postgres_client import get_postgres_client
        from config.sectors import detect_sector

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, source, priority FROM watchlist_tickers WHERE symbol = $1",
                ticker,
            )
            if existing:
                await conn.execute(
                    """
                    UPDATE watchlist_tickers
                    SET priority = 'high',
                        position_id = $1,
                        muted = false
                    WHERE symbol = $2
                    """,
                    position_id,
                    ticker,
                )
            else:
                sector = detect_sector(ticker)
                await conn.execute(
                    """
                    INSERT INTO watchlist_tickers
                    (symbol, sector, source, priority, position_id)
                    VALUES ($1, $2, 'position', 'high', $3)
                    """,
                    ticker,
                    sector,
                    position_id,
                )
        logger.info(f"📋 Auto-added {ticker} to watchlist (active position)")
    except Exception as e:
        logger.warning(f"Failed to auto-add position ticker to watchlist: {e}")


async def _update_watchlist_on_position_close(ticker: str, position_id: int) -> None:
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return

    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            other_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM positions
                WHERE ticker = $1
                  AND status = 'OPEN'
                  AND id != $2
                """,
                ticker,
                position_id,
            )

            if other_count and other_count > 0:
                logger.info(
                    f"📋 {ticker} still has {other_count} open position(s) — keeping high priority"
                )
                return

            ticker_row = await conn.fetchrow(
                "SELECT id, source FROM watchlist_tickers WHERE symbol = $1",
                ticker,
            )
            if not ticker_row:
                return

            if ticker_row["source"] == "position":
                await conn.execute(
                    "DELETE FROM watchlist_tickers WHERE symbol = $1",
                    ticker,
                )
                logger.info(
                    f"📋 Removed {ticker} from watchlist (position closed, was auto-added)"
                )
            else:
                await conn.execute(
                    """
                    UPDATE watchlist_tickers
                       SET priority = CASE WHEN source = 'scanner' THEN 'low' ELSE 'normal' END,
                           position_id = NULL
                     WHERE symbol = $1
                    """,
                    ticker,
                )
                logger.info(f"📋 {ticker} priority reset (position closed)")
    except Exception as e:
        logger.warning(f"Failed to update watchlist on position close: {e}")

# =========================================================================
# SIGNAL ACCEPT/DISMISS ENDPOINTS WITH FULL LOGGING
# =========================================================================

@router.post("/signals/{signal_id}/accept")
async def accept_signal(signal_id: str, request: AcceptSignalRequest):
    """
    Accept a trade signal and open a position.
    
    Logs comprehensive data for backtesting:
    - Original signal conditions
    - Actual entry price (vs recommended)
    - Triggering factors and bias alignment
    - Timestamp of decision
    """
    global _position_counter
    
    try:
        # Get signal data from Redis or PostgreSQL
        signal_data = await get_signal(signal_id)
        if not signal_data:
            # Try database
            signal_data = await get_signal_by_id(signal_id)
        
        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Update signal as SELECTED in database
        await update_signal_action(signal_id, "SELECTED")
        
        # Log the actual entry price to signal
        await update_signal_outcome(
            signal_id,
            actual_entry_price=request.actual_entry_price,
            notes=request.notes
        )
        
        # Capture bias snapshot for archival at open
        bias_at_open = await get_bias_snapshot()

        # Create position in database with full details
        position_data = {
            "ticker": signal_data.get('ticker'),
            "direction": signal_data.get('direction'),
            "entry_price": signal_data.get('entry_price'),  # Recommended entry
            "actual_entry_price": request.actual_entry_price,  # Actual entry
            "quantity": request.quantity,  # ADD QUANTITY HERE
            "entry_time": datetime.now(),
            "stop_loss": request.stop_loss or signal_data.get('stop_loss'),
            "target_1": request.target_1 or signal_data.get('target_1'),
            "target_2": request.target_2 or signal_data.get('target_2'),
            "strategy": signal_data.get('strategy'),
            "asset_class": signal_data.get('asset_class', 'EQUITY'),
            "signal_type": signal_data.get('signal_type'),
            "bias_level": signal_data.get('bias_alignment'),
            "bias_at_open": bias_at_open,
            "broker": "MANUAL"
        }
        
        db_position_id = await create_position(signal_id, position_data)
        
        # Also add to in-memory store for quick access
        position = {
            "id": db_position_id or _position_counter,
            "signal_id": signal_id,
            "ticker": position_data["ticker"],
            "direction": position_data["direction"],
            "entry_price": request.actual_entry_price,
            "recommended_entry": signal_data.get('entry_price'),
            "quantity": request.quantity,
            "stop_loss": position_data["stop_loss"],
            "target_1": position_data["target_1"],
            "target_2": position_data.get("target_2"),
            "strategy": position_data["strategy"],
            "signal_type": position_data["signal_type"],
            "bias_alignment": signal_data.get('bias_alignment'),
            "score": signal_data.get('score'),
            "triggering_factors": signal_data.get('triggering_factors'),
            "asset_class": position_data["asset_class"],
            "entry_time": datetime.now().isoformat(),
            "status": "OPEN"
        }
        
        _open_positions.append(position)
        if not db_position_id:
            _position_counter += 1
        
        # Remove from active signals cache
        await delete_signal(signal_id)

        await _upsert_watchlist_for_position(position["ticker"], position["id"])
        
        # Broadcast to all devices
        await manager.broadcast_position_update({
            "action": "POSITION_OPENED",
            "signal_id": signal_id,
            "position": position
        })
        
        # Broadcast signal removal from Trade Ideas
        await manager.broadcast({
            "type": "SIGNAL_ACCEPTED",
            "signal_id": signal_id,
            "position_id": position["id"]
        })
        
        logger.info(f"✅ Signal accepted: {position['ticker']} {position['direction']} @ ${request.actual_entry_price}")
        
        return {
            "status": "accepted",
            "signal_id": signal_id,
            "position_id": position["id"],
            "position": position
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/{signal_id}/accept-options")
async def accept_signal_as_options(signal_id: str, request: AcceptSignalAsOptionsRequest):
    """
    Accept a trade signal and open an OPTIONS position instead of equity.
    
    This endpoint:
    1. Marks the signal as SELECTED (same as equity accept)
    2. Creates an options position via the options_positions module
    3. Logs the acceptance with full signal context for backtesting
    """
    try:
        # Get signal data from Redis or PostgreSQL
        signal_data = await get_signal(signal_id)
        if not signal_data:
            signal_data = await get_signal_by_id(signal_id)
        
        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Update signal as SELECTED in database
        await update_signal_action(signal_id, "SELECTED")
        
        # Log the acceptance to signal record (include premium as entry context)
        await update_signal_outcome(
            signal_id,
            notes=request.notes or f"Accepted as OPTIONS: {request.strategy_type} | Premium: {request.net_premium}"
        )
        
        # Capture bias snapshot at time of entry (same as equity path)
        bias_at_open = await get_bias_snapshot()
        
        # Create options position via options_positions module
        from api.options_positions import (
            CreateOptionsPositionRequest,
            OptionLeg,
            create_options_position
        )
        
        # Convert legs to the options module format
        option_legs = [
            OptionLeg(
                action=leg.action,
                option_type=leg.option_type,
                strike=leg.strike,
                expiration=leg.expiration,
                quantity=leg.quantity,
                premium=leg.premium
            )
            for leg in request.legs
        ]
        
        # Build notes with signal context for backtesting traceability
        backtest_notes = (
            f"Signal: {signal_id} | "
            f"Score: {signal_data.get('score')} | "
            f"Bias: {signal_data.get('bias_alignment')} | "
            f"Strategy: {signal_data.get('strategy')} | "
            f"Signal Entry: ${signal_data.get('entry_price')}"
        )
        if request.notes:
            backtest_notes = f"{request.notes} | {backtest_notes}"
        
        options_request = CreateOptionsPositionRequest(
            underlying=request.underlying.upper(),
            strategy_type=request.strategy_type,
            direction=request.direction,
            legs=option_legs,
            net_premium=request.net_premium,
            max_profit=request.max_profit,
            max_loss=request.max_loss,
            breakeven=request.breakeven,
            notes=backtest_notes,
            thesis=request.thesis
        )
        
        options_result = await create_options_position(options_request)
        
        # Attach signal_id and bias snapshot to the options position for backtesting
        options_position_id = options_result.get("position_id")
        if options_position_id:
            from api.options_positions import _options_positions
            if options_position_id in _options_positions:
                _options_positions[options_position_id]["signal_id"] = signal_id
                _options_positions[options_position_id]["bias_at_open"] = bias_at_open
                _options_positions[options_position_id]["signal_score"] = signal_data.get("score")
                _options_positions[options_position_id]["signal_strategy"] = signal_data.get("strategy")
                _options_positions[options_position_id]["signal_entry_price"] = signal_data.get("entry_price")
            
            # Persist signal_id and bias to database
            try:
                from database.postgres_client import link_options_position_to_signal
                await link_options_position_to_signal(
                    options_position_id, signal_id, bias_at_open, signal_data
                )
            except Exception as e:
                logger.warning(f"Could not persist signal link to DB: {e}")
        
        # Remove from active signals cache
        await delete_signal(signal_id)
        
        # Broadcast signal removal from Trade Ideas
        await manager.broadcast({
            "type": "SIGNAL_ACCEPTED",
            "signal_id": signal_id,
            "position_id": options_result.get("position_id"),
            "trade_type": "OPTIONS"
        })
        
        logger.info(
            f"✅ Signal accepted as OPTIONS: {request.underlying} "
            f"{request.strategy_type} {request.direction} - "
            f"Premium: ${request.net_premium} (from signal {signal_id})"
        )
        
        return {
            "status": "accepted",
            "trade_type": "OPTIONS",
            "signal_id": signal_id,
            "position_id": options_result.get("position_id"),
            "position": options_result.get("position")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting signal as options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/{signal_id}/dismiss")
async def dismiss_signal(signal_id: str, request: DismissSignalRequest):
    """
    Dismiss a trade signal with reason logging.
    
    Logs:
    - Reason for dismissal
    - Timestamp
    - Notes for future analysis
    """
    try:
        # Get signal data
        signal_data = await get_signal(signal_id)
        if not signal_data:
            signal_data = await get_signal_by_id(signal_id)
        
        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Update signal as DISMISSED in database
        await update_signal_action(signal_id, "DISMISSED")
        
        # Log dismissal notes
        notes = f"Dismissed: {request.reason or 'No reason provided'}"
        if request.notes:
            notes += f" - {request.notes}"
        
        await update_signal_outcome(signal_id, notes=notes)
        
        # Remove from Redis cache
        await delete_signal(signal_id)

        # Decrement active signal count for this ticker
        try:
            from database.redis_client import get_redis_client

            client = await get_redis_client()
            ticker = (signal_data.get("ticker") or "").upper().strip()
            if client and ticker:
                key = f"signal:active:{ticker}"
                new_val = await client.decr(key)
                if new_val is not None and new_val < 0:
                    await client.set(key, 0)
        except Exception:
            pass
        
        # Broadcast dismissal to all devices
        await manager.broadcast({
            "type": "SIGNAL_DISMISSED",
            "signal_id": signal_id,
            "reason": request.reason
        })
        
        logger.info(f"❌ Signal dismissed: {signal_data.get('ticker', signal_id)} - {request.reason}")
        
        return {
            "status": "dismissed",
            "signal_id": signal_id,
            "reason": request.reason
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dismissing signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signal/action")
async def handle_signal_action(action: SignalAction):
    """
    Legacy endpoint for backwards compatibility.
    Use /signals/{signal_id}/accept or /signals/{signal_id}/dismiss instead.
    """
    if action.action.upper() == "DISMISS":
        return await dismiss_signal(action.signal_id, DismissSignalRequest(signal_id=action.signal_id))
    elif action.action.upper() == "SELECT":
        # For legacy, get signal and use its entry price
        signal_data = await get_signal(action.signal_id)
        if not signal_data:
            signal_data = await get_signal_by_id(action.signal_id)
        
        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        return await accept_signal(
            action.signal_id,
            AcceptSignalRequest(
                signal_id=action.signal_id,
                actual_entry_price=signal_data.get('entry_price', 0),
                quantity=1
            )
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use DISMISS or SELECT.")

@router.post("/positions/open")
async def open_position(request: OpenPositionRequest):
    """
    Open a new position with entry price and quantity.
    Persists to both in-memory cache and PostgreSQL.
    """
    global _position_counter
    
    try:
        # Create position in database first
        bias_at_open = await get_bias_snapshot()

        position_data = {
            "ticker": request.ticker,
            "direction": request.direction,
            "entry_price": request.entry_price,
            "entry_time": datetime.now(),
            "quantity": request.quantity,
            "stop_loss": request.stop_loss,
            "target_1": request.target_1,
            "target_2": None,
            "strategy": request.strategy,
            "asset_class": request.asset_class,
            "signal_type": request.signal_type,
            "bias_level": request.bias_level,
            "bias_at_open": bias_at_open,
            "broker": "MANUAL"
        }
        
        # Save to PostgreSQL
        try:
            db_position_id = await create_position(request.signal_id, position_data)
        except Exception as db_err:
            logger.warning(f"Failed to persist position to DB: {db_err}")
            db_position_id = None
        
        # Also keep in memory for fast access
        position = {
            "id": db_position_id or _position_counter,
            "signal_id": request.signal_id,
            "ticker": request.ticker,
            "direction": request.direction,
            "entry_price": request.entry_price,
            "quantity": request.quantity,
            "stop_loss": request.stop_loss,
            "target_1": request.target_1,
            "strategy": request.strategy,
            "asset_class": request.asset_class,
            "signal_type": request.signal_type,
            "bias_level": request.bias_level,
            "entry_time": datetime.now().isoformat(),
            "status": "OPEN"
        }
        
        _open_positions.append(position)
        if not db_position_id:
            _position_counter += 1
        
        # Remove from active signals
        await delete_signal(request.signal_id)

        await _upsert_watchlist_for_position(position["ticker"], position["id"])
        
        # Broadcast to all devices
        await manager.broadcast_position_update({
            "action": "POSITION_OPENED",
            "position": position
        })
        
        logger.info(f"📈 Position opened: {request.ticker} {request.direction} @ ${request.entry_price} x {request.quantity}")
        
        return {"status": "success", "position_id": position["id"], "position": position}
    
    except Exception as e:
        logger.error(f"Error opening position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/manual")
async def create_manual_position(request: ManualPositionRequest):
    """
    Create a manual position without requiring a signal.
    For trades made outside of the hub's signal system.
    """
    global _position_counter
    
    try:
        # Generate a manual signal ID
        signal_id = f"MANUAL_{request.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        bias_at_open = await get_bias_snapshot()

        # Create position data
        position_data = {
            "ticker": request.ticker,
            "direction": request.direction,
            "entry_price": request.entry_price,
            "quantity": request.quantity,  # ADD QUANTITY HERE
            "entry_time": datetime.now(),
            "stop_loss": request.stop_loss,
            "target_1": request.target_1,
            "target_2": None,
            "strategy": request.strategy or "Manual Entry",
            "asset_class": request.asset_class,
            "signal_type": "MANUAL",
            "notes": request.notes,
            "bias_at_open": bias_at_open,
            "broker": "MANUAL"
        }
        
        # First, create a dummy signal record to satisfy foreign key
        try:
            from database.postgres_client import log_signal
            await log_signal({
                "signal_id": signal_id,
                "ticker": request.ticker,
                "strategy": request.strategy or "Manual Entry",
                "direction": request.direction,
                "signal_type": "MANUAL",
                "entry_price": request.entry_price,
                "stop_loss": request.stop_loss,
                "target_1": request.target_1,
                "timestamp": datetime.now().isoformat(),
                "asset_class": request.asset_class,
                "score": 0,
                "bias_alignment": "N/A"
            })
        except Exception as signal_err:
            logger.warning(f"Failed to create dummy signal: {signal_err}")
        
        # Save position to PostgreSQL
        try:
            db_position_id = await create_position(signal_id, position_data)
            logger.info(f"✅ Manual position saved to PostgreSQL: {request.ticker}")
        except Exception as db_err:
            logger.error(f"❌ Failed to persist manual position to DB: {db_err}")
            # Continue anyway - position will still work in memory
            db_position_id = None
        
        # Create position object for memory/UI
        position = {
            "id": db_position_id or _position_counter,
            "signal_id": signal_id,
            "ticker": request.ticker,
            "direction": request.direction,
            "entry_price": request.entry_price,
            "quantity": request.quantity,
            "stop_loss": request.stop_loss,
            "target_1": request.target_1,
            "strategy": request.strategy or "Manual Entry",
            "asset_class": request.asset_class,
            "signal_type": "MANUAL",
            "notes": request.notes,
            "entry_time": datetime.now().isoformat(),
            "status": "OPEN"
        }
        
        _open_positions.append(position)
        if not db_position_id:
            _position_counter += 1
        
        # Broadcast to all devices
        await manager.broadcast_position_update({
            "action": "POSITION_OPENED",
            "position": position
        })
        
        logger.info(f"📝 Manual position created: {request.ticker} {request.direction} @ ${request.entry_price} x {request.quantity}")
        
        return {"status": "success", "position_id": position["id"], "position": position}
    
    except Exception as e:
        logger.error(f"Error creating manual position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class UpdatePositionRequest(BaseModel):
    """Request to update a position"""
    quantity: Optional[int] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    notes: Optional[str] = None


@router.patch("/positions/{position_id}")
async def update_position(position_id: int, request: UpdatePositionRequest):
    """
    Update an existing position (quantity, stops, targets, notes).
    """
    try:
        # Find in memory
        position = None
        for p in _open_positions:
            if p["id"] == position_id:
                position = p
                break
        
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        # Update memory
        if request.quantity is not None:
            position["quantity"] = request.quantity
        if request.stop_loss is not None:
            position["stop_loss"] = request.stop_loss
        if request.target_1 is not None:
            position["target_1"] = request.target_1
        if request.notes is not None:
            position["notes"] = request.notes
        
        # Update database
        try:
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                updates = []
                params = []
                param_idx = 1
                
                if request.quantity is not None:
                    updates.append(f"quantity = ${param_idx}")
                    params.append(request.quantity)
                    param_idx += 1
                if request.stop_loss is not None:
                    updates.append(f"stop_loss = ${param_idx}")
                    params.append(request.stop_loss)
                    param_idx += 1
                if request.target_1 is not None:
                    updates.append(f"target_1 = ${param_idx}")
                    params.append(request.target_1)
                    param_idx += 1
                if request.notes is not None:
                    updates.append(f"notes = ${param_idx}")
                    params.append(request.notes)
                    param_idx += 1
                
                if updates:
                    params.append(position_id)
                    query = f"UPDATE positions SET {', '.join(updates)} WHERE id = ${param_idx}"
                    await conn.execute(query, *params)
                    
        except Exception as db_err:
            logger.warning(f"Failed to update position in DB: {db_err}")
        
        logger.info(f"📝 Position {position_id} updated: qty={request.quantity}, stop={request.stop_loss}, target={request.target_1}")
        
        return {"status": "success", "position": position}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def sync_positions_from_database():
    """
    Sync open positions from database to in-memory cache.
    Called on startup to restore positions after restart.
    """
    global _open_positions, _position_counter
    
    try:
        logger.info("🔄 Starting position sync from database...")
        db_positions = await get_open_positions()
        logger.info(f"📊 Database returned {len(db_positions) if db_positions else 0} positions")
        
        if db_positions:
            _open_positions = []
            max_id = 0
            
            for pos in db_positions:
                logger.info(f"Processing position: {pos.get('ticker')} - {pos.get('direction')}")
                
                # Handle entry_time - could be datetime object or string
                entry_time_value = pos.get("entry_time")
                if entry_time_value:
                    if isinstance(entry_time_value, str):
                        entry_time_str = entry_time_value
                    else:
                        entry_time_str = entry_time_value.isoformat()
                else:
                    entry_time_str = None
                
                position = {
                    "id": pos.get("id", 0),
                    "signal_id": pos.get("signal_id"),
                    "ticker": pos.get("ticker"),
                    "direction": pos.get("direction"),
                    "entry_price": float(pos.get("entry_price", 0)) if pos.get("entry_price") else 0,
                    "quantity": pos.get("quantity", 1),
                    "stop_loss": float(pos.get("stop_loss", 0)) if pos.get("stop_loss") else None,
                    "target_1": float(pos.get("target_1", 0)) if pos.get("target_1") else None,
                    "strategy": pos.get("strategy"),
                    "asset_class": pos.get("asset_class", "EQUITY"),
                    "signal_type": pos.get("signal_type"),
                    "bias_level": pos.get("bias_level"),
                    "entry_time": entry_time_str,
                    "status": pos.get("status", "OPEN")
                }
                _open_positions.append(position)
                max_id = max(max_id, position["id"])
            
            _position_counter = max_id + 1
            logger.info(f"✅ Synced {len(_open_positions)} open positions from database")
        else:
            logger.warning("⚠️ No open positions returned from database query")
    
    except Exception as e:
        logger.error(f"❌ Failed to sync positions from database: {e}", exc_info=True)

@router.post("/positions/close")
async def close_position(request: ClosePositionRequest):
    """
    Close a position with comprehensive outcome logging.
    
    Logs for backtesting:
    - Trade outcome (WIN/LOSS/BREAKEVEN)
    - Loss reason if applicable (SETUP_FAILED/EXECUTION_ERROR)
    - Whether stop loss was hit
    - Notes for analysis
    """
    try:
        # Find the position in memory
        position = None
        position_idx = None
        for idx, p in enumerate(_open_positions):
            if p["id"] == request.position_id:
                position = p
                position_idx = idx
                break
        
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        # Determine quantity to close
        quantity_closed = request.quantity_closed or position.get("quantity", 1)
        
        # Calculate P&L
        if position["direction"] == "LONG":
            pnl_per_unit = request.exit_price - position["entry_price"]
        else:
            pnl_per_unit = position["entry_price"] - request.exit_price
        
        realized_pnl = pnl_per_unit * quantity_closed
        
        # Determine trade outcome if not provided
        trade_outcome = request.trade_outcome
        if not trade_outcome:
            if realized_pnl > 0:
                trade_outcome = "WIN"
            elif realized_pnl < 0:
                trade_outcome = "LOSS"
            else:
                trade_outcome = "BREAKEVEN"
        
        # Capture bias snapshot at close for archival
        bias_at_close = await get_bias_snapshot()

        # Create comprehensive trade history record
        trade_record = {
            "id": position["id"],
            "signal_id": position.get("signal_id"),
            "ticker": position["ticker"],
            "direction": position["direction"],
            "entry_price": position["entry_price"],
            "recommended_entry": position.get("recommended_entry"),
            "exit_price": request.exit_price,
            "quantity_closed": quantity_closed,
            "realized_pnl": round(realized_pnl, 2),
            "strategy": position.get("strategy"),
            "signal_type": position.get("signal_type"),
            "bias_alignment": position.get("bias_alignment"),
            "score": position.get("score"),
            "triggering_factors": position.get("triggering_factors"),
            "entry_time": position.get("entry_time"),
            "exit_time": datetime.now().isoformat(),
            "asset_class": position.get("asset_class"),
            "bias_at_close": bias_at_close,
            # Outcome logging for backtesting
            "trade_outcome": trade_outcome,
            "loss_reason": request.loss_reason if trade_outcome == "LOSS" else None,
            "actual_stop_hit": request.actual_stop_hit,
            "notes": request.notes
        }
        
        _closed_trades.append(trade_record)
        
        # Update PostgreSQL with outcome
        signal_id = position.get("signal_id")
        if signal_id:
            try:
                await update_signal_outcome(
                    signal_id,
                    actual_exit_price=request.exit_price,
                    actual_stop_hit=request.actual_stop_hit,
                    trade_outcome=trade_outcome,
                    loss_reason=request.loss_reason,
                    notes=request.notes
                )
            except Exception as db_err:
                logger.warning(f"Failed to update signal outcome: {db_err}")
        
        # Check if partial or full close
        remaining_qty = position.get("quantity", 1) - quantity_closed
        
        if remaining_qty <= 0:
            # Full close - remove position
            _open_positions.pop(position_idx)
            status = "closed"
            
            # Also close in database if position exists there
            try:
                await close_position_in_db(
                    position_id=position["id"],
                    exit_price=request.exit_price,
                    exit_time=datetime.now(),
                    realized_pnl=round(realized_pnl, 2),
                    trade_outcome=trade_outcome,
                    quantity_closed=quantity_closed,
                    bias_at_close=bias_at_close,
                    loss_reason=request.loss_reason if trade_outcome == "LOSS" else None,
                    notes=request.notes
                )
            except Exception as db_err:
                logger.warning(f"Failed to close position in DB: {db_err}")

            await _update_watchlist_on_position_close(position["ticker"], position["id"])
            
            outcome_emoji = "🎯" if trade_outcome == "WIN" else "❌" if trade_outcome == "LOSS" else "➖"
            logger.info(f"{outcome_emoji} Position closed: {position['ticker']} - {trade_outcome} - P&L: ${realized_pnl:.2f}")
            
            if trade_outcome == "LOSS" and request.loss_reason:
                logger.info(f"   Loss reason: {request.loss_reason}")
        else:
            # Partial close - update quantity
            _open_positions[position_idx]["quantity"] = remaining_qty
            status = "partial_close"
            try:
                await update_position_quantity(position["id"], remaining_qty, quantity_closed)
            except Exception as db_err:
                logger.warning(f"Failed to update position quantity in DB: {db_err}")
            logger.info(f"📉 Partial close: {position['ticker']} - Closed {quantity_closed}, Remaining {remaining_qty}")
        
        # Broadcast update
        await manager.broadcast_position_update({
            "action": "POSITION_CLOSED" if status == "closed" else "POSITION_PARTIAL_CLOSE",
            "position_id": position["id"],
            "trade_record": trade_record,
            "trade_outcome": trade_outcome,
            "loss_reason": request.loss_reason
        })
        
        return {
            "status": status,
            "trade_outcome": trade_outcome,
            "loss_reason": request.loss_reason if trade_outcome == "LOSS" else None,
            "realized_pnl": round(realized_pnl, 2),
            "remaining_quantity": max(0, remaining_qty),
            "trade_record": trade_record
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/positions/open")
async def get_open_positions_api():
    """
    Get all open positions
    Returns list of active trades
    """
    
    try:
        # Return in-memory positions (faster than DB query for real-time)
        return {"status": "success", "positions": _open_positions}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/positions/{position_id}")
async def remove_position(position_id: int):
    """
    Remove a position from active list without archiving.
    Intended for glitched or unwanted trades.
    """
    try:
        position = None
        position_idx = None
        for idx, p in enumerate(_open_positions):
            if p["id"] == position_id:
                position = p
                position_idx = idx
                break

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        _open_positions.pop(position_idx)

        try:
            await delete_open_position(position_id, position.get("signal_id"))
        except Exception as db_err:
            logger.warning(f"Failed to delete position from DB: {db_err}")

        await manager.broadcast_position_update({
            "action": "POSITION_REMOVED",
            "position_id": position_id,
            "position": position
        })

        return {
            "status": "removed",
            "position_id": position_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing position: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/positions/history")
async def get_trade_history():
    """
    Get closed trade history for backtesting
    """
    try:
        return {
            "status": "success",
            "trades": _closed_trades,
            "total_trades": len(_closed_trades),
            "total_pnl": sum(t.get("realized_pnl", 0) for t in _closed_trades)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/debug-db")
async def debug_positions_db():
    """
    Debug endpoint: Check what positions exist in PostgreSQL vs memory
    """
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM positions ORDER BY created_at DESC LIMIT 10")
            from database.postgres_client import serialize_db_row
            db_positions = [serialize_db_row(dict(row)) for row in rows]
        
        return {
            "status": "success",
            "db_positions": db_positions,
            "db_count": len(db_positions),
            "memory_positions": _open_positions,
            "memory_count": len(_open_positions),
            "synced": len(db_positions) == len(_open_positions)
        }
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/force-sync")
async def force_sync_positions():
    """
    Manually trigger position sync from database to memory
    """
    try:
        await sync_positions_from_database()
        return {
            "status": "success",
            "message": f"Synced {len(_open_positions)} positions from database",
            "positions": _open_positions
        }
    except Exception as e:
        logger.error(f"Error forcing position sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/diagnose")
async def diagnose_positions():
    """
    Diagnostic endpoint to troubleshoot position loading
    """
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        
        # Query 1: All positions
        async with pool.acquire() as conn:
            all_rows = await conn.fetch("SELECT id, ticker, status FROM positions ORDER BY created_at DESC")
            
        # Query 2: Open positions only  
        async with pool.acquire() as conn:
            open_rows = await conn.fetch("SELECT id, ticker, status FROM positions WHERE status = 'OPEN'")
        
        # Test get_open_positions function
        from_function = await get_open_positions()
        
        return {
            "status": "success",
            "all_positions_count": len(all_rows),
            "all_positions": [dict(r) for r in all_rows],
            "open_query_count": len(open_rows),
            "open_query_results": [dict(r) for r in open_rows],
            "function_result_count": len(from_function),
            "function_results": from_function,
            "memory_count": len(_open_positions),
            "memory_positions": _open_positions
        }
    except Exception as e:
        logger.error(f"Error in diagnose endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/position/update")
async def update_position(update: PositionUpdate):
    """
    Update an existing position (for manual exits)
    Future: This will be automated via broker APIs
    """
    
    try:
        # TODO: Implement position update logic
        # For now, this is a placeholder for future broker API integration
        
        return {
            "status": "success",
            "message": "Position update received (manual execution required)"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/signals/active")
async def get_active_signals_api():
    """
    Get all active trade ideas (not dismissed or selected).
    Returns top 10 ranked by score with bias alignment.
    
    Falls back to Redis cache, then PostgreSQL for persistence.
    Re-scores signals that don't have proper scores.
    """
    from database.redis_client import get_active_signals as get_redis_signals
    from scoring.trade_ideas_scorer import calculate_signal_score, get_score_tier
    from scheduler.bias_scheduler import get_bias_status
    from database.postgres_client import update_signal_with_score
    
    try:
        # First try Redis for fast access
        redis_signals = _normalize_signal_payloads(await get_redis_signals())
        logger.info(f"📡 Redis returned {len(redis_signals)} signals")
        
        # Always try PostgreSQL too - signals might have expired from Redis
        pg_signals = []
        try:
            pg_signals = _normalize_signal_payloads(await get_active_trade_ideas(limit=50))
            logger.info(f"📡 PostgreSQL returned {len(pg_signals)} signals")
        except Exception as db_err:
            logger.warning(f"Could not fetch from PostgreSQL: {db_err}")
        
        # Merge signals (prefer Redis for speed, but include PostgreSQL for persistence)
        signal_ids = set()
        signals = []
        
        # First add all Redis signals
        for sig in redis_signals:
            sig_id = sig.get('signal_id')
            if sig_id and sig_id not in signal_ids:
                signal_ids.add(sig_id)
                signals.append(sig)
        
        # Then add PostgreSQL signals that aren't already in Redis
        for sig in pg_signals:
            sig_id = sig.get('signal_id')
            if sig_id and sig_id not in signal_ids:
                signal_ids.add(sig_id)
                signals.append(sig)
                # Re-cache in Redis for faster access next time
                await cache_signal(sig_id, sig, ttl=7200)
        
        logger.info(f"📡 Total merged signals: {len(signals)}")
        
        # Get current bias for re-scoring
        bias_status = get_bias_status()
        current_bias = {
            "daily": bias_status.get("daily", {}),
            "weekly": bias_status.get("weekly", {}),
            "cyclical": bias_status.get("cyclical", {})
        }
        
        # Re-score signals that don't have proper scores
        for sig in signals:
            current_score = sig.get('score')
            # Re-score if score is 0, None, or missing proper bias_alignment
            if not current_score or current_score == 0 or not sig.get('bias_alignment'):
                try:
                    score, bias_alignment, factors = calculate_signal_score(sig, current_bias)
                    sig['score'] = score
                    sig['bias_alignment'] = bias_alignment
                    sig['triggering_factors'] = factors
                    sig['scoreTier'] = get_score_tier(score)
                    
                    # Set confidence and potentially upgrade signal type
                    direction = sig.get('direction', '').upper()
                    
                    if score >= 85:
                        sig['confidence'] = "HIGH"
                        sig['priority'] = "HIGH"
                        # Upgrade to APIS/KODIAK for strongest signals (rare, 85+ only)
                        if direction in ["LONG", "BUY"]:
                            sig['signal_type'] = "APIS_CALL"
                        elif direction in ["SHORT", "SELL"]:
                            sig['signal_type'] = "KODIAK_CALL"
                    elif score >= 75:
                        sig['confidence'] = "HIGH"
                        sig['priority'] = "HIGH"
                    elif score >= 55:
                        sig['confidence'] = "MEDIUM"
                    else:
                        sig['confidence'] = "LOW"
                    
                    # Update in DB asynchronously
                    try:
                        await update_signal_with_score(sig.get('signal_id'), score, bias_alignment, factors)
                    except:
                        pass  # Non-critical
                        
                except Exception as score_err:
                    logger.warning(f"Failed to rescore signal: {score_err}")
                    sig['score'] = 50  # Default
                    sig['bias_alignment'] = 'NEUTRAL'
        
        # Filter out tickers that have open positions
        open_tickers = set()
        try:
            open_pos = await get_open_positions()
            open_tickers = {pos.get('ticker', '').upper() for pos in open_pos if pos.get('ticker')}
            if open_tickers:
                signals = [s for s in signals if s.get('ticker', '').upper() not in open_tickers]
                logger.info(f"📊 Filtered out {len(open_tickers)} tickers with open positions: {open_tickers}")
        except Exception as e:
            logger.warning(f"Could not filter open positions: {e}")
        
        # Deduplicate: Group by ticker and merge multiple strategies into one signal
        ticker_groups = {}
        for sig in signals:
            ticker = sig.get('ticker', '').upper()
            if not ticker:
                continue
            
            if ticker not in ticker_groups:
                ticker_groups[ticker] = sig.copy()
                # Initialize strategies as a list
                current_strategy = sig.get('strategy', 'Unknown')
                ticker_groups[ticker]['strategies'] = [current_strategy] if current_strategy else []
                current_sig_type = sig.get('signal_type', 'SIGNAL')
                ticker_groups[ticker]['signal_types'] = [current_sig_type] if current_sig_type else []
                # Ensure triggering_factors is a list
                tf = ticker_groups[ticker].get('triggering_factors')
                if tf and isinstance(tf, str):
                    ticker_groups[ticker]['triggering_factors'] = [tf]
                elif not isinstance(tf, list):
                    ticker_groups[ticker]['triggering_factors'] = []
            else:
                # Merge into existing signal for this ticker
                existing = ticker_groups[ticker]

                ts_new = sig.get('timestamp') or sig.get('created_at') or ''
                ts_existing = existing.get('timestamp') or existing.get('created_at') or ''

                # If the new signal is more recent, prefer it as the base record
                if ts_new > ts_existing:
                    previous = existing
                    existing = sig.copy()
                    ticker_groups[ticker] = existing

                    # Carry over strategies and signal types from the previous record
                    previous_strategies = previous.get('strategies') if isinstance(previous.get('strategies'), list) else [previous.get('strategy', 'Unknown')]
                    previous_types = previous.get('signal_types') if isinstance(previous.get('signal_types'), list) else [previous.get('signal_type', 'SIGNAL')]
                    
                    current_strategy = existing.get('strategy', 'Unknown')
                    existing['strategies'] = [current_strategy] if current_strategy else []
                    for strategy in previous_strategies:
                        if strategy and strategy not in existing['strategies']:
                            existing['strategies'].append(strategy)
                    
                    current_sig_type = existing.get('signal_type', 'SIGNAL')
                    existing['signal_types'] = [current_sig_type] if current_sig_type else []
                    for sig_type in previous_types:
                        if sig_type and sig_type not in existing['signal_types']:
                            existing['signal_types'].append(sig_type)
                    
                    # Merge triggering factors
                    previous_factors = previous.get('triggering_factors', [])
                    if isinstance(previous_factors, str):
                        previous_factors = [previous_factors]
                    elif not isinstance(previous_factors, list):
                        previous_factors = []
                    
                    current_factors = existing.get('triggering_factors', [])
                    if isinstance(current_factors, str):
                        current_factors = [current_factors]
                    elif not isinstance(current_factors, list):
                        current_factors = []
                    
                    for factor in previous_factors:
                        if factor and factor not in current_factors:
                            current_factors.append(factor)
                    existing['triggering_factors'] = current_factors
                
                # Refresh reference after potential replacement
                existing = ticker_groups[ticker]
                
                # Ensure strategies is a list (defensive)
                if not isinstance(existing.get('strategies'), list):
                    existing['strategies'] = [existing.get('strategy', 'Unknown')]
                
                # Add strategy if not already listed
                strategy = sig.get('strategy', 'Unknown')
                if strategy and strategy not in existing['strategies']:
                    existing['strategies'].append(strategy)
                
                # Ensure signal_types is a list (defensive)
                if not isinstance(existing.get('signal_types'), list):
                    existing['signal_types'] = [existing.get('signal_type', 'SIGNAL')]
                
                # Add signal type if not already listed
                sig_type = sig.get('signal_type', 'SIGNAL')
                if sig_type and sig_type not in existing['signal_types']:
                    existing['signal_types'].append(sig_type)
                
                # If base record is missing score, backfill from this signal
                if not existing.get('score') and sig.get('score') is not None:
                    existing['score'] = sig.get('score')
                    existing['scoreTier'] = sig.get('scoreTier', existing.get('scoreTier', 'MODERATE'))
                    existing['confidence'] = sig.get('confidence', existing.get('confidence', 'MEDIUM'))
                    existing['priority'] = sig.get('priority', existing.get('priority', 'MEDIUM'))
                
                # Merge triggering factors (combine unique factors)
                new_factors = sig.get('triggering_factors')
                if new_factors:
                    # Ensure new_factors is a list
                    if isinstance(new_factors, str):
                        new_factors = [new_factors]
                    elif not isinstance(new_factors, list):
                        new_factors = []
                    
                    # Ensure existing_factors is a list
                    existing_factors = existing.get('triggering_factors', [])
                    if isinstance(existing_factors, str):
                        existing_factors = [existing_factors]
                    elif not isinstance(existing_factors, list):
                        existing_factors = []
                    
                    for factor in new_factors:
                        if factor and factor not in existing_factors:
                            existing_factors.append(factor)
                    existing['triggering_factors'] = existing_factors
                
                # Keep most recent timestamp
                ts_new = sig.get('timestamp') or sig.get('created_at') or ''
                ts_existing = existing.get('timestamp') or existing.get('created_at') or ''
                if ts_new > ts_existing:
                    existing['timestamp'] = ts_new
                    existing['created_at'] = ts_new
        
        # Convert back to list
        signals = list(ticker_groups.values())
        logger.info(f"📊 Deduplicated to {len(signals)} unique tickers")
        
        # Sort by recency first (newest signals on top), then by score as tiebreaker
        # This ensures fresh signals are always visible even if older ones scored higher
        def get_sort_key(sig):
            # Parse timestamp - newer = higher priority
            ts = sig.get('timestamp') or sig.get('created_at') or '1970-01-01'
            if isinstance(ts, str):
                ts_str = ts
            else:
                ts_str = str(ts)
            # Score as secondary sort (higher = better)
            score = sig.get('score', 0) or 0
            return (ts_str, score)
        
        signals.sort(key=get_sort_key, reverse=True)
        
        # Separate counter-trend signals
        # Get composite bias direction to determine what counts as counter-trend
        counter_trend_signals = []
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached and abs(cached.composite_score) >= 0.1:
                market_is_bullish = cached.composite_score > 0
                for sig in signals:
                    sig_dir = (sig.get('direction') or '').upper()
                    is_long = sig_dir in ('LONG', 'BUY')
                    is_counter = (market_is_bullish and not is_long) or (not market_is_bullish and is_long)
                    if is_counter:
                        sig['is_counter_trend'] = True
                        counter_trend_signals.append(sig)
        except Exception:
            pass
        
        # Top 2 counter-trend signals by score
        counter_trend_signals.sort(key=lambda s: s.get('score', 0) or 0, reverse=True)
        top_counter = counter_trend_signals[:2]
        top_counter_ids = {s.get('signal_id') for s in top_counter}
        
        # Return top 10 for display (but keep more in queue)
        # Ensure counter-trend signals aren't duplicated if they're already in top 10
        top_signals = signals[:10]
        top_signal_ids = {s.get('signal_id') for s in top_signals}
        
        # Add counter-trend signals that aren't already in top 10
        extra_counter = [s for s in top_counter if s.get('signal_id') not in top_signal_ids]
        
        queue_size = len(signals)
        
        return {
            "status": "success",
            "signals": top_signals,
            "counter_trend_signals": extra_counter,
            "queue_size": queue_size,
            "has_more": queue_size > 10
        }
    
    except Exception as e:
        logger.error(f"Error fetching active signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/active/paged")
async def get_active_signals_paged(
    limit: int = 10,
    offset: int = 0,
    asset_class: Optional[str] = None
):
    """
    Paginated active trade ideas for "Reload previous".
    """
    try:
        result = await get_active_trade_ideas_paginated(
            limit=limit,
            offset=offset,
            asset_class=asset_class
        )

        signals = result.get("signals", [])
        total = result.get("total", 0)
        has_more = (offset + len(signals)) < total

        return {
            "status": "success",
            "signals": signals,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": has_more
        }
    except Exception as e:
        logger.error(f"Error fetching paged signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/queue")
async def get_signal_queue():
    """
    Get the full queue of active signals (for auto-refill).
    Returns up to 50 signals ranked by score.
    """
    from database.redis_client import get_active_signals as get_redis_signals
    
    try:
        signals = _normalize_signal_payloads(await get_redis_signals())
        
        if not signals:
            signals = _normalize_signal_payloads(await get_active_trade_ideas(limit=50))
        
        signals.sort(key=lambda x: x.get('score', 0) or 0, reverse=True)
        
        return {
            "status": "success",
            "signals": signals,
            "total": len(signals)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/archive")
async def get_archived_signals_api(filters: ArchiveFilters):
    """
    Get archived signals for backtesting analysis.
    
    Supports filtering by:
    - ticker, strategy, user_action, trade_outcome
    - bias_alignment, date range
    - Pagination via limit/offset
    """
    try:
        filter_dict = {
            "ticker": filters.ticker,
            "strategy": filters.strategy,
            "user_action": filters.user_action,
            "trade_outcome": filters.trade_outcome,
            "bias_alignment": filters.bias_alignment,
            "start_date": filters.start_date,
            "end_date": filters.end_date
        }
        
        # Remove None values
        filter_dict = {k: v for k, v in filter_dict.items() if v is not None}
        
        result = await get_archived_signals(
            filters=filter_dict,
            limit=filters.limit,
            offset=filters.offset
        )
        
        return {
            "status": "success",
            **result
        }
    
    except Exception as e:
        logger.error(f"Error fetching archived signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/debug")
async def debug_signals():
    """
    Debug endpoint to check signal storage status.
    Returns counts from Redis and PostgreSQL.
    """
    from database.redis_client import get_active_signals as get_redis_signals
    from database.postgres_client import get_postgres_client
    
    debug_info = {
        "redis": {"count": 0, "sample": None},
        "postgresql": {"active_count": 0, "total_count": 0, "sample": None}
    }
    
    try:
        # Check Redis
        redis_signals = _normalize_signal_payloads(await get_redis_signals())
        debug_info["redis"]["count"] = len(redis_signals)
        if redis_signals:
            debug_info["redis"]["sample"] = {
                "signal_id": redis_signals[0].get("signal_id"),
                "ticker": redis_signals[0].get("ticker"),
                "asset_class": redis_signals[0].get("asset_class")
            }
    except Exception as e:
        debug_info["redis"]["error"] = str(e)
    
    try:
        # Check PostgreSQL
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # Count active (user_action IS NULL)
            active_count = await conn.fetchval(
                "SELECT COUNT(*) FROM signals WHERE user_action IS NULL"
            )
            debug_info["postgresql"]["active_count"] = active_count
            
            # Count total
            total_count = await conn.fetchval("SELECT COUNT(*) FROM signals")
            debug_info["postgresql"]["total_count"] = total_count
            
            # Get sample active signal
            sample = await conn.fetchrow(
                "SELECT signal_id, ticker, asset_class, created_at FROM signals WHERE user_action IS NULL ORDER BY created_at DESC LIMIT 1"
            )
            if sample:
                debug_info["postgresql"]["sample"] = dict(sample)
    except Exception as e:
        debug_info["postgresql"]["error"] = str(e)
    
    return debug_info


@router.delete("/signals/clear-all")
async def clear_all_signals():
    """
    Clear all active signals from Redis and PostgreSQL.
    Use this to remove test/corrupted signals and start fresh.
    
    WARNING: This permanently deletes all active signals!
    """
    from database.redis_client import get_active_signals as get_redis_signals, delete_signal
    from database.postgres_client import get_postgres_client
    
    cleared = {
        "redis": 0,
        "postgresql": 0
    }
    
    try:
        # Clear Redis signals
        redis_signals = _normalize_signal_payloads(await get_redis_signals())
        for sig in redis_signals:
            sig_id = sig.get('signal_id')
            if sig_id:
                await delete_signal(sig_id)
                cleared["redis"] += 1
        
        logger.info(f"Cleared {cleared['redis']} signals from Redis")
    except Exception as e:
        logger.error(f"Error clearing Redis: {e}")
    
    try:
        # Clear PostgreSQL active signals (set user_action to 'CLEARED')
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE signals SET user_action = 'CLEARED' WHERE user_action IS NULL"
            )
            # Parse the result to get count
            cleared["postgresql"] = int(result.split()[-1]) if result else 0
        
        logger.info(f"Cleared {cleared['postgresql']} signals from PostgreSQL")
    except Exception as e:
        logger.error(f"Error clearing PostgreSQL: {e}")
    
    return {
        "status": "success",
        "message": "All active signals cleared",
        "cleared": cleared
    }


@router.get("/signals/statistics")
async def get_trading_statistics(
    ticker: Optional[str] = None,
    strategy: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get aggregate trading statistics for backtesting analysis.
    
    Returns:
    - Total trades, wins, losses, breakeven
    - Win rate (overall and for bias-aligned trades)
    - Setup failures vs execution errors
    """
    try:
        filters = {}
        if ticker:
            filters["ticker"] = ticker
        if strategy:
            filters["strategy"] = strategy
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
        
        stats = await get_backtest_statistics(filters)
        
        return {
            "status": "success",
            "statistics": stats
        }
    
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
