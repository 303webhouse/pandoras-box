"""
Savita Indicator (BofA Sell Side Indicator)
Contrarian sentiment indicator measuring Wall Street strategists' average recommended equity allocation

How it works:
- Measures the average recommended equity allocation from Wall Street sell-side strategists
- Acts as a CONTRARIAN indicator (when everyone is bullish, be cautious)
- Best used for macro/strategic decisions (monthly updates)

Thresholds:
- SELL signal (Extreme Bullishness = Bearish): Reading > 57.7%
- BUY signal (Extreme Bearishness = Bullish): Reading < 51.3%

Bias Mapping:
- Above 60%: URSA_MAJOR (extreme sell signal)
- 57.7% - 60%: URSA_MINOR (caution, bearish lean)  
- 51.3% - 57.7%: NEUTRAL
- 48% - 51.3%: TORO_MINOR (cautiously bullish)
- Below 48%: TORO_MAJOR (strong buy signal)

Current Reading (as of last update): 55.9% = NEUTRAL

Data Source: Bank of America Global Research (monthly updates)
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Savita Indicator Configuration
SAVITA_CONFIG = {
    # Current reading - UPDATE THIS MONTHLY when new data is released
    "current_reading": 55.9,  # As of last update
    "last_updated": "2026-01-15",  # Date of last BofA report
    
    # Thresholds (from BofA research)
    "thresholds": {
        "extreme_bullish": 57.7,  # Above = SELL signal
        "extreme_bearish": 51.3,  # Below = BUY signal
        "ursa_major": 60.0,  # Very extreme bullishness
        "toro_major": 48.0,  # Very extreme bearishness
    },
    
    # Enabled by default
    "enabled": True
}


def get_savita_reading() -> Dict[str, Any]:
    """
    Get the current Savita Indicator reading and interpretation
    
    Returns:
        {
            "reading": float,
            "bias": str (URSA_MAJOR, URSA_MINOR, NEUTRAL, TORO_MINOR, TORO_MAJOR),
            "signal": str (SELL, NEUTRAL, BUY),
            "interpretation": str,
            "last_updated": str,
            "enabled": bool
        }
    """
    reading = SAVITA_CONFIG["current_reading"]
    thresholds = SAVITA_CONFIG["thresholds"]
    
    # Determine bias level
    if reading >= thresholds["ursa_major"]:
        bias = "URSA_MAJOR"
        signal = "SELL"
        interpretation = f"Extreme bullishness ({reading}%) - Strong contrarian SELL signal"
    elif reading >= thresholds["extreme_bullish"]:
        bias = "URSA_MINOR"
        signal = "SELL"
        interpretation = f"High bullishness ({reading}%) - Contrarian SELL signal"
    elif reading <= thresholds["toro_major"]:
        bias = "TORO_MAJOR"
        signal = "BUY"
        interpretation = f"Extreme bearishness ({reading}%) - Strong contrarian BUY signal"
    elif reading <= thresholds["extreme_bearish"]:
        bias = "TORO_MINOR"
        signal = "BUY"
        interpretation = f"Low bullishness ({reading}%) - Contrarian BUY signal"
    else:
        bias = "NEUTRAL"
        signal = "NEUTRAL"
        interpretation = f"Moderate sentiment ({reading}%) - No clear contrarian signal"
    
    return {
        "reading": reading,
        "bias": bias,
        "signal": signal,
        "interpretation": interpretation,
        "last_updated": SAVITA_CONFIG["last_updated"],
        "enabled": SAVITA_CONFIG["enabled"],
        "thresholds": thresholds
    }


def update_savita_reading(new_reading: float, update_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Update the Savita Indicator with a new reading from BofA
    
    Args:
        new_reading: The new equity allocation % (e.g., 55.9)
        update_date: Optional date string (defaults to today)
    
    Returns:
        Updated Savita data
    """
    if new_reading < 0 or new_reading > 100:
        raise ValueError("Savita reading must be between 0 and 100 (percentage)")
    
    SAVITA_CONFIG["current_reading"] = new_reading
    SAVITA_CONFIG["last_updated"] = update_date or datetime.now().strftime("%Y-%m-%d")
    
    logger.info(f"📊 Savita Indicator updated: {new_reading}% as of {SAVITA_CONFIG['last_updated']}")
    
    return get_savita_reading()


def set_savita_enabled(enabled: bool) -> None:
    """Enable or disable the Savita Indicator bias filter"""
    SAVITA_CONFIG["enabled"] = enabled
    logger.info(f"Savita Indicator {'enabled' if enabled else 'disabled'}")


