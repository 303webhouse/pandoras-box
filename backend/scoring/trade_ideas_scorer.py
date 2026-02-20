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
# Reduced by 20 points to prevent score inflation
STRATEGY_BASE_SCORES = {
    # CTA Scanner signals (highest quality)
    "GOLDEN_TOUCH": 65,
    "TWO_CLOSE_VOLUME": 60,
    "PULLBACK_ENTRY": 50,
    "TRAPPED_LONGS": 55,        # Short signal: bearish capitulation play
    "TRAPPED_SHORTS": 55,       # Long signal: short squeeze play
    "BEARISH_BREAKDOWN": 50,    # Short signal: key support break
    "DEATH_CROSS": 60,          # Short signal: 50/200 SMA cross (high conviction)
    "RESISTANCE_REJECTION": 45, # Short signal: failed breakout at resistance
    
    # Hunter Scanner signals
    "URSA_SIGNAL": 55,
    "TAURUS_SIGNAL": 55,
    
    # TradingView webhook signals - Triple Line variants
    "TRIPLE_LINE": 50,
    "TRIPLE LINE TREND RETRACEMENT": 50,
    "TRIPLE_LINE_TREND_RETRACEMENT": 50,
    
    # BTC macro confluence (highest conviction)
    "APIS_CALL": 70,
    "KODIAK_CALL": 70,
    
    # Exhaustion signals
    "EXHAUSTION": 45,
    "EXHAUSTION_TOP": 45,
    "EXHAUSTION_BOTTOM": 45,
    
    # Sniper signals
    "SNIPER": 40,
    "SNIPER_URSA": 40,
    "SNIPER_TAURUS": 40,
    
    # Generic types
    "BULLISH_TRADE": 35,
    "BEAR_CALL": 35,
    
    # Default for unknown strategies
    "DEFAULT": 30
}

# Bias alignment multipliers (softened to allow counter-trend signals through)
BIAS_ALIGNMENT = {
    "STRONG_ALIGNED": 1.25,     # Signal direction matches strong composite bias
    "ALIGNED": 1.10,            # Signal direction matches moderate composite bias
    "NEUTRAL": 1.0,             # Composite near zero / can't determine
    "COUNTER_BIAS": 0.85,       # Signal goes against moderate composite bias
    "STRONG_COUNTER": 0.70      # Signal goes against strong composite bias
}

# Technical confluence bonuses
# Cut in half to prevent bonus stacking
TECHNICAL_BONUSES = {
    "ideal_rsi": 5,             # RSI in ideal range (30-40 for longs, 60-70 for shorts)
    "strong_adx": 4,            # ADX > 25 (strong trend)
    "favorable_zone": 6,        # CTA zone supports direction
    "high_rvol": 3,             # Relative volume > 1.5
    "sma_alignment": 4          # Price/SMA alignment supports direction
}

# Recency decay (hours)
RECENCY_CONFIG = {
    "full_bonus_hours": 1,      # Full recency bonus within 1 hour
    "half_life_hours": 4,       # Score decays by 50% after 4 hours
    "max_bonus": 8              # Maximum recency bonus points (reduced from 15)
}

# Sector priority bonuses
SECTOR_PRIORITY_BONUS = {
    "leading_aligned": 8,       # Signal in leading sector, aligned with bullish bias
    "lagging_counter": 8,       # Signal in lagging sector, aligned with bearish bias (short)
    "neutral_sector": 0,        # Neutral sector, no bonus
    "misaligned_sector": -5     # Signal against sector trend (e.g., long in lagging during bull)
}

# Ticker to sector mapping (common tickers)
TICKER_SECTORS = {
    # Technology
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology", 
    "GOOGL": "Technology", "GOOG": "Technology", "META": "Technology",
    "AMD": "Technology", "INTC": "Technology", "CRM": "Technology",
    "ORCL": "Technology", "ADBE": "Technology", "NOW": "Technology",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary", "NKE": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "MCD": "Consumer Discretionary",
    "NFLX": "Consumer Discretionary",
    # Healthcare
    "UNH": "Healthcare", "JNJ": "Healthcare", "PFE": "Healthcare",
    "ABBV": "Healthcare", "MRK": "Healthcare", "LLY": "Healthcare",
    # Financials
    "JPM": "Financials", "BAC": "Financials", "GS": "Financials",
    "MS": "Financials", "WFC": "Financials", "C": "Financials",
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy",
    # Industrials
    "CAT": "Industrials", "BA": "Industrials", "UPS": "Industrials",
    "HON": "Industrials", "GE": "Industrials", "RTX": "Industrials",
    # Consumer Staples
    "PG": "Consumer Staples", "KO": "Consumer Staples", "PEP": "Consumer Staples",
    "WMT": "Consumer Staples", "COST": "Consumer Staples",
    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    # Materials
    "LIN": "Materials", "APD": "Materials", "SHW": "Materials",
    # Real Estate
    "PLD": "Real Estate", "AMT": "Real Estate", "SPG": "Real Estate",
    # Communication Services
    "DIS": "Communication Services", "CMCSA": "Communication Services",
    "VZ": "Communication Services", "T": "Communication Services"
}


