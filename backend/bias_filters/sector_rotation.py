"""
Sector Rotation Bias Filter
Weekly bias indicator based on offensive vs defensive sector leadership

The Logic:
- OFFENSIVE sectors (XLK Tech, XLY Consumer Discretionary) leading = BULLISH
- DEFENSIVE sectors (XLU Utilities, XLP Consumer Staples) leading = BEARISH
- Mixed leadership = NEUTRAL

We compare 5-day performance of offensive vs defensive sectors.

Data Inputs:
- XLK (Technology) - weekly performance
- XLY (Consumer Discretionary) - weekly performance
- XLU (Utilities) - weekly performance
- XLP (Consumer Staples) - weekly performance

Update Frequency: Weekly (every Monday)
"""

import logging
from typing import Dict, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SectorRotationBias(str, Enum):
    """Sector rotation bias levels"""
    URSA_MAJOR = "URSA_MAJOR"      # Strong defensive leadership
    URSA_MINOR = "URSA_MINOR"      # Mild defensive leadership
    NEUTRAL = "NEUTRAL"            # Mixed / no clear leader
    TORO_MINOR = "TORO_MINOR"      # Mild offensive leadership
    TORO_MAJOR = "TORO_MAJOR"      # Strong offensive leadership


# Sector ETFs
OFFENSIVE_SECTORS = ["XLK", "XLY"]  # Tech, Consumer Discretionary
DEFENSIVE_SECTORS = ["XLU", "XLP"]  # Utilities, Consumer Staples

# Current state storage
_sector_rotation_state: Dict[str, Any] = {
    "offensive_avg_return": None,
    "defensive_avg_return": None,
    "spread": None,  # offensive - defensive
    "bias": SectorRotationBias.NEUTRAL.value,
    "bias_level": 3,
    "last_updated": None,
    "description": "Awaiting data",
    "sector_details": {}
}

# Thresholds
SECTOR_ROTATION_CONFIG = {
    "strong_spread_pct": 2.0,    # >2% spread = strong signal
    "mild_spread_pct": 0.75,     # 0.75-2% spread = mild signal
    "lookback_days": 5,          # 5 trading days (1 week)
}


def calculate_sector_rotation_bias(sector_returns: Dict[str, float]) -> Dict[str, Any]:
    """
    Calculate sector rotation bias from sector performance data.
    
    Args:
        sector_returns: Dict of ticker -> 5-day return percentage
                       e.g., {"XLK": 2.5, "XLY": 1.8, "XLU": -0.5, "XLP": 0.2}
    
    Returns:
        Dict with bias, spread, and context
    """
    config = SECTOR_ROTATION_CONFIG
    
    # Calculate average returns
    offensive_returns = [sector_returns.get(s, 0) for s in OFFENSIVE_SECTORS]
    defensive_returns = [sector_returns.get(s, 0) for s in DEFENSIVE_SECTORS]
    
    offensive_avg = sum(offensive_returns) / len(offensive_returns) if offensive_returns else 0
    defensive_avg = sum(defensive_returns) / len(defensive_returns) if defensive_returns else 0
    
    # Spread: positive = offensive leading, negative = defensive leading
    spread = offensive_avg - defensive_avg
    
    # Determine bias based on spread
    if spread >= config["strong_spread_pct"]:
        bias = SectorRotationBias.TORO_MAJOR
        bias_level = 5
        description = f"🐂 RISK-ON: Offensive sectors leading by {spread:.1f}%. Tech & Consumer Discretionary outperforming."
    
    elif spread >= config["mild_spread_pct"]:
        bias = SectorRotationBias.TORO_MINOR
        bias_level = 4
        description = f"📈 LEAN BULLISH: Offensive sectors mildly leading ({spread:+.1f}%)."
    
    elif spread <= -config["strong_spread_pct"]:
        bias = SectorRotationBias.URSA_MAJOR
        bias_level = 1
        description = f"🐻 RISK-OFF: Defensive sectors leading by {abs(spread):.1f}%. Utilities & Staples outperforming."
    
    elif spread <= -config["mild_spread_pct"]:
        bias = SectorRotationBias.URSA_MINOR
        bias_level = 2
        description = f"⚠️ LEAN BEARISH: Defensive sectors mildly leading ({spread:+.1f}%)."
    
    else:
        bias = SectorRotationBias.NEUTRAL
        bias_level = 3
        description = f"➖ NEUTRAL: No clear sector leadership (spread: {spread:+.1f}%)."
    
    return {
        "offensive_avg_return": round(offensive_avg, 2),
        "defensive_avg_return": round(defensive_avg, 2),
        "spread": round(spread, 2),
        "bias": bias.value,
        "bias_level": bias_level,
        "description": description,
        "sector_details": {
            ticker: round(ret, 2) for ticker, ret in sector_returns.items()
        },
        "timestamp": datetime.now().isoformat()
    }


async def auto_fetch_and_update() -> Dict[str, Any]:
    """
    Auto-fetch sector data using yfinance and update Sector Rotation bias.
    Called by the scheduler.
    """
    global _sector_rotation_state
    
    try:
        import yfinance as yf
        
        all_sectors = OFFENSIVE_SECTORS + DEFENSIVE_SECTORS
        sector_returns = {}
        
        for ticker in all_sectors:
            try:
                etf = yf.Ticker(ticker)
                hist = etf.history(period="10d")
                
                if len(hist) >= 6:
                    current_price = float(hist['Close'].iloc[-1])
                    price_5d_ago = float(hist['Close'].iloc[-6])
                    pct_change = ((current_price - price_5d_ago) / price_5d_ago) * 100
                    sector_returns[ticker] = pct_change
                else:
                    logger.warning(f"Not enough data for {ticker}")
                    sector_returns[ticker] = 0.0
                    
            except Exception as e:
                logger.warning(f"Error fetching {ticker}: {e}")
                sector_returns[ticker] = 0.0
        
        # Calculate bias
        result = calculate_sector_rotation_bias(sector_returns)
        _sector_rotation_state.update(result)
        _sector_rotation_state["last_updated"] = datetime.now().isoformat()
        _sector_rotation_state["data_source"] = "yfinance_auto"
        
        logger.info(f"📊 Sector Rotation updated: {result['bias']} (spread: {result['spread']:+.1f}%)")
        
        return {"status": "success", "data": _sector_rotation_state}
        
    except Exception as e:
        logger.error(f"Error fetching sector rotation data: {e}")
        return {"status": "error", "message": str(e)}


def get_sector_rotation_status() -> Dict[str, Any]:
    """Get current Sector Rotation bias status"""
    return {
        **_sector_rotation_state,
        "config": SECTOR_ROTATION_CONFIG,
        "offensive_sectors": OFFENSIVE_SECTORS,
        "defensive_sectors": DEFENSIVE_SECTORS
    }


def get_bias_for_scoring() -> Dict[str, Any]:
    """
    Get simplified bias for signal scoring integration
    """
    bias = _sector_rotation_state.get("bias", SectorRotationBias.NEUTRAL.value)
    level = _sector_rotation_state.get("bias_level", 3)
    
    return {
        "bias": bias,
        "bias_level": level,
        "allows_longs": level >= 3,
        "allows_shorts": level <= 3,
        "last_updated": _sector_rotation_state.get("last_updated")
    }
