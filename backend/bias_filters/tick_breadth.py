"""
TICK Range Breadth Model Bias Filter
Checks if signal aligns with current market bias
Target: <5ms execution time
"""

from typing import Tuple
from database.redis_client import get_bias

async def check_bias_alignment(direction: str, timeframe: str) -> Tuple[str, bool]:
    """
    Check if signal direction aligns with current bias
    
    Args:
        direction: "LONG" or "SHORT"
        timeframe: "DAILY", "WEEKLY", or "MONTHLY"
    
    Returns:
        (bias_level, is_aligned): Current bias and whether signal aligns
    """
    
    # Get current bias from Redis cache
    bias_data = await get_bias(timeframe)
    
    if not bias_data:
        # No bias data available, default to neutral
        return "NEUTRAL", False
    
    bias_level = bias_data.get('level', 'NEUTRAL')
    
    # Determine alignment
    is_aligned = False
    
    if direction == "LONG":
        # Long signals align with bullish bias
        if bias_level in ["TORO_MINOR", "TORO_MAJOR"]:
            is_aligned = True
    
    elif direction == "SHORT":
        # Short signals align with bearish bias
        if bias_level in ["URSA_MINOR", "URSA_MAJOR"]:
            is_aligned = True
    
    return bias_level, is_aligned

def calculate_bias_strength(bias_level: str) -> float:
    """
    Convert bias level to numerical strength score
    Returns: -1.0 (strong bearish) to +1.0 (strong bullish)
    """
    
    bias_scores = {
        "URSA_MAJOR": -1.0,
        "URSA_MINOR": -0.5,
        "NEUTRAL": 0.0,
        "TORO_MINOR": 0.5,
        "TORO_MAJOR": 1.0
    }
    
    return bias_scores.get(bias_level, 0.0)

async def calculate_daily_bias(tick_high: int, tick_low: int) -> str:
    """
    Calculate daily bias based on TICK range
    
    Wide range (high > +1000 OR low < -1000) = Bullish
    Narrow range (high < +500 AND low > -500) = Bearish
    Mixed = Neutral
    """
    
    is_wide = tick_high > 1000 or tick_low < -1000
    is_narrow = tick_high < 500 and tick_low > -500
    
    if is_wide:
        return "TORO_MINOR"  # Wide range = bullish participation
    elif is_narrow:
        return "URSA_MINOR"  # Narrow range = weak participation
    else:
        return "NEUTRAL"

async def calculate_weekly_bias(tick_history: list) -> str:
    """
    Calculate weekly bias based on last 5 days of TICK ranges
    
    Args:
        tick_history: List of dicts with 'tick_high', 'tick_low', 'date'
    
    Returns:
        Bias level: URSA_MAJOR, URSA_MINOR, NEUTRAL, TORO_MINOR, TORO_MAJOR
    """
    
    if len(tick_history) < 5:
        return "NEUTRAL"
    
    wide_days = 0
    narrow_days = 0
    
    for day in tick_history[-5:]:
        tick_high = day['tick_high']
        tick_low = day['tick_low']
        
        if tick_high > 1000 or tick_low < -1000:
            wide_days += 1
        elif tick_high < 500 and tick_low > -500:
            narrow_days += 1
    
    # Strong bullish: 4+ wide days
    if wide_days >= 4:
        return "TORO_MAJOR"
    # Moderate bullish: 3 wide days
    elif wide_days == 3:
        return "TORO_MINOR"
    # Strong bearish: 4+ narrow days
    elif narrow_days >= 4:
        return "URSA_MAJOR"
    # Moderate bearish: 3 narrow days
    elif narrow_days == 3:
        return "URSA_MINOR"
    # Mixed signals
    else:
        return "NEUTRAL"
