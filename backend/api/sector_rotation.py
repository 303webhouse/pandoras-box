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


# =========================================================================
# SECTOR MOMENTUM / ROTATION DETECTOR (11-sector sharp rotation tracking)
# =========================================================================

@router.get("/momentum")
async def get_sector_momentum():
    """
    Get current sector rotation momentum for all 11 sectors.
    
    Returns each sector's relative strength vs SPY, rotation momentum,
    status (SURGING/DUMPING/STEADY), acceleration, and rank changes.
    """
    try:
        from bias_filters.sector_momentum import get_cached_rotation
        data = await get_cached_rotation()
        if not data:
            return {
                "status": "no_data",
                "message": "Sector rotation data not yet computed. Trigger /sector-rotation/momentum/refresh."
            }
        
        # Sort by rotation momentum for display
        sorted_sectors = sorted(
            data.values(),
            key=lambda x: x.get("rotation_momentum", 0),
            reverse=True,
        )
        
        surging = [s for s in sorted_sectors if s["status"] == "SURGING"]
        dumping = [s for s in sorted_sectors if s["status"] == "DUMPING"]
        
        return {
            "status": "success",
            "sectors": sorted_sectors,
            "summary": {
                "surging": [s["sector"] for s in surging],
                "dumping": [s["sector"] for s in dumping],
                "surging_count": len(surging),
                "dumping_count": len(dumping),
            },
            "updated_at": sorted_sectors[0].get("updated_at") if sorted_sectors else None,
        }
    except Exception as e:
        logger.error(f"Error getting sector momentum: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/momentum/refresh")
async def refresh_sector_momentum():
    """Manually trigger sector rotation momentum computation."""
    try:
        from bias_filters.sector_momentum import refresh_sector_rotation
        data = await refresh_sector_rotation()
        
        if not data:
            return {"status": "error", "message": "Failed to compute sector rotation data"}
        
        surging = [s for s in data.values() if s["status"] == "SURGING"]
        dumping = [s for s in data.values() if s["status"] == "DUMPING"]
        
        return {
            "status": "success",
            "sectors_computed": len(data),
            "surging": [s["sector"] for s in surging],
            "dumping": [s["sector"] for s in dumping],
        }
    except Exception as e:
        logger.error(f"Error refreshing sector momentum: {e}")
        raise HTTPException(status_code=500, detail=str(e))
