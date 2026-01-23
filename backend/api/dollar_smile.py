"""
Dollar Smile API Endpoints
Macro bias indicator based on USD strength context

Endpoints:
- GET /dollar-smile/status - Get current Dollar Smile bias
- POST /dollar-smile/webhook - Receive TradingView webhook updates
- POST /dollar-smile/manual - Manually set bias (testing)
- GET /dollar-smile/scoring - Get bias for signal scoring
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dollar-smile", tags=["Dollar Smile Macro Bias"])

# Import Dollar Smile module
from bias_filters.dollar_smile import (
    get_dollar_smile_status,
    update_from_webhook,
    get_bias_for_scoring,
    manually_set_bias
)


class ManualBiasRequest(BaseModel):
    """Request body for manually setting bias"""
    bias: str  # URSA_MAJOR, URSA_MINOR, NEUTRAL, TORO_MINOR, TORO_MAJOR
    dxy_current: Optional[float] = None
    vix_current: Optional[float] = None
    notes: Optional[str] = None


@router.get("/status")
async def get_status():
    """
    Get current Dollar Smile macro bias
    
    Returns:
    - Current bias (TORO/URSA/NEUTRAL)
    - Position on Dollar Smile curve
    - DXY and VIX values
    - Last update time
    """
    try:
        status = get_dollar_smile_status()
        return {
            "status": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"Error getting Dollar Smile status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receive webhook from TradingView
    
    Expected payload formats:
    
    1. Full update:
    {
        "indicator": "dollar_smile",
        "dxy_current": 104.50,
        "dxy_5d_ago": 102.00,
        "vix_current": 18.5
    }
    
    2. DXY-only update:
    {
        "indicator": "dxy",
        "value": 104.50,
        "value_5d_ago": 102.00
    }
    
    3. VIX-only update:
    {
        "indicator": "vix",
        "value": 18.5
    }
    """
    try:
        payload = await request.json()
        logger.info(f"💵 Dollar Smile webhook received: {payload}")
        
        result = update_from_webhook(payload)
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Dollar Smile webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scoring")
async def get_scoring_data():
    """
    Get Dollar Smile bias for signal scoring
    
    Use this to adjust CTA/other signal scores based on macro bias.
    
    Returns:
    - bias: Current bias level
    - allows_longs: Should we take long positions?
    - allows_shorts: Should we take short positions?
    - score_modifier: Points to add/subtract from signals
    """
    try:
        scoring = get_bias_for_scoring()
        return {
            "status": "success",
            "data": scoring
        }
    except Exception as e:
        logger.error(f"Error getting scoring data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual")
async def set_manual_bias(request: ManualBiasRequest):
    """
    Manually set Dollar Smile bias
    
    Use this when:
    - Testing the system
    - TradingView webhooks aren't set up yet
    - Override based on your own analysis
    
    Valid bias values:
    - URSA_MAJOR (1) - Strongly bearish
    - URSA_MINOR (2) - Lean bearish
    - NEUTRAL (3) - No directional bias
    - TORO_MINOR (4) - Lean bullish
    - TORO_MAJOR (5) - Strongly bullish
    """
    try:
        result = manually_set_bias(
            bias=request.bias,
            dxy_current=request.dxy_current,
            vix_current=request.vix_current,
            notes=request.notes
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting manual bias: {e}")
        raise HTTPException(status_code=500, detail=str(e))
