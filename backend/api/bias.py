"""
Bias Indicators API
Provides endpoints for all macro bias filters including:
- Savita Indicator (BofA Sell Side)
- TICK Breadth (intraday)
- Future: VIX, Put/Call Ratio, etc.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Import bias filters
try:
    from bias_filters.savita_indicator import (
        get_savita_reading,
        update_savita_reading,
        set_savita_enabled,
        get_savita_config,
        check_savita_bias
    )
    SAVITA_AVAILABLE = True
except ImportError:
    SAVITA_AVAILABLE = False
    logger.warning("Savita indicator module not available")


class SavitaUpdate(BaseModel):
    """Request model for updating Savita reading"""
    reading: float  # The new reading (e.g., 55.9)
    date: Optional[str] = None  # Optional date string


class BiasCheckRequest(BaseModel):
    """Request model for checking bias confluence"""
    direction: str  # "LONG" or "SHORT"


# ====================
# SAVITA INDICATOR
# ====================

@router.get("/bias/savita")
async def get_savita():
    """
    Get the current Savita Indicator reading
    
    The Savita Indicator measures Wall Street strategists' average recommended
    equity allocation. It's a CONTRARIAN indicator:
    - High readings (>57.7%): Crowd too bullish = BEARISH signal
    - Low readings (<51.3%): Crowd too bearish = BULLISH signal
    
    Updated monthly by Bank of America.
    """
    if not SAVITA_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Savita indicator module not loaded"
        }
    
    return {
        "status": "success",
        **get_savita_reading()
    }


@router.put("/bias/savita")
async def update_savita(update: SavitaUpdate):
    """
    Update the Savita Indicator with a new reading from BofA monthly report
    
    Example:
    {
        "reading": 56.2,
        "date": "2026-02-01"
    }
    """
    if not SAVITA_AVAILABLE:
        raise HTTPException(status_code=503, detail="Savita indicator not available")
    
    try:
        result = update_savita_reading(update.reading, update.date)
        logger.info(f"Savita updated to {update.reading}%")
        return {
            "status": "success",
            "message": f"Savita Indicator updated to {update.reading}%",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bias/savita/check")
async def check_savita_direction(request: BiasCheckRequest):
    """
    Check if a trade direction aligns with Savita sentiment
    
    Request:
    {
        "direction": "LONG" or "SHORT"
    }
    
    Response includes whether the direction has sentiment confluence
    """
    if not SAVITA_AVAILABLE:
        raise HTTPException(status_code=503, detail="Savita indicator not available")
    
    direction = request.direction.upper()
    if direction not in ["LONG", "SHORT"]:
        raise HTTPException(status_code=400, detail="Direction must be LONG or SHORT")
    
    result = check_savita_bias(direction)
    return {
        "status": "success",
        "direction": direction,
        **result
    }


@router.post("/bias/savita/enable")
async def enable_savita(enabled: bool = True):
    """Enable or disable the Savita indicator filter"""
    if not SAVITA_AVAILABLE:
        raise HTTPException(status_code=503, detail="Savita indicator not available")
    
    set_savita_enabled(enabled)
    return {
        "status": "success",
        "savita_enabled": enabled
    }


@router.get("/bias/savita/config")
async def get_savita_configuration():
    """Get full Savita indicator configuration including thresholds"""
    if not SAVITA_AVAILABLE:
        return {"status": "unavailable"}
    
    return {
        "status": "success",
        **get_savita_config()
    }


# ====================
# ALL BIAS SUMMARY
# ====================

@router.get("/bias/summary")
async def get_all_bias_indicators():
    """
    Get a summary of all active bias indicators
    
    Returns:
    - Savita (monthly sentiment)
    - Future: TICK, VIX, Put/Call, etc.
    """
    summary = {
        "status": "success",
        "indicators": {}
    }
    
    # Savita
    if SAVITA_AVAILABLE:
        savita = get_savita_reading()
        summary["indicators"]["savita"] = {
            "name": "Savita (BofA Sell Side)",
            "timeframe": "MONTHLY",
            "reading": savita["reading"],
            "bias": savita["bias"],
            "signal": savita["signal"],
            "interpretation": savita["interpretation"],
            "last_updated": savita["last_updated"]
        }
    
    # Determine overall macro bias
    biases = [ind.get("bias") for ind in summary["indicators"].values() if ind.get("bias")]
    
    if biases:
        # Count bias direction
        bullish_count = sum(1 for b in biases if "TORO" in b)
        bearish_count = sum(1 for b in biases if "URSA" in b)
        
        if bullish_count > bearish_count:
            summary["overall_macro_bias"] = "TORO" if bullish_count > 1 else "TORO_MINOR"
        elif bearish_count > bullish_count:
            summary["overall_macro_bias"] = "URSA" if bearish_count > 1 else "URSA_MINOR"
        else:
            summary["overall_macro_bias"] = "NEUTRAL"
    else:
        summary["overall_macro_bias"] = "UNKNOWN"
    
    return summary
