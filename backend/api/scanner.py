"""
Scanner API Endpoints
Provides REST API for the Hunter scanner functionality
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory cache for latest scan results
_latest_scan_results = {
    "scan_time": None,
    "ursa_signals": [],
    "taurus_signals": [],
    "status": "idle"
}

# Try to import scanner
try:
    from scanners.hunter import (
        run_full_scan, 
        get_scanner_config, 
        set_scanner_enabled,
        update_scanner_filters,
        SP500_TOP_100,
        SCANNER_AVAILABLE
    )
except ImportError:
    SCANNER_AVAILABLE = False
    logger.warning("Scanner module not available")


class ScanRequest(BaseModel):
    """Request model for running a scan"""
    mode: str = "all"  # "all", "ursa", or "taurus"
    tickers: Optional[List[str]] = None


class FilterUpdate(BaseModel):
    """Request model for updating scanner filters"""
    adx_min: Optional[int] = None
    rsi_bull_max: Optional[int] = None
    rsi_bear_min: Optional[int] = None
    rvol_min: Optional[float] = None


@router.get("/scanner/status")
async def get_scanner_status():
    """Get current scanner status and configuration"""
    if not SCANNER_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Scanner dependencies not installed",
            "install_command": "pip install yfinance pandas_ta"
        }
    
    config = get_scanner_config()
    return {
        "status": _latest_scan_results["status"],
        "enabled": config["enabled"],
        "last_scan": _latest_scan_results["scan_time"],
        "signals_cached": {
            "ursa": len(_latest_scan_results["ursa_signals"]),
            "taurus": len(_latest_scan_results["taurus_signals"])
        },
        "config": config
    }


@router.get("/scanner/results")
async def get_scan_results(mode: str = "all"):
    """
    Get the latest scan results
    
    Args:
        mode: "all", "ursa", or "taurus"
    """
    if _latest_scan_results["scan_time"] is None:
        return {
            "status": "no_data",
            "message": "No scan has been run yet. POST to /api/scanner/run to start a scan."
        }
    
    result = {
        "scan_time": _latest_scan_results["scan_time"],
        "status": "success"
    }
    
    if mode in ["all", "ursa"]:
        result["ursa_signals"] = _latest_scan_results["ursa_signals"]
    
    if mode in ["all", "taurus"]:
        result["taurus_signals"] = _latest_scan_results["taurus_signals"]
    
    return result


@router.post("/scanner/run")
async def run_scanner(request: ScanRequest, background_tasks: BackgroundTasks):
    """
    Trigger a new scan
    
    This runs in the background and updates the cached results.
    Poll /api/scanner/results to get updated results.
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Scanner not available. Install: pip install yfinance pandas_ta"
        )
    
    # Update status
    _latest_scan_results["status"] = "scanning"
    
    # Run scan in background
    background_tasks.add_task(
        _run_scan_task,
        request.tickers,
        request.mode
    )
    
    return {
        "status": "started",
        "message": f"Scan started in background (mode={request.mode})",
        "check_results": "/api/scanner/results"
    }


async def _run_scan_task(tickers: Optional[List[str]], mode: str):
    """Background task to run the scan"""
    global _latest_scan_results
    
    try:
        results = await run_full_scan(tickers=tickers, mode=mode)
        
        _latest_scan_results["scan_time"] = results.get("scan_time")
        _latest_scan_results["ursa_signals"] = results.get("ursa_signals", [])
        _latest_scan_results["taurus_signals"] = results.get("taurus_signals", [])
        _latest_scan_results["status"] = "complete"
        
        logger.info(f"✅ Scan complete: {len(_latest_scan_results['ursa_signals'])} URSA, {len(_latest_scan_results['taurus_signals'])} TAURUS")
        
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        _latest_scan_results["status"] = f"error: {str(e)}"


@router.post("/scanner/enable")
async def enable_scanner(enabled: bool = True):
    """Enable or disable the scanner"""
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Scanner not available")
    
    set_scanner_enabled(enabled)
    return {"status": "success", "scanner_enabled": enabled}


@router.put("/scanner/filters")
async def update_filters(filters: FilterUpdate):
    """Update scanner filter parameters"""
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Scanner not available")
    
    updates = {k: v for k, v in filters.dict().items() if v is not None}
    
    if updates:
        update_scanner_filters(updates)
    
    return {
        "status": "success",
        "updated_filters": updates,
        "current_config": get_scanner_config()
    }


@router.get("/scanner/tickers")
async def get_available_tickers():
    """Get list of tickers available for scanning"""
    if not SCANNER_AVAILABLE:
        return {"tickers": [], "message": "Scanner not available"}
    
    return {
        "tickers": SP500_TOP_100,
        "count": len(SP500_TOP_100),
        "description": "S&P 500 Top 100 most liquid stocks"
    }
