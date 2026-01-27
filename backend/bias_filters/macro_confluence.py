"""
Macro Confluence Checker
Validates signals against macro environment for high-conviction trades

Checks:
1. BTC vs 50 SMA - Crypto momentum
2. DXY trend - Risk-on vs Risk-off
3. QQQ vs 200 SMA - Tech/Risk asset health

When all macro factors align with signal direction:
- Bullish + all bullish macro = APIS CALL
- Bearish + all bearish macro = KODIAK CALL
"""

import logging
from typing import Dict, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import yfinance for real-time data
try:
    import yfinance as yf
    import pandas as pd
    MACRO_DATA_AVAILABLE = True
except ImportError:
    MACRO_DATA_AVAILABLE = False
    logger.warning("yfinance not available for macro data")

# Cache for macro data (refreshes every 15 minutes)
_macro_cache = {
    "last_update": None,
    "data": None
}

CACHE_DURATION_MINUTES = 15


async def get_macro_data() -> Optional[Dict]:
    """
    Fetch current macro indicator data
    
    Returns:
        {
            "btc_price": float,
            "btc_sma_50": float,
            "btc_above_50sma": bool,
            "dxy_price": float,
            "dxy_sma_20": float,
            "dxy_rising": bool,  # Risk-off if rising
            "qqq_price": float,
            "qqq_sma_200": float,
            "qqq_above_200sma": bool
        }
    """
    global _macro_cache
    
    if not MACRO_DATA_AVAILABLE:
        logger.warning("Cannot fetch macro data - yfinance not installed")
        return None
    
    # Check cache
    now = datetime.now()
    if (_macro_cache["last_update"] and 
        (now - _macro_cache["last_update"]).total_seconds() < CACHE_DURATION_MINUTES * 60):
        return _macro_cache["data"]
    
    try:
        logger.info("📊 Fetching macro data (BTC, DXY, QQQ)...")
        
        # Fetch data for all three
        btc = yf.Ticker("BTC-USD")
        dxy = yf.Ticker("DX-Y.NYB")  # Dollar Index
        qqq = yf.Ticker("QQQ")
        
        # Get historical data for SMA calculations
        btc_hist = btc.history(period="3mo")
        dxy_hist = dxy.history(period="1mo")
        qqq_hist = qqq.history(period="1y")
        
        # BTC calculations
        btc_price = float(btc_hist['Close'].iloc[-1]) if not btc_hist.empty else None
        btc_sma_50 = float(btc_hist['Close'].rolling(50).mean().iloc[-1]) if len(btc_hist) >= 50 else None
        btc_above_50sma = bool(btc_price > btc_sma_50) if btc_price and btc_sma_50 else None
        
        # DXY calculations (20 SMA for trend)
        dxy_price = float(dxy_hist['Close'].iloc[-1]) if not dxy_hist.empty else None
        dxy_sma_20 = float(dxy_hist['Close'].rolling(20).mean().iloc[-1]) if len(dxy_hist) >= 20 else None
        # DXY rising = price above SMA = risk-off
        dxy_rising = bool(dxy_price > dxy_sma_20) if dxy_price and dxy_sma_20 else None
        
        # QQQ calculations
        qqq_price = float(qqq_hist['Close'].iloc[-1]) if not qqq_hist.empty else None
        qqq_sma_200 = float(qqq_hist['Close'].rolling(200).mean().iloc[-1]) if len(qqq_hist) >= 200 else None
        qqq_above_200sma = bool(qqq_price > qqq_sma_200) if qqq_price and qqq_sma_200 else None
        
        macro_data = {
            "btc_price": round(btc_price, 2) if btc_price else None,
            "btc_sma_50": round(btc_sma_50, 2) if btc_sma_50 else None,
            "btc_above_50sma": btc_above_50sma,
            "dxy_price": round(dxy_price, 2) if dxy_price else None,
            "dxy_sma_20": round(dxy_sma_20, 2) if dxy_sma_20 else None,
            "dxy_rising": dxy_rising,  # True = risk-off
            "qqq_price": round(qqq_price, 2) if qqq_price else None,
            "qqq_sma_200": round(qqq_sma_200, 2) if qqq_sma_200 else None,
            "qqq_above_200sma": qqq_above_200sma,
            "updated_at": now.isoformat()
        }
        
        # Update cache
        _macro_cache["data"] = macro_data
        _macro_cache["last_update"] = now
        
        logger.info(f"✅ Macro data updated: BTC>${'50SMA' if btc_above_50sma else '<50SMA'}, "
                   f"DXY {'↑risk-off' if dxy_rising else '↓risk-on'}, "
                   f"QQQ>${'200SMA' if qqq_above_200sma else '<200SMA'}")
        
        return macro_data
        
    except Exception as e:
        logger.error(f"Error fetching macro data: {e}")
        return _macro_cache.get("data")  # Return stale cache if available


