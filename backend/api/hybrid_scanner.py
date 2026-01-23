"""
Hybrid Market Scanner API Endpoints
Technical + Fundamental analysis with directional change detection

Endpoints:
- GET /hybrid/scan - Full market scan
- GET /hybrid/technical/{ticker} - Single ticker technical analysis
- GET /hybrid/fundamental/{ticker} - Single ticker fundamental analysis
- GET /hybrid/combined/{ticker} - Combined analysis for single ticker
- GET /hybrid/changes - Recent directional changes
- GET /hybrid/candidates - Strategy candidates (Ursa Hunter feed)
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hybrid", tags=["Hybrid Scanner"])

# Import scanner
try:
    from scanners.hybrid_scanner import (
        get_scanner,
        scan_market,
        get_technical,
        get_fundamental,
        refresh_technicals,
        get_aggregate_sentiment,
        is_cache_fresh,
        TRADINGVIEW_TA_AVAILABLE,
        YFINANCE_AVAILABLE
    )
    SCANNER_AVAILABLE = True
except ImportError as e:
    SCANNER_AVAILABLE = False
    logger.warning(f"Hybrid Scanner not available: {e}")


@router.get("/status")
async def get_scanner_status():
    """Check scanner availability and dependencies"""
    return {
        "available": SCANNER_AVAILABLE,
        "dependencies": {
            "tradingview_ta": TRADINGVIEW_TA_AVAILABLE if SCANNER_AVAILABLE else False,
            "yfinance": YFINANCE_AVAILABLE if SCANNER_AVAILABLE else False,
        },
        "message": "Hybrid Scanner ready" if SCANNER_AVAILABLE else "Scanner dependencies not installed"
    }


@router.get("/price/{ticker}")
async def get_current_price(ticker: str):
    """
    Get current price for a ticker (for P&L calculation)
    Fast lookup using yfinance
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker.upper())
        hist = stock.history(period="1d")
        
        if hist.empty:
            return {"ticker": ticker, "price": None, "error": "No data"}
        
        price = float(hist['Close'].iloc[-1])
        return {"ticker": ticker.upper(), "price": round(price, 2)}
    except Exception as e:
        logger.error(f"Error getting price for {ticker}: {e}")
        return {"ticker": ticker, "price": None, "error": str(e)}


