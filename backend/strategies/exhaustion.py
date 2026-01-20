"""
Exhaustion Levels Strategy Validator
Based on the Leledc Exhaustion Bar indicator

Identifies potential reversal points where buyers/sellers are exhausted:
- EXHAUSTION_BULL: Sellers exhausted after extended downtrend (potential bottom)
- EXHAUSTION_BEAR: Buyers exhausted after extended uptrend (potential top)

Best used on Daily or 4H timeframes for swing trading reversals.
"""

from typing import Tuple, Dict, Any
from datetime import datetime

# Strategy configuration (can be toggled)
STRATEGY_CONFIG = {
    "enabled": True,
    "name": "Exhaustion Levels",
    "version": "1.0.0",
    "description": "Identifies trend exhaustion points for reversal trades",
    "recommended_timeframes": ["1D", "4H", "1H"],
    "params": {
        "min_momentum_bars": 10,  # Minimum consecutive momentum bars
        "swing_length": 40,       # Lookback for highest high / lowest low
    }
}


async def validate_exhaustion_signal(signal: Dict[Any, Any]) -> Tuple[bool, str]:
    """
    Validate if a signal meets Exhaustion strategy requirements
    
    Exhaustion signals indicate potential reversals:
    - EXHAUSTION_BULL: After extended selling, potential bounce
    - EXHAUSTION_BEAR: After extended buying, potential pullback
    
    Returns:
        (is_valid, details): Boolean and explanation string
    """
    if not STRATEGY_CONFIG["enabled"]:
        return False, "Exhaustion strategy is disabled"
    
    # Extract signal data
    ticker = signal.get('ticker')
    direction = signal.get('direction', '').upper()
    signal_type = signal.get('signal_type', '').upper()
    price = signal.get('entry_price') or signal.get('current_price')
    timeframe = signal.get('timeframe', '')
    
    # Validate direction
    valid_directions = {
        'LONG': 'EXHAUSTION_BULL',
        'BUY': 'EXHAUSTION_BULL', 
        'BULLISH': 'EXHAUSTION_BULL',
        'UP': 'EXHAUSTION_BULL',
        'SHORT': 'EXHAUSTION_BEAR',
        'SELL': 'EXHAUSTION_BEAR',
        'BEARISH': 'EXHAUSTION_BEAR',
        'DOWN': 'EXHAUSTION_BEAR'
    }
    
    if direction not in valid_directions:
        return False, f"Invalid direction for exhaustion signal: {direction}"
    
    exhaustion_type = valid_directions[direction]
    
    # Check timeframe recommendation
    recommended = STRATEGY_CONFIG["recommended_timeframes"]
    timeframe_warning = ""
    if timeframe and timeframe.upper() not in recommended:
        timeframe_warning = f" (Note: {timeframe} not ideal, prefer {', '.join(recommended)})"
    
    # Basic validation passed
    return True, f"Valid {exhaustion_type} signal: {ticker} - Trend reversal potential{timeframe_warning}"


def classify_exhaustion_signal(direction: str, price: float = None, 
                                swing_high: float = None, swing_low: float = None) -> Dict:
    """
    Classify and score an exhaustion signal
    
    Returns signal classification with metadata
    """
    direction = direction.upper()
    
    if direction in ['LONG', 'BUY', 'BULLISH', 'UP']:
        signal_type = 'EXHAUSTION_BULL'
        action = 'LONG'
        description = 'Sellers exhausted - potential reversal UP'
        color = '#7CFF6B'  # Lime green
    else:
        signal_type = 'EXHAUSTION_BEAR'
        action = 'SHORT'
        description = 'Buyers exhausted - potential reversal DOWN'
        color = '#FF6B35'  # Orange
    
    return {
        'signal_type': signal_type,
        'action': action,
        'description': description,
        'color': color,
        'strategy': 'Exhaustion Levels',
        'trade_type': 'REVERSAL'
    }


def calculate_exhaustion_targets(direction: str, entry_price: float, 
                                  swing_high: float = None, swing_low: float = None) -> Dict:
    """
    Calculate stop loss and targets for exhaustion trades
    
    For reversals:
    - Stop: Just beyond the exhaustion point (the extreme)
    - Target 1: 50% retracement of the prior move
    - Target 2: Full retracement (back to origin of move)
    """
    direction = direction.upper()
    
    if direction in ['LONG', 'BUY', 'BULLISH', 'UP']:
        # Bullish exhaustion - we're buying the dip
        stop_loss = entry_price * 0.98  # 2% below entry as default
        target_1 = entry_price * 1.03   # 3% above
        target_2 = entry_price * 1.06   # 6% above
        
        if swing_low and swing_high:
            move_size = swing_high - swing_low
            stop_loss = swing_low - (move_size * 0.1)  # Below the low
            target_1 = entry_price + (move_size * 0.5)  # 50% retracement
            target_2 = swing_high  # Full retracement
    else:
        # Bearish exhaustion - we're shorting the top
        stop_loss = entry_price * 1.02  # 2% above entry as default
        target_1 = entry_price * 0.97   # 3% below
        target_2 = entry_price * 0.94   # 6% below
        
        if swing_low and swing_high:
            move_size = swing_high - swing_low
            stop_loss = swing_high + (move_size * 0.1)  # Above the high
            target_1 = entry_price - (move_size * 0.5)  # 50% retracement
            target_2 = swing_low  # Full retracement
    
    return {
        'stop_loss': round(stop_loss, 2),
        'target_1': round(target_1, 2),
        'target_2': round(target_2, 2)
    }


def get_strategy_config() -> Dict:
    """Return current strategy configuration"""
    return STRATEGY_CONFIG.copy()


def set_strategy_enabled(enabled: bool) -> None:
    """Enable or disable the strategy"""
    STRATEGY_CONFIG["enabled"] = enabled


def update_strategy_params(params: Dict) -> None:
    """Update strategy parameters"""
    STRATEGY_CONFIG["params"].update(params)
