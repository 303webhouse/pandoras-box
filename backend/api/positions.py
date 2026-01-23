"""
Positions API
Manages selected trades and open positions
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging

from database.redis_client import get_signal, delete_signal
from database.postgres_client import (
    update_signal_action,
    create_position,
    get_open_positions
)
from websocket.broadcaster import manager

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory position store (for quick demo - should use Redis/Postgres in production)
_open_positions = []
_closed_trades = []
_position_counter = 1

class SignalAction(BaseModel):
    """User action on a signal"""
    signal_id: str
    action: str  # "DISMISS" or "SELECT"

class PositionUpdate(BaseModel):
    """Update an existing position"""
    position_id: int
    exit_price: Optional[float] = None
    status: Optional[str] = None  # "OPEN", "CLOSED", "STOPPED_OUT", "TARGET_HIT"

class OpenPositionRequest(BaseModel):
    """Request to open a new position"""
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

class ClosePositionRequest(BaseModel):
    """Request to close a position"""
    position_id: str
    exit_price: float
    quantity_closed: float

@router.post("/signal/action")
async def handle_signal_action(action: SignalAction):
    """
    Handle user action on a signal (dismiss or select)
    """
    
    try:
        signal_id = action.signal_id
        user_action = action.action.upper()
        
        if user_action not in ["DISMISS", "SELECT"]:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        # Get signal data from Redis
        signal_data = await get_signal(signal_id)
        
        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Update database
        await update_signal_action(signal_id, user_action)
        
        if user_action == "DISMISS":
            # Remove from Redis cache
            await delete_signal(signal_id)
            
            # Broadcast dismissal to all devices
            await manager.broadcast({
                "type": "SIGNAL_DISMISSED",
                "signal_id": signal_id
            })
            
            return {"status": "dismissed", "signal_id": signal_id}
        
        elif user_action == "SELECT":
            # Create position in database
            position_data = {
                "ticker": signal_data['ticker'],
                "direction": signal_data['direction'],
                "entry_price": signal_data['entry_price'],
                "entry_time": datetime.now(),
                "stop_loss": signal_data['stop_loss'],
                "target_1": signal_data['target_1'],
                "broker": "MANUAL"
            }
            
            await create_position(signal_id, position_data)
            
            # Remove from active signals cache
            await delete_signal(signal_id)
            
            # Broadcast selection to all devices
            await manager.broadcast_position_update({
                "action": "POSITION_OPENED",
                "signal_id": signal_id,
                "position": position_data
            })
            
            return {"status": "selected", "signal_id": signal_id, "position": position_data}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/positions/open")
async def open_position(request: OpenPositionRequest):
    """
    Open a new position with entry price and quantity
    """
    global _position_counter
    
    try:
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

@router.post("/positions/close")
async def close_position(request: ClosePositionRequest):
    """
    Close a position (supports partial close)
    Logs to trade history for backtesting
    """
    try:
        # Find the position
        position = None
        position_idx = None
        for idx, p in enumerate(_open_positions):
            if str(p["id"]) == str(request.position_id) or p["signal_id"] == request.position_id:
                position = p
                position_idx = idx
                break
        
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        # Calculate P&L
        if position["direction"] == "LONG":
            pnl_per_unit = request.exit_price - position["entry_price"]
        else:
            pnl_per_unit = position["entry_price"] - request.exit_price
        
        realized_pnl = pnl_per_unit * request.quantity_closed
        
        # Create trade history record
        trade_record = {
            "id": position["id"],
            "signal_id": position["signal_id"],
            "ticker": position["ticker"],
            "direction": position["direction"],
            "entry_price": position["entry_price"],
            "exit_price": request.exit_price,
            "quantity_closed": request.quantity_closed,
            "realized_pnl": round(realized_pnl, 2),
            "strategy": position.get("strategy"),
            "signal_type": position.get("signal_type"),
            "bias_level": position.get("bias_level"),
            "entry_time": position.get("entry_time"),
            "exit_time": datetime.now().isoformat(),
            "asset_class": position.get("asset_class")
        }
        
        _closed_trades.append(trade_record)
        
        # Check if partial or full close
        remaining_qty = position["quantity"] - request.quantity_closed
        
        if remaining_qty <= 0:
            # Full close - remove position
            _open_positions.pop(position_idx)
            status = "closed"
            logger.info(f"📉 Position closed: {position['ticker']} - P&L: ${realized_pnl:.2f}")
        else:
            # Partial close - update quantity
            _open_positions[position_idx]["quantity"] = remaining_qty
            status = "partial_close"
            logger.info(f"📉 Partial close: {position['ticker']} - Closed {request.quantity_closed}, Remaining {remaining_qty}")
        
        # Broadcast update
        await manager.broadcast_position_update({
            "action": "POSITION_CLOSED" if status == "closed" else "POSITION_PARTIAL_CLOSE",
            "position_id": position["id"],
            "trade_record": trade_record
        })
        
        return {
            "status": status,
            "realized_pnl": round(realized_pnl, 2),
            "remaining_quantity": remaining_qty if remaining_qty > 0 else 0,
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
async def get_active_signals():
    """
    Get all active signals (not dismissed or selected)
    Used by frontend to populate trade recommendation columns
    """
    
    from database.redis_client import get_active_signals
    
    try:
        signals = await get_active_signals()
        
        # Sort by score (highest first)
        # Use existing score if available, otherwise calculate
        from scoring.rank_trades import calculate_signal_score
        
        for signal in signals:
            # Only recalculate if score not already set or if signal has required fields
            if 'score' not in signal or signal.get('score') is None:
                # Use .get() to handle missing fields gracefully
                signal['score'] = calculate_signal_score(
                    signal.get('signal_type', 'NEUTRAL'),
                    signal.get('risk_reward', 0),
                    signal.get('adx'),
                    signal.get('line_separation'),
                    signal.get('bias_aligned', False)
                )
        
        signals.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        return {"status": "success", "signals": signals}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
