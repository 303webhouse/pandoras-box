"""
Alerts API - Black Swan and Earnings Alerts
"""

from fastapi import APIRouter, Query, Depends
from typing import List, Dict, Any, Optional
import logging
import json

from pydantic import BaseModel

from utils.pivot_auth import verify_pivot_key

router = APIRouter()
logger = logging.getLogger(__name__)

PIVOT_ALERTS_KEY = "pivot:alerts"
PIVOT_ALERTS_MAX = 100


class PivotAlertRequest(BaseModel):
    """Pivot alert payload"""
    type: str = "anomaly"
    message: str
    timestamp: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@router.get("/alerts/black-swan")
async def get_black_swan_alerts():
    """
    Get all active Black Swan alerts
    
    Returns alerts for:
    - Fed events (FOMC today or upcoming)
    - VIX spikes
    - Gap moves in major indices
    - Volume surges
    """
    try:
        from alerts.black_swan import get_all_black_swan_alerts, should_pause_trading
        
        alerts = get_all_black_swan_alerts()
        pause_trading = should_pause_trading()
        
        return {
            "status": "success",
            "alerts": alerts,
            "total_alerts": len(alerts),
            "should_pause_trading": pause_trading,
            "recommendation": "Pause new entries and tighten stops" if pause_trading else "Normal trading conditions"
        }
    except Exception as e:
        logger.error(f"Error fetching Black Swan alerts: {e}")
        return {
            "status": "error",
            "detail": str(e),
            "alerts": []
        }


@router.post("/alerts/pivot")
async def receive_pivot_alert(payload: PivotAlertRequest, _: str = Depends(verify_pivot_key)):
    """Store Pivot anomaly alerts for dashboard display."""
    try:
        from database.redis_client import get_redis_client, sanitize_for_json

        client = await get_redis_client()
        if not client:
            return {"status": "error", "detail": "Redis unavailable"}

        record = sanitize_for_json(payload.model_dump())
        await client.lpush(PIVOT_ALERTS_KEY, json.dumps(record))
        await client.ltrim(PIVOT_ALERTS_KEY, 0, PIVOT_ALERTS_MAX - 1)

        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error storing Pivot alert: {e}")
        return {"status": "error", "detail": str(e)}


@router.get("/alerts/earnings/{ticker}")
async def get_earnings_alert(ticker: str):
    """
    Check earnings timing for a specific ticker
    
    Returns:
    - When next earnings is
    - Whether to avoid (pre-earnings) or target (post-earnings)
    - Score adjustment recommendation
    """
    try:
        from alerts.earnings_calendar import check_earnings_timing
        
        ticker = ticker.upper().strip()
        earnings_info = check_earnings_timing(ticker)
        
        return {
            "status": "success",
            **earnings_info
        }
    except Exception as e:
        logger.error(f"Error checking earnings for {ticker}: {e}")
        return {
            "status": "error",
            "detail": str(e),
            "ticker": ticker
        }


@router.get("/alerts/earnings/check-positions")
async def check_positions_earnings():
    """
    Check all open positions for upcoming earnings
    
    Returns warnings for any positions with earnings in next 3 days
    """
    try:
        from alerts.earnings_calendar import check_open_position_earnings
        from api.positions import _open_positions
        
        warnings = check_open_position_earnings(_open_positions)
        
        return {
            "status": "success",
            "warnings": warnings,
            "total_warnings": len(warnings),
            "recommendation": "Review positions with upcoming earnings" if warnings else "No earnings concerns"
        }
    except Exception as e:
        logger.error(f"Error checking position earnings: {e}")
        return {
            "status": "error",
            "detail": str(e),
            "warnings": []
        }