@router.get("/scan")
async def run_market_scan(
    tickers: Optional[str] = Query(None, description="Comma-separated list of tickers (optional, uses default universe)"),
    interval: str = Query("1d", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d, 1W, 1M"),
    sector: Optional[str] = Query(None, description="Filter by sector (e.g., Technology, Healthcare)"),
    market_cap: Optional[str] = Query(None, description="Filter by cap class (Mega Cap, Large Cap, Mid Cap, Small Cap)"),
    sort_by: str = Query("signal_strength", description="Sort by: signal_strength, analyst_upside"),
    macro_bias: str = Query("NEUTRAL", description="Macro bias: BULLISH, BEARISH, NEUTRAL"),
    detect_changes: bool = Query(True, description="Track directional changes"),
    limit: int = Query(50, description="Max results", ge=1, le=200)
):
    """
    Run full market scan
    
    Scans universe of stocks for technical signals and fundamental data.
    Detects directional changes and filters candidates for strategies.
    
    Example:
    - /hybrid/scan?sort_by=analyst_upside&sector=Technology
    - /hybrid/scan?macro_bias=BEARISH&detect_changes=true
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    try:
        # Parse tickers if provided
        ticker_list = None
        if tickers:
            ticker_list = [t.strip().upper() for t in tickers.split(",")]
        
        result = await scan_market(
            tickers=ticker_list,
            interval=interval,
            filter_sector=sector,
            filter_market_cap=market_cap,
            sort_by=sort_by,
            macro_bias=macro_bias,
            detect_changes=detect_changes,
            limit=limit
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Market scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/technical/{ticker}")
async def get_technical_analysis(
    ticker: str,
    interval: str = Query("1d", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d, 1W, 1M")
):
    """
    Get TradingView technical analysis for a single ticker
    
    Returns:
    - Overall signal (STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL)
    - Signal score (Buy/Sell/Neutral counts)
    - Oscillator values (RSI, MACD, Stoch, etc.)
    - Moving average positions
    - Current price data
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    try:
        result = get_technical(ticker.upper(), interval)
        
        if result.get("signal") == "ERROR":
            raise HTTPException(status_code=404, detail=result.get("error", "Analysis failed"))
        
        return {
            "status": "success",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Technical analysis error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fundamental/{ticker}")
async def get_fundamental_analysis(ticker: str):
    """
    Get fundamental data for a single ticker
    
    Returns:
    - Analyst consensus (STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL)
    - Price targets (current, mean, high, low)
    - Upside/downside percentage
    - Company metadata (sector, industry, market cap)
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    try:
        result = get_fundamental(ticker.upper())
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return {
            "status": "success",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fundamental analysis error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/combined/{ticker}")
async def get_combined_analysis(
    ticker: str,
    interval: str = Query("1d", description="Technical analysis timeframe")
):
    """
    Get combined technical + fundamental analysis for a single ticker
    
    This replicates the "two gauge" view from the spec:
    - Top Gauge: Technical signal (TradingView)
    - Bottom Gauge: Analyst rating (yfinance)
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    try:
        ticker = ticker.upper()
        
        # Get both analyses
        technical = get_technical(ticker, interval)
        fundamental = get_fundamental(ticker)
        
        # Calculate combined score
        tech_signal = technical.get("signal", "NEUTRAL")
        analyst_consensus = fundamental.get("analyst", {}).get("consensus", "NONE")
        upside_pct = fundamental.get("price_target", {}).get("upside_pct")
        
        # Map signals to scores
        tech_score_map = {
            "STRONG_BUY": 5, "BUY": 4, "NEUTRAL": 3, "SELL": 2, "STRONG_SELL": 1
        }
        analyst_score_map = {
            "STRONG_BUY": 5, "BUY": 4, "HOLD": 3, "SELL": 2, "STRONG_SELL": 1, "NONE": 3
        }
        
        tech_score = tech_score_map.get(tech_signal, 3)
        analyst_score = analyst_score_map.get(analyst_consensus, 3)
        
        # Combined recommendation
        combined_score = (tech_score + analyst_score) / 2
        if combined_score >= 4.5:
            combined_rec = "STRONG_BUY"
        elif combined_score >= 3.5:
            combined_rec = "BUY"
        elif combined_score >= 2.5:
            combined_rec = "NEUTRAL"
        elif combined_score >= 1.5:
            combined_rec = "SELL"
        else:
            combined_rec = "STRONG_SELL"
        
        return {
            "status": "success",
            "ticker": ticker,
            "technical_gauge": {
                "signal": tech_signal,
                "score": technical.get("signal_score", {}),
                "oscillators_summary": technical.get("oscillators", {}).get("summary"),
                "ma_summary": technical.get("moving_averages", {}).get("summary"),
                "from_cache": technical.get("from_cache", False),
                "timestamp": technical.get("timestamp"),
            },
            "analyst_gauge": {
                "consensus": analyst_consensus,
                "rating_mean": fundamental.get("analyst", {}).get("rating_mean"),
                "num_analysts": fundamental.get("analyst", {}).get("num_analysts"),
                "upside_pct": upside_pct,
                "price_target": fundamental.get("price_target", {}).get("mean"),
            },
            "combined": {
                "recommendation": combined_rec,
                "score": round(combined_score, 1),
            },
            "metadata": fundamental.get("metadata", {}),
            "price": technical.get("price", {}),
        }
        
    except Exception as e:
        logger.error(f"Combined analysis error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes")
async def get_directional_changes():
    """
    Get recent directional signal changes
    
    Returns tickers that have flipped from:
    - Neutral/Sell → Buy (Bullish Change)
    - Neutral/Buy → Sell (Bearish Change)
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    try:
        scanner = get_scanner()
        state = scanner.state
        
        # Find recent changes by comparing timestamps
        changes = []
        for ticker, data in state.get("signals", {}).items():
            changes.append({
                "ticker": ticker,
                "current_signal": data.get("signal"),
                "updated_at": data.get("updated_at")
            })
        
        # Sort by most recent
        changes.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        
        return {
            "status": "success",
            "last_scan": state.get("last_scan"),
            "total_tracked": len(state.get("signals", {})),
            "recent_updates": changes[:50]
        }
        
    except Exception as e:
        logger.error(f"Error getting changes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candidates/{strategy}")
async def get_strategy_candidates(
    strategy: str,
    limit: int = Query(20, description="Max candidates", ge=1, le=100)
):
    """
    Get pre-filtered candidates for a specific strategy
    
    Strategies:
    - ursa_hunter: Bearish candidates (Sell signals)
    - bullish_hunter: Bullish candidates (Buy signals)
    
    This is the TOP-OF-FUNNEL filter that feeds into strategy execution.
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    strategy = strategy.lower()
    
    if strategy not in ["ursa_hunter", "bullish_hunter", "ursa", "bullish"]:
        raise HTTPException(status_code=400, detail="Invalid strategy. Use: ursa_hunter, bullish_hunter")
    
    try:
        scanner = get_scanner()
        
        bias = "BEARISH" if "ursa" in strategy else "BULLISH"
        candidates = scanner.get_strategy_candidates(bias)
        
        return {
            "status": "success",
            "strategy": strategy,
            "bias": bias,
            "candidate_count": len(candidates),
            "candidates": candidates[:limit]
        }
        
    except Exception as e:
        logger.error(f"Error getting candidates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# DAILY CACHE & AGGREGATE ENDPOINTS (for Macro Bias)
# =========================================================================

@router.get("/cache-status")
async def get_cache_status():
    """
    Check technical cache freshness
    
    Cache is refreshed daily at 9:45 AM ET (15 min after market open).
    Returns whether cache is valid and when it was last updated.
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    try:
        scanner = get_scanner()
        cache = scanner.technical_cache
        
        return {
            "status": "success",
            "cache_valid": scanner.is_cache_valid(),
            "last_refresh": cache.get("last_refresh"),
            "tickers_cached": len(cache.get("tickers", {})),
            "refresh_schedule": "Daily at 9:45 AM ET",
            "message": "Cache is fresh" if scanner.is_cache_valid() else "Cache needs refresh"
        }
        
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
async def trigger_technical_refresh(
    tickers: Optional[str] = Query(None, description="Comma-separated tickers to refresh (optional)")
):
    """
    Trigger daily technical data refresh
    
    Should be called once daily at 9:45 AM ET (15 min after market open).
    This pulls fresh technical signals from TradingView and caches them.
    
    Rate limits are respected by adding delays between calls.
    Takes approximately 30-60 seconds for the default watchlist.
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    try:
        ticker_list = None
        if tickers:
            ticker_list = [t.strip().upper() for t in tickers.split(",")]
        
        result = await refresh_technicals(ticker_list)
        
        return {
            "status": "success",
            "message": f"Refreshed {result.get('success_count')} tickers",
            **result
        }
        
    except Exception as e:
        logger.error(f"Error refreshing technical cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aggregate")
async def get_aggregate_technical_sentiment():
    """
    Get aggregate technical sentiment across all cached tickers
    
    This is used for the Daily Macro Bias indicator:
    - STRONG_BULLISH: 60%+ tickers showing Buy
    - BULLISH: 50-60% tickers showing Buy
    - NEUTRAL: Mixed signals
    - BEARISH: 50-60% tickers showing Sell  
    - STRONG_BEARISH: 60%+ tickers showing Sell
    
    Use this to gauge overall market technical health.
    """
    if not SCANNER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Hybrid Scanner not available")
    
    try:
        aggregate = get_aggregate_sentiment()
        
        return {
            "status": "success",
            "aggregate": aggregate,
            "cache_valid": is_cache_fresh(),
            "use_for": "Daily Macro Bias - Market Technical Health"
        }
        
    except Exception as e:
        logger.error(f"Error getting aggregate sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sectors")
async def get_available_sectors():
    """Get list of available sectors for filtering"""
    sectors = [
        "Technology",
        "Healthcare", 
        "Financial Services",
        "Consumer Cyclical",
        "Consumer Defensive",
        "Industrials",
        "Energy",
        "Basic Materials",
        "Utilities",
        "Real Estate",
        "Communication Services"
    ]
    
    return {
        "sectors": sectors,
        "market_cap_classes": ["Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap"]
    }