# =========================================================================
# SCORING FUNCTIONS
# =========================================================================

def calculate_signal_score(
    signal: Dict[str, Any],
    current_bias: Dict[str, Any],
    sector_strength: Dict[str, Any] = None
) -> Tuple[float, str, Dict[str, Any]]:
    """
    Calculate composite score for a trade signal.
    
    Args:
        signal: Signal data dict with strategy, direction, ticker, etc.
        current_bias: Current bias state with daily, weekly, cyclical levels
        sector_strength: Optional sector strength data for priority scoring
    
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
        "composite_score": current_bias.get("composite_score"),
        "source": "composite" if "composite_score" in current_bias else "legacy_voting"
    }
    
    # 3. Technical confluence bonuses
    tech_bonus = 0
    tech_details = {}
    
    # RSI bonus
    rsi = signal.get('rsi')  # RSI only - never fall back to ADX
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

    # Zone upgrade bonus - signal coincides with zone improvement
    zone_upgrade_ctx = signal.get('zone_upgrade_context')
    if zone_upgrade_ctx and zone_upgrade_ctx.get('zone_upgraded'):
        zone_up_bonus = TECHNICAL_BONUSES.get("favorable_zone", 4)
        tech_bonus += zone_up_bonus
        tech_details["zone_upgrade"] = {
            "from": zone_upgrade_ctx.get("previous_zone"),
            "to": zone_upgrade_ctx.get("current_zone"),
            "bonus": zone_up_bonus
        }

    # Zone downgrade bonus - SHORT signal coincides with zone deterioration
    zone_downgrade_ctx = signal.get('zone_downgrade_context')
    if zone_downgrade_ctx and zone_downgrade_ctx.get('zone_downgraded'):
        zone_down_bonus = TECHNICAL_BONUSES.get("favorable_zone", 4)
        tech_bonus += zone_down_bonus
        tech_details["zone_downgrade"] = {
            "from": zone_downgrade_ctx.get("previous_zone"),
            "to": zone_downgrade_ctx.get("current_zone"),
            "bonus": zone_down_bonus
        }

    # Confluence bonus - multiple aligned signals on same ticker
    confluence = signal.get('confluence')
    if confluence and confluence.get('count', 0) >= 2:
        confluence_boost = confluence.get('boost', 0)
        # Scale scanner boost (25-65) to scorer range and cap at 10.
        scorer_confluence_bonus = min(confluence_boost // 5, 10)
        tech_bonus += scorer_confluence_bonus
        tech_details["confluence"] = {
            "signals": confluence.get("count"),
            "combo": confluence.get("combo"),
            "bonus": scorer_confluence_bonus
        }
    
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
    
    # 6. Sector priority bonus
    sector_bonus = 0
    ticker = signal.get('ticker', '').upper()
    sector = TICKER_SECTORS.get(ticker)
    
    if sector and sector_strength:
        sector_data = sector_strength.get(sector, {})
        sector_trend = sector_data.get("trend", "neutral")
        
        # Determine if sector alignment helps or hurts
        is_bullish_signal = direction in ["LONG", "BUY"]
        is_bearish_signal = direction in ["SHORT", "SELL"]
        
        if sector_trend == "leading":
            if is_bullish_signal:
                sector_bonus = SECTOR_PRIORITY_BONUS["leading_aligned"]
            else:
                sector_bonus = SECTOR_PRIORITY_BONUS["misaligned_sector"]
        elif sector_trend == "lagging":
            if is_bearish_signal:
                sector_bonus = SECTOR_PRIORITY_BONUS["lagging_counter"]
            else:
                sector_bonus = SECTOR_PRIORITY_BONUS["misaligned_sector"]
        
        triggering_factors["sector_priority"] = {
            "sector": sector,
            "trend": sector_trend,
            "bonus": sector_bonus,
            "rank": sector_data.get("rank")
        }
    
    # Calculate final score
    raw_score = base_score + tech_bonus + recency_bonus + rr_bonus + sector_bonus
    final_score = raw_score * alignment_multiplier

    # =========================================================================
    # CIRCUIT BREAKER SCORING MODIFIERS
    # =========================================================================
    circuit_breaker_modifier = 1.0
    cb_applied = False

    try:
        from webhooks.circuit_breaker import get_circuit_breaker_state
        cb_state = get_circuit_breaker_state()

        if cb_state.get("active"):
            cb_trigger = cb_state.get("trigger", "")
            scoring_mod = cb_state.get("scoring_modifier", 1.0)
            is_long = direction in ["LONG", "BUY"]
            is_short = direction in ["SHORT", "SELL"]

            # Determine signal type for exhaustion/reversal bonus
            is_exhaustion = signal_type in ["EXHAUSTION", "EXHAUSTION_TOP", "EXHAUSTION_BOTTOM"]
            is_reversal = signal.get("trade_type", "").upper() == "REVERSAL"

            # BEARISH circuit breaker (SPY down, VIX spike)
            if cb_trigger in ["spy_down_1pct", "spy_down_2pct", "vix_spike", "vix_extreme"]:
                if is_long:
                    # Penalize LONG signals
                    circuit_breaker_modifier = scoring_mod
                    cb_applied = True
                    triggering_factors["circuit_breaker_penalty"] = {
                        "trigger": cb_trigger,
                        "direction": "LONG",
                        "modifier": scoring_mod,
                        "reason": "Bearish circuit breaker penalizes longs"
                    }
                elif is_short:
                    # Boost SHORT signals
                    circuit_breaker_modifier = 1.3
                    cb_applied = True
                    triggering_factors["circuit_breaker_bonus"] = {
                        "trigger": cb_trigger,
                        "direction": "SHORT",
                        "modifier": 1.3,
                        "reason": "Bearish circuit breaker boosts shorts"
                    }

                    # Extra boost for exhaustion/reversal shorts
                    if is_exhaustion or is_reversal:
                        circuit_breaker_modifier *= 1.2
                        triggering_factors["circuit_breaker_bonus"]["exhaustion_boost"] = 1.2
                        triggering_factors["circuit_breaker_bonus"]["total_modifier"] = circuit_breaker_modifier

            # BULLISH circuit breaker (SPY recovery)
            elif cb_trigger in ["spy_up_2pct", "spy_recovery"]:
                if is_short:
                    # Penalize SHORT signals
                    circuit_breaker_modifier = scoring_mod
                    cb_applied = True
                    triggering_factors["circuit_breaker_penalty"] = {
                        "trigger": cb_trigger,
                        "direction": "SHORT",
                        "modifier": scoring_mod,
                        "reason": "Bullish circuit breaker penalizes shorts"
                    }
                elif is_long:
                    # Boost LONG signals
                    circuit_breaker_modifier = 1.3
                    cb_applied = True
                    triggering_factors["circuit_breaker_bonus"] = {
                        "trigger": cb_trigger,
                        "direction": "LONG",
                        "modifier": 1.3,
                        "reason": "Bullish circuit breaker boosts longs"
                    }

                    # Extra boost for exhaustion/reversal longs
                    if is_exhaustion or is_reversal:
                        circuit_breaker_modifier *= 1.2
                        triggering_factors["circuit_breaker_bonus"]["exhaustion_boost"] = 1.2
                        triggering_factors["circuit_breaker_bonus"]["total_modifier"] = circuit_breaker_modifier

            # Apply modifier
            if cb_applied:
                final_score *= circuit_breaker_modifier
                logger.info(f"⚠️ Circuit breaker modifier applied to {signal.get('ticker')}: {circuit_breaker_modifier:.2f}x")

    except Exception as e:
        logger.warning(f"Error applying circuit breaker modifiers: {e}")

    # Cap at 100
    final_score = min(100, max(0, final_score))

    triggering_factors["calculation"] = {
        "base_score": base_score,
        "technical_bonus": tech_bonus,
        "recency_bonus": recency_bonus,
        "rr_bonus": rr_bonus,
        "sector_bonus": sector_bonus,
        "raw_score": raw_score,
        "alignment_multiplier": alignment_multiplier,
        "circuit_breaker_modifier": circuit_breaker_modifier if cb_applied else None,
        "final_score": round(final_score, 2)
    }
    
    logger.info(f"📊 Scored {signal.get('ticker', 'UNKNOWN')}: {round(final_score, 2)} ({bias_alignment})")
    
    return round(final_score, 2), bias_alignment, triggering_factors


def calculate_bias_alignment(direction: str, bias_data: Dict[str, Any]) -> Tuple[str, float]:
    """
    Determine how well a signal aligns with the composite bias engine.
    
    Uses the composite_score directly (range: -1.0 to +1.0) as the single
    source of truth, replacing the old daily/weekly/cyclical weighted average.
    
    Falls back to old voting system data if composite is unavailable.
    """
    if not direction:
        return "NEUTRAL", BIAS_ALIGNMENT["NEUTRAL"]
    
    composite_score = _get_composite_score(bias_data)
    is_long = direction.upper() in ("LONG", "BUY")
    
    # For LONG signals, positive composite = aligned; for SHORT, negative = aligned
    # Flip sign for shorts so the same thresholds work for both directions
    directional_score = composite_score if is_long else -composite_score
    
    if directional_score >= 0.4:
        return "STRONG_ALIGNED", BIAS_ALIGNMENT["STRONG_ALIGNED"]
    elif directional_score >= 0.1:
        return "ALIGNED", BIAS_ALIGNMENT["ALIGNED"]
    elif directional_score >= -0.1:
        return "NEUTRAL", BIAS_ALIGNMENT["NEUTRAL"]
    elif directional_score >= -0.4:
        return "COUNTER_BIAS", BIAS_ALIGNMENT["COUNTER_BIAS"]
    else:
        return "STRONG_COUNTER", BIAS_ALIGNMENT["STRONG_COUNTER"]


def _get_composite_score(bias_data: Dict[str, Any]) -> float:
    """
    Extract composite score, trying multiple sources:
    1. composite_score field passed directly in bias_data
    2. Live fetch from cached composite in Redis
    3. Fallback: derive from old voting system data
    """
    # Source 1: Direct composite score in bias_data
    if "composite_score" in bias_data:
        try:
            return float(bias_data["composite_score"])
        except (TypeError, ValueError):
            pass
    
    # Source 2: Fetch from composite engine cache
    try:
        import asyncio
        from bias_engine.composite import get_cached_composite
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context — can't await here synchronously.
            # Try a thread-safe approach via the cached Redis value.
            import json
            from database.redis_client import _redis_client
            if _redis_client:
                import redis.asyncio
                # Fall through to source 3 if we can't get it synchronously
                pass
        else:
            result = loop.run_until_complete(get_cached_composite())
            if result:
                return float(result.composite_score)
    except Exception:
        pass
    
    # Source 3: Fallback — derive from old voting system levels
    return _derive_score_from_old_bias(bias_data)


def _derive_score_from_old_bias(bias_data: Dict[str, Any]) -> float:
    """
    Fallback: convert old daily/weekly/cyclical levels to an approximate
    composite score in [-1, 1] range. Used only when composite engine
    data is unavailable.
    """
    level_map = {
        "MAJOR_TORO": 0.8, "TORO_MAJOR": 0.8,
        "MINOR_TORO": 0.4, "TORO_MINOR": 0.4,
        "LEAN_TORO": 0.15,
        "NEUTRAL": 0.0,
        "LEAN_URSA": -0.15,
        "MINOR_URSA": -0.4, "URSA_MINOR": -0.4,
        "MAJOR_URSA": -0.8, "URSA_MAJOR": -0.8,
    }
    
    daily_level = bias_data.get("daily", {}).get("level", "")
    weekly_level = bias_data.get("weekly", {}).get("level", "")
    cyclical_level = bias_data.get("cyclical", {}).get("level", "")
    
    d = level_map.get(daily_level, 0.0)
    w = level_map.get(weekly_level, 0.0)
    c = level_map.get(cyclical_level, 0.0)
    
    return max(-1.0, min(1.0, d * 0.3 + w * 0.5 + c * 0.2))


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


def score_signal_batch(signals: list, current_bias: Dict[str, Any], sector_strength: Dict[str, Any] = None) -> list:
    """
    Score a batch of signals and return sorted by score descending.
    Optionally includes sector priority based on sector_strength data.
    """
    scored_signals = []
    
    for signal in signals:
        score, alignment, factors = calculate_signal_score(signal, current_bias, sector_strength)
        
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
    if score >= 75:
        return "EXCEPTIONAL"
    elif score >= 60:
        return "STRONG"
    elif score >= 45:
        return "MODERATE"
    elif score >= 30:
        return "WEAK"
    else:
        return "LOW"
