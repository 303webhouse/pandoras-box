"""
Signal Classification and Ranking
Determines signal type (APIS CALL, KODIAK CALL, etc.) based on macro alignment
"""

def classify_signal(
    direction: str,
    bias_level: str,
    bias_aligned: bool,
    adx: float,
    line_separation: float
) -> str:
    """
    Classify signal into one of four categories:
    - APIS CALL: Strong bullish, macro-aligned
    - KODIAK CALL: Strong bearish, macro-aligned
    - BULLISH TRADE: Good long setup, less conviction
    - BEAR CALL: Good short setup, less conviction
    
    Args:
        direction: "LONG" or "SHORT"
        bias_level: Current macro bias (URSA_MAJOR to TORO_MAJOR)
        bias_aligned: Whether signal aligns with bias
        adx: ADX value (trend strength)
        line_separation: Distance between lines in points
    
    Returns:
        Signal type string
    """
    
    # Strong signal criteria
    is_strong_setup = adx > 30 and line_separation > 15
    is_major_bias = bias_level in ["URSA_MAJOR", "TORO_MAJOR"]
    
    # Classification logic
    if direction == "LONG":
        # Strong bullish signal if:
        # - Aligned with bullish bias (Toro Minor/Major)
        # - Strong technical setup (high ADX + wide separation)
        if bias_aligned and (is_strong_setup or is_major_bias):
            return "APIS_CALL"
        else:
            return "BULLISH_TRADE"
    
    elif direction == "SHORT":
        # Strong bearish signal if:
        # - Aligned with bearish bias (Ursa Minor/Major)
        # - Strong technical setup
        if bias_aligned and (is_strong_setup or is_major_bias):
            return "KODIAK_CALL"
        else:
            return "BEAR_CALL"
    
    # Fallback (shouldn't reach here with valid inputs)
    return "BULLISH_TRADE" if direction == "LONG" else "BEAR_CALL"

def calculate_signal_score(
    signal_type: str,
    risk_reward: float,
    adx: float,
    line_separation: float,
    bias_aligned: bool
) -> float:
    """
    Calculate overall signal quality score for ranking
    Returns: 0.0 to 100.0
    
    Used to rank the "10 best trades" in the UI
    """
    
    # Base score from signal type
    type_scores = {
        "APIS_CALL": 40,
        "KODIAK_CALL": 40,
        "BULLISH_TRADE": 20,
        "BEAR_CALL": 20
    }
    base_score = type_scores.get(signal_type, 0)
    
    # Risk/reward scoring (max 30 points)
    # 2:1 R:R = 20 points, 3:1 = 25 points, 4:1+ = 30 points
    rr_score = min(risk_reward * 7.5, 30)
    
    # Technical strength scoring (max 20 points)
    # ADX component (10 points)
    adx_score = min((adx - 25) / 2.5, 10)
    # Line separation component (10 points)
    sep_score = min((line_separation - 10) / 2, 10)
    tech_score = adx_score + sep_score
    
    # Bias alignment bonus (10 points)
    alignment_score = 10 if bias_aligned else 0
    
    # Total score
    total = base_score + rr_score + tech_score + alignment_score
    
    return round(total, 1)

def get_signal_display_config(signal_type: str) -> dict:
    """
    Get UI display configuration for each signal type
    Returns color codes and styling info
    """
    
    configs = {
        "APIS_CALL": {
            "color": "#7CFF6B",  # Bright lime green
            "label": "🐝 APIS CALL",
            "priority": 1
        },
        "BULLISH_TRADE": {
            "color": "#4CAF50",  # Darker green
            "label": "📈 BULLISH TRADE",
            "priority": 2
        },
        "KODIAK_CALL": {
            "color": "#FF6B35",  # Bright orange
            "label": "🐻 KODIAK CALL",
            "priority": 1
        },
        "BEAR_CALL": {
            "color": "#FF8C42",  # Darker orange
            "label": "📉 BEAR CALL",
            "priority": 2
        }
    }
    
    return configs.get(signal_type, {
        "color": "#888888",
        "label": "TRADE",
        "priority": 3
    })
