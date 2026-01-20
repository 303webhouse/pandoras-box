"""
Ursa/Taurus Hunter-Sniper Strategy Validator
Identifies "trapped traders" with institutional volume backing

Strategy Logic:
- URSA (Bear): Price < 200 SMA, Price < VWAP, ADX > 20, RSI > 40, RVOL > 1.5
- TAURUS (Bull): Price > 200 SMA, Price > VWAP, ADX > 20, RSI < 60, RVOL > 1.5

Target: <10ms execution time for webhook validation
"""

from typing import Tuple, Dict, Any, Optional
from datetime import datetime

# Strategy configuration (can be toggled)
STRATEGY_CONFIG = {
    "enabled": True,
    "name": "Ursa/Taurus Hunter-Sniper",
    "version": "1.0.0",
    "params": {
        "adx_threshold": 20,
        "rsi_bull_max": 60,
        "rsi_bear_min": 40,
        "rvol_threshold": 1.5,
    }
}

async def validate_ursa_signal(signal: Dict[Any, Any]) -> Tuple[bool, str]:
    """
    Validate if a signal meets URSA (Bearish) strategy requirements
    
    URSA Criteria:
    - Price < 200 SMA (macro bearish)
    - Price < 20-Day VWAP (buyers trapped)
    - ADX > 20 (trending)
    - RSI > 40 (not oversold yet - room to fall)
    - RVOL > 1.5 (institutional volume)
    
    Returns:
        (is_valid, details): Boolean and explanation string
    """
    if not STRATEGY_CONFIG["enabled"]:
        return False, "Ursa/Taurus strategy is disabled"
    
    params = STRATEGY_CONFIG["params"]
    
    # Extract signal data
    ticker = signal.get('ticker')
    direction = signal.get('direction', '').upper()
    price = signal.get('current_price') or signal.get('entry_price')
    sma_200 = signal.get('sma_200')
    vwap = signal.get('vwap') or signal.get('vwap_20')
    adx = signal.get('adx')
    rsi = signal.get('rsi')
    rvol = signal.get('rvol')
    
    # Must be a SHORT/BEARISH signal for URSA
    if direction not in ["SHORT", "BEARISH", "SELL"]:
        return False, f"URSA requires SHORT direction, got: {direction}"
    
    # Validation checks
    errors = []
    
    # 1. Macro Filter: Price < 200 SMA
    if sma_200 and price:
        if price >= sma_200:
            errors.append(f"Price ${price:.2f} above 200 SMA ${sma_200:.2f}")
    
    # 2. VWAP Trap: Price < VWAP (buyers underwater)
    if vwap and price:
        if price >= vwap:
            errors.append(f"Price ${price:.2f} above VWAP ${vwap:.2f} - no trapped longs")
    
    # 3. Trend Strength: ADX > threshold
    if adx is not None:
        if adx < params["adx_threshold"]:
            errors.append(f"ADX {adx:.1f} < {params['adx_threshold']} - weak trend")
    
    # 4. Momentum Room: RSI > 40 (not oversold)
    if rsi is not None:
        if rsi <= params["rsi_bear_min"]:
            errors.append(f"RSI {rsi:.1f} <= {params['rsi_bear_min']} - already oversold")
    
    # 5. Institutional Volume: RVOL > 1.5
    if rvol is not None:
        if rvol < params["rvol_threshold"]:
            errors.append(f"RVOL {rvol:.2f} < {params['rvol_threshold']} - low institutional interest")
    
    if errors:
        return False, f"URSA rejected: {'; '.join(errors)}"
    
    return True, f"Valid URSA signal: {ticker} SHORT - trapped longs detected"


