"""
CTA Strategy API Endpoints
Provides access to CTA scanner and analysis
"""

from fastapi import APIRouter, HTTPException
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cta", tags=["CTA Strategy"])

# Import scanner
try:
    from scanners.cta_scanner import (
        run_cta_scan,
        analyze_ticker_cta,
        scan_ticker_cta,
        get_cta_config,
        set_cta_enabled,
        CTA_SCANNER_AVAILABLE
    )
except ImportError:
    CTA_SCANNER_AVAILABLE = False
    logger.warning("CTA Scanner not available - install: pip install yfinance pandas_ta")


@router.get("/scan")
async def cta_full_scan(include_watchlist: bool = True):
    """
    Run full CTA scan on watchlist + S&P 500
    
    Returns signals with Entry/Stop/Target for each:
    - Golden Touch (rare, high-probability)
    - Two-Close + Volume confirmations
    - Pullback entries in Max Long zone
    - Zone upgrades
    """
    if not CTA_SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="CTA Scanner not available. Install: pip install yfinance pandas_ta")
    
    try:
        results = await run_cta_scan(include_watchlist=include_watchlist)
        return results
    except Exception as e:
        logger.error(f"CTA scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/{ticker}")
async def cta_analyze_ticker(ticker: str):
    """
    Detailed CTA analysis of a single ticker
    
    Returns:
    - Current CTA zone
    - Distance to all key SMAs
    - Any active signals
    - Recommendation (action + entry/stop/target if applicable)
    """
    if not CTA_SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="CTA Scanner not available")
    
    try:
        result = await analyze_ticker_cta(ticker)
        return result
    except Exception as e:
        logger.error(f"CTA analysis error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/{ticker}")
async def cta_ticker_signals(ticker: str):
    """
    Get active CTA signals for a specific ticker
    """
    if not CTA_SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="CTA Scanner not available")
    
    try:
        signals = await scan_ticker_cta(ticker.upper())
        return {
            "ticker": ticker.upper(),
            "signal_count": len(signals),
            "signals": signals
        }
    except Exception as e:
        logger.error(f"CTA signals error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan/custom")
async def cta_custom_scan(tickers: List[str]):
    """
    Run CTA scan on custom list of tickers
    """
    if not CTA_SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="CTA Scanner not available")
    
    if not tickers or len(tickers) == 0:
        raise HTTPException(status_code=400, detail="No tickers provided")
    
    if len(tickers) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 tickers per scan")
    
    try:
        results = await run_cta_scan(tickers=[t.upper() for t in tickers], include_watchlist=False)
        return results
    except Exception as e:
        logger.error(f"CTA custom scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def cta_get_config():
    """Get current CTA scanner configuration"""
    if not CTA_SCANNER_AVAILABLE:
        return {"available": False}
    return {"available": True, "config": get_cta_config()}


@router.post("/config/enable")
async def cta_set_enabled(enabled: bool):
    """Enable or disable CTA scanner"""
    if not CTA_SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="CTA Scanner not available")
    
    set_cta_enabled(enabled)
    return {"enabled": enabled}


@router.post("/scan/push")
async def cta_scan_and_push():
    """
    Run CTA scan and push signals to Trade Ideas
    This triggers the scheduled scan manually
    """
    if not CTA_SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="CTA Scanner not available")
    
    try:
        from scheduler.bias_scheduler import run_cta_scan_scheduled
        
        await run_cta_scan_scheduled()
        
        return {
            "status": "success",
            "message": "CTA scan complete - signals pushed to Trade Ideas"
        }
    except Exception as e:
        logger.error(f"Error in manual CTA scan push: {e}")
        raise HTTPException(status_code=500, detail=str(e))
