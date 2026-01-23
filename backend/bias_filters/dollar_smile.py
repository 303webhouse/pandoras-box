"""
Dollar Smile Macro Bias Filter
Weekly bias indicator based on USD strength context

The Dollar Smile Theory:
- LEFT side (USD up + VIX high): Risk-Off / URSA - Fear driving USD strength
- RIGHT side (USD up + VIX low): Risk-On / TORO - Growth driving USD strength  
- BOTTOM (USD flat/down + VIX low): NEUTRAL - Stagnation
- TRANSITION (USD down + VIX rising): URSA MINOR - Caution

Data Inputs:
- DXY (US Dollar Index) - daily close + 5-day rate of change
- VIX (Volatility Index) - current level

Update Frequency: Daily, but interpret on weekly scale
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DollarSmileBias(str, Enum):
    """Dollar Smile bias levels mapped to trading bias"""
    URSA_MAJOR = "URSA_MAJOR"      # Left side of smile - Fear/Risk-Off
    URSA_MINOR = "URSA_MINOR"      # Transition - Caution
    NEUTRAL = "NEUTRAL"            # Bottom of smile - Stagnation
    TORO_MINOR = "TORO_MINOR"      # Transitioning to risk-on
    TORO_MAJOR = "TORO_MAJOR"      # Right side of smile - Growth/Risk-On


class SmilePosition(str, Enum):
    """Position on the Dollar Smile curve"""
    LEFT_FEAR = "LEFT_FEAR"        # USD up, VIX high - Risk-off
    RIGHT_GROWTH = "RIGHT_GROWTH"  # USD up, VIX low - Risk-on
    BOTTOM_STAGNATION = "BOTTOM_STAGNATION"  # USD flat/down, VIX low
    TRANSITION = "TRANSITION"      # USD down, VIX rising


# Current state storage (will be replaced with Redis/DB in production)
_dollar_smile_state: Dict[str, Any] = {
    "dxy_current": None,
    "dxy_5d_change_pct": None,
    "vix_current": None,
    "smile_position": None,
    "bias": DollarSmileBias.NEUTRAL,
    "bias_level": 3,  # 1-5 scale matching PROJECT_RULES
    "last_updated": None,
    "last_webhook": None,
    "description": "Awaiting data from TradingView webhooks"
}

# Thresholds (configurable)
DOLLAR_SMILE_CONFIG = {
    "dxy_strong_move_pct": 2.0,      # DXY up >2% over 5 days = strong move
    "dxy_weak_threshold_pct": 0.5,   # DXY change <0.5% = flat
    "vix_fear_threshold": 20,        # VIX >20 = elevated fear
    "vix_calm_threshold": 15,        # VIX <15 = very calm
}


def calculate_dollar_smile_bias(
    dxy_current: float,
    dxy_5d_ago: float,
    vix_current: float
) -> Dict[str, Any]:
    """
    Calculate Dollar Smile bias from current market data
    
    Args:
        dxy_current: Current DXY price
        dxy_5d_ago: DXY price 5 trading days ago
        vix_current: Current VIX level
    
    Returns:
        Dict with bias, position, and context
    """
    # Calculate 5-day DXY change
    dxy_change_pct = ((dxy_current - dxy_5d_ago) / dxy_5d_ago) * 100
    
    config = DOLLAR_SMILE_CONFIG
    
    # Determine smile position and bias
    dxy_rising_strong = dxy_change_pct >= config["dxy_strong_move_pct"]
    dxy_rising_weak = dxy_change_pct > config["dxy_weak_threshold_pct"]
    dxy_falling = dxy_change_pct < -config["dxy_weak_threshold_pct"]
    dxy_flat = not dxy_rising_weak and not dxy_falling
    
    vix_high = vix_current >= config["vix_fear_threshold"]
    vix_low = vix_current < config["vix_fear_threshold"]
    vix_very_low = vix_current < config["vix_calm_threshold"]
    vix_rising = False  # Would need historical VIX to determine
    
    # Apply Dollar Smile logic
    if dxy_rising_strong and vix_high:
        # LEFT SIDE - Fear/Risk-Off
        position = SmilePosition.LEFT_FEAR
        bias = DollarSmileBias.URSA_MAJOR
        bias_level = 1
        description = f"🐻 RISK-OFF: USD surging (+{dxy_change_pct:.1f}%) with elevated fear (VIX {vix_current:.1f}). Left side of Dollar Smile."
        
    elif dxy_rising_strong and vix_low:
        # RIGHT SIDE - Growth/Risk-On
        position = SmilePosition.RIGHT_GROWTH
        bias = DollarSmileBias.TORO_MAJOR
        bias_level = 5
        description = f"🐂 RISK-ON: USD strong (+{dxy_change_pct:.1f}%) with low fear (VIX {vix_current:.1f}). Right side of Dollar Smile - growth regime."
        
    elif (dxy_flat or dxy_falling) and vix_low:
        # BOTTOM - Stagnation
        position = SmilePosition.BOTTOM_STAGNATION
        bias = DollarSmileBias.NEUTRAL
        bias_level = 3
        description = f"➖ STAGNATION: USD flat/weak ({dxy_change_pct:+.1f}%) with calm VIX ({vix_current:.1f}). Bottom of Dollar Smile."
        
    elif dxy_falling and vix_high:
        # TRANSITION - USD weakness + rising fear = caution
        position = SmilePosition.TRANSITION
        bias = DollarSmileBias.URSA_MINOR
        bias_level = 2
        description = f"⚠️ CAUTION: USD falling ({dxy_change_pct:.1f}%) while VIX elevated ({vix_current:.1f}). Transitioning to risk-off."
        
    elif dxy_rising_weak and vix_high:
        # Mild USD strength with fear - lean bearish
        position = SmilePosition.TRANSITION
        bias = DollarSmileBias.URSA_MINOR
        bias_level = 2
        description = f"⚠️ MIXED: USD mildly up (+{dxy_change_pct:.1f}%) but VIX elevated ({vix_current:.1f}). Lean cautious."
        
    elif dxy_rising_weak and vix_very_low:
        # Mild USD strength with very calm VIX - lean bullish
        position = SmilePosition.RIGHT_GROWTH
        bias = DollarSmileBias.TORO_MINOR
        bias_level = 4
        description = f"📈 LEAN BULLISH: USD up (+{dxy_change_pct:.1f}%) with very calm VIX ({vix_current:.1f}). Leaning toward risk-on."
        
    else:
        # Default to neutral
        position = SmilePosition.BOTTOM_STAGNATION
        bias = DollarSmileBias.NEUTRAL
        bias_level = 3
        description = f"➖ NEUTRAL: DXY {dxy_change_pct:+.1f}%, VIX {vix_current:.1f}. No clear Dollar Smile signal."
    
    return {
        "dxy_current": round(dxy_current, 2),
        "dxy_5d_ago": round(dxy_5d_ago, 2),
        "dxy_5d_change_pct": round(dxy_change_pct, 2),
        "vix_current": round(vix_current, 1),
        "smile_position": position.value,
        "bias": bias.value,
        "bias_level": bias_level,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }


def update_from_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update Dollar Smile state from TradingView webhook
    
    Expected payload format (from TradingView alert):
    {
        "indicator": "dollar_smile",
        "dxy_current": 104.50,
        "dxy_5d_ago": 102.00,
        "vix_current": 18.5
    }
    
    Or individual updates:
    {
        "indicator": "dxy",
        "value": 104.50,
        "value_5d_ago": 102.00
    }
    {
        "indicator": "vix", 
        "value": 18.5
    }
    """
    global _dollar_smile_state
    
    try:
        indicator = payload.get("indicator", "").lower()
        
        if indicator == "dollar_smile":
            # Full update with all data
            dxy_current = float(payload["dxy_current"])
            dxy_5d_ago = float(payload["dxy_5d_ago"])
            vix_current = float(payload["vix_current"])
            
            result = calculate_dollar_smile_bias(dxy_current, dxy_5d_ago, vix_current)
            _dollar_smile_state.update(result)
            _dollar_smile_state["last_webhook"] = datetime.now().isoformat()
            _dollar_smile_state["last_updated"] = datetime.now().isoformat()
            
            logger.info(f"💵 Dollar Smile updated: {result['bias']} - {result['description'][:50]}...")
            return {"status": "success", "data": _dollar_smile_state}
            
        elif indicator == "dxy":
            # DXY-only update
            _dollar_smile_state["dxy_current"] = float(payload["value"])
            if "value_5d_ago" in payload:
                _dollar_smile_state["dxy_5d_ago"] = float(payload["value_5d_ago"])
            _dollar_smile_state["last_webhook"] = datetime.now().isoformat()
            
            # Recalculate if we have all data
            if _dollar_smile_state["dxy_current"] and _dollar_smile_state.get("dxy_5d_ago") and _dollar_smile_state["vix_current"]:
                result = calculate_dollar_smile_bias(
                    _dollar_smile_state["dxy_current"],
                    _dollar_smile_state["dxy_5d_ago"],
                    _dollar_smile_state["vix_current"]
                )
                _dollar_smile_state.update(result)
                
            logger.info(f"💵 DXY updated: {_dollar_smile_state['dxy_current']}")
            return {"status": "success", "data": _dollar_smile_state}
            
        elif indicator == "vix":
            # VIX-only update
            _dollar_smile_state["vix_current"] = float(payload["value"])
            _dollar_smile_state["last_webhook"] = datetime.now().isoformat()
            
            # Recalculate if we have all data
            if _dollar_smile_state["dxy_current"] and _dollar_smile_state.get("dxy_5d_ago") and _dollar_smile_state["vix_current"]:
                result = calculate_dollar_smile_bias(
                    _dollar_smile_state["dxy_current"],
                    _dollar_smile_state["dxy_5d_ago"],
                    _dollar_smile_state["vix_current"]
                )
                _dollar_smile_state.update(result)
                
            logger.info(f"💵 VIX updated: {_dollar_smile_state['vix_current']}")
            return {"status": "success", "data": _dollar_smile_state}
            
        else:
            return {"status": "error", "message": f"Unknown indicator: {indicator}"}
            
    except KeyError as e:
        logger.error(f"Missing required field in webhook: {e}")
        return {"status": "error", "message": f"Missing field: {e}"}
    except Exception as e:
        logger.error(f"Error processing Dollar Smile webhook: {e}")
        return {"status": "error", "message": str(e)}


