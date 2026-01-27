"""
Trade Ideas Scoring Algorithm

Calculates a composite score for each signal based on:
1. Base signal quality (strategy-specific)
2. Bias alignment multiplier (aligned = bonus, counter = penalty)
3. Technical confluence (RSI, ADX, zone alignment)
4. Recency bonus (newer signals score higher)
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# =========================================================================
# SCORING CONFIGURATION
# =========================================================================

# Base scores by signal type/strategy (0-100 scale)
STRATEGY_BASE_SCORES = {
    # CTA Scanner signals (highest quality)
    "GOLDEN_TOUCH": 85,
    "TWO_CLOSE_VOLUME": 80,
    "ZONE_UPGRADE": 75,
    "PULLBACK_ENTRY": 70,
    
    # Hunter Scanner signals
    "URSA_SIGNAL": 75,
    "TAURUS_SIGNAL": 75,
    
    # TradingView webhook signals
    "TRIPLE_LINE": 70,
    "EXHAUSTION_TOP": 65,
    "EXHAUSTION_BOTTOM": 65,
    "SNIPER_URSA": 60,
    "SNIPER_TAURUS": 60,
    
    # Default for unknown strategies
    "DEFAULT": 50
}

# Bias alignment multipliers
BIAS_ALIGNMENT = {
    "STRONG_ALIGNED": 1.5,      # Signal direction matches major bias (e.g., LONG + MAJOR_TORO)
    "ALIGNED": 1.25,            # Signal direction matches minor/lean bias
    "NEUTRAL": 1.0,             # Can't determine alignment
    "COUNTER_BIAS": 0.6,        # Signal goes against current bias
    "STRONG_COUNTER": 0.4       # Signal goes against major bias
}

# Technical confluence bonuses
TECHNICAL_BONUSES = {
    "ideal_rsi": 10,            # RSI in ideal range (30-40 for longs, 60-70 for shorts)
    "strong_adx": 8,            # ADX > 25 (strong trend)
    "favorable_zone": 12,       # CTA zone supports direction
    "high_rvol": 5,             # Relative volume > 1.5
    "sma_alignment": 8          # Price/SMA alignment supports direction
}

# Recency decay (hours)
RECENCY_CONFIG = {
    "full_bonus_hours": 1,      # Full recency bonus within 1 hour
    "half_life_hours": 4,       # Score decays by 50% after 4 hours
    "max_bonus": 15             # Maximum recency bonus points
}


# =========================================================================
# SCORING FUNCTIONS
# =========================================================================

def calculate_signal_score(
    signal: Dict[str, Any],
    current_bias: Dict[str, Any]
) -> Tuple[float, str, Dict[str, Any]]:
    """
    Calculate composite score for a trade signal.
    
    Args:
        signal: Signal data dict with strategy, direction, ticker, etc.
        current_bias: Current bias state with daily, weekly, cyclical levels
    
    Returns:
        Tuple of (score, bias_alignment, triggering_factors)
    """
    triggering_factors = {}
    
    # 1. Base score from strategy
    strategy = signal.get('strategy', '').upper()
    signal_type = signal.get('signal_type', '').upper()
    
    # Try strategy first, then signal_type, then default
    base_score = STRATEGY_BASE_SCORES.get(
        strategy,
        STRATEGY_BASE_SCORES.get(signal_type, STRATEGY_BASE_SCORES["DEFAULT"])
    )
    triggering_factors["base_score"] = {
        "value": base_score,
        "source": strategy or signal_type or "DEFAULT"
    }
    
    # 2. Bias alignment multiplier
    direction = signal.get('direction', '').upper()
    bias_alignment, alignment_multiplier = calculate_bias_alignment(direction, current_bias)
    triggering_factors["bias_alignment"] = {
        "value": bias_alignment,
        "multiplier": alignment_multiplier,
        "direction": direction,
        "bias_levels": {
            "daily": current_bias.get("daily", {}).get("level"),
            "weekly": current_bias.get("weekly", {}).get("level"),
            "cyclical": current_bias.get("cyclical", {}).get("level")
        }
    }
    
    # 3. Technical confluence bonuses
    tech_bonus = 0
    tech_details = {}
    
    # RSI bonus
    rsi = signal.get('rsi') or signal.get('adx')  # Some signals have RSI in metrics
    if rsi:
        rsi_bonus = calculate_rsi_bonus(rsi, direction)
        tech_bonus += rsi_bonus
        tech_details["rsi"] = {"value": rsi, "bonus": rsi_bonus}
    
    # ADX bonus
    adx = signal.get('adx')
    if adx and adx > 25:
        adx_bonus = TECHNICAL_BONUSES["strong_adx"]
        tech_bonus += adx_bonus
        tech_details["adx"] = {"value": adx, "bonus": adx_bonus}
    
    # CTA Zone bonus
    cta_zone = signal.get('cta_zone')
    if cta_zone:
        zone_bonus = calculate_zone_bonus(cta_zone, direction)
        tech_bonus += zone_bonus
        tech_details["cta_zone"] = {"value": cta_zone, "bonus": zone_bonus}
    
    # RVOL bonus
    rvol = signal.get('rvol') or signal.get('volume_ratio')
    if rvol and rvol > 1.5:
        rvol_bonus = TECHNICAL_BONUSES["high_rvol"]
        tech_bonus += rvol_bonus
        tech_details["rvol"] = {"value": rvol, "bonus": rvol_bonus}
    
    triggering_factors["technical_confluence"] = {
        "total_bonus": tech_bonus,
        "details": tech_details
    }
    
    # 4. Recency bonus
    timestamp = signal.get('timestamp')
    recency_bonus = calculate_recency_bonus(timestamp)
    triggering_factors["recency"] = {
        "bonus": recency_bonus,
        "timestamp": str(timestamp) if timestamp else None
    }
    
    # 5. Risk/Reward bonus
    rr = signal.get('risk_reward')
    rr_bonus = 0
    if rr:
        if rr >= 3:
            rr_bonus = 10
        elif rr >= 2:
            rr_bonus = 5
        triggering_factors["risk_reward"] = {"value": rr, "bonus": rr_bonus}
    
    # Calculate final score
    raw_score = base_score + tech_bonus + recency_bonus + rr_bonus
    final_score = raw_score * alignment_multiplier
    
    # Cap at 100
    final_score = min(100, max(0, final_score))
    
    triggering_factors["calculation"] = {
        "base_score": base_score,
        "technical_bonus": tech_bonus,
        "recency_bonus": recency_bonus,
        "rr_bonus": rr_bonus,
        "raw_score": raw_score,
        "alignment_multiplier": alignment_multiplier,
        "final_score": round(final_score, 2)
    }
    
    logger.info(f"📊 Scored {signal.get('ticker', 'UNKNOWN')}: {round(final_score, 2)} ({bias_alignment})")
    
    return round(final_score, 2), bias_alignment, triggering_factors


def calculate_bias_alignment(direction: str, bias_data: Dict[str, Any]) -> Tuple[str, float]:
    """
    Determine how well a signal aligns with current bias.
    
    Uses a weighted average:
    - Weekly: 50% weight (most important for swing trades)
    - Daily: 30% weight
    - Cyclical: 20% weight
    """
    if not direction:
        return "NEUTRAL", BIAS_ALIGNMENT["NEUTRAL"]
    
    is_long = direction == "LONG"
    
    # Get bias levels
    daily_level = bias_data.get("daily", {}).get("level", "")
    weekly_level = bias_data.get("weekly", {}).get("level", "")
    cyclical_level = bias_data.get("cyclical", {}).get("level", "")
    
    def level_to_score(level: str) -> int:
        """Convert bias level to numeric score (-3 to +3)"""
        level_map = {
            "MAJOR_TORO": 3, "MINOR_TORO": 2, "LEAN_TORO": 1,
            "LEAN_URSA": -1, "MINOR_URSA": -2, "MAJOR_URSA": -3
        }
        return level_map.get(level, 0)
    
    # Calculate weighted bias score
    daily_score = level_to_score(daily_level) * 0.3
    weekly_score = level_to_score(weekly_level) * 0.5
    cyclical_score = level_to_score(cyclical_level) * 0.2
    
    weighted_bias = daily_score + weekly_score + cyclical_score
    
    # Determine alignment
    if is_long:
        # LONG signals want positive bias
        if weighted_bias >= 2:
            return "STRONG_ALIGNED", BIAS_ALIGNMENT["STRONG_ALIGNED"]
        elif weighted_bias >= 0.5:
            return "ALIGNED", BIAS_ALIGNMENT["ALIGNED"]
        elif weighted_bias >= -0.5:
            return "NEUTRAL", BIAS_ALIGNMENT["NEUTRAL"]
        elif weighted_bias >= -2:
            return "COUNTER_BIAS", BIAS_ALIGNMENT["COUNTER_BIAS"]
        else:
            return "STRONG_COUNTER", BIAS_ALIGNMENT["STRONG_COUNTER"]
    else:
        # SHORT signals want negative bias
        if weighted_bias <= -2:
            return "STRONG_ALIGNED", BIAS_ALIGNMENT["STRONG_ALIGNED"]
        elif weighted_bias <= -0.5:
            return "ALIGNED", BIAS_ALIGNMENT["ALIGNED"]
        elif weighted_bias <= 0.5:
            return "NEUTRAL", BIAS_ALIGNMENT["NEUTRAL"]
        elif weighted_bias <= 2:
            return "COUNTER_BIAS", BIAS_ALIGNMENT["COUNTER_BIAS"]
        else:
            return "STRONG_COUNTER", BIAS_ALIGNMENT["STRONG_COUNTER"]


def calculate_rsi_bonus(rsi: float, direction: str) -> int:
    """Calculate RSI bonus based on ideal ranges for direction"""
    if direction == "LONG":
        # Ideal: oversold (30-40) or recovering (40-50)
        if 30 <= rsi <= 40:
            return TECHNICAL_BONUSES["ideal_rsi"]
        elif 40 < rsi <= 50:
            return TECHNICAL_BONUSES["ideal_rsi"] // 2
    elif direction == "SHORT":
        # Ideal: overbought (60-70) or weakening (50-60)
        if 60 <= rsi <= 70:
            return TECHNICAL_BONUSES["ideal_rsi"]
        elif 50 <= rsi < 60:
            return TECHNICAL_BONUSES["ideal_rsi"] // 2
    
    return 0


def calculate_zone_bonus(cta_zone: str, direction: str) -> int:
    """Calculate CTA zone bonus based on alignment with direction"""
    zone_upper = cta_zone.upper() if cta_zone else ""
    
    if direction == "LONG":
        if zone_upper in ["MAX_LONG", "DE_LEVERAGING"]:
            return TECHNICAL_BONUSES["favorable_zone"]
        elif zone_upper == "WATERFALL":
            return -TECHNICAL_BONUSES["favorable_zone"]  # Penalty
    elif direction == "SHORT":
        if zone_upper in ["CAPITULATION", "WATERFALL"]:
            return TECHNICAL_BONUSES["favorable_zone"]
        elif zone_upper == "MAX_LONG":
            return -TECHNICAL_BONUSES["favorable_zone"]  # Penalty
    
    return 0


def calculate_recency_bonus(timestamp) -> int:
    """Calculate bonus for recent signals"""
    if not timestamp:
        return 0
    
    try:
        if isinstance(timestamp, str):
            signal_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            signal_time = timestamp
        
        # Make both timezone-naive for comparison
        if signal_time.tzinfo:
            signal_time = signal_time.replace(tzinfo=None)
        
        now = datetime.now()
        age_hours = (now - signal_time).total_seconds() / 3600
        
        if age_hours <= RECENCY_CONFIG["full_bonus_hours"]:
            return RECENCY_CONFIG["max_bonus"]
        elif age_hours <= RECENCY_CONFIG["half_life_hours"]:
            # Linear decay
            decay_factor = 1 - (age_hours - RECENCY_CONFIG["full_bonus_hours"]) / (RECENCY_CONFIG["half_life_hours"] - RECENCY_CONFIG["full_bonus_hours"])
            return int(RECENCY_CONFIG["max_bonus"] * decay_factor)
        else:
            return 0
    
    except Exception as e:
        logger.warning(f"Error calculating recency bonus: {e}")
        return 0


def score_signal_batch(signals: list, current_bias: Dict[str, Any]) -> list:
    """
    Score a batch of signals and return sorted by score descending.
    """
    scored_signals = []
    
    for signal in signals:
        score, alignment, factors = calculate_signal_score(signal, current_bias)
        
        signal_copy = signal.copy()
        signal_copy['score'] = score
        signal_copy['bias_alignment'] = alignment
        signal_copy['triggering_factors'] = factors
        
        scored_signals.append(signal_copy)
    
    # Sort by score descending
    scored_signals.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    return scored_signals


def get_top_trade_ideas(signals: list, current_bias: Dict[str, Any], limit: int = 10) -> list:
    """
    Get the top N trade ideas ranked by score.
    """
    scored = score_signal_batch(signals, current_bias)
    return scored[:limit]


def is_signal_strong(score: float) -> bool:
    """Determine if a signal should get the pulse animation (top tier)"""
    return score >= 75


def get_score_tier(score: float) -> str:
    """Get the tier classification for UI display"""
    if score >= 85:
        return "EXCEPTIONAL"
    elif score >= 75:
        return "STRONG"
    elif score >= 60:
        return "MODERATE"
    elif score >= 45:
        return "WEAK"
    else:
        return "LOW"
