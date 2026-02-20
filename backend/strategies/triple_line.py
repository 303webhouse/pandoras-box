"""
Triple Line Trend Retracement Strategy Validator
Validates incoming signals against approved strategy criteria
Target: <10ms execution time
"""

from typing import Tuple, Dict, Any
from datetime import datetime, time

async def validate_triple_line_signal(signal: Dict[Any, Any]) -> Tuple[bool, str]:
    """
    Validate if a signal meets Triple Line strategy requirements
    
    Returns:
        (is_valid, details): Boolean and explanation string
    """
    
    ticker = signal.get('ticker')
    direction = signal.get('direction')
    adx = signal.get('adx')
    line_separation = signal.get('line_separation')
    timestamp_str = signal.get('timestamp')
    
    # Parse timestamp and convert to ET for time-based rules
    try:
        from zoneinfo import ZoneInfo
        signal_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        et_time = signal_time.astimezone(ZoneInfo("America/New_York"))
        signal_hour = et_time.hour
        signal_minute = et_time.minute
    except Exception:
        # Fallback: use current ET time
        from zoneinfo import ZoneInfo
        et_now = datetime.now(ZoneInfo("America/New_York"))
        signal_hour = et_now.hour
        signal_minute = et_now.minute
    
    # Validation checks
    
    # 1. ADX must be > 25 (reject if missing)
    if adx is None:
        return False, "ADX not provided - cannot validate trend strength"
    if adx < 25:
        return False, f"ADX too low: {adx} < 25"
    
    # 2. Lines must be separated by at least 10 points (reject if missing)
    if line_separation is None:
        return False, "Line separation not provided - cannot validate setup"
    if line_separation < 10:
        return False, f"Lines too close: {line_separation} < 10 points"
    
    # 3. Must be after 10:00 AM ET
    # Assuming server runs in ET or timestamp is ET
    # Convert to decimal for easy comparison: 10:00 AM = 10.0
    time_decimal = signal_hour + (signal_minute / 60.0)
    if time_decimal < 10.0:
        return False, f"Too early: signal at {signal_hour}:{signal_minute:02d}, must be after 10:00 AM ET"
    
    # 4. Direction must be LONG or SHORT
    if direction not in ["LONG", "SHORT"]:
        return False, f"Invalid direction: {direction}"
    
    # 5. Must have valid entry and stop loss
    entry = signal.get('entry_price')
    stop = signal.get('stop_loss')
    
    if not entry or not stop:
        return False, "Missing entry price or stop loss"
    
    # 6. Stop loss must be in correct direction
    if direction == "LONG" and stop >= entry:
        return False, f"Invalid stop for LONG: stop {stop} must be below entry {entry}"
    
    if direction == "SHORT" and stop <= entry:
        return False, f"Invalid stop for SHORT: stop {stop} must be above entry {entry}"
    
    # All checks passed
    return True, f"Valid {direction} signal: ADX={adx}, separation={line_separation}pts"

def calculate_signal_strength(adx: float, line_separation: float) -> float:
    """
    Calculate signal strength score for ranking
    Returns: 0.0 to 1.0
    """
    
    # ADX scoring (25-50 range mapped to 0-1)
    adx_score = min((adx - 25) / 25, 1.0)
    
    # Line separation scoring (10-30 range mapped to 0-1)
    separation_score = min((line_separation - 10) / 20, 1.0)
    
    # Weighted average (ADX is more important)
    strength = (adx_score * 0.6) + (separation_score * 0.4)
    
    return round(strength, 2)