def get_dollar_smile_status() -> Dict[str, Any]:
    """Get current Dollar Smile bias status"""
    return {
        **_dollar_smile_state,
        "config": DOLLAR_SMILE_CONFIG
    }


def get_bias_for_scoring() -> Dict[str, Any]:
    """
    Get simplified bias for signal scoring integration
    
    Returns:
        {
            "bias": "TORO_MAJOR" | "TORO_MINOR" | "NEUTRAL" | "URSA_MINOR" | "URSA_MAJOR",
            "bias_level": 1-5,
            "allows_longs": bool,
            "allows_shorts": bool,
            "score_modifier": int (-20 to +20)
        }
    """
    bias = _dollar_smile_state.get("bias", DollarSmileBias.NEUTRAL)
    level = _dollar_smile_state.get("bias_level", 3)
    
    # Determine what's allowed based on bias
    allows_longs = level >= 3  # Neutral or bullish
    allows_shorts = level <= 3  # Neutral or bearish
    
    # Score modifier for signals
    score_modifiers = {
        1: -20,  # URSA_MAJOR: Strong penalty for longs
        2: -10,  # URSA_MINOR: Moderate penalty for longs
        3: 0,    # NEUTRAL: No modifier
        4: +10,  # TORO_MINOR: Moderate boost for longs
        5: +20,  # TORO_MAJOR: Strong boost for longs
    }
    
    return {
        "bias": bias if isinstance(bias, str) else bias.value,
        "bias_level": level,
        "allows_longs": allows_longs,
        "allows_shorts": allows_shorts,
        "score_modifier": score_modifiers.get(level, 0),
        "last_updated": _dollar_smile_state.get("last_updated")
    }