def check_savita_bias(direction: str) -> Dict[str, Any]:
    """
    Check if a trade direction aligns with Savita bias
    
    Args:
        direction: "LONG" or "SHORT"
    
    Returns:
        {
            "allowed": bool,
            "reason": str,
            "savita_data": {...}
        }
    """
    if not SAVITA_CONFIG["enabled"]:
        return {
            "allowed": True,
            "reason": "Savita filter disabled",
            "savita_data": None
        }
    
    savita = get_savita_reading()
    bias = savita["bias"]
    
    # URSA bias (extreme bullishness = bearish outlook) - favor shorts
    if bias in ["URSA_MAJOR", "URSA_MINOR"]:
        if direction == "SHORT":
            return {
                "allowed": True,
                "reason": f"Savita ({savita['reading']}%) supports SHORT - crowd too bullish",
                "savita_data": savita,
                "confluence": True
            }
        else:
            return {
                "allowed": True,  # Allow but flag as against sentiment
                "reason": f"Savita ({savita['reading']}%) warns against LONG - crowd too bullish",
                "savita_data": savita,
                "confluence": False
            }
    
    # TORO bias (extreme bearishness = bullish outlook) - favor longs
    if bias in ["TORO_MAJOR", "TORO_MINOR"]:
        if direction == "LONG":
            return {
                "allowed": True,
                "reason": f"Savita ({savita['reading']}%) supports LONG - crowd too bearish",
                "savita_data": savita,
                "confluence": True
            }
        else:
            return {
                "allowed": True,  # Allow but flag as against sentiment
                "reason": f"Savita ({savita['reading']}%) warns against SHORT - crowd too bearish",
                "savita_data": savita,
                "confluence": False
            }
    
    # NEUTRAL - no strong signal either way
    return {
        "allowed": True,
        "reason": f"Savita ({savita['reading']}%) is neutral - no sentiment edge",
        "savita_data": savita,
        "confluence": None
    }


def get_savita_config() -> Dict[str, Any]:
    """Get current Savita configuration"""
    return {
        **SAVITA_CONFIG.copy(),
        "current_interpretation": get_savita_reading()
    }


async def auto_search_savita_update() -> Dict[str, Any]:
    """
    Use Gemini AI to search for the latest BofA Sell Side Indicator reading.
    Should be called daily from 12th-23rd of each month during release window.
    
    Returns:
        {
            "status": "success" | "no_update" | "error",
            "new_reading": float | None,
            "previous_reading": float,
            "source": str,
            "message": str
        }
    """
    import os
    
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        return {
            "status": "error",
            "message": "GEMINI_API_KEY not configured",
            "previous_reading": SAVITA_CONFIG["current_reading"]
        }
    
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=gemini_api_key)
        # Try multiple model names for compatibility
        model_names = ['gemini-1.5-flash-latest', 'gemini-1.0-pro', 'gemini-pro-latest']
        model = None
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                # Test if model works
                break
            except Exception:
                continue
        
        if model is None:
            raise Exception("No compatible Gemini model found")
        
        prompt = """Search for the latest Bank of America Sell Side Indicator (also known as the BofA Sell Side Indicator or Savita Subramanian's indicator).

This indicator measures Wall Street strategists' average recommended equity allocation as a percentage.

Please find the most recent reading and respond in this exact format:
READING: [number]%
DATE: [month year]
SOURCE: [where you found it]

If you cannot find a recent reading (within the last 2 months), respond with:
NOT_FOUND

Only provide the number if you are confident it is the actual BofA Sell Side Indicator reading."""

        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        logger.info(f"Gemini Savita search response: {response_text}")
        
        if "NOT_FOUND" in response_text:
            return {
                "status": "no_update",
                "message": "No recent Savita reading found",
                "previous_reading": SAVITA_CONFIG["current_reading"]
            }
        
        # Parse the response
        import re
        reading_match = re.search(r'READING:\s*([\d.]+)%?', response_text)
        date_match = re.search(r'DATE:\s*(.+)', response_text)
        source_match = re.search(r'SOURCE:\s*(.+)', response_text)
        
        if reading_match:
            new_reading = float(reading_match.group(1))
            
            # Validate the reading is in reasonable range (40-70%)
            if 40 <= new_reading <= 70:
                previous = SAVITA_CONFIG["current_reading"]
                
                # Only update if it's different from current
                if abs(new_reading - previous) > 0.1:
                    date_str = date_match.group(1).strip() if date_match else datetime.now().strftime("%Y-%m-%d")
                    source = source_match.group(1).strip() if source_match else "Gemini search"
                    
                    # Update the indicator
                    update_savita_reading(new_reading, date_str)
                    
                    logger.info(f"✅ Savita updated via Gemini: {previous}% -> {new_reading}%")
                    
                    return {
                        "status": "success",
                        "new_reading": new_reading,
                        "previous_reading": previous,
                        "date": date_str,
                        "source": source,
                        "message": f"Updated from {previous}% to {new_reading}%"
                    }
                else:
                    return {
                        "status": "no_update",
                        "message": f"Reading unchanged at {new_reading}%",
                        "previous_reading": previous
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Invalid reading {new_reading}% (outside 40-70% range)",
                    "previous_reading": SAVITA_CONFIG["current_reading"]
                }
        else:
            return {
                "status": "error",
                "message": "Could not parse reading from Gemini response",
                "response": response_text,
                "previous_reading": SAVITA_CONFIG["current_reading"]
            }
            
    except Exception as e:
        logger.error(f"Error in Gemini Savita search: {e}")
        return {
            "status": "error",
            "message": str(e),
            "previous_reading": SAVITA_CONFIG["current_reading"]
        }
