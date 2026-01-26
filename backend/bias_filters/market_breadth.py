"""
Market Breadth Bias Filter
Weekly bias indicator based on equal-weight vs cap-weight performance

The Logic:
- RSP (Equal Weight S&P 500) outperforming SPY (Cap Weight) = HEALTHY breadth (Bullish)
- SPY outperforming RSP = NARROW leadership (Bearish/Caution)
- Similar performance = NEUTRAL

When RSP beats SPY, it means the average stock is doing well (broad participation).
When SPY beats RSP, it means only the mega-caps are carrying the market (narrow, fragile).

Data Inputs:
- RSP (Invesco S&P 500 Equal Weight ETF) - 5-day performance
- SPY (SPDR S&P 500 ETF) - 5-day performance

Update Frequency: Weekly (every Monday)
"""

import logging
from typing import Dict, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MarketBreadthBias(str, Enum):
    """Market breadth bias levels"""
    URSA_MAJOR = "URSA_MAJOR"      # Very narrow leadership
    URSA_MINOR = "URSA_MINOR"      # Mild narrow leadership
    NEUTRAL = "NEUTRAL"            # No clear breadth signal
    TORO_MINOR = "TORO_MINOR"      # Mild broad participation
    TORO_MAJOR = "TORO_MAJOR"      # Strong broad participation


# Current state storage
_market_breadth_state: Dict[str, Any] = {
    "rsp_return": None,
    "spy_return": None,
    "spread": None,  # RSP return - SPY return (positive = healthy breadth)
    "bias": MarketBreadthBias.NEUTRAL.value,
    "bias_level": 3,
    "last_updated": None,
    "description": "Awaiting data"
}

# Thresholds
MARKET_BREADTH_CONFIG = {
    "strong_spread_pct": 1.5,    # >1.5% spread = strong signal
    "mild_spread_pct": 0.5,      # 0.5-1.5% spread = mild signal
    "lookback_days": 5,          # 5 trading days (1 week)
}


def calculate_market_breadth_bias(rsp_return: float, spy_return: float) -> Dict[str, Any]:
    """
    Calculate market breadth bias from ETF performance.
    
    Args:
        rsp_return: 5-day return of RSP (equal weight S&P) in percent
        spy_return: 5-day return of SPY (cap weight S&P) in percent
    
    Returns:
        Dict with bias, spread, and context
    """
    config = MARKET_BREADTH_CONFIG
    
    # Spread: positive = RSP outperforming (broad), negative = SPY outperforming (narrow)
    spread = rsp_return - spy_return
    
    # Determine bias based on spread
    if spread >= config["strong_spread_pct"]:
        bias = MarketBreadthBias.TORO_MAJOR
        bias_level = 5
        description = f"🐂 HEALTHY BREADTH: Equal-weight crushing cap-weight by {spread:.1f}%. Broad participation."
    
    elif spread >= config["mild_spread_pct"]:
        bias = MarketBreadthBias.TORO_MINOR
        bias_level = 4
        description = f"📈 GOOD BREADTH: RSP outperforming SPY by {spread:+.1f}%. Average stock doing well."
    
    elif spread <= -config["strong_spread_pct"]:
        bias = MarketBreadthBias.URSA_MAJOR
        bias_level = 1
        description = f"🐻 NARROW MARKET: Mega-caps carrying the load - SPY beating RSP by {abs(spread):.1f}%."
    
    elif spread <= -config["mild_spread_pct"]:
        bias = MarketBreadthBias.URSA_MINOR
        bias_level = 2
        description = f"⚠️ NARROW LEADERSHIP: SPY outperforming RSP by {abs(spread):.1f}%. Watch for rotation."
    
    else:
        bias = MarketBreadthBias.NEUTRAL
        bias_level = 3
        description = f"➖ NEUTRAL: Cap-weight and equal-weight tracking closely (spread: {spread:+.1f}%)."
    
    return {
        "rsp_return": round(rsp_return, 2),
        "spy_return": round(spy_return, 2),
        "spread": round(spread, 2),
        "bias": bias.value,
        "bias_level": bias_level,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }


async def auto_fetch_and_update() -> Dict[str, Any]:
    """
    Auto-fetch market breadth data using yfinance and update bias.
    """
    global _market_breadth_state
    
    try:
        import yfinance as yf
        
        # Fetch RSP (Equal Weight S&P 500)
        rsp = yf.Ticker("RSP")
        rsp_hist = rsp.history(period="10d")
        
        # Fetch SPY (Cap Weight S&P 500)
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="10d")
        
        if len(rsp_hist) < 6 or len(spy_hist) < 6:
            logger.warning("Not enough data for market breadth calculation")
            return {"status": "error", "message": "Insufficient data"}
        
        # Calculate 5-day returns
        rsp_current = float(rsp_hist['Close'].iloc[-1])
        rsp_5d_ago = float(rsp_hist['Close'].iloc[-6])
        rsp_return = ((rsp_current - rsp_5d_ago) / rsp_5d_ago) * 100
        
        spy_current = float(spy_hist['Close'].iloc[-1])
        spy_5d_ago = float(spy_hist['Close'].iloc[-6])
        spy_return = ((spy_current - spy_5d_ago) / spy_5d_ago) * 100
        
        # Calculate bias
        result = calculate_market_breadth_bias(rsp_return, spy_return)
        _market_breadth_state.update(result)
        _market_breadth_state["last_updated"] = datetime.now().isoformat()
        _market_breadth_state["data_source"] = "yfinance_auto"
        
        logger.info(f"📊 Market Breadth updated: {result['bias']} (spread: {result['spread']:+.1f}%)")
        
        return {"status": "success", "data": _market_breadth_state}
        
    except Exception as e:
        logger.error(f"Error fetching market breadth data: {e}")
        return {"status": "error", "message": str(e)}


def get_market_breadth_status() -> Dict[str, Any]:
    """Get current market breadth bias status"""
    return {
        **_market_breadth_state,
        "config": MARKET_BREADTH_CONFIG
    }


def get_bias_for_scoring() -> Dict[str, Any]:
    """Get simplified bias for signal scoring integration"""
    bias = _market_breadth_state.get("bias", MarketBreadthBias.NEUTRAL.value)
    level = _market_breadth_state.get("bias_level", 3)
    
    return {
        "bias": bias,
        "bias_level": level,
        "allows_longs": level >= 3,
        "allows_shorts": level <= 3,
        "last_updated": _market_breadth_state.get("last_updated")
    }
