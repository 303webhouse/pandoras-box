"""
Bias Scheduler API Endpoints

Provides access to automated bias data with trend tracking:
- GET /bias-auto/status - Get all bias levels with trends
- GET /bias-auto/{timeframe} - Get specific timeframe
- GET /bias-auto/{timeframe}/history - Get historical values
- POST /bias-auto/refresh - Manually trigger refresh
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bias-auto", tags=["Bias Scheduler"])

# Import scheduler functions
try:
    from scheduler.bias_scheduler import (
        get_bias_status,
        get_bias_history,
        refresh_daily_bias,
        refresh_weekly_bias,
        refresh_monthly_bias,
        run_scheduled_refreshes,
        BiasTimeframe
    )
    SCHEDULER_AVAILABLE = True
except ImportError as e:
    SCHEDULER_AVAILABLE = False
    logger.warning(f"Bias scheduler not available: {e}")


@router.get("/status")
async def get_all_bias_status():
    """
    Get current bias status for all timeframes with trend information
    
    Returns:
    - daily: Current daily bias with trend vs yesterday
    - weekly: Current weekly bias with trend vs last week
    - monthly: Current monthly bias with trend vs last month
    """
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bias scheduler not available")
    
    try:
        status = get_bias_status()
        
        return {
            "status": "success",
            "data": status,
            "schedule": {
                "daily": "9:45 AM ET every trading day",
                "weekly": "9:45 AM ET every Monday",
                "monthly": "9:45 AM ET first trading day of month"
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting bias status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{timeframe}")
async def get_timeframe_bias(timeframe: str):
    """
    Get bias status for a specific timeframe
    
    Args:
        timeframe: DAILY, WEEKLY, or MONTHLY
    
    Returns detailed bias info including:
    - Current level and timestamp
    - Previous level for trend comparison
    - Trend direction (IMPROVING, DECLINING, STABLE)
    - Details about data sources
    """
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bias scheduler not available")
    
    try:
        tf = BiasTimeframe(timeframe.upper())
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid timeframe. Use: DAILY, WEEKLY, or MONTHLY"
        )
    
    try:
        status = get_bias_status(tf)
        
        return {
            "status": "success",
            "data": status
        }
        
    except Exception as e:
        logger.error(f"Error getting {timeframe} bias: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{timeframe}/history")
async def get_timeframe_history(
    timeframe: str,
    limit: int = Query(10, ge=1, le=30, description="Number of historical entries")
):
    """
    Get historical bias values for a timeframe
    
    Useful for seeing how bias has changed over time.
    """
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bias scheduler not available")
    
    try:
        tf = BiasTimeframe(timeframe.upper())
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid timeframe. Use: DAILY, WEEKLY, or MONTHLY"
        )
    
    try:
        history = get_bias_history(tf, limit)
        
        return {
            "status": "success",
            "timeframe": timeframe.upper(),
            "count": len(history),
            "history": history
        }
        
    except Exception as e:
        logger.error(f"Error getting {timeframe} history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
async def manual_refresh(
    timeframe: Optional[str] = Query(None, description="Specific timeframe to refresh, or all if not specified")
):
    """
    Manually trigger bias refresh
    
    Normally this runs automatically:
    - Daily: 9:45 AM ET every trading day
    - Weekly: 9:45 AM ET every Monday
    - Monthly: 9:45 AM ET first trading day of month
    
    Use this endpoint to force a refresh outside the schedule.
    """
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bias scheduler not available")
    
    try:
        if timeframe:
            tf = timeframe.upper()
            if tf == "DAILY":
                result = await refresh_daily_bias()
            elif tf == "WEEKLY":
                result = await refresh_weekly_bias()
            elif tf == "MONTHLY":
                result = await refresh_monthly_bias()
            else:
                raise HTTPException(status_code=400, detail="Invalid timeframe")
            
            return {
                "status": "success",
                "message": f"{tf} bias refreshed",
                "result": result
            }
        else:
            # Refresh all
            await run_scheduled_refreshes()
            
            return {
                "status": "success",
                "message": "All biases refreshed",
                "data": get_bias_status()
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing bias: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule")
async def get_schedule_info():
    """Get information about the automatic refresh schedule"""
    return {
        "status": "success",
        "schedule": {
            "daily": {
                "time": "9:45 AM ET",
                "days": "Monday through Friday (trading days)",
                "source": "Hybrid Scanner aggregate technical sentiment"
            },
            "weekly": {
                "time": "9:45 AM ET",
                "days": "Monday only",
                "source": "Weekly technical analysis of major indices (SPY, QQQ, IWM, DIA)"
            },
            "monthly": {
                "time": "9:45 AM ET",
                "days": "First trading day of month",
                "source": "Monthly technical analysis of major indices"
            }
        },
        "trend_tracking": {
            "description": "Each refresh stores the previous value to calculate trends",
            "directions": {
                "IMPROVING": "More bullish than previous period",
                "DECLINING": "More bearish than previous period",
                "STABLE": "Same as previous period",
                "NEW": "First reading (no previous data)"
            }
        }
    }
