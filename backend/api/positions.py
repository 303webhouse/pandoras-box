"""
Positions API
Manages selected trades and open positions
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from database.redis_client import get_signal, delete_signal
from database.postgres_client import (
    update_signal_action,
    create_position,
    get_open_positions
)
from websocket.broadcaster import manager

router = APIRouter()

class SignalAction(BaseModel):
    """User action on a signal"""
    signal_id: str
    action: str  # "DISMISS" or "SELECT"

class PositionUpdate(BaseModel):
    """Update an existing position"""
    position_id: int
    exit_price: Optional[float] = None
    status: Optional[str] = None  # "OPEN", "CLOSED", "STOPPED_OUT", "TARGET_HIT"

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

@router.get("/positions/open")
async def get_open_positions_api():
    """
    Get all open positions
    Returns list of active trades
    """
    
    try:
        positions = await get_open_positions()
        return {"status": "success", "positions": positions}
    
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
        from scoring.rank_trades import calculate_signal_score
        
        for signal in signals:
            signal['score'] = calculate_signal_score(
                signal['signal_type'],
                signal['risk_reward'],
                signal['adx'],
                signal['line_separation'],
                signal['bias_aligned']
            )
        
        signals.sort(key=lambda x: x['score'], reverse=True)
        
        return {"status": "success", "signals": signals}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
