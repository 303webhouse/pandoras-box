"""
Automated Bias Scheduler

Handles automatic refresh of all bias indicators:
- Daily Bias: Refreshes at 9:45 AM ET every trading day (intraday factors)
- Weekly Bias: Refreshes at 9:45 AM ET every Monday (6-factor model)
- Cyclical Bias: Long-term macro indicators (200 SMA, yield curve, Sahm Rule, etc.)

Hierarchical system: Cyclical â†’ Weekly â†’ Daily (higher timeframes modify lower)

Stores historical values to show trends (vs previous period).
"""

import os
import json
import logging
import asyncio
import pytz
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

# Eastern Time for market hours
ET = pytz.timezone('America/New_York')

def get_eastern_now() -> datetime:
    """Get current time in Eastern Time (market hours)"""
    return datetime.now(ET)

# State file for bias history
BIAS_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bias_history.json")
BASELINE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "weekly_baseline.json")

# Weekly baseline storage (Monday's reading)
_weekly_baseline = {
    "timestamp": None,
    "total_vote": None,
    "factors": {},
    "level": None
}

# Scheduler status tracking
_scheduler_status = {
    "cta_scanner": {
        "last_run": None,
        "signals_found": 0,
        "status": "idle",
        "interval": "15-30 min (market hours)"
    },
    "crypto_scanner": {
        "last_run": None,
        "signals_found": 0,
        "status": "idle",
        "interval": "30 min (24/7)"
    },
    "bias_refresh": {
        "last_run": None,
        "status": "idle"
    },
    "composite_bias": {
        "last_run": None,
        "status": "idle",
        "interval": "15 min"
    },
    "price_collection": {
        "last_run": None,
        "status": "idle",
        "interval": "5 min"
    },
    "benchmark_tracker": {
        "last_run": None,
        "status": "idle",
        "interval": "Daily 4:10 PM ET"
    },
    "portfolio_monitor": {
        "last_run": None,
        "status": "idle",
        "interval": "Daily 4:15 PM ET"
    },
    "health_monitor": {
        "last_run": None,
        "status": "idle",
        "interval": "Daily 4:30 PM ET"
    },
    "scheduler_started": None
}

