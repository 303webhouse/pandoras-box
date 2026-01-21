"""
BTC Bottom Signals API Endpoints
Dashboard for tracking derivative bottom signals
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/btc", tags=["BTC Signals"])

# Import the signals module
from bias_filters.btc_bottom_signals import (
    get_all_signals,
    get_signal,
    update_signal_manual,
    reset_all_signals,
    get_signal_ids,
    get_btc_sessions,
    get_current_session
)


class ManualSignalUpdate(BaseModel):
    """Request body for manual signal updates"""
    status: str  # FIRING, NEUTRAL, UNKNOWN
    value: Optional[Any] = None
    notes: Optional[str] = None


@router.get("/bottom-signals")
async def get_bottom_signals_dashboard():
    """
    Get the full BTC bottom signals dashboard
    
    Returns all 8+ signals with their current status,
    firing count, and overall verdict.
    """
    try:
        return await get_all_signals()
    except Exception as e:
        logger.error(f"Error getting bottom signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bottom-signals/{signal_id}")
async def get_single_signal(signal_id: str):
    """Get a specific bottom signal by ID"""
    signal = await get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal '{signal_id}' not found")
    return {"signal_id": signal_id, **signal}


@router.post("/bottom-signals/{signal_id}")
async def update_signal(signal_id: str, update: ManualSignalUpdate):
    """
    Manually update a bottom signal's status
    
    Use this when you've checked a signal on TradingView/Coinalyze
    and want to log it in the dashboard.
    
    Status options: FIRING, NEUTRAL, UNKNOWN
    """
    try:
        result = await update_signal_manual(
            signal_id=signal_id,
            status=update.status,
            value=update.value,
            notes=update.notes
        )
        return {"status": "success", "signal": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating signal {signal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bottom-signals/reset")
async def reset_signals():
    """Reset all manual signals to UNKNOWN status"""
    try:
        await reset_all_signals()
        return {"status": "success", "message": "All manual signals reset"}
    except Exception as e:
        logger.error(f"Error resetting signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signal-ids")
async def list_signal_ids():
    """Get list of all signal IDs for reference"""
    return {"signal_ids": get_signal_ids()}


@router.get("/sessions")
async def get_trading_sessions():
    """
    Get BTC trading session windows
    
    Shows key intraday time windows with their significance:
    - Asia Handoff (8pm-9pm ET)
    - London Open (4am-6am ET)
    - Peak Volume (11am-1pm ET)
    - ETF Fixing (3pm-4pm ET)
    - Friday CME Close (3:55pm-4pm ET)
    """
    sessions = get_btc_sessions()
    current = get_current_session()
    
    return {
        "sessions": sessions,
        "current_session": current,
        "timezone": "America/New_York"
    }


@router.get("/sessions/current")
async def get_active_session():
    """Check if we're currently in a key BTC trading session"""
    current = get_current_session()
    if current:
        return {"in_session": True, **current}
    return {"in_session": False, "message": "Not currently in a key trading session"}
