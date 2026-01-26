"""
Market Indicators API Endpoints
Combined endpoints for Credit Spreads, Market Breadth, and VIX Term Structure

Endpoints:
- GET /market-indicators/credit-spreads - HYG vs TLT risk appetite
- GET /market-indicators/market-breadth - RSP vs SPY participation
- GET /market-indicators/vix-term - VIX vs VIX3M sentiment
- POST /market-indicators/refresh-all - Refresh all indicators
"""

from fastapi import APIRouter, HTTPException
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market-indicators", tags=["Market Indicators"])


# ========== Credit Spreads ==========

@router.get("/credit-spreads")
async def get_credit_spreads_status():
    """
    Get current Credit Spreads bias (HYG vs TLT)
    
    HYG outperforming = Risk-On (Bullish)
    TLT outperforming = Risk-Off (Bearish)
    """
    try:
        from bias_filters.credit_spreads import get_credit_spread_status
        status = get_credit_spread_status()
        return {"status": "success", "data": status}
    except Exception as e:
        logger.error(f"Error getting credit spreads status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/credit-spreads/refresh")
async def refresh_credit_spreads():
    """Manually refresh credit spreads data"""
    try:
        from bias_filters.credit_spreads import auto_fetch_and_update
        result = await auto_fetch_and_update()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing credit spreads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Market Breadth ==========

@router.get("/market-breadth")
async def get_market_breadth_status():
    """
    Get current Market Breadth bias (RSP vs SPY)
    
    RSP outperforming = Healthy breadth (Bullish)
    SPY outperforming = Narrow leadership (Bearish)
    """
    try:
        from bias_filters.market_breadth import get_market_breadth_status
        status = get_market_breadth_status()
        return {"status": "success", "data": status}
    except Exception as e:
        logger.error(f"Error getting market breadth status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/market-breadth/refresh")
async def refresh_market_breadth():
    """Manually refresh market breadth data"""
    try:
        from bias_filters.market_breadth import auto_fetch_and_update
        result = await auto_fetch_and_update()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing market breadth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== VIX Term Structure ==========

@router.get("/vix-term")
async def get_vix_term_status():
    """
    Get current VIX Term Structure bias (VIX vs VIX3M)
    
    Contango (VIX < VIX3M) = Calm expectations (Bullish)
    Backwardation (VIX > VIX3M) = Near-term fear (Bearish)
    """
    try:
        from bias_filters.vix_term_structure import get_vix_term_status
        status = get_vix_term_status()
        return {"status": "success", "data": status}
    except Exception as e:
        logger.error(f"Error getting VIX term status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vix-term/refresh")
async def refresh_vix_term():
    """Manually refresh VIX term structure data"""
    try:
        from bias_filters.vix_term_structure import auto_fetch_and_update
        result = await auto_fetch_and_update()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing VIX term structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Refresh All ==========

@router.post("/refresh-all")
async def refresh_all_indicators():
    """
    Refresh all market indicators at once
    
    Returns status of each indicator refresh.
    """
    results = {}
    
    # Credit Spreads
    try:
        from bias_filters.credit_spreads import auto_fetch_and_update as fetch_credit
        cs_result = await fetch_credit()
        results["credit_spreads"] = cs_result
    except Exception as e:
        results["credit_spreads"] = {"status": "error", "message": str(e)}
    
    # Market Breadth
    try:
        from bias_filters.market_breadth import auto_fetch_and_update as fetch_breadth
        mb_result = await fetch_breadth()
        results["market_breadth"] = mb_result
    except Exception as e:
        results["market_breadth"] = {"status": "error", "message": str(e)}
    
    # VIX Term Structure
    try:
        from bias_filters.vix_term_structure import auto_fetch_and_update as fetch_vix
        vt_result = await fetch_vix()
        results["vix_term_structure"] = vt_result
    except Exception as e:
        results["vix_term_structure"] = {"status": "error", "message": str(e)}
    
    return {
        "status": "success",
        "message": "All market indicators refreshed",
        "results": results
    }


# ========== Summary ==========

@router.get("/summary")
async def get_all_indicators_summary():
    """
    Get summary of all market indicators
    
    Returns current bias and level for each indicator.
    """
    summary = {}
    
    try:
        from bias_filters.credit_spreads import get_bias_for_scoring as get_cs
        summary["credit_spreads"] = get_cs()
    except:
        summary["credit_spreads"] = {"bias": "UNKNOWN", "bias_level": 3}
    
    try:
        from bias_filters.market_breadth import get_bias_for_scoring as get_mb
        summary["market_breadth"] = get_mb()
    except:
        summary["market_breadth"] = {"bias": "UNKNOWN", "bias_level": 3}
    
    try:
        from bias_filters.vix_term_structure import get_bias_for_scoring as get_vt
        summary["vix_term_structure"] = get_vt()
    except:
        summary["vix_term_structure"] = {"bias": "UNKNOWN", "bias_level": 3}
    
    try:
        from bias_filters.dollar_smile import get_bias_for_scoring as get_ds
        summary["dollar_smile"] = get_ds()
    except:
        summary["dollar_smile"] = {"bias": "UNKNOWN", "bias_level": 3}
    
    try:
        from bias_filters.sector_rotation import get_bias_for_scoring as get_sr
        summary["sector_rotation"] = get_sr()
    except:
        summary["sector_rotation"] = {"bias": "UNKNOWN", "bias_level": 3}
    
    return {
        "status": "success",
        "data": summary
    }