def get_scheduler_status() -> Dict[str, Any]:
    """Get current scheduler status for all scheduled tasks"""
    now = get_eastern_now()
    is_market_hours = is_trading_day() and 9 <= now.hour <= 16
    
    # Calculate CTA interval based on time of day
    if is_market_hours:
        if now.hour == 9 or (now.hour == 10 and now.minute < 30) or now.hour >= 15:
            cta_interval = "15 min (volatility period)"
        else:
            cta_interval = "30 min (mid-day)"
    else:
        cta_interval = "Paused (after hours)"
    
    # Calculate next CTA run
    if is_market_hours:
        # Next 15 or 30 min mark
        if now.hour == 9 or (now.hour == 10 and now.minute < 30) or now.hour >= 15:
            # Every 15 min
            next_min = ((now.minute // 15) + 1) * 15
            if next_min >= 60:
                next_cta = now.replace(minute=0, second=0) + timedelta(hours=1)
            else:
                next_cta = now.replace(minute=next_min, second=0)
        else:
            # Every 30 min
            next_min = 30 if now.minute < 30 else 60
            if next_min >= 60:
                next_cta = now.replace(minute=0, second=0) + timedelta(hours=1)
            else:
                next_cta = now.replace(minute=next_min, second=0)
        next_cta_str = next_cta.strftime("%H:%M ET")
    else:
        next_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        if now.hour >= 16:
            next_open += timedelta(days=1)
        next_cta_str = f"Market open ({next_open.strftime('%Y-%m-%d %H:%M')} ET)"
    
    # Calculate next crypto run (always 30 min from last or next 30-min mark)
    next_crypto_min = 30 if now.minute < 30 else 60
    if next_crypto_min >= 60:
        next_crypto = now.replace(minute=0, second=0) + timedelta(hours=1)
    else:
        next_crypto = now.replace(minute=next_crypto_min, second=0)
    
    return {
        "current_time_et": now.strftime("%Y-%m-%d %H:%M:%S"),
        "is_trading_day": is_trading_day(),
        "is_market_hours": is_market_hours,
        "scheduler_started": _scheduler_status.get("scheduler_started"),
        "cta_scanner": {
            **_scheduler_status["cta_scanner"],
            "current_interval": cta_interval,
            "next_run_et": next_cta_str,
            "schedule": "First/last hour: 15min, Mid-day: 30min (market hours only)"
        },
        "crypto_scanner": {
            **_scheduler_status["crypto_scanner"],
            "next_run_et": next_crypto.strftime("%H:%M ET"),
            "schedule": "Every 30 minutes, 24/7"
        },
        "bias_refresh": {
            **_scheduler_status["bias_refresh"],
            "schedule": "9:45 AM ET on trading days"
        },
        "composite_bias": {
            **_scheduler_status["composite_bias"],
            "schedule": "Every 15 minutes"
        },
        "price_collection": {
            **_scheduler_status["price_collection"],
            "schedule": "Every 5 minutes (equities intraday in market hours, crypto 24/7)"
        },
        "benchmark_tracker": {
            **_scheduler_status["benchmark_tracker"],
            "schedule": "Daily at 4:10 PM ET"
        },
        "portfolio_monitor": {
            **_scheduler_status["portfolio_monitor"],
            "schedule": "Daily at 4:15 PM ET"
        },
        "health_monitor": {
            **_scheduler_status["health_monitor"],
            "schedule": "Daily at 4:30 PM ET"
        }
    }


class BiasTimeframe(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    CYCLICAL = "CYCLICAL"


class TrendDirection(str, Enum):
    IMPROVING = "IMPROVING"      # More bullish than previous
    DECLINING = "DECLINING"      # More bearish than previous
    STABLE = "STABLE"           # Same as previous
    NEW = "NEW"                 # No previous data


# Bias level numeric values for comparison (6-level system, no neutral)
BIAS_LEVELS = {
    "MAJOR_TORO": 6,
    "MAJOR TORO": 6,
    "MINOR_TORO": 5,
    "MINOR TORO": 5,
    "LEAN_TORO": 4,
    "LEAN TORO": 4,
    "LEAN_URSA": 3,
    "LEAN URSA": 3,
    "MINOR_URSA": 2,
    "MINOR URSA": 2,
    "MAJOR_URSA": 1,
    "MAJOR URSA": 1,
    # Legacy mappings for backward compatibility
    "TORO_MAJOR": 6,
    "TORO MAJOR": 6,
    "TORO_MINOR": 5,
    "TORO MINOR": 5,
    "NEUTRAL": 4,  # Map old neutral to LEAN_TORO (bullish default)
    "URSA_MINOR": 2,
    "URSA MINOR": 2,
    "URSA_MAJOR": 1,
    "URSA MAJOR": 1,
}

# Numeric value back to bias level name
LEVEL_TO_BIAS = {
    6: "MAJOR_TORO",
    5: "MINOR_TORO",
    4: "LEAN_TORO",
    3: "LEAN_URSA",
    2: "MINOR_URSA",
    1: "MAJOR_URSA",
}


def apply_hierarchical_modifier(
    base_level: str,
    modifier_level: str,
    modifier_name: str = "higher_timeframe"
) -> tuple[str, Dict[str, Any]]:
    """
    Apply hierarchical modification from a higher timeframe bias to a lower timeframe.
    
    6-Level System Rules:
    - MAJOR_TORO modifier (6): Boosts base by +1 level (max MAJOR_TORO)
    - MINOR_TORO modifier (5): Boosts base by +0.5
    - LEAN_TORO modifier (4): No change (already bullish lean)
    - LEAN_URSA modifier (3): No change (already bearish lean)
    - MINOR_URSA modifier (2): Reduces base by -0.5
    - MAJOR_URSA modifier (1): Reduces base by -1 level (min MAJOR_URSA)
    
    Args:
        base_level: The base bias level (e.g., from Daily calculation)
        modifier_level: The higher timeframe bias level (e.g., Weekly)
        modifier_name: Name for logging (e.g., "weekly" or "cyclical")
    
    Returns:
        Tuple of (modified_level, modification_details)
    """
    base_value = BIAS_LEVELS.get(base_level.upper().replace("_", " "), 4)  # Default to LEAN_TORO
    modifier_value = BIAS_LEVELS.get(modifier_level.upper().replace("_", " "), 4)
    
    original_value = base_value
    adjustment = 0
    adjustment_reason = "no_modifier"
    
    # Strong bullish modifier boosts by 1
    if modifier_value == 6:  # MAJOR_TORO
        adjustment = 1
        adjustment_reason = "strong_bullish_boost"
    # Minor bullish modifier boosts by 0.5
    elif modifier_value == 5:  # MINOR_TORO
        adjustment = 0.5
        adjustment_reason = "minor_bullish_boost"
    # Lean levels don't modify (they're already directional but not strong)
    elif modifier_value in [4, 3]:  # LEAN_TORO or LEAN_URSA
        adjustment = 0
        adjustment_reason = "lean_no_change"
    # Strong bearish modifier reduces by 1
    elif modifier_value == 1:  # MAJOR_URSA
        adjustment = -1
        adjustment_reason = "strong_bearish_drag"
    
    # Apply adjustment and clamp to valid range [1, 6]
    modified_value = base_value + adjustment
    modified_value = max(1, min(6, round(modified_value)))
    
    # Convert back to level name
    modified_level = LEVEL_TO_BIAS.get(modified_value, "LEAN_TORO")
    
    details = {
        "original_level": base_level,
        "original_value": original_value,
        "modifier_level": modifier_level,
        "modifier_value": modifier_value,
        "modifier_name": modifier_name,
        "adjustment": adjustment,
        "adjustment_reason": adjustment_reason,
        "modified_value": modified_value,
        "modified_level": modified_level,
        "was_modified": modified_level != base_level
    }
    
    if modified_level != base_level:
        logger.info(
            f"  Hierarchical modifier ({modifier_name}): {base_level} -> {modified_level} "
            f"({adjustment_reason}, adj={adjustment:+.1f})"
        )
    
    return modified_level, details


def get_effective_bias(timeframe: BiasTimeframe) -> Dict[str, Any]:
    """
    Get the effective bias for a timeframe, including hierarchical modifiers.
    
    Returns the raw bias AND the modified bias after applying higher timeframe influence.
    
    Daily Bias: Modified by Weekly + Cyclical
    Weekly Bias: Modified by Cyclical
    Cyclical Bias: No modifier (highest level)
    """
    history = _load_bias_history()
    
    # Get raw bias levels for each timeframe
    cyclical_data = history.get("cyclical", {}).get("current", {})
    weekly_data = history.get("weekly", {}).get("current", {})
    daily_data = history.get("daily", {}).get("current", {})
    
    cyclical_level = cyclical_data.get("level", "LEAN_TORO") if cyclical_data else "LEAN_TORO"
    weekly_level = weekly_data.get("level", "LEAN_TORO") if weekly_data else "LEAN_TORO"
    daily_level = daily_data.get("level", "LEAN_TORO") if daily_data else "LEAN_TORO"
    
    result = {
        "raw": {},
        "effective": {},
        "modifiers": {}
    }
    
    if timeframe == BiasTimeframe.CYCLICAL:
        # Cyclical has no modifier - it's the highest level
        result["raw"]["cyclical"] = cyclical_level
        result["effective"]["cyclical"] = cyclical_level
        result["modifiers"]["cyclical"] = None
        
    elif timeframe == BiasTimeframe.WEEKLY:
        # Weekly is modified by Cyclical
        modified_weekly, weekly_mod_details = apply_hierarchical_modifier(
            weekly_level, cyclical_level, "cyclical"
        )
        result["raw"]["weekly"] = weekly_level
        result["effective"]["weekly"] = modified_weekly
        result["modifiers"]["weekly"] = weekly_mod_details
        
    elif timeframe == BiasTimeframe.DAILY:
        # Weekly is first modified by Cyclical
        effective_weekly, weekly_mod_details = apply_hierarchical_modifier(
            weekly_level, cyclical_level, "cyclical"
        )
        
        # Then Daily is modified by the effective Weekly
        modified_daily, daily_mod_details = apply_hierarchical_modifier(
            daily_level, effective_weekly, "weekly"
        )
        
        result["raw"]["daily"] = daily_level
        result["raw"]["weekly"] = weekly_level
        result["raw"]["cyclical"] = cyclical_level
        result["effective"]["daily"] = modified_daily
        result["effective"]["weekly"] = effective_weekly
        result["modifiers"]["daily"] = daily_mod_details
        result["modifiers"]["weekly"] = weekly_mod_details
    
    return result


def _load_bias_history() -> Dict[str, Any]:
    """Load bias history from disk"""
    try:
        if os.path.exists(BIAS_HISTORY_FILE):
            with open(BIAS_HISTORY_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading bias history: {e}")
    
    return {
        "daily": {"current": None, "previous": None, "history": []},
        "weekly": {"current": None, "previous": None, "history": []},
        "cyclical": {"current": None, "previous": None, "history": []},
        "last_updated": None
    }


def _save_bias_history(data: Dict[str, Any]):
    """Save bias history to disk"""
    try:
        os.makedirs(os.path.dirname(BIAS_HISTORY_FILE), exist_ok=True)
        with open(BIAS_HISTORY_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving bias history: {e}")


def _load_weekly_baseline() -> Dict[str, Any]:
    """Load weekly baseline from disk"""
    global _weekly_baseline
    try:
        if os.path.exists(BASELINE_FILE):
            with open(BASELINE_FILE, 'r') as f:
                baseline = json.load(f)
                # Check if baseline is from this week (Monday or later) in Eastern Time
                if baseline.get("timestamp"):
                    baseline_date = datetime.fromisoformat(baseline["timestamp"])
                    now = get_eastern_now()
                    # Make baseline_date timezone-aware if it isn't
                    if baseline_date.tzinfo is None:
                        baseline_date = ET.localize(baseline_date)
                    # If baseline is older than current Monday, reset it
                    days_since_baseline = (now - baseline_date).days
                    if days_since_baseline < 7 and baseline_date.weekday() == 0:
                        _weekly_baseline = baseline
                        return baseline
    except Exception as e:
        logger.error(f"Error loading weekly baseline: {e}")
    
    return {
        "timestamp": None,
        "total_vote": None,
        "factors": {},
        "level": None
    }


def _save_weekly_baseline():
    """Save weekly baseline to disk"""
    global _weekly_baseline
    try:
        os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
        with open(BASELINE_FILE, 'w') as f:
            json.dump(_weekly_baseline, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving weekly baseline: {e}")


def calculate_trend(current_level: str, previous_level: str) -> TrendDirection:
    """Calculate trend direction between two bias levels"""
    if not previous_level:
        return TrendDirection.NEW
    
    current_val = BIAS_LEVELS.get(current_level.upper().replace("_", " "), 3)
    previous_val = BIAS_LEVELS.get(previous_level.upper().replace("_", " "), 3)
    
    if current_val > previous_val:
        return TrendDirection.IMPROVING
    elif current_val < previous_val:
        return TrendDirection.DECLINING
    else:
        return TrendDirection.STABLE


def update_bias(
    timeframe: BiasTimeframe,
    new_level: str,
    details: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Update bias for a timeframe, storing previous value for trend tracking
    
    Args:
        timeframe: DAILY, WEEKLY, or CYCLICAL
        new_level: The new bias level (e.g., "TORO_MAJOR", "NEUTRAL", etc.)
        details: Additional details to store (data sources, components, etc.)
    
    Returns:
        Dict with current, previous, trend, and timestamp
    """
    history = _load_bias_history()
    tf_key = timeframe.value.lower()
    
    # Get current data (will become previous)
    current_data = history.get(tf_key, {}).get("current")
    
    # Create new current entry (Eastern Time)
    now = get_eastern_now()
    new_entry = {
        "level": new_level,
        "timestamp": now.isoformat(),
        "details": details or {}
    }
    
    # Calculate trend
    previous_level = current_data.get("level") if current_data else None
    trend = calculate_trend(new_level, previous_level)
    
    # Update history
    if tf_key not in history:
        history[tf_key] = {"current": None, "previous": None, "history": []}
    
    # Shift current to previous
    if current_data:
        history[tf_key]["previous"] = current_data
        # Add to history (keep last 30 entries)
        history[tf_key]["history"] = [current_data] + history[tf_key].get("history", [])[:29]
    
    # Set new current
    history[tf_key]["current"] = new_entry
    history[tf_key]["trend"] = trend.value
    history["last_updated"] = now.isoformat()
    
    _save_bias_history(history)
    
    return {
        "timeframe": timeframe.value,
        "current": new_entry,
        "previous": current_data,
        "trend": trend.value,
        "trend_description": _get_trend_description(trend, previous_level, new_level)
    }


def _get_trend_description(trend: TrendDirection, previous: str, current: str) -> str:
    """Get human-readable trend description"""
    if trend == TrendDirection.NEW:
        return "First reading"
    elif trend == TrendDirection.IMPROVING:
        return f"â†‘ More bullish (was {previous})"
    elif trend == TrendDirection.DECLINING:
        return f"â†“ More bearish (was {previous})"
    else:
        return f"â†’ Unchanged from {previous}"


def calculate_shift_status(baseline_vote: int, current_vote: int) -> Dict[str, Any]:
    """
    Calculate shift status comparing current vote to baseline vote
    
    Args:
        baseline_vote: Monday's baseline vote (-12 to +12)
        current_vote: Current day's vote (-12 to +12)
    
    Returns:
        Dict with delta, status, and description
    """
    delta = current_vote - baseline_vote
    
    if delta >= 6:
        status = "STRONGLY_IMPROVING"
        description = "Sentiment strongly improving since Monday"
    elif delta >= 3:
        status = "IMPROVING"
        description = "Sentiment improving since Monday"
    elif delta <= -6:
        status = "STRONGLY_DETERIORATING"
        description = "Sentiment strongly deteriorating since Monday"
    elif delta <= -3:
        status = "DETERIORATING"
        description = "Sentiment deteriorating since Monday"
    else:
        status = "STABLE"
        description = "Sentiment stable since Monday"
    
    return {
        "delta": delta,
        "status": status,
        "description": description
    }


def get_weekly_baseline() -> Dict[str, Any]:
    """Get the current weekly baseline (Monday's reading)"""
    return _weekly_baseline.copy()


def get_bias_status(timeframe: BiasTimeframe = None) -> Dict[str, Any]:
    """
    Get current bias status with trend information
    
    Args:
        timeframe: Specific timeframe, or None for all
    
    Returns:
        Dict with bias data including trends
    """
    history = _load_bias_history()
    
    if timeframe:
        tf_key = timeframe.value.lower()
        tf_data = history.get(tf_key, {}) or {}
        current = tf_data.get("current") or {}
        previous = tf_data.get("previous") or {}
        
        return {
            "timeframe": timeframe.value,
            "level": current.get("level", "NEUTRAL") if current else "NEUTRAL",
            "timestamp": current.get("timestamp") if current else None,
            "details": current.get("details", {}) if current else {},
            "trend": tf_data.get("trend", "NEW"),
            "previous": {
                "level": previous.get("level") if previous else None,
                "timestamp": previous.get("timestamp") if previous else None
            }
        }
    
    # Return all timeframes
    result = {}
    for tf in BiasTimeframe:
        tf_key = tf.value.lower()
        tf_data = history.get(tf_key, {}) or {}
        current = tf_data.get("current") or {}
        previous = tf_data.get("previous") or {}
        
        result[tf_key] = {
            "level": current.get("level", "NEUTRAL") if current else "NEUTRAL",
            "timestamp": current.get("timestamp") if current else None,
            "trend": tf_data.get("trend", "NEW"),
            "previous_level": previous.get("level") if previous else None,
            "details": current.get("details", {}) if current else {}  # Include factor details
        }
    
    result["last_updated"] = history.get("last_updated")
    return result


def get_bias_history(timeframe: BiasTimeframe, limit: int = 10) -> List[Dict[str, Any]]:
    """Get historical bias values for a timeframe"""
    history = _load_bias_history()
    tf_key = timeframe.value.lower()
    
    tf_data = history.get(tf_key, {}) or {}
    entries = []
    
    # Add current
    current = tf_data.get("current")
    if current:
        entries.append(current)
    
    # Add history
    hist_list = tf_data.get("history") or []
    entries.extend(hist_list)
    
    return entries[:limit]


# =========================================================================
# REFRESH FUNCTIONS - Called by scheduler
# =========================================================================

async def refresh_daily_bias() -> Dict[str, Any]:
    """
    Refresh daily bias based on 7-FACTOR calculable analysis:
    1. SPY RSI - Momentum oscillator (overbought/oversold)
    2. VIX Level - Fear gauge
    3. Tech Leadership - QQQ vs SPY relative strength
    4. Small Cap Risk - IWM vs SPY (risk-on/off)
    5. SPY Trend - Price vs 9 EMA
    6. Breadth - RSP vs SPY (equal weight vs cap weight)
    7. TICK Range Breadth - Linda Raschke method (wide/narrow participation)
    
    All factors calculated from price data - no external feeds needed.
    """
    logger.info("ðŸ“Š Refreshing Daily Bias (6-Factor Calculable Model)...")
    
    factor_votes = []  # List of (name, vote, details)
    
    try:
        from scanners.hybrid_scanner import get_scanner
        scanner = get_scanner()
        
        # =====================================================================
        # FACTOR 1: SPY RSI (Momentum)
        # =====================================================================
        try:
            spy_data = scanner.get_technical_analysis("SPY", interval="1d")
            # Note: oscillators.rsi is lowercase in the scanner response
            rsi = spy_data.get("oscillators", {}).get("rsi", 50) or 50
            
            # RSI scoring: <30 = oversold (bullish), >70 = overbought (bearish)
            if rsi <= 30:
                rsi_vote = 2
                rsi_signal = "OVERSOLD"
            elif rsi <= 40:
                rsi_vote = 1
                rsi_signal = "LEAN_OVERSOLD"
            elif rsi >= 70:
                rsi_vote = -2
                rsi_signal = "OVERBOUGHT"
            elif rsi >= 60:
                rsi_vote = -1
                rsi_signal = "LEAN_OVERBOUGHT"
            else:
                rsi_vote = 0
                rsi_signal = "NEUTRAL"
            
            factor_votes.append(("spy_rsi", rsi_vote, {
                "rsi": round(rsi, 1) if rsi else 50,
                "signal": rsi_signal
            }))
            logger.info(f"  ðŸ“Š SPY RSI: {rsi:.1f} - {rsi_signal} (vote: {rsi_vote:+d})")
            
        except Exception as e:
            logger.warning(f"Error in SPY RSI factor: {e}")
            factor_votes.append(("spy_rsi", 0, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 2: VIX Level (Fear Gauge)
        # =====================================================================
        try:
            # Try multiple VIX proxies in order of preference
            # VIXY (1x VIX ETF) works on CBOE exchange
            vix_proxies = ["VIXY", "UVXY", "VXX"]
            vix_data = None
            vix_ticker_used = None
            
            for vix_proxy in vix_proxies:
                try:
                    vix_data = scanner.get_technical_analysis(vix_proxy, interval="1d")
                    if vix_data.get("signal") != "ERROR":
                        vix_ticker_used = vix_proxy
                        break
                except Exception:
                    continue
            
            if vix_data and vix_data.get("signal") != "ERROR":
                # Get the price from the nested structure
                vix_close = vix_data.get("price", {}).get("close", 0) or 0
                vix_signal_raw = vix_data.get("signal", "NEUTRAL")
                
                # Use VIX proxy signal: falling VIX = bullish, rising VIX = bearish
                if vix_signal_raw in ["SELL", "STRONG_SELL"]:
                    # VIX proxy falling = VIX falling = bullish
                    vix_vote = 2 if vix_signal_raw == "STRONG_SELL" else 1
                    vix_signal = "LOW_FEAR"
                elif vix_signal_raw in ["BUY", "STRONG_BUY"]:
                    # VIX proxy rising = VIX rising = bearish
                    vix_vote = -2 if vix_signal_raw == "STRONG_BUY" else -1
                    vix_signal = "HIGH_FEAR"
                else:
                    vix_vote = 0
                    vix_signal = "NEUTRAL"
                
                factor_votes.append(("vix_level", vix_vote, {
                    "vix_proxy": vix_ticker_used,
                    "price": round(vix_close, 2) if vix_close else 0,
                    "proxy_signal": vix_signal_raw,
                    "signal": vix_signal
                }))
                logger.info(f"  VIX Level: {vix_ticker_used} {vix_signal_raw} - {vix_signal} (vote: {vix_vote:+d})")
            else:
                # All VIX proxies failed - use neutral vote
                logger.warning("All VIX proxies failed, using neutral vote")
                factor_votes.append(("vix_level", 0, {"error": "No VIX proxy available"}))
            
        except Exception as e:
            logger.warning(f"Error in VIX factor: {e}")
            factor_votes.append(("vix_level", 0, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 3: Tech Leadership (QQQ vs SPY)
        # =====================================================================
        try:
            spy_data = scanner.get_technical_analysis("SPY", interval="1d")
            qqq_data = scanner.get_technical_analysis("QQQ", interval="1d")
            
            # Get change_pct from nested price structure
            spy_change = spy_data.get("price", {}).get("change_pct", 0) or 0
            qqq_change = qqq_data.get("price", {}).get("change_pct", 0) or 0
            diff = qqq_change - spy_change
            
            # QQQ outperforming = tech leading = bullish for growth
            if diff > 0.5:
                tech_vote = 2
                tech_signal = "TECH_LEADING"
            elif diff > 0.1:
                tech_vote = 1
                tech_signal = "TECH_SLIGHT_LEAD"
            elif diff < -0.5:
                tech_vote = -2
                tech_signal = "TECH_LAGGING"
            elif diff < -0.1:
                tech_vote = -1
                tech_signal = "TECH_SLIGHT_LAG"
            else:
                tech_vote = 0
                tech_signal = "BALANCED"
            
            factor_votes.append(("tech_leadership", tech_vote, {
                "qqq_change": round(qqq_change, 2),
                "spy_change": round(spy_change, 2),
                "diff": round(diff, 2),
                "signal": tech_signal
            }))
            logger.info(f"  ðŸ’» Tech Leadership: QQQ {qqq_change:+.2f}% vs SPY {spy_change:+.2f}% - {tech_signal} (vote: {tech_vote:+d})")
            
        except Exception as e:
            logger.warning(f"Error in Tech Leadership factor: {e}")
            factor_votes.append(("tech_leadership", 0, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 4: Small Cap Risk (IWM vs SPY)
        # =====================================================================
        try:
            spy_data = scanner.get_technical_analysis("SPY", interval="1d")
            iwm_data = scanner.get_technical_analysis("IWM", interval="1d")
            
            spy_change = spy_data.get("price", {}).get("change_pct", 0) or 0
            iwm_change = iwm_data.get("price", {}).get("change_pct", 0) or 0
            diff = iwm_change - spy_change
            
            # IWM outperforming = risk-on = bullish
            if diff > 0.5:
                risk_vote = 2
                risk_signal = "RISK_ON"
            elif diff > 0.1:
                risk_vote = 1
                risk_signal = "SLIGHT_RISK_ON"
            elif diff < -0.5:
                risk_vote = -2
                risk_signal = "RISK_OFF"
            elif diff < -0.1:
                risk_vote = -1
                risk_signal = "SLIGHT_RISK_OFF"
            else:
                risk_vote = 0
                risk_signal = "NEUTRAL"
            
            factor_votes.append(("small_cap_risk", risk_vote, {
                "iwm_change": round(iwm_change, 2),
                "spy_change": round(spy_change, 2),
                "diff": round(diff, 2),
                "signal": risk_signal
            }))
            logger.info(f"  ðŸƒ Small Cap Risk: IWM {iwm_change:+.2f}% vs SPY {spy_change:+.2f}% - {risk_signal} (vote: {risk_vote:+d})")
            
        except Exception as e:
            logger.warning(f"Error in Small Cap Risk factor: {e}")
            factor_votes.append(("small_cap_risk", 0, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 5: SPY Trend (Price vs 9 EMA)
        # =====================================================================
        try:
            spy_data = scanner.get_technical_analysis("SPY", interval="1d")
            price = spy_data.get("price", {}).get("close", 0) or 0
            ma_data = spy_data.get("moving_averages", {})
            
            # Get EMA20 value and compare to price
            ema20 = ma_data.get("ema20", 0) or 0
            spy_signal = spy_data.get("signal", "NEUTRAL")
            
            # Use the overall signal as trend indicator
            signal_to_vote = {"STRONG_BUY": 2, "BUY": 1, "NEUTRAL": 0, "SELL": -1, "STRONG_SELL": -2}
            trend_vote = signal_to_vote.get(spy_signal, 0)
            
            factor_votes.append(("spy_trend", trend_vote, {
                "price": round(price, 2) if price else 0,
                "signal": spy_signal,
                "ema20": round(ema20, 2) if ema20 else 0
            }))
            logger.info(f"  ðŸ“ˆ SPY Trend: {spy_signal} (vote: {trend_vote:+d})")
            
        except Exception as e:
            logger.warning(f"Error in SPY Trend factor: {e}")
            factor_votes.append(("spy_trend", 0, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 6: Market Breadth (RSP vs SPY)
        # =====================================================================
        try:
            spy_data = scanner.get_technical_analysis("SPY", interval="1d")
            rsp_data = scanner.get_technical_analysis("RSP", interval="1d")
            
            spy_change = spy_data.get("price", {}).get("change_pct", 0) or 0
            rsp_change = rsp_data.get("price", {}).get("change_pct", 0) or 0
            diff = rsp_change - spy_change
            
            # RSP outperforming = broad participation = bullish breadth
            if diff > 0.3:
                breadth_vote = 2
                breadth_signal = "BROAD_STRENGTH"
            elif diff > 0.1:
                breadth_vote = 1
                breadth_signal = "HEALTHY_BREADTH"
            elif diff < -0.3:
                breadth_vote = -2
                breadth_signal = "NARROW_RALLY"
            elif diff < -0.1:
                breadth_vote = -1
                breadth_signal = "WEAK_BREADTH"
            else:
                breadth_vote = 0
                breadth_signal = "NEUTRAL"
            
            factor_votes.append(("market_breadth", breadth_vote, {
                "rsp_change": round(rsp_change, 2),
                "spy_change": round(spy_change, 2),
                "diff": round(diff, 2),
                "signal": breadth_signal
            }))
            logger.info(f"  ðŸ“Š Breadth: RSP {rsp_change:+.2f}% vs SPY {spy_change:+.2f}% - {breadth_signal} (vote: {breadth_vote:+d})")
            
        except Exception as e:
            logger.warning(f"Error in SPY vs RSP factor: {e}")
            factor_votes.append(("spy_vs_rsp", 0, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 7: TICK Range Breadth (Linda Raschke method)
        # =====================================================================
        try:
            from bias_filters.tick_breadth import get_tick_status
            tick_status = await get_tick_status()
            
            tick_bias = tick_status.get("daily_bias", "NEUTRAL")
            tick_high = tick_status.get("tick_high", 0)
            tick_low = tick_status.get("tick_low", 0)
            
            # TICK logic:
            # Wide range (high > +1000 OR low < -1000) = TORO (bullish participation)
            # Narrow range (high < +500 AND low > -500) = URSA (weak participation)
            if tick_bias == "TORO_MINOR":
                tick_vote = 2
                tick_signal = "WIDE_RANGE"
            elif tick_bias == "URSA_MINOR":
                tick_vote = -2
                tick_signal = "NARROW_RANGE"
            else:
                tick_vote = 0
                tick_signal = "NEUTRAL"
            
            factor_votes.append(("tick_breadth", tick_vote, {
                "tick_high": tick_high,
                "tick_low": tick_low,
                "bias": tick_bias,
                "signal": tick_signal
            }))
            tick_high_disp = int(round(float(tick_high or 0)))
            tick_low_disp = int(round(float(tick_low or 0)))
            logger.info(
                f"  TICK Breadth: High {tick_high_disp:+d} / Low {tick_low_disp:+d} - {tick_signal} (vote: {tick_vote:+d})"
            )
            
        except Exception as e:
            logger.warning(f"Error in TICK Breadth factor: {e}")
            factor_votes.append(("tick_breadth", 0, {"error": str(e)}))
        
        # =====================================================================
        # CALCULATE TOTAL VOTE AND DETERMINE BIAS
        # =====================================================================
        total_vote = sum(vote for _, vote, _ in factor_votes)
        max_possible = 14  # 7 factors Ã— 2 max each
        
        # Thresholds for 7 factors (6-level system, no neutral)
        # Adjusted for 14 max possible (was 12)
        # Use weekly bias as tiebreaker when vote = 0
        if total_vote >= 8:  # Was 7
            new_level = "MAJOR_TORO"
        elif total_vote >= 4:  # Was 3
            new_level = "MINOR_TORO"
        elif total_vote > 0:
            new_level = "LEAN_TORO"
        elif total_vote == 0:
            # Tiebreaker: use weekly bias direction
            weekly_data = get_bias_status(BiasTimeframe.WEEKLY)
            weekly_level = weekly_data.get("level", "LEAN_TORO") if weekly_data else "LEAN_TORO"
            if "URSA" in weekly_level.upper():
                new_level = "LEAN_URSA"
            else:
                new_level = "LEAN_TORO"  # Default bullish
        elif total_vote > -4:  # Was -3
            new_level = "LEAN_URSA"
        elif total_vote > -8:  # Was -7
            new_level = "MINOR_URSA"
        else:
            new_level = "MAJOR_URSA"

        # =====================================================================
        # CIRCUIT BREAKER OVERRIDE
        # =====================================================================
        original_level = new_level
        circuit_breaker_applied = False

        try:
            from webhooks.circuit_breaker import get_circuit_breaker_state
            cb_state = get_circuit_breaker_state()

            if cb_state.get("active"):
                bias_cap = cb_state.get("bias_cap")
                bias_floor = cb_state.get("bias_floor")

                # Apply bias cap (maximum bullish level)
                if bias_cap:
                    cap_value = BIAS_LEVELS.get(bias_cap, 6)
                    current_value = BIAS_LEVELS.get(new_level, 4)

                    if current_value > cap_value:
                        new_level = bias_cap
                        circuit_breaker_applied = True
                        logger.warning(f"âš ï¸ Circuit breaker CAP applied: {original_level} -> {new_level}")

                # Apply bias floor (minimum bearish level)
                if bias_floor:
                    floor_value = BIAS_LEVELS.get(bias_floor, 1)
                    current_value = BIAS_LEVELS.get(new_level, 4)

                    if current_value > floor_value:
                        new_level = bias_floor
                        circuit_breaker_applied = True
                        logger.warning(f"âš ï¸ Circuit breaker FLOOR applied: {original_level} -> {new_level}")

        except Exception as e:
            logger.warning(f"Error applying circuit breaker: {e}")

        # Build details
        details = {
            "source": "7_factor_daily",
            "total_vote": total_vote,
            "max_possible": max_possible,
            "factors": {name: {"vote": vote, "details": det} for name, vote, det in factor_votes},
            "circuit_breaker": {
                "applied": circuit_breaker_applied,
                "original_level": original_level if circuit_breaker_applied else None,
                "trigger": cb_state.get("trigger") if circuit_breaker_applied else None
            } if circuit_breaker_applied else None
        }
        
        # Update bias with trend tracking
        result = update_bias(BiasTimeframe.DAILY, new_level, details=details)
        
        logger.info(f"âœ… Daily Bias updated: {new_level} (total vote: {total_vote}/{max_possible})")
        return result
        
    except Exception as e:
        logger.error(f"Error refreshing daily bias: {e}")
        return {"error": str(e)}


async def refresh_weekly_bias() -> Dict[str, Any]:
    """
    Refresh weekly bias based on 6-FACTOR calculable analysis:
    1. Index Trends (SPY, QQQ, IWM, SMH weekly signals) - includes semiconductors
    2. Dollar Trend (DXY direction - weak dollar = bullish for stocks)
    3. Sector Rotation (XLK vs XLU - offensive vs defensive)
    4. Credit Spreads (HYG vs TLT - risk appetite)
    5. Market Breadth (RSP vs SPY weekly - participation)
    6. VIX Term Structure (VIX vs VIX3M - sentiment)
    
    All factors calculated from ETF prices - no external feeds needed.
    
    Runs daily at 9:45 AM ET. Monday's reading becomes the weekly baseline.
    Subsequent days are compared to Monday's baseline to detect shifts.
    """
    global _weekly_baseline
    
    logger.info("ðŸ“Š Refreshing Weekly Bias (6-Factor Calculable Model)...")
    
    # Check if it's Monday or if no baseline exists (Eastern Time)
    now = get_eastern_now()
    is_monday = now.weekday() == 0
    baseline_exists = _weekly_baseline.get("timestamp") is not None
    
    # Load baseline if not already loaded (in case of restart)
    if not baseline_exists:
        _weekly_baseline = _load_weekly_baseline()
        baseline_exists = _weekly_baseline.get("timestamp") is not None
    
    # Update baseline if it's Monday or no baseline exists
    if is_monday or not baseline_exists:
        logger.info("  ðŸ“Œ Setting new weekly baseline (Monday or first run)")
    
    factor_votes = []  # List of (factor_name, vote, details)
    
    try:
        from scanners.hybrid_scanner import get_scanner
        scanner = get_scanner()
    except Exception as e:
        logger.error(f"Failed to get scanner: {e}")
        return {"error": str(e)}
    
    # ========== FACTOR 1: Index Trends (SPY/QQQ/IWM/SMH) ==========
    try:
        indices = ["SPY", "QQQ", "IWM", "SMH"]
        index_signals = {}
        bullish_count = 0
        bearish_count = 0
        
        for ticker in indices:
            try:
                tech = scanner.get_technical_analysis(ticker, interval="1W")
                logger.debug(f"    {ticker} data: signal={tech.get('signal')}, error={tech.get('error')}")
                signal = tech.get("signal", "NEUTRAL")
                index_signals[ticker] = signal
                
                if signal in ["BUY", "STRONG_BUY"]:
                    bullish_count += 1
                elif signal in ["SELL", "STRONG_SELL"]:
                    bearish_count += 1
            except Exception as e:
                index_signals[ticker] = "ERROR"
                logger.warning(f"Error getting {ticker} signal: {e}")
        
        # Vote: 4/4 bullish = +2, 3/4 = +1, 3/4 bearish = -1, 4/4 bearish = -2
        if bullish_count >= 4:
            idx_vote = 2
            idx_signal = "ALL_BULLISH"
        elif bullish_count >= 3:
            idx_vote = 1
            idx_signal = "MOSTLY_BULLISH"
        elif bearish_count >= 4:
            idx_vote = -2
            idx_signal = "ALL_BEARISH"
        elif bearish_count >= 3:
            idx_vote = -1
            idx_signal = "MOSTLY_BEARISH"
        else:
            idx_vote = 0
            idx_signal = "MIXED"
        
        factor_votes.append(("index_trends", idx_vote, {
            "signals": index_signals,
            "bullish": bullish_count,
            "bearish": bearish_count,
            "signal": idx_signal
        }))
        logger.info(f"  ðŸ“ˆ Index Trends (SPY/QQQ/IWM/SMH): {bullish_count} bullish, {bearish_count} bearish - {idx_signal} (vote: {idx_vote:+d})")
        
    except Exception as e:
        logger.warning(f"Error in index trends factor: {e}")
        factor_votes.append(("index_trends", 0, {"error": str(e)}))
    
    # ========== FACTOR 2: Dollar Trend (using UUP - Dollar Bullish ETF) ==========
    try:
        # Use UUP (Invesco DB US Dollar Index Bullish Fund) instead of DXY
        uup_data = scanner.get_technical_analysis("UUP", interval="1W")
        uup_signal = uup_data.get("signal", "NEUTRAL")
        uup_change = uup_data.get("price", {}).get("change_pct", 0) or 0
        
        # Weak dollar = bullish for stocks (inverse relationship)
        # UUP rising = dollar strengthening = bearish for stocks
        if uup_signal in ["SELL", "STRONG_SELL"]:
            dollar_vote = 2 if uup_signal == "STRONG_SELL" else 1
            dollar_status = "WEAK_DOLLAR"
        elif uup_signal in ["BUY", "STRONG_BUY"]:
            dollar_vote = -2 if uup_signal == "STRONG_BUY" else -1
            dollar_status = "STRONG_DOLLAR"
        else:
            dollar_vote = 0
            dollar_status = "NEUTRAL"
        
        factor_votes.append(("dollar_trend", dollar_vote, {
            "uup_signal": uup_signal,
            "uup_change": round(uup_change, 2) if uup_change else 0,
            "status": dollar_status
        }))
        logger.info(f"  ðŸ’µ Dollar Trend: UUP {uup_signal} ({uup_change:+.2f}%) - {dollar_status} (vote: {dollar_vote:+d})")
        
    except Exception as e:
        logger.warning(f"Error in dollar trend factor: {e}")
        factor_votes.append(("dollar_trend", 0, {"error": str(e)}))
    
    # ========== FACTOR 3: Sector Rotation (XLK vs XLU) ==========
    try:
        xlk_data = scanner.get_technical_analysis("XLK", interval="1W")
        xlu_data = scanner.get_technical_analysis("XLU", interval="1W")
        
        xlk_change = xlk_data.get("price", {}).get("change_pct", 0) or 0
        xlu_change = xlu_data.get("price", {}).get("change_pct", 0) or 0
        diff = xlk_change - xlu_change
        
        # Tech outperforming utilities = risk-on = bullish
        if diff > 1.5:
            sector_vote = 2
            sector_signal = "STRONG_RISK_ON"
        elif diff > 0.5:
            sector_vote = 1
            sector_signal = "RISK_ON"
        elif diff < -1.5:
            sector_vote = -2
            sector_signal = "STRONG_RISK_OFF"
        elif diff < -0.5:
            sector_vote = -1
            sector_signal = "RISK_OFF"
        else:
            sector_vote = 0
            sector_signal = "NEUTRAL"
        
        factor_votes.append(("sector_rotation", sector_vote, {
            "xlk_change": round(xlk_change, 2),
            "xlu_change": round(xlu_change, 2),
            "diff": round(diff, 2),
            "signal": sector_signal
        }))
        logger.info(f"  ðŸ“Š Sector Rotation: XLK {xlk_change:+.2f}% vs XLU {xlu_change:+.2f}% - {sector_signal} (vote: {sector_vote:+d})")
        
    except Exception as e:
        logger.warning(f"Error in sector rotation factor: {e}")
        factor_votes.append(("sector_rotation", 0, {"error": str(e)}))
    
    # ========== FACTOR 4: Credit Spreads (HYG vs TLT) ==========
    try:
        hyg_data = scanner.get_technical_analysis("HYG", interval="1W")
        tlt_data = scanner.get_technical_analysis("TLT", interval="1W")
        
        hyg_change = hyg_data.get("price", {}).get("change_pct", 0) or 0
        tlt_change = tlt_data.get("price", {}).get("change_pct", 0) or 0
        diff = hyg_change - tlt_change
        
        # HYG outperforming TLT = risk appetite = bullish
        if diff > 1.0:
            credit_vote = 2
            credit_signal = "STRONG_RISK_APPETITE"
        elif diff > 0.3:
            credit_vote = 1
            credit_signal = "RISK_APPETITE"
        elif diff < -1.0:
            credit_vote = -2
            credit_signal = "FLIGHT_TO_SAFETY"
        elif diff < -0.3:
            credit_vote = -1
            credit_signal = "CAUTION"
        else:
            credit_vote = 0
            credit_signal = "NEUTRAL"
        
        factor_votes.append(("credit_spreads", credit_vote, {
            "hyg_change": round(hyg_change, 2),
            "tlt_change": round(tlt_change, 2),
            "diff": round(diff, 2),
            "signal": credit_signal
        }))
        logger.info(f"  ðŸ’³ Credit Spreads: HYG {hyg_change:+.2f}% vs TLT {tlt_change:+.2f}% - {credit_signal} (vote: {credit_vote:+d})")
        
    except Exception as e:
        logger.warning(f"Error in credit spreads factor: {e}")
        factor_votes.append(("credit_spreads", 0, {"error": str(e)}))
    
    # ========== FACTOR 5: Market Breadth (RSP vs SPY weekly) ==========
    try:
        spy_data = scanner.get_technical_analysis("SPY", interval="1W")
        rsp_data = scanner.get_technical_analysis("RSP", interval="1W")
        
        spy_change = spy_data.get("price", {}).get("change_pct", 0) or 0
        rsp_change = rsp_data.get("price", {}).get("change_pct", 0) or 0
        diff = rsp_change - spy_change
        
        # RSP outperforming = broad participation = bullish breadth
        if diff > 0.5:
            breadth_vote = 2
            breadth_signal = "BROAD_STRENGTH"
        elif diff > 0.15:
            breadth_vote = 1
            breadth_signal = "HEALTHY_BREADTH"
        elif diff < -0.5:
            breadth_vote = -2
            breadth_signal = "NARROW_LEADERSHIP"
        elif diff < -0.15:
            breadth_vote = -1
            breadth_signal = "WEAK_BREADTH"
        else:
            breadth_vote = 0
            breadth_signal = "NEUTRAL"
        
        factor_votes.append(("market_breadth", breadth_vote, {
            "rsp_change": round(rsp_change, 2),
            "spy_change": round(spy_change, 2),
            "diff": round(diff, 2),
            "signal": breadth_signal
        }))
        logger.info(f"  ðŸ“Š Market Breadth: RSP {rsp_change:+.2f}% vs SPY {spy_change:+.2f}% - {breadth_signal} (vote: {breadth_vote:+d})")
        
    except Exception as e:
        logger.warning(f"Error in market breadth factor: {e}")
        factor_votes.append(("market_breadth", 0, {"error": str(e)}))
    
    # ========== FACTOR 6: VIX Term Structure ==========
    try:
        from bias_filters.vix_term_structure import auto_fetch_and_update as fetch_vix_term, get_bias_for_scoring as get_vix_term_bias
        
        await fetch_vix_term()
        vix_term = get_vix_term_bias()
        vt_level = vix_term.get("bias_level", 3)
        
        vt_vote = vt_level - 3
        factor_votes.append(("vix_term_structure", vt_vote, {"bias_level": vt_level, "bias": vix_term.get("bias")}))
        
        logger.info(f"  ðŸ“‰ VIX Term Structure: {vix_term.get('bias')} (level {vt_level})")
        
    except Exception as e:
        logger.warning(f"Error in VIX term structure factor: {e}")
        factor_votes.append(("vix_term_structure", 0, {"error": str(e)}))
    
    # ========== AGGREGATE VOTES ==========
    total_vote = sum(v[1] for v in factor_votes)
    max_possible = len(factor_votes) * 2  # Each factor can vote -2 to +2
    
    # Map total vote to bias level
    # Range: -12 to +12 for 6 factors
    # Thresholds for 6 factors (6-level system, no neutral)
    # Use cyclical bias as tiebreaker when vote = 0
    if total_vote >= 7:
        new_level = "MAJOR_TORO"
    elif total_vote >= 3:
        new_level = "MINOR_TORO"
    elif total_vote > 0:
        new_level = "LEAN_TORO"
    elif total_vote == 0:
        # Tiebreaker: use cyclical bias direction
        cyclical_data = get_bias_status(BiasTimeframe.CYCLICAL)
        cyclical_level = cyclical_data.get("level", "LEAN_TORO") if cyclical_data else "LEAN_TORO"
        if "URSA" in cyclical_level.upper():
            new_level = "LEAN_URSA"
        else:
            new_level = "LEAN_TORO"  # Default bullish
    elif total_vote > -3:
        new_level = "LEAN_URSA"
    elif total_vote > -7:
        new_level = "MINOR_URSA"
    else:
        new_level = "MAJOR_URSA"
    
    # Build details
    details = {
        "source": "6_factor_weekly",
        "total_vote": total_vote,
        "max_possible": max_possible,
        "factors": {name: {"vote": vote, "details": det} for name, vote, det in factor_votes}
    }
    
    # Update baseline if it's Monday or no baseline exists
    if is_monday or not baseline_exists:
        _weekly_baseline = {
            "timestamp": now.isoformat(),
            "total_vote": total_vote,
            "factors": {name: {"vote": vote, "details": det} for name, vote, det in factor_votes},
            "level": new_level
        }
        _save_weekly_baseline()
        baseline_exists = True  # Update flag after setting baseline
        logger.info(f"  âœ… Weekly baseline set: {new_level} (vote: {total_vote})")
    
    # Calculate shift status compared to baseline (only on non-Monday days with existing baseline)
    shift_info = None
    if baseline_exists and not is_monday:
        baseline_vote = _weekly_baseline.get("total_vote", 0)
        shift_info = calculate_shift_status(baseline_vote, total_vote)
        logger.info(f"  ðŸ“Š Shift vs baseline: {shift_info['status']} (delta: {shift_info['delta']})")
    
    # Update bias with trend tracking
    result = update_bias(BiasTimeframe.WEEKLY, new_level, details=details)
    
    # Add baseline and shift info to result
    result["baseline"] = {
        "timestamp": _weekly_baseline.get("timestamp"),
        "total_vote": _weekly_baseline.get("total_vote"),
        "level": _weekly_baseline.get("level")
    } if _weekly_baseline.get("timestamp") else None
    
    if shift_info:
        result["shift"] = shift_info
        
        # Broadcast WebSocket alert for significant shifts
        if shift_info["status"] in ["STRONGLY_IMPROVING", "STRONGLY_DETERIORATING"]:
            try:
                from websocket.broadcaster import manager
                
                baseline_level = _weekly_baseline.get("level", "UNKNOWN")
                alert = {
                    "type": "BIAS_SHIFT_ALERT",
                    "timestamp": now.isoformat(),
                    "message": f"Weekly bias shift detected: {baseline_level} â†’ {new_level}",
                    "baseline_vote": _weekly_baseline.get("total_vote"),
                    "current_vote": total_vote,
                    "delta": shift_info["delta"],
                    "shift_status": shift_info["status"],
                    "baseline_level": baseline_level,
                    "current_level": new_level
                }
                await manager.broadcast({"type": "bias_alert", "data": alert})
                logger.info(f"  ðŸš¨ Alert broadcast: {shift_info['status']}")
            except Exception as e:
                logger.warning(f"Error broadcasting shift alert: {e}")
    
    logger.info(f"âœ… Weekly Bias updated: {new_level} (total vote: {total_vote}/{max_possible})")
    return result


async def refresh_cyclical_bias() -> Dict[str, Any]:
    """
    Refresh cyclical bias based on 9-FACTOR long-term macro analysis with TIERED VOTING:
    
    Standard Factors (Â±2 max):
    1. 200 SMA Positions (SPY, QQQ, IWM above/below 200-day SMA)
    2. Savita Indicator (BofA sentiment)
    3. Long-term Breadth (RSP vs SPY equal-weight performance)
    4. VIX Regime (fear/complacency gauge)
    5. Cyclical vs Defensive (XLY vs XLP sector rotation)
    6. Copper/Gold Ratio (economic activity vs safety)
    
    Crisis-Tiered Factors (can exceed Â±2 in extreme conditions):
    7. Yield Curve: Â±2 normal, Â±3 if deeply inverted (< -0.5%)
    8. Credit Spreads: Â±2 normal, Â±3 if extreme stress
    9. Sahm Rule (FRED): Â±2 normal, Â±4 if recession triggered (real unemployment data)
    
    Max possible: Â±18 normal, Â±22 crisis conditions
    Updates: Weekly or on significant macro changes
    """
    logger.info("ðŸ“Š Refreshing Cyclical Bias (9-Factor Tiered Macro Model)...")
    
    factor_votes = []  # List of (name, vote, max_vote, details)
    import yfinance as yf
    
    try:
        # =====================================================================
        # FACTOR 1: 200 SMA Positions (SPY, QQQ, IWM) - Standard Â±2
        # =====================================================================
        try:
            indices = ["SPY", "QQQ", "IWM"]
            above_200sma = 0
            below_200sma = 0
            sma_details = {}
            
            for ticker in indices:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1y")
                    
                    if len(hist) >= 200:
                        close_price = float(hist['Close'].iloc[-1])
                        sma200_value = float(hist['Close'].tail(200).mean())
                        
                        if close_price > sma200_value:
                            above_200sma += 1
                            sma_details[ticker] = f"above (${close_price:.2f} > ${sma200_value:.2f})"
                        else:
                            below_200sma += 1
                            sma_details[ticker] = f"below (${close_price:.2f} < ${sma200_value:.2f})"
                    else:
                        sma_details[ticker] = f"insufficient data ({len(hist)} days)"
                except Exception as e:
                    logger.warning(f"Error getting 200 SMA for {ticker}: {e}")
                    sma_details[ticker] = f"error: {str(e)}"
            
            # Standard voting: Â±2 max
            if above_200sma == 3:
                sma_vote = 2
            elif above_200sma >= 2:
                sma_vote = 1
            elif below_200sma == 3:
                sma_vote = -2
            elif below_200sma >= 2:
                sma_vote = -1
            else:
                sma_vote = 0
                
            factor_votes.append(("sma_200_positions", sma_vote, 2, {
                "above_count": above_200sma,
                "below_count": below_200sma,
                "details": sma_details,
                "tier": "standard"
            }))
            logger.info(f"  ðŸ“ˆ 200 SMA Positions: {above_200sma}/3 above (vote: {sma_vote:+d}/Â±2)")
            
        except Exception as e:
            logger.warning(f"Error in 200 SMA factor: {e}")
            factor_votes.append(("sma_200_positions", 0, 2, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 2: Yield Curve - TIERED: Â±2 normal, Â±3 if deeply inverted
        # =====================================================================
        try:
            tnx = yf.Ticker("^TNX")
            tnx_hist = tnx.history(period="5d")
            
            if len(tnx_hist) > 0:
                yield_10y = float(tnx_hist['Close'].iloc[-1])
                
                try:
                    two_year = yf.Ticker("^IRX")
                    two_hist = two_year.history(period="5d")
                    if len(two_hist) > 0:
                        yield_short = float(two_hist['Close'].iloc[-1])
                        yield_2y = yield_short + 0.5
                    else:
                        yield_2y = yield_10y - 0.3
                except:
                    yield_2y = yield_10y - 0.3
                
                spread = yield_10y - yield_2y
                
                # TIERED VOTING: Deeply inverted gets extra weight
                if spread > 0.5:
                    yc_vote = 2
                    max_vote = 2
                    tier = "standard"
                elif spread > 0:
                    yc_vote = 1
                    max_vote = 2
                    tier = "standard"
                elif spread > -0.5:
                    yc_vote = -1
                    max_vote = 2
                    tier = "standard"
                elif spread > -1.0:
                    yc_vote = -2
                    max_vote = 2
                    tier = "standard"
                else:
                    # DEEPLY INVERTED: Tiered up to Â±3
                    yc_vote = -3
                    max_vote = 3
                    tier = "crisis"
                    
                factor_votes.append(("yield_curve", yc_vote, max_vote, {
                    "spread": round(spread, 3),
                    "us10y": round(yield_10y, 2),
                    "us02y": round(yield_2y, 2),
                    "status": "normal" if spread > 0 else ("inverted" if spread > -0.5 else "deeply_inverted"),
                    "tier": tier,
                    "data_source": "yfinance"
                }))
                logger.info(f"  ðŸ“‰ Yield Curve: {spread:.2f}% spread (vote: {yc_vote:+d}/Â±{max_vote}, {tier})")
            else:
                raise Exception("No treasury yield data available")
            
        except Exception as e:
            logger.warning(f"Error in yield curve factor: {e}")
            factor_votes.append(("yield_curve", -1, 2, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 3: Credit Spreads - TIERED: Â±2 normal, Â±3 if extreme
        # =====================================================================
        try:
            from bias_filters.credit_spreads import auto_fetch_and_update as fetch_credit_spreads
            from bias_filters.credit_spreads import get_bias_for_scoring as get_credit_bias
            
            await fetch_credit_spreads()
            credit_result = get_credit_bias()
            
            credit_level = credit_result.get("bias_level", 3)
            credit_bias = credit_result.get("bias", "NEUTRAL")
            
            # TIERED VOTING: Extreme credit stress gets extra weight
            if credit_level == 5:  # TORO_MAJOR
                credit_vote = 2
                max_vote = 2
                tier = "standard"
            elif credit_level == 4:  # TORO_MINOR
                credit_vote = 1
                max_vote = 2
                tier = "standard"
            elif credit_level == 3:  # NEUTRAL
                credit_vote = 0
                max_vote = 2
                tier = "standard"
            elif credit_level == 2:  # URSA_MINOR
                credit_vote = -1
                max_vote = 2
                tier = "standard"
            else:  # credit_level == 1, URSA_MAJOR (extreme credit stress)
                credit_vote = -3
                max_vote = 3
                tier = "crisis"
            
            factor_votes.append(("credit_spreads", credit_vote, max_vote, {
                "bias": credit_bias,
                "bias_level": credit_level,
                "tier": tier,
                "last_updated": credit_result.get("last_updated"),
                "data_source": "yfinance"
            }))
            logger.info(f"  ðŸ’³ Credit Spreads: {credit_bias} (vote: {credit_vote:+d}/Â±{max_vote}, {tier})")
            
        except Exception as e:
            logger.warning(f"Error in credit spreads factor: {e}")
            factor_votes.append(("credit_spreads", 0, 2, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 4: Excess CAPE Yield (ECY) - Standard Â±2
        # Rate-adjusted valuation: compares equity yield to real bond yield
        # =====================================================================
        try:
            from bias_filters.excess_cape_yield import get_ecy_reading
            ecy_result = await get_ecy_reading()
            
            if ecy_result.get("status") == "success":
                ecy_vote = ecy_result.get("vote", 0)
                ecy_bias = ecy_result.get("bias", "NEUTRAL")
                
                factor_votes.append(("excess_cape_yield", ecy_vote, 2, {
                    "bias": ecy_bias,
                    "cape": ecy_result.get("cape"),
                    "earnings_yield": ecy_result.get("earnings_yield"),
                    "real_yield": ecy_result.get("real_yield"),
                    "ecy": ecy_result.get("ecy"),
                    "signal": ecy_result.get("signal"),
                    "interpretation": ecy_result.get("interpretation"),
                    "tier": "standard"
                }))
                logger.info(f"  ðŸ“Š Excess CAPE Yield: {ecy_result.get('ecy')}% -> {ecy_bias} (vote: {ecy_vote:+d}/Â±2)")
            else:
                logger.warning(f"ECY data unavailable: {ecy_result.get('message')}")
                factor_votes.append(("excess_cape_yield", 0, 2, {"error": ecy_result.get("message")}))
            
        except Exception as e:
            logger.warning(f"Error in ECY factor: {e}")
            factor_votes.append(("excess_cape_yield", 0, 2, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 4b: Savita Indicator (OPTIONAL) - Standard Â±2
        # Only active if manually updated with recent BofA data
        # =====================================================================
        try:
            from bias_filters.savita_indicator import get_savita_reading, is_savita_stale
            
            # Only include Savita if it has fresh data (not stale)
            if not is_savita_stale():
                savita_result = get_savita_reading()
                savita_bias = savita_result.get("bias", "NEUTRAL")
                savita_level = BIAS_LEVELS.get(savita_bias, 4)
                savita_vote = savita_level - 4
                
                factor_votes.append(("savita_indicator", savita_vote, 2, {
                    "bias": savita_bias,
                    "bias_level": savita_level,
                    "reading": savita_result.get("reading"),
                    "signal": savita_result.get("signal"),
                    "tier": "standard",
                    "optional": True,
                    "note": "Manual input - BofA data"
                }))
                logger.info(f"  ðŸŽ¯ Savita Indicator (optional): {savita_bias} (vote: {savita_vote:+d}/Â±2)")
            else:
                logger.info(f"  â¸ï¸ Savita Indicator: Skipped (stale data >30 days)")
            
        except Exception as e:
            logger.warning(f"Error checking Savita: {e}")
        
        # =====================================================================
        # FACTOR 5: Long-term Breadth (RSP vs SPY) - Standard Â±2
        # =====================================================================
        try:
            from bias_filters.market_breadth import auto_fetch_and_update as fetch_market_breadth
            from bias_filters.market_breadth import get_bias_for_scoring as get_longterm_breadth
            
            await fetch_market_breadth()
            breadth_result = get_longterm_breadth()
            
            breadth_level = breadth_result.get("bias_level", 3)
            breadth_vote = breadth_level - 3
            
            factor_votes.append(("longterm_breadth", breadth_vote, 2, {
                "bias": breadth_result.get("bias", "NEUTRAL"),
                "bias_level": breadth_level,
                "tier": "standard",
                "last_updated": breadth_result.get("last_updated"),
                "data_source": "yfinance"
            }))
            logger.info(f"  ðŸ“Š Long-term Breadth: {breadth_result.get('bias')} (vote: {breadth_vote:+d}/Â±2)")
            
        except Exception as e:
            logger.warning(f"Error in breadth factor: {e}")
            factor_votes.append(("longterm_breadth", 0, 2, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 6: VIX Regime (Fear/Complacency Gauge) - Standard Â±2
        # =====================================================================
        try:
            vix = yf.Ticker("^VIX")
            vix_hist = vix.history(period="3mo")
            
            vix_vote = 0
            vix_details = {}
            
            if len(vix_hist) >= 20:
                current_vix = float(vix_hist['Close'].iloc[-1])
                vix_20d_avg = float(vix_hist['Close'].tail(20).mean())
                vix_3mo_low = float(vix_hist['Close'].min())
                vix_3mo_high = float(vix_hist['Close'].max())
                
                vix_details = {
                    "current_vix": round(current_vix, 2),
                    "vix_20d_avg": round(vix_20d_avg, 2),
                    "vix_3mo_low": round(vix_3mo_low, 2),
                    "vix_3mo_high": round(vix_3mo_high, 2),
                    "vix_percentile": round((current_vix - vix_3mo_low) / (vix_3mo_high - vix_3mo_low) * 100, 1) if vix_3mo_high != vix_3mo_low else 50
                }
                
                # VIX levels: <15 = complacent (bullish), 15-20 = normal, 20-25 = elevated, >25 = fear
                if current_vix < 14:
                    vix_vote = 2
                    vix_details["regime"] = "extreme_complacency"
                elif current_vix < 17:
                    vix_vote = 1
                    vix_details["regime"] = "complacent"
                elif current_vix < 22:
                    vix_vote = 0
                    vix_details["regime"] = "normal"
                elif current_vix < 28:
                    vix_vote = -1
                    vix_details["regime"] = "elevated_fear"
                else:
                    vix_vote = -2
                    vix_details["regime"] = "high_fear"
                    
                vix_details["tier"] = "standard"
                vix_details["data_source"] = "yfinance"
            else:
                vix_details = {"error": "Insufficient VIX data", "regime": "unknown", "tier": "standard"}
            
            factor_votes.append(("vix_regime", vix_vote, 2, vix_details))
            logger.info(f"  ðŸ˜° VIX Regime: {vix_details.get('regime', 'unknown')} (VIX: {vix_details.get('current_vix', 'N/A')}, vote: {vix_vote:+d}/Â±2)")
            
        except Exception as e:
            logger.warning(f"Error in VIX Regime factor: {e}")
            factor_votes.append(("vix_regime", 0, 2, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 7: Cyclical vs Defensive Rotation (XLY vs XLP) - Standard Â±2
        # =====================================================================
        try:
            # XLY = Consumer Discretionary (cyclical), XLP = Consumer Staples (defensive)
            xly = yf.Ticker("XLY")
            xlp = yf.Ticker("XLP")
            
            xly_hist = xly.history(period="2mo")  # Get 2 months to ensure 20 trading days
            xlp_hist = xlp.history(period="2mo")
            
            if len(xly_hist) >= 20 and len(xlp_hist) >= 20:
                # Calculate 20-day performance
                xly_current = float(xly_hist['Close'].iloc[-1])
                xly_20d_ago = float(xly_hist['Close'].iloc[-20])
                xly_return = ((xly_current - xly_20d_ago) / xly_20d_ago) * 100
                
                xlp_current = float(xlp_hist['Close'].iloc[-1])
                xlp_20d_ago = float(xlp_hist['Close'].iloc[-20])
                xlp_return = ((xlp_current - xlp_20d_ago) / xlp_20d_ago) * 100
                
                # Spread: positive = cyclicals leading (risk-on)
                rotation_spread = xly_return - xlp_return
                
                if rotation_spread > 3.0:
                    rotation_vote = 2
                    status = "strong_risk_on"
                elif rotation_spread > 1.0:
                    rotation_vote = 1
                    status = "mild_risk_on"
                elif rotation_spread < -3.0:
                    rotation_vote = -2
                    status = "strong_defensive"
                elif rotation_spread < -1.0:
                    rotation_vote = -1
                    status = "mild_defensive"
                else:
                    rotation_vote = 0
                    status = "neutral"
                
                factor_votes.append(("cyclical_vs_defensive", rotation_vote, 2, {
                    "xly_return_20d": round(xly_return, 2),
                    "xlp_return_20d": round(xlp_return, 2),
                    "spread": round(rotation_spread, 2),
                    "status": status,
                    "tier": "standard",
                    "data_source": "yfinance"
                }))
                logger.info(f"  ðŸ”„ Cyclical vs Defensive: {status} (spread: {rotation_spread:+.1f}%, vote: {rotation_vote:+d}/Â±2)")
            else:
                raise Exception("Insufficient XLY/XLP data")
                
        except Exception as e:
            logger.warning(f"Error in Cyclical vs Defensive factor: {e}")
            factor_votes.append(("cyclical_vs_defensive", 0, 2, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 8: Copper/Gold Ratio - Standard Â±2
        # =====================================================================
        try:
            # COPX = Copper miners ETF, GLD = Gold ETF
            # Alternative: Use futures proxies
            copper = yf.Ticker("COPX")  # Copper miners
            gold = yf.Ticker("GLD")     # Gold ETF
            
            copper_hist = copper.history(period="2mo")  # Get 2 months to ensure 20 trading days
            gold_hist = gold.history(period="2mo")
            
            if len(copper_hist) >= 20 and len(gold_hist) >= 20:
                # Calculate 20-day performance
                copper_current = float(copper_hist['Close'].iloc[-1])
                copper_20d_ago = float(copper_hist['Close'].iloc[-20])
                copper_return = ((copper_current - copper_20d_ago) / copper_20d_ago) * 100
                
                gold_current = float(gold_hist['Close'].iloc[-1])
                gold_20d_ago = float(gold_hist['Close'].iloc[-20])
                gold_return = ((gold_current - gold_20d_ago) / gold_20d_ago) * 100
                
                # Spread: positive = copper leading (economic optimism)
                cg_spread = copper_return - gold_return
                
                if cg_spread > 5.0:
                    cg_vote = 2
                    status = "economic_optimism"
                elif cg_spread > 2.0:
                    cg_vote = 1
                    status = "mild_optimism"
                elif cg_spread < -5.0:
                    cg_vote = -2
                    status = "flight_to_safety"
                elif cg_spread < -2.0:
                    cg_vote = -1
                    status = "mild_caution"
                else:
                    cg_vote = 0
                    status = "neutral"
                
                factor_votes.append(("copper_gold_ratio", cg_vote, 2, {
                    "copper_return_20d": round(copper_return, 2),
                    "gold_return_20d": round(gold_return, 2),
                    "spread": round(cg_spread, 2),
                    "status": status,
                    "tier": "standard",
                    "data_source": "yfinance"
                }))
                logger.info(f"  ðŸ¥‡ Copper/Gold: {status} (spread: {cg_spread:+.1f}%, vote: {cg_vote:+d}/Â±2)")
            else:
                raise Exception("Insufficient COPX/GLD data")
                
        except Exception as e:
            logger.warning(f"Error in Copper/Gold factor: {e}")
            factor_votes.append(("copper_gold_ratio", 0, 2, {"error": str(e)}))
        
        # =====================================================================
        # FACTOR 9: Sahm Rule (Real FRED Data) - TIERED: Â±2 normal, Â±4 if triggered
        # =====================================================================
        try:
            import os
            fred_api_key = os.environ.get("FRED_API_KEY")
            
            if fred_api_key:
                from fredapi import Fred
                fred = Fred(api_key=fred_api_key)
                
                # Get the real Sahm Rule indicator from FRED
                # SAHMREALTIME: Real-time Sahm Rule Recession Indicator
                sahm_data = fred.get_series('SAHMREALTIME', observation_start='2024-01-01')
                
                sahm_triggered = False
                sahm_vote = 0
                max_vote = 2
                tier = "standard"
                
                if len(sahm_data) > 0:
                    current_sahm = float(sahm_data.iloc[-1])
                    previous_sahm = float(sahm_data.iloc[-2]) if len(sahm_data) > 1 else current_sahm
                    sahm_trend = "rising" if current_sahm > previous_sahm else ("falling" if current_sahm < previous_sahm else "stable")
                    
                    sahm_details = {
                        "current_reading": round(current_sahm, 3),
                        "previous_reading": round(previous_sahm, 3),
                        "trend": sahm_trend,
                        "threshold": 0.50,
                        "last_date": str(sahm_data.index[-1].date())
                    }
                    
                    # Sahm Rule scoring: Crisis indicator + Trend matters
                    # Only gives bullish signal when LOW and FALLING (relief)
                    # Otherwise it's a bearish/neutral indicator
                    #
                    # >= 0.50 = Recession triggered (-4, crisis)
                    # 0.40-0.50 = High warning (-2)
                    # 0.30-0.40 + rising = Deteriorating (-1)
                    # 0.30-0.40 + falling = Improving but elevated (0)
                    # < 0.30 + rising = Moving wrong direction (-1)
                    # < 0.30 + falling = Relief signal (+1) - ONLY bullish case
                    
                    if current_sahm >= 0.50:
                        # RECESSION TRIGGERED - Maximum crisis weight
                        sahm_triggered = True
                        sahm_vote = -4
                        max_vote = 4
                        tier = "crisis_extreme"
                        sahm_details["status"] = "recession_triggered"
                    elif current_sahm >= 0.40:
                        # HIGH WARNING - Crisis weight
                        sahm_vote = -2
                        max_vote = 4
                        tier = "crisis"
                        sahm_details["status"] = "high_warning"
                    elif current_sahm >= 0.30:
                        # WARNING ZONE - trend matters
                        if sahm_trend == "rising":
                            sahm_vote = -1
                            sahm_details["status"] = "warning_deteriorating"
                        else:
                            sahm_vote = 0
                            sahm_details["status"] = "warning_improving"
                    elif current_sahm < 0.30:
                        # BELOW WARNING - trend determines signal
                        if sahm_trend == "falling":
                            # Relief signal - only bullish case
                            sahm_vote = 1
                            sahm_details["status"] = "relief_signal"
                        elif sahm_trend == "rising":
                            # Moving wrong direction
                            sahm_vote = -1
                            sahm_details["status"] = "rising_concern"
                        else:
                            # Stable/normal - no signal
                            sahm_vote = 0
                            sahm_details["status"] = "stable"
                    
                    sahm_details["tier"] = tier
                    sahm_details["data_source"] = "FRED"
                    
                    factor_votes.append(("sahm_rule", sahm_vote, max_vote, {
                        "triggered": sahm_triggered,
                        **sahm_details
                    }))
                    logger.info(f"  ðŸš¨ Sahm Rule (FRED): {sahm_details['status']} (reading: {current_sahm:.3f}, vote: {sahm_vote:+d}/Â±{max_vote}, {tier})")
                else:
                    raise Exception("No Sahm Rule data returned from FRED")
            else:
                # No FRED API key - use placeholder
                factor_votes.append(("sahm_rule", 0, 2, {
                    "status": "no_api_key",
                    "tier": "standard",
                    "note": "Set FRED_API_KEY environment variable for real data"
                }))
                logger.warning("  ðŸš¨ Sahm Rule: No FRED API key configured")
                
        except Exception as e:
            logger.warning(f"Error in Sahm Rule factor: {e}")
            factor_votes.append(("sahm_rule", 0, 2, {"error": str(e), "tier": "standard"}))
        
        # =====================================================================
        # CALCULATE TOTAL VOTE AND DETERMINE BIAS (9-Factor Tiered System)
        # =====================================================================
        total_vote = sum(vote for _, vote, _, _ in factor_votes)
        max_possible_normal = 18  # 9 factors Ã— 2 max each (normal conditions)
        max_possible_crisis = sum(max_v for _, _, max_v, _ in factor_votes)  # Actual max based on current tier
        
        # Check if any crisis-tier factors are active
        crisis_active = any(det.get("tier", "standard").startswith("crisis") for _, _, _, det in factor_votes)
        
        # Thresholds for 9 factors with tiered voting
        # Adjusted for higher max possible vote range (Â±18 normal, Â±22 crisis)
        if total_vote >= 11:
            new_level = "MAJOR_TORO"
        elif total_vote >= 5:
            new_level = "MINOR_TORO"
        elif total_vote >= 0:
            new_level = "LEAN_TORO"
        elif total_vote > -5:
            new_level = "LEAN_URSA"
        elif total_vote > -11:
            new_level = "MINOR_URSA"
        else:
            new_level = "MAJOR_URSA"
        
        # Build details
        details = {
            "source": "9_factor_tiered_cyclical",
            "total_vote": total_vote,
            "max_possible_normal": max_possible_normal,
            "max_possible_current": max_possible_crisis,
            "crisis_mode_active": crisis_active,
            "factors": {name: {"vote": vote, "max_vote": max_v, "details": det} for name, vote, max_v, det in factor_votes}
        }
        
        # Update bias with trend tracking
        result = update_bias(BiasTimeframe.CYCLICAL, new_level, details=details)
        
        mode_str = "CRISIS MODE" if crisis_active else "normal"
        logger.info(f"âœ… Cyclical Bias updated: {new_level} (vote: {total_vote}/Â±{max_possible_crisis}, {mode_str})")
        return result
        
    except Exception as e:
        logger.error(f"Error refreshing cyclical bias: {e}")
        return {"error": str(e)}


# =========================================================================
# SCHEDULER SETUP
# =========================================================================

_scheduler_started = False

def is_trading_day() -> bool:
    """Check if today is a trading day (Mon-Fri, not a holiday) in Eastern Time"""
    today = get_eastern_now().date()
    if today.weekday() >= 5:
        return False

    holiday_dates = (
        _nyse_holidays(today.year - 1)
        | _nyse_holidays(today.year)
        | _nyse_holidays(today.year + 1)
    )
    return today not in holiday_dates


def _observed_date(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nyse_holidays(year: int) -> set[date]:
    holidays: set[date] = set()

    holidays.add(_observed_date(date(year, 1, 1)))      # New Year's Day
    holidays.add(_nth_weekday(year, 1, 0, 3))           # MLK Day (3rd Monday Jan)
    holidays.add(_nth_weekday(year, 2, 0, 3))           # Presidents Day (3rd Monday Feb)

    good_friday = _easter_date(year) - timedelta(days=2)
    holidays.add(good_friday)

    holidays.add(_last_weekday(year, 5, 0))             # Memorial Day (last Monday May)
    holidays.add(_observed_date(date(year, 6, 19)))     # Juneteenth
    holidays.add(_observed_date(date(year, 7, 4)))      # Independence Day
    holidays.add(_nth_weekday(year, 9, 0, 1))           # Labor Day (1st Monday Sep)
    holidays.add(_nth_weekday(year, 11, 3, 4))          # Thanksgiving (4th Thursday Nov)
    holidays.add(_observed_date(date(year, 12, 25)))    # Christmas

    return holidays


def is_first_trading_day_of_month() -> bool:
    """Check if today is the first trading day of the month (Eastern Time)"""
    today = get_eastern_now()
    
    # Find first weekday of month
    first_day = today.replace(day=1, tzinfo=ET)
    while first_day.weekday() >= 5:  # Saturday or Sunday
        first_day += timedelta(days=1)
    
    return today.date() == first_day.date()


async def run_signal_scoring_job() -> None:
    """Score pending signals and clean up stale discovery tickers."""
    try:
        from jobs.score_signals import score_pending_signals, cleanup_stale_discovery_tickers
        await score_pending_signals()
        await cleanup_stale_discovery_tickers()
    except Exception as e:
        logger.warning(f"Signal scoring job failed: {e}")


async def run_savita_auto_search():
    """
    Run Gemini-powered search for latest Savita indicator reading.
    Called by scheduler from 12th-23rd of each month at 8:00 AM ET.
    """
    now = get_eastern_now()
    logger.info(f"ðŸ” Running Savita auto-search at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    try:
        from bias_filters.savita_indicator import auto_search_savita_update
        result = await auto_search_savita_update()
        
        if result.get("status") == "success":
            logger.info(f"âœ… Savita updated: {result.get('previous_reading')}% -> {result.get('new_reading')}%")
        elif result.get("status") == "no_update":
            logger.info(f"ðŸ“Š Savita unchanged: {result.get('message')}")
        else:
            logger.warning(f"âš ï¸ Savita search issue: {result.get('message')}")
            
    except Exception as e:
        logger.error(f"âŒ Savita auto-search error: {e}")


async def refresh_btc_bottom_signals():
    """
    Auto-refresh BTC Bottom Signals from all API sources
    Runs every 5 minutes, 24/7
    """
    try:
        from bias_filters.btc_bottom_signals import update_all_signals
        
        logger.info("ðŸ”„ Refreshing BTC Bottom Signals from APIs...")
        result = await update_all_signals()
        
        confluence = result.get('confluence', {})
        firing = confluence.get('firing', 0)
        total = confluence.get('total', 9)
        
        logger.info(f"âœ… BTC Signals refreshed: {firing}/{total} firing")
        
        # Log any API issues
        api_status = result.get('api_status', {})
        unavailable = [api for api, status in api_status.items() if not status]
        if unavailable:
            logger.warning(f"âš ï¸ Unavailable BTC data sources: {', '.join(unavailable)}")
            
    except Exception as e:
        logger.error(f"âŒ BTC Bottom Signals refresh error: {e}")


async def auto_dismiss_old_signals():
    """
    Auto-dismiss signals older than 24 hours to keep Trade Ideas fresh.
    Runs every hour.
    """
    try:
        from database.postgres_client import get_postgres_client
        
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # Dismiss signals older than 24 hours that haven't been acted upon
            result = await conn.execute("""
                UPDATE signals 
                SET user_action = 'DISMISSED', 
                    dismissed_at = NOW(),
                    notes = COALESCE(notes || ' | ', '') || 'Auto-dismissed after 24h'
                WHERE user_action IS NULL 
                AND created_at < NOW() - INTERVAL '24 hours'
            """)
            
            # Extract count from result status (e.g., "UPDATE 5")
            count = 0
            if hasattr(result, 'split'):
                parts = result.split()
                if len(parts) > 1 and parts[1].isdigit():
                    count = int(parts[1])
            
            if count > 0:
                logger.info(f"ðŸ—‘ï¸ Auto-dismissed {count} signals older than 24 hours")
            
    except Exception as e:
        logger.error(f"âŒ Auto-dismiss error: {e}")


async def run_price_collection_job(backfill: bool = False):
    """
    Collect and persist OHLCV price history.
    - backfill=True: one-time startup backfill window.
    - backfill=False: incremental append cadence.
    """
    now = get_eastern_now()
    _scheduler_status["price_collection"]["status"] = "running"
    try:
        from analytics.price_collector import collect_price_history_cycle, run_price_backfill_once

        if backfill:
            result = await run_price_backfill_once()
        else:
            result = await collect_price_history_cycle(backfill=False)

        _scheduler_status["price_collection"]["last_run"] = now.isoformat()
        _scheduler_status["price_collection"]["status"] = result.get("status", "completed")
        logger.info(
            "Price collection (%s): status=%s tickers=%s rows=%s",
            "backfill" if backfill else "incremental",
            result.get("status"),
            result.get("tickers"),
            result.get("rows_upserted"),
        )
    except Exception as e:
        _scheduler_status["price_collection"]["status"] = f"error: {e}"
        logger.error(f"Price collection error: {e}")


async def run_benchmark_tracker_job():
    """Update benchmark baselines at market close."""
    now = get_eastern_now()
    _scheduler_status["benchmark_tracker"]["status"] = "running"
    try:
        from analytics.benchmark_tracker import update_benchmarks

        result = await update_benchmarks()
        _scheduler_status["benchmark_tracker"]["last_run"] = now.isoformat()
        _scheduler_status["benchmark_tracker"]["status"] = result.get("status", "completed")
        logger.info("Benchmark tracker updated: %s", result.get("status"))
    except Exception as e:
        _scheduler_status["benchmark_tracker"]["status"] = f"error: {e}"
        logger.error(f"Benchmark tracker error: {e}")


async def run_portfolio_monitor_job():
    """Persist portfolio risk snapshot and alert on correlated exposure."""
    now = get_eastern_now()
    _scheduler_status["portfolio_monitor"]["status"] = "running"
    try:
        from analytics.portfolio_monitor import snapshot_portfolio_and_alert

        result = await snapshot_portfolio_and_alert()
        _scheduler_status["portfolio_monitor"]["last_run"] = now.isoformat()
        _scheduler_status["portfolio_monitor"]["status"] = result.get("status", "completed")
        logger.info("Portfolio monitor updated: %s", result.get("status"))
    except Exception as e:
        _scheduler_status["portfolio_monitor"]["status"] = f"error: {e}"
        logger.error(f"Portfolio monitor error: {e}")


async def run_health_monitor_job():
    """Compute rolling strategy health grades and alert on degraded sources."""
    now = get_eastern_now()
    _scheduler_status["health_monitor"]["status"] = "running"
    try:
        from analytics.health_monitor import run_strategy_health_monitor

        result = await run_strategy_health_monitor(window_days=30)
        _scheduler_status["health_monitor"]["last_run"] = now.isoformat()
        _scheduler_status["health_monitor"]["status"] = result.get("status", "completed")
        logger.info(
            "Strategy health monitor updated: status=%s sources=%s alerts=%s",
            result.get("status"),
            result.get("sources"),
            result.get("alerts"),
        )
    except Exception as e:
        _scheduler_status["health_monitor"]["status"] = f"error: {e}"
        logger.error(f"Strategy health monitor error: {e}")


async def reset_circuit_breaker_scheduled():
    """
    Reset circuit breaker at market open (9:30 AM ET)
    Clears any overnight risk events
    """
    try:
        from webhooks.circuit_breaker import reset_circuit_breaker
        result = reset_circuit_breaker()
        logger.info(f"ðŸ”“ Circuit breaker reset at market open: {result}")
    except Exception as e:
        logger.error(f"Error resetting circuit breaker: {e}")


async def run_scheduled_refreshes():
    """
    Run appropriate refreshes based on current time/day
    Called by the scheduler at 9:45 AM ET
    """
    now = get_eastern_now()
    logger.info(f"â° Running scheduled bias refresh at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    if not is_trading_day():
        logger.info("Not a trading day, skipping refresh")
        return
    
    # Always refresh daily
    await refresh_daily_bias()
    
    # Always refresh weekly (runs daily, Monday sets baseline)
    await refresh_weekly_bias()
    
    # Refresh cyclical on Mondays (long-term macro doesn't change daily)
    if now.weekday() == 0:  # Monday
        await refresh_cyclical_bias()
    
    # Run sector strength scan every morning
    await scan_sector_strength()
    
    # Compute sector rotation momentum
    try:
        from bias_filters.sector_momentum import refresh_sector_rotation
        await refresh_sector_rotation()
    except Exception as e:
        logger.warning(f"Sector rotation momentum refresh failed: {e}")
    
    # Update scheduler status
    _scheduler_status["bias_refresh"]["last_run"] = now.isoformat()
    _scheduler_status["bias_refresh"]["status"] = "completed"


async def refresh_composite_bias():
    """
    Refresh composite bias (15-minute safety net).
    Also refreshes sector rotation momentum during market hours.
    """
    # Refresh sector rotation momentum alongside composite
    try:
        from bias_filters.sector_momentum import refresh_sector_rotation
        await refresh_sector_rotation()
    except Exception as e:
        logger.debug(f"Sector rotation refresh during composite cycle: {e}")

    # Score all 20 factors (including FRED-sourced macro factors) and write to Redis
    # so that compute_composite() has fresh readings to aggregate.
    try:
        from bias_engine.factor_scorer import score_all_factors
        await score_all_factors()
    except Exception as e:
        logger.warning(f"Factor scoring failed during composite refresh: {e}")

    try:
        from bias_engine.composite import compute_composite
    except ImportError as e:
        logger.warning(f"Composite bias engine not available: {e}")
        return None

    now = get_eastern_now()
    try:
        result = await compute_composite()
        _scheduler_status["composite_bias"]["last_run"] = now.isoformat()
        _scheduler_status["composite_bias"]["status"] = "completed"
        logger.info(f"ðŸ§­ Composite bias refreshed: {result.bias_level} ({result.composite_score:.2f})")
        return result
    except Exception as e:
        _scheduler_status["composite_bias"]["status"] = f"error: {str(e)}"
        logger.warning(f"Error refreshing composite bias: {e}")
        return None


async def scan_sector_strength():
    """
    Scan sector ETFs to determine which sectors are leading/lagging.
    Updates the watchlist with sector strength rankings.
    
    Criteria:
    - Price vs 20 SMA (momentum)
    - Price vs 50 SMA (trend)
    - Relative strength vs SPY
    """
    logger.info("ðŸ“Š Scanning sector strength...")
    
    try:
        import yfinance as yf
        
        # Sector ETFs to analyze
        SECTOR_ETFS = {
            "Technology": "XLK",
            "Consumer Discretionary": "XLY",
            "Healthcare": "XLV",
            "Financials": "XLF",
            "Industrials": "XLI",
            "Consumer Staples": "XLP",
            "Energy": "XLE",
            "Utilities": "XLU",
            "Materials": "XLB",
            "Real Estate": "XLRE",
            "Communication Services": "XLC"
        }
        
        def _fetch_history(symbol: str):
            ticker = yf.Ticker(symbol)
            return ticker.history(period="3mo")

        # Get SPY as benchmark
        spy_hist = await asyncio.to_thread(_fetch_history, "SPY")
        if spy_hist.empty:
            logger.warning("Could not fetch SPY data for sector comparison")
            return
        
        spy_price = float(spy_hist['Close'].iloc[-1])
        spy_sma20 = float(spy_hist['Close'].rolling(20).mean().iloc[-1])
        spy_pct_change_month = (spy_price / spy_hist['Close'].iloc[-21] - 1) * 100 if len(spy_hist) >= 21 else 0
        
        sector_scores = {}
        
        for sector_name, etf in SECTOR_ETFS.items():
            try:
                hist = await asyncio.to_thread(_fetch_history, etf)
                
                if hist.empty or len(hist) < 50:
                    continue
                
                price = float(hist['Close'].iloc[-1])
                sma20 = float(hist['Close'].rolling(20).mean().iloc[-1])
                sma50 = float(hist['Close'].rolling(50).mean().iloc[-1])
                
                # Calculate metrics
                above_20sma = price > sma20
                above_50sma = price > sma50
                pct_change_month = (price / hist['Close'].iloc[-21] - 1) * 100 if len(hist) >= 21 else 0
                
                # Relative strength vs SPY
                relative_strength = pct_change_month - spy_pct_change_month
                
                # Score: higher = stronger sector
                score = 0
                if above_20sma:
                    score += 1
                if above_50sma:
                    score += 1
                if relative_strength > 1:
                    score += 2  # Outperforming SPY significantly
                elif relative_strength > 0:
                    score += 1  # Slightly outperforming
                elif relative_strength < -1:
                    score -= 1  # Underperforming
                
                sector_scores[sector_name] = {
                    "etf": etf,
                    "price": round(price, 2),
                    "above_20sma": above_20sma,
                    "above_50sma": above_50sma,
                    "pct_change_month": round(pct_change_month, 2),
                    "relative_strength": round(relative_strength, 2),
                    "strength": score,
                    "trend": "leading" if score >= 3 else ("lagging" if score <= 0 else "neutral")
                }
                
            except Exception as e:
                logger.warning(f"Error scanning {sector_name} ({etf}): {e}")
                continue
        
        # Rank sectors by strength
        sorted_sectors = sorted(sector_scores.items(), key=lambda x: x[1]["strength"], reverse=True)
        for rank, (sector_name, data) in enumerate(sorted_sectors, 1):
            sector_scores[sector_name]["rank"] = rank
        
        logger.info(f"âœ… Sector strength scan complete: {len(sector_scores)} sectors analyzed")
        
        # Log top and bottom sectors
        if sorted_sectors:
            top = sorted_sectors[0]
            bottom = sorted_sectors[-1]
            logger.info(f"   Leading: {top[0]} ({top[1]['etf']}) - score {top[1]['strength']}")
            logger.info(f"   Lagging: {bottom[0]} ({bottom[1]['etf']}) - score {bottom[1]['strength']}")
        
        # Update watchlist with sector strength (direct call avoids localhost dependency)
        try:
            from api.watchlist import SectorStrengthUpdate, update_sector_strength
            await update_sector_strength(SectorStrengthUpdate(sector_strength=sector_scores), _="internal")
            logger.info("   Sector strength saved to watchlist")
        except Exception as e:
            logger.warning(f"Could not update watchlist with sector strength: {e}")
        
        return sector_scores
        
    except Exception as e:
        logger.error(f"Error in sector strength scan: {e}")
        import traceback
        traceback.print_exc()
        return {}


async def start_scheduler():
    """Start the background scheduler"""
    global _scheduler_started, _weekly_baseline, _scheduler_status
    
    if _scheduler_started:
        logger.info("Scheduler already running")
        return
    
    _scheduler_started = True
    _scheduler_status["scheduler_started"] = get_eastern_now().isoformat()
    logger.info("ðŸš€ Starting bias scheduler...")
    
    # Load weekly baseline from disk
    _weekly_baseline = _load_weekly_baseline()
    if _weekly_baseline.get("timestamp"):
        logger.info(f"  ðŸ“Œ Loaded weekly baseline: {_weekly_baseline.get('level')} (from {_weekly_baseline.get('timestamp')})")
    else:
        logger.info("  ðŸ“Œ No weekly baseline found - will be set on next Monday")
    
    # Run initial refresh on startup (Railway has ephemeral filesystem)
    logger.info("  ðŸ”„ Running initial bias refresh on startup...")
    try:
        await refresh_daily_bias()
        await refresh_weekly_bias()
        await refresh_cyclical_bias()
        # Score all composite factors (including FRED) so the composite engine
        # has data immediately on boot rather than waiting for the first 15-min cycle.
        try:
            from bias_engine.factor_scorer import score_all_factors
            await score_all_factors()
        except Exception as fs_err:
            logger.warning(f"  Initial factor scoring failed: {fs_err}")
        logger.info("  âœ… Initial bias refresh complete")
    except Exception as e:
        logger.error(f"  âŒ Error during initial refresh: {e}")

    # Kick off startup price-history backfill asynchronously.
    try:
        asyncio.create_task(run_price_collection_job(backfill=True))
        logger.info("  ðŸ“¦ Analytics price backfill task started")
    except Exception as e:
        logger.warning(f"  âš ï¸ Could not start analytics backfill task: {e}")
    
    # Use APScheduler if available, otherwise use simple asyncio loop
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        scheduler = AsyncIOScheduler()

        # Circuit breaker reset at market open (9:30 AM ET)
        scheduler.add_job(
            reset_circuit_breaker_scheduled,
            CronTrigger(hour=9, minute=30, day_of_week='mon-fri'),
            id='circuit_breaker_reset',
            name='Circuit Breaker Daily Reset',
            replace_existing=True
        )

        # Daily refresh at multiple times throughout the day (9:45 AM, 11:00 AM, 1:00 PM, 3:00 PM ET)
        scheduler.add_job(
            run_scheduled_refreshes,
            CronTrigger(hour=9, minute=45, day_of_week='mon-fri'),
            id='bias_refresh_0945',
            name='Daily Bias Refresh (9:45 AM)',
            replace_existing=True
        )

        scheduler.add_job(
            run_scheduled_refreshes,
            CronTrigger(hour=11, minute=0, day_of_week='mon-fri'),
            id='bias_refresh_1100',
            name='Daily Bias Refresh (11:00 AM)',
            replace_existing=True
        )

        scheduler.add_job(
            run_scheduled_refreshes,
            CronTrigger(hour=13, minute=0, day_of_week='mon-fri'),
            id='bias_refresh_1300',
            name='Daily Bias Refresh (1:00 PM)',
            replace_existing=True
        )

        scheduler.add_job(
            run_scheduled_refreshes,
            CronTrigger(hour=15, minute=0, day_of_week='mon-fri'),
            id='bias_refresh_1500',
            name='Daily Bias Refresh (3:00 PM)',
            replace_existing=True
        )

        # Savita auto-search at 8:00 AM ET, days 12-23 of each month
        scheduler.add_job(
            run_savita_auto_search,
            CronTrigger(hour=8, minute=0, day='12-23'),
            id='savita_search',
            name='Savita Auto-Search (BofA Indicator)',
            replace_existing=True
        )
        
        # BTC Bottom Signals refresh every 5 minutes (24/7)
        scheduler.add_job(
            refresh_btc_bottom_signals,
            'interval',
            minutes=5,
            id='btc_signals_refresh',
            name='BTC Bottom Signals Auto-Refresh',
            replace_existing=True
        )
        
        # Auto-dismiss old signals every hour
        scheduler.add_job(
            auto_dismiss_old_signals,
            'interval',
            hours=1,
            id='auto_dismiss_signals',
            name='Auto-Dismiss Old Signals',
            replace_existing=True
        )

        # Composite bias refresh every 15 minutes
        scheduler.add_job(
            refresh_composite_bias,
            'interval',
            minutes=15,
            id='composite_bias_refresh',
            name='Composite Bias Refresh',
            replace_existing=True
        )

        # Price history collection every 5 minutes.
        scheduler.add_job(
            run_price_collection_job,
            'interval',
            minutes=5,
            kwargs={"backfill": False},
            id='price_history_collection',
            name='Price History Collection',
            replace_existing=True,
            coalesce=True,
            max_instances=1
        )

        # Daily analytics updates at/after market close.
        scheduler.add_job(
            run_benchmark_tracker_job,
            CronTrigger(day_of_week='mon-fri', hour=16, minute=10, timezone=ET),
            id='benchmark_tracker',
            name='Benchmark Tracker',
            replace_existing=True
        )

        scheduler.add_job(
            run_portfolio_monitor_job,
            CronTrigger(day_of_week='mon-fri', hour=16, minute=15, timezone=ET),
            id='portfolio_monitor',
            name='Portfolio Risk Snapshot',
            replace_existing=True
        )

        scheduler.add_job(
            run_health_monitor_job,
            CronTrigger(day_of_week='mon-fri', hour=16, minute=30, timezone=ET),
            id='health_monitor',
            name='Strategy Health Monitor',
            replace_existing=True
        )

        # Nightly signal outcome scoring + discovery cleanup (9:00 PM ET)
        scheduler.add_job(
            run_signal_scoring_job,
            CronTrigger(day_of_week='mon-fri', hour=21, minute=0, timezone=ET),
            id='signal_scoring',
            name='Signal Outcome Scoring',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("âœ… APScheduler started - bias refresh scheduled for 9:45 AM ET")
        logger.info("âœ… Savita auto-search scheduled for 8:00 AM ET (days 12-23)")
        logger.info("âœ… BTC Bottom Signals refresh scheduled every 5 minutes")
        logger.info("âœ… Auto-dismiss old signals scheduled every hour")
        logger.info("âœ… Composite bias refresh scheduled every 15 minutes")
        logger.info("âœ… Price history collection scheduled every 5 minutes")
        logger.info("âœ… Benchmark tracker scheduled daily at 4:10 PM ET")
        logger.info("âœ… Portfolio monitor scheduled daily at 4:15 PM ET")
        logger.info("âœ… Strategy health monitor scheduled daily at 4:30 PM ET")
        logger.info("âœ… Signal outcome scoring scheduled for 9:00 PM ET")
        
        # ALSO start the scanner loop (APScheduler doesn't handle the variable-interval scanners)
        asyncio.create_task(_scanner_loop())
        logger.info("âœ… Scanner loop started (CTA + Crypto)")
        
    except ImportError:
        logger.warning("APScheduler not installed, using fallback scheduler")
        # Fallback: Simple asyncio-based scheduler (handles both bias refresh AND scanners)
        asyncio.create_task(_fallback_scheduler())


async def _scanner_loop():
    """
    Dedicated scanner loop for CTA and Crypto scanners.
    Runs alongside APScheduler (which handles bias refresh).
    
    Schedule:
    - CTA Scanner (Equities): 
        - First hour (9:30-10:30): Every 15 min
        - Mid-day (10:30-15:00): Every 30 min  
        - Last hour (15:00-16:00): Every 15 min
    - Crypto Scanner: Every 30 min, 24/7
    """
    logger.info("Starting scanner loop (CTA + Crypto)")
    
    last_cta_scan_time = None
    last_crypto_scan_time = None
    
    while True:
        try:
            now = get_eastern_now()
            current_hour = now.hour
            current_minute = now.minute
            
            # =========================================
            # CTA SCANNER (EQUITIES): Smart frequency during market hours
            # =========================================
            if is_trading_day() and 9 <= current_hour <= 16:
                # Determine scan interval based on time of day
                if current_hour == 9 or (current_hour == 10 and current_minute < 30):
                    cta_interval_minutes = 15
                elif current_hour >= 15:
                    cta_interval_minutes = 15
                else:
                    cta_interval_minutes = 30
                
                should_scan_cta = False
                if last_cta_scan_time is None:
                    should_scan_cta = True
                else:
                    minutes_since_last = (now - last_cta_scan_time).total_seconds() / 60
                    should_scan_cta = minutes_since_last >= cta_interval_minutes
                
                if should_scan_cta:
                    last_cta_scan_time = now
                    _scheduler_status["cta_scanner"]["status"] = "running"
                    logger.info(f"â° CTA scan (interval: {cta_interval_minutes}min) - ET: {now.strftime('%H:%M')}")
                    await run_cta_scan_scheduled()
                    await asyncio.sleep(30)
                    continue
            
            # =========================================
            # CRYPTO SCANNER: 24/7, every 30 minutes
            # =========================================
            should_scan_crypto = False
            if last_crypto_scan_time is None:
                should_scan_crypto = True
            else:
                minutes_since_crypto = (now - last_crypto_scan_time).total_seconds() / 60
                should_scan_crypto = minutes_since_crypto >= 30
            
            if should_scan_crypto:
                last_crypto_scan_time = now
                _scheduler_status["crypto_scanner"]["status"] = "running"
                logger.info(f"â° Crypto scan (24/7) - ET: {now.strftime('%H:%M')}")
                await run_crypto_scan_scheduled()
                await asyncio.sleep(30)
                continue
            
            # Check every minute
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in scanner loop: {e}")
            await asyncio.sleep(60)


async def _fallback_scheduler():
    """
    Fallback scheduler using asyncio (runs in background)
    Used when APScheduler is not installed.
    
    Schedule:
    - Bias Refresh: 9:45 AM ET on trading days
    - CTA Scanner (Equities): 
        - First hour (9:30-10:30): Every 15 min
        - Mid-day (10:30-15:00): Every 30 min  
        - Last hour (15:00-16:00): Every 15 min
    - Crypto Scanner: Every 30 min, 24/7
    """
    logger.info("Starting fallback scheduler loop (using Eastern Time)")
    
    last_cta_scan_time = None
    last_crypto_scan_time = None
    last_bias_refresh_date = None
    last_composite_refresh_time = None
    last_price_collection_time = None
    last_benchmark_date = None
    last_portfolio_date = None
    last_health_monitor_date = None
    
    while True:
        now = get_eastern_now()
        current_hour = now.hour
        current_minute = now.minute
        
        # =========================================
        # BIAS REFRESH: 9:45 AM ET on trading days
        # =========================================
        if is_trading_day() and current_hour == 9 and 45 <= current_minute < 46:
            today_str = now.strftime("%Y-%m-%d")
            if last_bias_refresh_date != today_str:
                last_bias_refresh_date = today_str
                logger.info(f"â° 9:45 AM ET trigger - running bias refresh")
                await run_scheduled_refreshes()
                await asyncio.sleep(120)
                continue

        # =========================================
        # COMPOSITE BIAS: Every 15 minutes
        # =========================================
        should_refresh_composite = False
        if last_composite_refresh_time is None:
            should_refresh_composite = True
        else:
            minutes_since_composite = (now - last_composite_refresh_time).total_seconds() / 60
            should_refresh_composite = minutes_since_composite >= 15

        if should_refresh_composite:
            last_composite_refresh_time = now
            await refresh_composite_bias()
            await asyncio.sleep(10)
            continue

        # =========================================
        # PRICE COLLECTION: Every 5 minutes
        # =========================================
        should_collect_prices = False
        if last_price_collection_time is None:
            should_collect_prices = True
        else:
            minutes_since_prices = (now - last_price_collection_time).total_seconds() / 60
            should_collect_prices = minutes_since_prices >= 5

        if should_collect_prices:
            last_price_collection_time = now
            await run_price_collection_job(backfill=False)
            await asyncio.sleep(10)
            continue

        # =========================================
        # BENCHMARK TRACKER: Daily at 4:10 PM ET
        # =========================================
        if is_trading_day() and current_hour == 16 and 10 <= current_minute < 11:
            today_str = now.strftime("%Y-%m-%d")
            if last_benchmark_date != today_str:
                last_benchmark_date = today_str
                await run_benchmark_tracker_job()
                await asyncio.sleep(10)
                continue

        # =========================================
        # PORTFOLIO MONITOR: Daily at 4:15 PM ET
        # =========================================
        if is_trading_day() and current_hour == 16 and 15 <= current_minute < 16:
            today_str = now.strftime("%Y-%m-%d")
            if last_portfolio_date != today_str:
                last_portfolio_date = today_str
                await run_portfolio_monitor_job()
                await asyncio.sleep(10)
                continue

        # =========================================
        # HEALTH MONITOR: Daily at 4:30 PM ET
        # =========================================
        if is_trading_day() and current_hour == 16 and 30 <= current_minute < 31:
            today_str = now.strftime("%Y-%m-%d")
            if last_health_monitor_date != today_str:
                last_health_monitor_date = today_str
                await run_health_monitor_job()
                await asyncio.sleep(10)
                continue
        
        # =========================================
        # CTA SCANNER (EQUITIES): Smart frequency during market hours
        # =========================================
        if is_trading_day() and 9 <= current_hour <= 16:
            # Determine scan interval based on time of day
            if current_hour == 9 or (current_hour == 10 and current_minute < 30):
                # First hour: Every 15 minutes (high volatility at open)
                cta_interval_minutes = 15
            elif current_hour >= 15:
                # Last hour: Every 15 minutes (high volatility at close)
                cta_interval_minutes = 15
            else:
                # Mid-day: Every 30 minutes
                cta_interval_minutes = 30
            
            # Check if enough time has passed since last scan
            should_scan_cta = False
            if last_cta_scan_time is None:
                should_scan_cta = True
            else:
                minutes_since_last = (now - last_cta_scan_time).total_seconds() / 60
                should_scan_cta = minutes_since_last >= cta_interval_minutes
            
            if should_scan_cta:
                last_cta_scan_time = now
                _scheduler_status["cta_scanner"]["status"] = "running"
                logger.info(f"â° CTA scan (interval: {cta_interval_minutes}min) - ET: {now.strftime('%H:%M')}")
                await run_cta_scan_scheduled()
                await asyncio.sleep(30)
                continue
        
        # =========================================
        # CRYPTO SCANNER: 24/7, every 30 minutes
        # =========================================
        should_scan_crypto = False
        if last_crypto_scan_time is None:
            should_scan_crypto = True
        else:
            minutes_since_crypto = (now - last_crypto_scan_time).total_seconds() / 60
            should_scan_crypto = minutes_since_crypto >= 30
        
        if should_scan_crypto:
            last_crypto_scan_time = now
            _scheduler_status["crypto_scanner"]["status"] = "running"
            logger.info(f"â° Crypto scan (24/7) - ET: {now.strftime('%H:%M')}")
            await run_crypto_scan_scheduled()
            await asyncio.sleep(30)
            continue
        
        # Check every minute
        await asyncio.sleep(60)


# =========================================================================
# CTA SCANNER SCHEDULED TASK
# =========================================================================

async def run_cta_scan_scheduled():
    """
    Run CTA scanner automatically and push signals to Trade Ideas
    Scheduled: Every hour during market hours (9:30 AM - 4:00 PM ET)
    """
    logger.info("ðŸŽ¯ Running scheduled CTA scan...")
    
    try:
        from scanners.cta_scanner import run_cta_scan, CTA_SCANNER_AVAILABLE
        from websocket.broadcaster import manager
        from database.redis_client import cache_signal
        from database.postgres_client import log_signal, update_signal_with_score, has_recent_active_signal
        from scoring.trade_ideas_scorer import calculate_signal_score
        
        if not CTA_SCANNER_AVAILABLE:
            logger.warning("CTA Scanner not available - skipping scheduled scan")
            return
        
        # Run the scan
        result = await run_cta_scan(include_watchlist=True)
        
        if result.get("error"):
            logger.error(f"CTA scan error: {result['error']}")
            return
        
        # Get all signals
        all_signals = result.get("top_signals", [])
        
        if not all_signals:
            logger.info("CTA scan complete - no new signals found")
            return
        
        logger.info(f"CTA scan found {len(all_signals)} signals")
        
        # Get current bias status for scoring
        current_bias = {
            "daily": get_bias_status().get("daily", {}),
            "weekly": get_bias_status().get("weekly", {}),
            "cyclical": get_bias_status().get("cyclical", {})
        }
        
        # Load watchlist for bonus scoring
        watchlist = []
        try:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT symbol FROM watchlist_tickers "
                    "WHERE source IN ('manual', 'position') AND muted = false"
                )
            watchlist = [row["symbol"] for row in rows]
        except Exception as e:
            logger.warning(f"Failed to load watchlist symbols: {e}")
        
        # Get current bias status for alignment check
        bias_status = get_bias_status()
        
        # Push each signal to Trade Ideas via WebSocket
        pushed_count = 0
        cooldown_hours = int(os.getenv("CTA_SIGNAL_COOLDOWN_HOURS", "24"))
        for signal in all_signals[:10]:  # Limit to top 10
            ticker = signal.get("symbol")
            if not ticker:
                continue

            try:
                if await has_recent_active_signal(ticker, cooldown_hours, strategy="CTA Scanner"):
                    logger.info(f"â³ Skipping CTA signal for {ticker} (cooldown {cooldown_hours}h)")
                    continue
            except Exception as dedupe_err:
                logger.warning(f"CTA cooldown check failed for {ticker}: {dedupe_err}")

            base_score = signal.get("priority", 50)
            
            # Calculate bonus points
            score_bonuses = []
            
            # 1. Watchlist bonus (+10)
            if ticker in watchlist:
                base_score += 10
                score_bonuses.append("Watchlist")
            
            # 2. Bias alignment bonus (+10)
            bias_aligned = await check_bias_alignment_for_cta(signal.get("direction"))
            if bias_aligned:
                base_score += 10
                score_bonuses.append("Bias Aligned")
            
            # 3. Options flow confirmation (+10)
            flow_confirmed = await check_flow_confirmation_for_cta(ticker, signal.get("direction"))
            if flow_confirmed:
                base_score += 10
                score_bonuses.append("Flow Confirmed")
            
            # Update confidence based on final score
            if base_score >= 70:
                confidence = "HIGH"
            elif base_score >= 55:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"
            
            # Build notes with bonuses
            notes = signal.get("description", "")
            if score_bonuses:
                notes += f" [+{len(score_bonuses)*10}: {', '.join(score_bonuses)}]"
            
            # Convert CTA signal format to standard signal format
            setup = signal.get("setup", {}) or {}
            trade_signal = {
                "signal_id": signal.get("signal_id"),
                "timestamp": signal.get("timestamp"),
                "ticker": ticker,
                "strategy": "CTA Scanner",
                "direction": signal.get("direction", "LONG"),
                "signal_type": signal.get("signal_type"),
                "entry_price": setup.get("entry"),
                "stop_loss": setup.get("stop"),
                "target_1": setup.get("t1") or setup.get("target"),
                "target_2": setup.get("t2") or setup.get("target"),
                "risk_reward": setup.get("rr_ratio"),
                "timeframe": "DAILY",
                "asset_class": "EQUITY",
                "status": "ACTIVE",
                "cta_zone": signal.get("cta_zone"),
                "notes": notes
            }
            
            # Calculate score using the new scoring algorithm
            score, bias_alignment, triggering_factors = calculate_signal_score(trade_signal, current_bias)
            
            # Add legacy bonus adjustments to triggering factors
            if score_bonuses:
                triggering_factors["legacy_bonuses"] = score_bonuses
            
            trade_signal["score"] = score
            trade_signal["bias_alignment"] = bias_alignment
            trade_signal["triggering_factors"] = triggering_factors
            
            # Determine confidence based on score
            if score >= 75:
                trade_signal["confidence"] = "HIGH"
            elif score >= 55:
                trade_signal["confidence"] = "MEDIUM"
            else:
                trade_signal["confidence"] = "LOW"
            
            # Log to PostgreSQL (permanent record)
            try:
                await log_signal(trade_signal)
                await update_signal_with_score(
                    trade_signal["signal_id"],
                    score,
                    bias_alignment,
                    triggering_factors
                )
            except Exception as db_err:
                logger.warning(f"Failed to log CTA signal to DB: {db_err}")
            
            # Cache in Redis (for quick access)
            await cache_signal(trade_signal["signal_id"], trade_signal, ttl=7200)  # 2 hour TTL

            try:
                from database.redis_client import get_redis_client
                client = await get_redis_client()
                if client:
                    await client.incr(f"signal:active:{ticker}")
                    await client.expire(f"signal:active:{ticker}", 7200)
            except Exception:
                pass

            # Record signal outcome tracking
            try:
                from database.postgres_client import get_postgres_client
                pool = await get_postgres_client()
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO signal_outcomes
                            (signal_id, symbol, signal_type, direction, cta_zone,
                             entry, stop, t1, t2, invalidation_level, created_at, outcome)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), 'PENDING')
                        ON CONFLICT (signal_id) DO NOTHING
                        """,
                        signal.get("signal_id"),
                        signal.get("symbol"),
                        signal.get("signal_type"),
                        signal.get("direction"),
                        signal.get("cta_zone"),
                        setup.get("entry"),
                        setup.get("stop"),
                        setup.get("t1"),
                        setup.get("t2"),
                        setup.get("invalidation_level"),
                    )
            except Exception as e:
                logger.warning(f"Failed to record signal outcome: {e}")
            
            # Broadcast to all connected devices (use smart broadcast for priority handling)
            await manager.broadcast_signal_smart(trade_signal, priority_threshold=75.0)
            pushed_count += 1
            
            logger.info(f"ðŸ“¡ CTA signal pushed: {ticker} {signal.get('signal_type')} (score: {score}, {bias_alignment})")
        
        # Update scheduler status
        _scheduler_status["cta_scanner"]["last_run"] = get_eastern_now().isoformat()
        _scheduler_status["cta_scanner"]["signals_found"] = len(all_signals)
        _scheduler_status["cta_scanner"]["status"] = "completed"
        
        logger.info(f"âœ… CTA scheduled scan complete - {pushed_count}/{len(all_signals)} signals pushed to Trade Ideas")
        
    except Exception as e:
        _scheduler_status["cta_scanner"]["status"] = f"error: {str(e)}"
        logger.error(f"Error in scheduled CTA scan: {e}")


async def trigger_cta_scan_now():
    """
    Manually trigger a CTA scan (called from API)
    """
    await run_cta_scan_scheduled()


async def check_bias_alignment_for_cta(direction: str) -> bool:
    """
    Check if current bias indicators align with signal direction
    Returns True if daily/weekly biases support the trade direction
    """
    try:
        bias_status = get_bias_status()
        
        # Map bias levels to numeric values
        daily_level = bias_status.get("daily", {}).get("level", "NEUTRAL")
        weekly_level = bias_status.get("weekly", {}).get("level", "NEUTRAL")
        
        daily_val = BIAS_LEVELS.get(daily_level.upper().replace("_", " "), 3)
        weekly_val = BIAS_LEVELS.get(weekly_level.upper().replace("_", " "), 3)
        
        if direction == "LONG":
            # LONG signals need bullish bias (>= 4)
            return daily_val >= 4 or weekly_val >= 4
        else:
            # SHORT signals need bearish bias (<= 2)
            return daily_val <= 2 or weekly_val <= 2
            
    except Exception as e:
        logger.warning(f"Error checking bias alignment: {e}")
        return False


async def check_flow_confirmation_for_cta(ticker: str, direction: str) -> bool:
    """
    Check if there's recent options flow supporting this trade
    Returns True if flow exists in the same direction within last 24 hours
    """
    try:
        # Try to get flow data from Redis
        from database.redis_client import get_redis_client
        import json
        
        client = await get_redis_client()
        
        # Check for recent UW flow alerts for this ticker
        flow_key = f"uw:flow:{ticker}"
        flow_data = await client.get(flow_key)
        
        if not flow_data:
            return False
        
        flow = json.loads(flow_data)
        flow_sentiment = flow.get("sentiment", "").upper()
        
        # Check if flow aligns with signal direction
        if direction == "LONG" and flow_sentiment == "BULLISH":
            return True
        elif direction == "SHORT" and flow_sentiment == "BEARISH":
            return True
        
        return False
        
    except Exception as e:
        logger.warning(f"Error checking flow confirmation: {e}")
        return False


# =========================================================================
# CRYPTO SCANNER SCHEDULED TASK (24/7)
# =========================================================================

# Top crypto tickers to scan
CRYPTO_TICKERS = [
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'ADA-USD', 
    'AVAX-USD', 'DOGE-USD', 'DOT-USD', 'LINK-USD', 'MATIC-USD',
    'LTC-USD', 'UNI-USD', 'ATOM-USD', 'NEAR-USD', 'APT-USD'
]

async def run_crypto_scan_scheduled():
    """
    Run crypto scanner 24/7 and push signals to Trade Ideas.
    Scheduled: Every 30 minutes around the clock.
    
    Uses Hunter Scanner logic but focused on crypto tickers.
    """
    logger.info("ðŸª™ Running scheduled Crypto scan...")
    
    try:
        from scanners.cta_scanner import analyze_ticker_cta as analyze_single_ticker, CTA_SCANNER_AVAILABLE as SCANNER_AVAILABLE
        from websocket.broadcaster import manager
        from database.redis_client import cache_signal
        from database.postgres_client import log_signal, update_signal_with_score
        from scoring.trade_ideas_scorer import calculate_signal_score
        
        if not SCANNER_AVAILABLE:
            logger.warning("CTA Scanner not available for crypto scan")
            _scheduler_status["crypto_scanner"]["status"] = "unavailable"
            return
        
        # Get current bias for scoring
        bias_status = get_bias_status()
        current_bias = {
            "daily": bias_status.get("daily", {}),
            "weekly": bias_status.get("weekly", {}),
            "cyclical": bias_status.get("cyclical", {})
        }
        
        signals_found = 0
        
        for ticker in CRYPTO_TICKERS:
            try:
                # Analyze ticker
                result = await analyze_single_ticker(ticker)
                if not result or result.get("error"):
                    continue

                signals = result.get("signals", [])
                if not signals:
                    continue

                best_signal = max(signals, key=lambda s: s.get("priority", 0))
                cta_analysis = result.get("cta_analysis", {})

                direction = best_signal.get("direction", "LONG")
                signal_type = best_signal.get("signal_type", "CTA_SIGNAL")
                signal_id = f"{ticker}_{direction}_{get_eastern_now().strftime('%Y%m%d_%H%M%S')}"

                setup = best_signal.get("setup", {}) or {}
                trade_signal = {
                    "signal_id": signal_id,
                    "timestamp": get_eastern_now().isoformat(),
                    "ticker": ticker,
                    "strategy": "Crypto Scanner",
                    "direction": direction,
                    "signal_type": signal_type,
                    "entry_price": setup.get("entry") or cta_analysis.get("current_price"),
                    "stop_loss": setup.get("stop"),
                    "target_1": setup.get("t1") or setup.get("target"),
                    "target_2": setup.get("t2") or setup.get("target"),
                    "risk_reward": setup.get("rr_ratio"),
                    "timeframe": "DAILY",
                    "asset_class": "CRYPTO",
                    "status": "ACTIVE",
                    "cta_zone": cta_analysis.get("cta_zone"),
                    "confidence": best_signal.get("confidence", "MEDIUM"),
                }
                
                # Calculate score
                score, bias_alignment, triggering_factors = calculate_signal_score(trade_signal, current_bias)
                
                trade_signal["score"] = score
                trade_signal["bias_alignment"] = bias_alignment
                trade_signal["triggering_factors"] = triggering_factors
                
                # Set confidence
                if score >= 75:
                    trade_signal["confidence"] = "HIGH"
                elif score >= 55:
                    trade_signal["confidence"] = "MEDIUM"
                else:
                    trade_signal["confidence"] = "LOW"
                
                # Log to PostgreSQL
                try:
                    await log_signal(trade_signal)
                    await update_signal_with_score(signal_id, score, bias_alignment, triggering_factors)
                except Exception as db_err:
                    logger.warning(f"Failed to log crypto signal to DB: {db_err}")
                
                # Cache in Redis (longer TTL for crypto since it's 24/7)
                await cache_signal(signal_id, trade_signal, ttl=14400)  # 4 hour TTL
                
                # Broadcast
                await manager.broadcast_signal_smart(trade_signal, priority_threshold=75.0)
                
                logger.info(f"ðŸª™ Crypto signal: {ticker} {signal_type} (score: {score})")
                signals_found += 1
                
            except Exception as ticker_err:
                logger.warning(f"Error scanning {ticker}: {ticker_err}")
                continue
        
        # Update scheduler status
        _scheduler_status["crypto_scanner"]["last_run"] = get_eastern_now().isoformat()
        _scheduler_status["crypto_scanner"]["signals_found"] = signals_found
        _scheduler_status["crypto_scanner"]["status"] = "completed"
        
        logger.info(f"âœ… Crypto scan complete - {signals_found} signals found")
        
    except Exception as e:
        _scheduler_status["crypto_scanner"]["status"] = f"error: {str(e)}"
        logger.error(f"Error in crypto scan: {e}")
        import traceback
        traceback.print_exc()


async def trigger_crypto_scan_now():
    """Manually trigger a crypto scan"""
    await run_crypto_scan_scheduled()