async def check_btc_macro_confluence(direction: str) -> Tuple[bool, Dict]:
    """
    Check if BTC signal aligns with macro environment
    
    Args:
        direction: "LONG" or "SHORT"
    
    Returns:
        (has_confluence, details)
        - has_confluence: True if all macro factors agree
        - details: Dict with individual check results
    """
    macro = await get_macro_data()
    
    if not macro:
        return False, {"error": "Unable to fetch macro data"}
    
    direction = direction.upper()
    
    # Define what each macro indicator says (ensure all bools are Python bools)
    btc_above = macro.get("btc_above_50sma")
    dxy_rising = macro.get("dxy_rising")
    qqq_above = macro.get("qqq_above_200sma")
    
    checks = {
        "btc_momentum": {
            "bullish": bool(btc_above) if btc_above is not None else None,
            "value": f"BTC {'>' if btc_above else '<'} 50 SMA",
            "price": macro.get("btc_price"),
            "sma": macro.get("btc_sma_50")
        },
        "dxy_environment": {
            "bullish": bool(not dxy_rising) if dxy_rising is not None else None,  # DXY falling = risk-on = bullish
            "value": f"DXY {'rising (risk-off)' if dxy_rising else 'falling (risk-on)'}",
            "price": macro.get("dxy_price"),
            "sma": macro.get("dxy_sma_20")
        },
        "qqq_trend": {
            "bullish": bool(qqq_above) if qqq_above is not None else None,
            "value": f"QQQ {'>' if qqq_above else '<'} 200 SMA",
            "price": macro.get("qqq_price"),
            "sma": macro.get("qqq_sma_200")
        }
    }
    
    # Check confluence based on direction
    if direction in ["LONG", "BUY", "BULLISH"]:
        # For bullish: all should be bullish
        btc_agrees = bool(checks["btc_momentum"]["bullish"] == True)
        dxy_agrees = bool(checks["dxy_environment"]["bullish"] == True)  # DXY falling
        qqq_agrees = bool(checks["qqq_trend"]["bullish"] == True)
        
        confluence = bool(btc_agrees and dxy_agrees and qqq_agrees)
        
    elif direction in ["SHORT", "SELL", "BEARISH"]:
        # For bearish: all should be bearish
        btc_agrees = bool(checks["btc_momentum"]["bullish"] == False)
        dxy_agrees = bool(checks["dxy_environment"]["bullish"] == False)  # DXY rising
        qqq_agrees = bool(checks["qqq_trend"]["bullish"] == False)
        
        confluence = bool(btc_agrees and dxy_agrees and qqq_agrees)
        
    else:
        return False, {"error": f"Unknown direction: {direction}"}
    
    # Count how many agree
    agreements = sum([btc_agrees, dxy_agrees, qqq_agrees])
    
    details = {
        "direction": direction,
        "full_confluence": bool(confluence),
        "agreement_count": f"{agreements}/3",
        "checks": {
            "btc_50sma": {
                "agrees": bool(btc_agrees),
                "status": checks["btc_momentum"]["value"],
                "price": checks["btc_momentum"]["price"],
                "sma": checks["btc_momentum"]["sma"]
            },
            "dxy_trend": {
                "agrees": bool(dxy_agrees),
                "status": checks["dxy_environment"]["value"],
                "price": checks["dxy_environment"]["price"],
                "sma": checks["dxy_environment"]["sma"]
            },
            "qqq_200sma": {
                "agrees": bool(qqq_agrees),
                "status": checks["qqq_trend"]["value"],
                "price": checks["qqq_trend"]["price"],
                "sma": checks["qqq_trend"]["sma"]
            }
        },
        "recommendation": get_recommendation(direction, bool(confluence), agreements),
        "updated_at": macro.get("updated_at")
    }
    
    return confluence, details


def get_recommendation(direction: str, confluence: bool, agreements: int) -> str:
    """Generate trading recommendation based on confluence"""
    
    if confluence:
        if direction in ["LONG", "BUY", "BULLISH"]:
            return "🐂 APIS CALL - Full macro confluence for LONG"
        else:
            return "🐻 KODIAK CALL - Full macro confluence for SHORT"
    elif agreements >= 2:
        return f"⚠️ Partial confluence ({agreements}/3) - Proceed with caution"
    else:
        return f"❌ Low confluence ({agreements}/3) - Consider skipping this trade"


async def upgrade_signal_if_confluence(signal: Dict) -> Dict:
    """
    Check ANY signal and upgrade to APIS/KODIAK if macro confluence exists.
    
    APIS_CALL = Strong bullish with full macro confluence (all 3 factors bullish)
    KODIAK_CALL = Strong bearish with full macro confluence (all 3 factors bearish)
    
    Applies to ALL tickers (equities and crypto).
    
    Args:
        signal: The incoming signal dict
    
    Returns:
        Updated signal with potential upgrade
    """
    ticker = signal.get("ticker", "").upper()
    direction = signal.get("direction", "").upper()
    
    logger.info(f"🔍 Checking macro confluence for {ticker} {direction} signal...")
    
    has_confluence, details = await check_btc_macro_confluence(direction)
    
    # Add confluence data to signal
    signal["macro_confluence"] = details
    
    if has_confluence:
        # Upgrade signal type - APIS for bulls, KODIAK for bears
        if direction in ["LONG", "BUY", "BULLISH"]:
            signal["signal_type"] = "APIS_CALL"
            signal["priority"] = "HIGH"
            logger.info(f"⬆️ {ticker} signal upgraded to APIS CALL - full macro confluence!")
        else:
            signal["signal_type"] = "KODIAK_CALL"
            signal["priority"] = "HIGH"
            logger.info(f"⬆️ {ticker} signal upgraded to KODIAK CALL - full macro confluence!")
    else:
        # Keep original signal type but add confluence info
        signal["priority"] = "MEDIUM" if details.get("agreement_count", "0/3").startswith("2") else "LOW"
        logger.info(f"{ticker} signal not upgraded - confluence: {details.get('agreement_count')}")
    
    return signal