async def validate_taurus_signal(signal: Dict[Any, Any]) -> Tuple[bool, str]:
    """
    Validate if a signal meets TAURUS (Bullish) strategy requirements
    
    TAURUS Criteria:
    - Price > 200 SMA (macro bullish)
    - Price > 20-Day VWAP (shorts trapped)
    - ADX > 20 (trending)
    - RSI < 60 (not overbought yet - room to rise)
    - RVOL > 1.5 (institutional volume)
    
    Returns:
        (is_valid, details): Boolean and explanation string
    """
    if not STRATEGY_CONFIG["enabled"]:
        return False, "Ursa/Taurus strategy is disabled"
    
    params = STRATEGY_CONFIG["params"]
    
    # Extract signal data
    ticker = signal.get('ticker')
    direction = signal.get('direction', '').upper()
    price = signal.get('current_price') or signal.get('entry_price')
    sma_200 = signal.get('sma_200')
    vwap = signal.get('vwap') or signal.get('vwap_20')
    adx = signal.get('adx')
    rsi = signal.get('rsi')
    rvol = signal.get('rvol')
    
    # Must be a LONG/BULLISH signal for TAURUS
    if direction not in ["LONG", "BULLISH", "BUY"]:
        return False, f"TAURUS requires LONG direction, got: {direction}"
    
    # Validation checks
    errors = []
    
    # 1. Macro Filter: Price > 200 SMA
    if sma_200 and price:
        if price <= sma_200:
            errors.append(f"Price ${price:.2f} below 200 SMA ${sma_200:.2f}")
    
    # 2. VWAP Trap: Price > VWAP (shorts underwater)
    if vwap and price:
        if price <= vwap:
            errors.append(f"Price ${price:.2f} below VWAP ${vwap:.2f} - no trapped shorts")
    
    # 3. Trend Strength: ADX > threshold
    if adx is not None:
        if adx < params["adx_threshold"]:
            errors.append(f"ADX {adx:.1f} < {params['adx_threshold']} - weak trend")
    
    # 4. Momentum Room: RSI < 60 (not overbought)
    if rsi is not None:
        if rsi >= params["rsi_bull_max"]:
            errors.append(f"RSI {rsi:.1f} >= {params['rsi_bull_max']} - already overbought")
    
    # 5. Institutional Volume: RVOL > 1.5
    if rvol is not None:
        if rvol < params["rvol_threshold"]:
            errors.append(f"RVOL {rvol:.2f} < {params['rvol_threshold']} - low institutional interest")
    
    if errors:
        return False, f"TAURUS rejected: {'; '.join(errors)}"
    
    return True, f"Valid TAURUS signal: {ticker} LONG - trapped shorts detected"


async def validate_ursa_taurus_signal(signal: Dict[Any, Any]) -> Tuple[bool, str]:
    """
    Main entry point - routes to URSA or TAURUS based on signal direction
    """
    direction = signal.get('direction', '').upper()
    
    if direction in ["SHORT", "BEARISH", "SELL"]:
        return await validate_ursa_signal(signal)
    elif direction in ["LONG", "BULLISH", "BUY"]:
        return await validate_taurus_signal(signal)
    else:
        return False, f"Unknown direction: {direction}"


def calculate_hunter_score(signal_data: Dict[Any, Any]) -> float:
    """
    Calculate quality score for Hunter signals (0.0 to 100.0)
    
    Scoring weights:
    - ADX strength: 25%
    - RSI positioning: 25%
    - RVOL intensity: 30%
    - VWAP distance: 20%
    """
    score = 0.0
    
    adx = signal_data.get('adx', 0)
    rsi = signal_data.get('rsi', 50)
    rvol = signal_data.get('rvol', 1.0)
    vwap_distance = abs(signal_data.get('pct_distance_from_vwap', 0))
    
    # ADX score (20-50 range → 0-25 points)
    if adx >= 20:
        adx_score = min((adx - 20) / 30 * 25, 25)
        score += adx_score
    
    # RSI score (optimal is 45-55 for flexibility)
    # Further from extremes = better
    if 30 <= rsi <= 70:
        rsi_score = (1 - abs(rsi - 50) / 20) * 25
        score += max(rsi_score, 0)
    
    # RVOL score (1.5-5.0 range → 0-30 points)
    if rvol >= 1.5:
        rvol_score = min((rvol - 1.5) / 3.5 * 30, 30)
        score += rvol_score
    
    # VWAP distance score (1-10% range → 0-20 points)
    if vwap_distance >= 1:
        vwap_score = min(vwap_distance / 10 * 20, 20)
        score += vwap_score
    
    return round(score, 1)


def get_strategy_config() -> Dict:
    """Return current strategy configuration"""
    return STRATEGY_CONFIG.copy()


def set_strategy_enabled(enabled: bool) -> None:
    """Enable or disable the strategy"""
    STRATEGY_CONFIG["enabled"] = enabled


def update_strategy_params(params: Dict) -> None:
    """Update strategy parameters"""
    STRATEGY_CONFIG["params"].update(params)
