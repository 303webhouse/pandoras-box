"""
Bias Scheduler API Endpoints

Provides access to automated bias data with trend tracking:
- GET /bias-auto/status - Get all bias levels with trends
- GET /bias-auto/{timeframe} - Get specific timeframe (DAILY, WEEKLY, CYCLICAL)
- GET /bias-auto/{timeframe}/history - Get historical values
- POST /bias-auto/refresh - Manually trigger refresh

Hierarchical system: Cyclical → Weekly → Daily (higher timeframes modify lower)
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
        get_effective_bias,
        refresh_daily_bias,
        refresh_weekly_bias,
        refresh_cyclical_bias,
        run_scheduled_refreshes,
        get_weekly_baseline,
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
    
    Hierarchical system: Cyclical → Weekly → Daily
    
    Returns:
    - daily: Current daily bias with trend vs yesterday (includes effective bias)
    - weekly: Current weekly bias with trend vs last week (includes effective bias)
    - cyclical: Long-term macro bias (200 SMA, yield curve, Sahm Rule, etc.)
    - effective: Hierarchically modified bias levels
    """
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bias scheduler not available")
    
    try:
        status = get_bias_status()
        
        # Get effective bias (with hierarchical modifiers) for Daily
        effective_daily = get_effective_bias(BiasTimeframe.DAILY)
        
        return {
            "status": "success",
            "data": status,
            "effective": {
                "daily": effective_daily.get("effective", {}).get("daily"),
                "weekly": effective_daily.get("effective", {}).get("weekly"),
                "cyclical": effective_daily.get("raw", {}).get("cyclical"),
                "modifiers": {
                    "daily": effective_daily.get("modifiers", {}).get("daily"),
                    "weekly": effective_daily.get("modifiers", {}).get("weekly")
                }
            },
            "hierarchy_explanation": {
                "system": "Cyclical -> Weekly -> Daily",
                "description": "Higher timeframe biases modify lower timeframe biases. "
                               "TORO_MAJOR boosts +1, URSA_MAJOR drags -1, minor levels have smaller effects."
            },
            "schedule": {
                "daily": "9:45 AM ET every trading day (intraday factors)",
                "weekly": "9:45 AM ET every Monday (6-factor model)",
                "cyclical": "9:45 AM ET every Monday (long-term macro)"
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting bias status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shift-status")
async def get_shift_status():
    """
    Get current weekly bias shift status vs Monday baseline
    
    Returns:
    - baseline: Monday's baseline reading (timestamp, total_vote, level)
    - current: Current day's reading (from latest weekly bias)
    - delta: Difference between current and baseline votes
    - shift_status: STABLE, IMPROVING, STRONGLY_IMPROVING, DETERIORATING, or STRONGLY_DETERIORATING
    """
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bias scheduler not available")
    
    try:
        baseline = get_weekly_baseline()
        weekly_status = get_bias_status(BiasTimeframe.WEEKLY)
        
        # Get current reading from weekly status
        current_details = weekly_status.get("details", {})
        current_vote = current_details.get("total_vote", 0)
        current_level = weekly_status.get("level", "NEUTRAL")
        
        # Calculate shift if baseline exists
        if baseline.get("timestamp"):
            from scheduler.bias_scheduler import calculate_shift_status
            baseline_vote = baseline.get("total_vote", 0)
            shift_info = calculate_shift_status(baseline_vote, current_vote)
            
            return {
                "status": "success",
                "baseline": {
                    "timestamp": baseline.get("timestamp"),
                    "total_vote": baseline.get("total_vote"),
                    "level": baseline.get("level")
                },
                "current": {
                    "timestamp": weekly_status.get("timestamp"),
                    "total_vote": current_vote,
                    "level": current_level
                },
                "delta": shift_info["delta"],
                "shift_status": shift_info["status"],
                "description": shift_info["description"]
            }
        else:
            return {
                "status": "success",
                "baseline": None,
                "current": {
                    "timestamp": weekly_status.get("timestamp"),
                    "total_vote": current_vote,
                    "level": current_level
                },
                "message": "No baseline set yet. Baseline will be set on next Monday."
            }
        
    except Exception as e:
        logger.error(f"Error getting shift status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{timeframe}")
async def get_timeframe_bias(timeframe: str):
    """
    Get bias status for a specific timeframe
    
    Args:
        timeframe: DAILY, WEEKLY, or CYCLICAL
    
    Returns detailed bias info including:
    - Current level and timestamp
    - Previous level for trend comparison
    - Trend direction (IMPROVING, DECLINING, STABLE)
    - Details about data sources and individual factors
    """
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bias scheduler not available")
    
    try:
        tf = BiasTimeframe(timeframe.upper())
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid timeframe. Use: DAILY, WEEKLY, or CYCLICAL"
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
            detail=f"Invalid timeframe. Use: DAILY, WEEKLY, or CYCLICAL"
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
    - Daily: 9:45 AM ET every trading day (intraday factors)
    - Weekly: 9:45 AM ET every Monday (6-factor model)
    - Cyclical: 9:45 AM ET every Monday (long-term macro)
    
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
            elif tf == "CYCLICAL":
                result = await refresh_cyclical_bias()
            else:
                raise HTTPException(status_code=400, detail="Invalid timeframe. Use: DAILY, WEEKLY, or CYCLICAL")
            
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


@router.get("/effective/{timeframe}")
async def get_effective_bias_endpoint(timeframe: str):
    """
    Get the EFFECTIVE bias for a timeframe after applying hierarchical modifiers.
    
    Hierarchical System:
    - Cyclical (macro) → modifies → Weekly → modifies → Daily
    
    For example:
    - If Daily raw = TORO_MINOR but Weekly (effective) = URSA_MAJOR
    - The effective Daily might be reduced to NEUTRAL due to bearish weekly drag
    
    Args:
        timeframe: DAILY, WEEKLY, or CYCLICAL
    
    Returns:
    - raw: The unmodified bias levels
    - effective: The bias after applying hierarchical modifiers
    - modifiers: Details about what modifications were applied
    """
    if not SCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Bias scheduler not available")
    
    try:
        tf = BiasTimeframe(timeframe.upper())
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid timeframe. Use: DAILY, WEEKLY, or CYCLICAL"
        )
    
    try:
        effective = get_effective_bias(tf)
        
        return {
            "status": "success",
            "timeframe": timeframe.upper(),
            "hierarchical_system": "Cyclical -> Weekly -> Daily",
            "data": effective
        }
        
    except Exception as e:
        logger.error(f"Error getting effective {timeframe} bias: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule")
async def get_schedule_info():
    """Get information about the automatic refresh schedule"""
    return {
        "status": "success",
        "hierarchical_system": {
            "description": "Cyclical → Weekly → Daily (higher timeframes modify lower)",
            "flow": "Long-term macro sets backdrop, Weekly conditions modify it, Daily fine-tunes"
        },
        "schedule": {
            "daily": {
                "time": "9:45 AM ET",
                "days": "Monday through Friday (trading days)",
                "source": "6-factor intraday analysis: TICK/ADD, Put/Call, VIX, VOLD, TRIN, SPY vs RSP",
                "updates": "Multiple times per day"
            },
            "weekly": {
                "time": "9:45 AM ET",
                "days": "Every trading day (Monday sets baseline, daily compares to baseline)",
                "source": "6-factor weekly analysis: Index Technicals, Dollar Smile, Sector Rotation, Credit Spreads, Market Breadth, VIX Term Structure"
            },
            "cyclical": {
                "time": "9:45 AM ET",
                "days": "Every Monday (long-term macro doesn't change daily)",
                "source": "9-factor macro analysis: 200 SMA, Yield Curve, Credit Spreads, Savita, Breadth, VIX Regime, Cyclical/Defensive, Copper/Gold, Sahm Rule"
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
        },
        "weekly_shift_detection": {
            "description": "Weekly bias runs daily and compares to Monday's baseline",
            "shift_statuses": {
                "STABLE": "Delta -2 to +2 (sentiment stable)",
                "IMPROVING": "Delta +3 to +5 (sentiment improving)",
                "STRONGLY_IMPROVING": "Delta +6 or more (sentiment strongly improving)",
                "DETERIORATING": "Delta -3 to -5 (sentiment deteriorating)",
                "STRONGLY_DETERIORATING": "Delta -6 or less (sentiment strongly deteriorating)"
            },
            "alerts": "WebSocket alerts are broadcast for STRONGLY_IMPROVING and STRONGLY_DETERIORATING shifts"
        }
    }


# =========================================================================
# SAVITA INDICATOR ENDPOINTS
# =========================================================================

@router.get("/savita")
async def get_savita_status():
    """
    Get current Savita Indicator (BofA Sell Side Indicator) status
    
    This is a contrarian sentiment indicator:
    - High reading (>57.7%) = Wall Street too bullish = Bearish signal
    - Low reading (<51.3%) = Wall Street too bearish = Bullish signal
    """
    try:
        from bias_filters.savita_indicator import get_savita_reading, get_savita_config
        
        return {
            "status": "success",
            "data": get_savita_reading(),
            "config": get_savita_config()
        }
    except Exception as e:
        logger.error(f"Error getting Savita status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/savita/update")
async def update_savita(
    reading: float = Query(..., ge=40, le=70, description="New Savita reading (40-70%)"),
    date: Optional[str] = Query(None, description="Date of reading (YYYY-MM-DD)")
):
    """
    Manually update the Savita Indicator reading
    
    Use this when you see a new BofA Sell Side Indicator release in the news.
    
    Args:
        reading: The new equity allocation % (e.g., 55.9)
        date: Optional date string (defaults to today)
    """
    try:
        from bias_filters.savita_indicator import update_savita_reading
        
        result = update_savita_reading(reading, date)
        
        return {
            "status": "success",
            "message": f"Savita updated to {reading}%",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating Savita: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/savita/auto-search")
async def trigger_savita_auto_search():
    """
    Trigger Gemini AI search for latest Savita reading
    
    This uses Google Gemini to search the web for the latest
    BofA Sell Side Indicator reading. Normally runs automatically
    from 12th-23rd of each month.
    """
    try:
        from bias_filters.savita_indicator import auto_search_savita_update
        
        result = await auto_search_savita_update()
        
        return {
            "status": "success",
            "search_result": result
        }
    except Exception as e:
        logger.error(f"Error in Savita auto-search: {e}")
        raise HTTPException(status_code=500, detail=str(e))