def manually_set_bias(
    bias: str,
    dxy_current: Optional[float] = None,
    vix_current: Optional[float] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Manually set Dollar Smile bias (for testing or when webhooks unavailable)
    """
    global _dollar_smile_state
    
    bias_map = {
        "URSA_MAJOR": (DollarSmileBias.URSA_MAJOR, 1),
        "URSA_MINOR": (DollarSmileBias.URSA_MINOR, 2),
        "NEUTRAL": (DollarSmileBias.NEUTRAL, 3),
        "TORO_MINOR": (DollarSmileBias.TORO_MINOR, 4),
        "TORO_MAJOR": (DollarSmileBias.TORO_MAJOR, 5),
    }
    
    if bias.upper() not in bias_map:
        return {"status": "error", "message": f"Invalid bias: {bias}"}
    
    bias_enum, level = bias_map[bias.upper()]
    
    _dollar_smile_state["bias"] = bias_enum.value
    _dollar_smile_state["bias_level"] = level
    _dollar_smile_state["last_updated"] = datetime.now().isoformat()
    _dollar_smile_state["description"] = notes or f"Manually set to {bias.upper()}"
    
    if dxy_current:
        _dollar_smile_state["dxy_current"] = dxy_current
    if vix_current:
        _dollar_smile_state["vix_current"] = vix_current
    
    logger.info(f"💵 Dollar Smile manually set: {bias.upper()} (level {level})")
    
    return {"status": "success", "data": _dollar_smile_state}
