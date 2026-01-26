"""
Sector Rotation API Endpoints
Weekly bias indicator based on offensive vs defensive sector leadership

Endpoints:
- GET /sector-rotation/status - Get current sector rotation bias
- POST /sector-rotation/refresh - Manually trigger refresh
- GET /sector-rotation/scoring - Get bias for signal scoring
"""

from fastapi import APIRouter, HTTPException
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sector-rotation", tags=["Sector Rotation Bias"])

# Import Sector Rotation module
from bias_filters.sector_rotation import (
    get_sector_rotation_status,
    auto_fetch_and_update,
    get_bias_for_scoring
)


@router.get("/status")
async def get_status():
    """
    Get current Sector Rotation bias
    
    Returns:
    - Current bias (TORO/URSA/NEUTRAL)
    - Offensive vs defensive sector performance
    - Spread between sectors
    - Individual sector returns
    """
    try:
        status = get_sector_rotation_status()
        return {
            "status": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"Error getting Sector Rotation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
async def refresh_sector_rotation():
    """
    Manually trigger sector rotation data refresh
    
    Fetches latest sector ETF data via yfinance and recalculates bias.
    """
    try:
        result = await auto_fetch_and_update()
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing sector rotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scoring")
async def get_scoring_data():
    """
    Get Sector Rotation bias for signal scoring
    
    Returns:
    - bias: Current bias level
    - allows_longs: Should we take long positions?
    - allows_shorts: Should we take short positions?
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
