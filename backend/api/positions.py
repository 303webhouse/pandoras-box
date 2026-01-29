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
    get_archived_signals,
    get_signal_by_id,
    update_signal_outcome,
    close_position_in_db,
    get_position_by_id,
    get_backtest_statistics
)
from websocket.broadcaster import manager

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory position store (synced with database on startup)
_open_positions = []
_closed_trades = []
_position_counter = 1


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
        
        # Create position in database with full details
        position_data = {
            "ticker": signal_data.get('ticker'),
            "direction": signal_data.get('direction'),
            "entry_price": signal_data.get('entry_price'),  # Recommended entry
            "actual_entry_price": request.actual_entry_price,  # Actual entry
            "entry_time": datetime.now(),
            "stop_loss": request.stop_loss or signal_data.get('stop_loss'),
            "target_1": request.target_1 or signal_data.get('target_1'),
            "target_2": request.target_2 or signal_data.get('target_2'),
            "strategy": signal_data.get('strategy'),
            "asset_class": signal_data.get('asset_class', 'EQUITY'),
            "signal_type": signal_data.get('signal_type'),
            "bias_level": signal_data.get('bias_alignment'),
            "broker": "MANUAL"
        }
        
        await create_position(signal_id, position_data)
        
        # Also add to in-memory store for quick access
        position = {
            "id": _position_counter,
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
        _position_counter += 1
        
        # Remove from active signals cache
        await delete_signal(signal_id)
        
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
        position_data = {
            "ticker": request.ticker,
            "direction": request.direction,
            "entry_price": request.entry_price,
            "entry_time": datetime.now(),
            "stop_loss": request.stop_loss,
            "target_1": request.target_1,
            "strategy": request.strategy,
            "asset_class": request.asset_class,
            "signal_type": request.signal_type,
            "bias_level": request.bias_level,
            "broker": "MANUAL"
        }
        
        # Save to PostgreSQL
        try:
            await create_position(request.signal_id, position_data)
        except Exception as db_err:
            logger.warning(f"Failed to persist position to DB: {db_err}")
        
        # Also keep in memory for fast access
        position = {
            "id": _position_counter,
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
        _position_counter += 1
        
        # Remove from active signals
        await delete_signal(request.signal_id)
        
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
        
        # Create position data
        position_data = {
            "ticker": request.ticker,
            "direction": request.direction,
            "entry_price": request.entry_price,
            "entry_time": datetime.now(),
            "stop_loss": request.stop_loss,
            "target_1": request.target_1,
            "strategy": request.strategy or "Manual Entry",
            "asset_class": request.asset_class,
            "signal_type": "MANUAL",
            "notes": request.notes,
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
            await create_position(signal_id, position_data)
            logger.info(f"✅ Manual position saved to PostgreSQL: {request.ticker}")
        except Exception as db_err:
            logger.error(f"❌ Failed to persist manual position to DB: {db_err}")
            # Continue anyway - position will still work in memory
        
        # Create position object for memory/UI
        position = {
            "id": _position_counter,
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
            # (future: implement close_position_in_db)
            
            outcome_emoji = "🎯" if trade_outcome == "WIN" else "❌" if trade_outcome == "LOSS" else "➖"
            logger.info(f"{outcome_emoji} Position closed: {position['ticker']} - {trade_outcome} - P&L: ${realized_pnl:.2f}")
            
            if trade_outcome == "LOSS" and request.loss_reason:
                logger.info(f"   Loss reason: {request.loss_reason}")
        else:
            # Partial close - update quantity
            _open_positions[position_idx]["quantity"] = remaining_qty
            status = "partial_close"
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
        redis_signals = await get_redis_signals()
        logger.info(f"📡 Redis returned {len(redis_signals)} signals")
        
        # Always try PostgreSQL too - signals might have expired from Redis
        pg_signals = []
        try:
            pg_signals = await get_active_trade_ideas(limit=50)
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
                ticker_groups[ticker]['strategies'] = [sig.get('strategy', 'Unknown')]
                ticker_groups[ticker]['signal_types'] = [sig.get('signal_type', 'SIGNAL')]
            else:
                # Merge into existing signal for this ticker
                existing = ticker_groups[ticker]
                
                # Add strategy if not already listed
                strategy = sig.get('strategy', 'Unknown')
                if strategy not in existing['strategies']:
                    existing['strategies'].append(strategy)
                
                # Add signal type if not already listed
                sig_type = sig.get('signal_type', 'SIGNAL')
                if sig_type not in existing['signal_types']:
                    existing['signal_types'].append(sig_type)
                
                # Keep the highest score
                if sig.get('score', 0) > existing.get('score', 0):
                    existing['score'] = sig['score']
                    existing['scoreTier'] = sig.get('scoreTier', 'MODERATE')
                    existing['confidence'] = sig.get('confidence', 'MEDIUM')
                    existing['priority'] = sig.get('priority', 'MEDIUM')
                
                # Merge triggering factors (combine unique factors)
                if sig.get('triggering_factors'):
                    existing_factors = existing.get('triggering_factors', [])
                    for factor in sig['triggering_factors']:
                        if factor not in existing_factors:
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
        
        # Return top 10 for display (but keep more in queue)
        top_signals = signals[:10]
        queue_size = len(signals)
        
        return {
            "status": "success",
            "signals": top_signals,
            "queue_size": queue_size,
            "has_more": queue_size > 10
        }
    
    except Exception as e:
        logger.error(f"Error fetching active signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/queue")
async def get_signal_queue():
    """
    Get the full queue of active signals (for auto-refill).
    Returns up to 50 signals ranked by score.
    """
    from database.redis_client import get_active_signals as get_redis_signals
    
    try:
        signals = await get_redis_signals()
        
        if not signals:
            signals = await get_active_trade_ideas(limit=50)
        
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
        redis_signals = await get_redis_signals()
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
        redis_signals = await get_redis_signals()
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
