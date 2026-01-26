"""
Automated Bias Scheduler

Handles automatic refresh of all bias indicators:
- Daily Bias: Refreshes at 9:45 AM ET every trading day
- Weekly Bias: Refreshes at 9:45 AM ET every Monday
- Monthly Bias: Refreshes at 9:45 AM ET on first trading day of month

Stores historical values to show trends (vs previous period).
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

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


class BiasTimeframe(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class TrendDirection(str, Enum):
    IMPROVING = "IMPROVING"      # More bullish than previous
    DECLINING = "DECLINING"      # More bearish than previous
    STABLE = "STABLE"           # Same as previous
    NEW = "NEW"                 # No previous data


# Bias level numeric values for comparison
BIAS_LEVELS = {
    "TORO_MAJOR": 5,
    "TORO MAJOR": 5,
    "TORO_MINOR": 4,
    "TORO MINOR": 4,
    "NEUTRAL": 3,
    "URSA_MINOR": 2,
    "URSA MINOR": 2,
    "URSA_MAJOR": 1,
    "URSA MAJOR": 1,
}


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
        "monthly": {"current": None, "previous": None, "history": []},
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
                # Check if baseline is from this week (Monday or later)
                if baseline.get("timestamp"):
                    baseline_date = datetime.fromisoformat(baseline["timestamp"])
                    now = datetime.now()
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
        timeframe: DAILY, WEEKLY, or MONTHLY
        new_level: The new bias level (e.g., "TORO_MAJOR", "NEUTRAL", etc.)
        details: Additional details to store (data sources, components, etc.)
    
    Returns:
        Dict with current, previous, trend, and timestamp
    """
    history = _load_bias_history()
    tf_key = timeframe.value.lower()
    
    # Get current data (will become previous)
    current_data = history.get(tf_key, {}).get("current")
    
    # Create new current entry
    now = datetime.now()
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
        return f"↑ More bullish (was {previous})"
    elif trend == TrendDirection.DECLINING:
        return f"↓ More bearish (was {previous})"
    else:
        return f"→ Unchanged from {previous}"


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
            "previous_level": previous.get("level") if previous else None
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
    Refresh daily bias based on:
    - Technical aggregate sentiment (Hybrid Scanner)
    - Market indicators
    
    Scheduled: 9:45 AM ET every trading day
    """
    logger.info("📊 Refreshing Daily Bias...")
    
    try:
        # Import here to avoid circular imports
        from scanners.hybrid_scanner import get_aggregate_sentiment, refresh_technicals, is_cache_fresh
        
        # Refresh technical cache if needed
        if not is_cache_fresh():
            logger.info("Refreshing technical cache for daily bias...")
            await refresh_technicals()
        
        # Get aggregate sentiment
        aggregate = get_aggregate_sentiment()
        
        # Map aggregate sentiment to bias level
        sentiment = aggregate.get("sentiment", "NEUTRAL")
        
        bias_map = {
            "STRONG_BULLISH": "TORO_MAJOR",
            "BULLISH": "TORO_MINOR",
            "NEUTRAL": "NEUTRAL",
            "BEARISH": "URSA_MINOR",
            "STRONG_BEARISH": "URSA_MAJOR"
        }
        
        new_level = bias_map.get(sentiment, "NEUTRAL")
        
        # Update bias with trend tracking
        result = update_bias(
            BiasTimeframe.DAILY,
            new_level,
            details={
                "source": "hybrid_scanner_aggregate",
                "bullish_pct": aggregate.get("bullish_pct"),
                "bearish_pct": aggregate.get("bearish_pct"),
                "tickers_analyzed": aggregate.get("total_tickers"),
                "technical_refresh_time": aggregate.get("last_refresh")
            }
        )
        
        logger.info(f"✅ Daily Bias updated: {new_level} (trend: {result.get('trend')})")
        return result
        
    except Exception as e:
        logger.error(f"Error refreshing daily bias: {e}")
        return {"error": str(e)}


async def refresh_weekly_bias() -> Dict[str, Any]:
    """
    Refresh weekly bias based on 6-FACTOR analysis:
    1. Index Technicals (SPY, QQQ, IWM, DIA weekly signals)
    2. Dollar Smile (DXY + VIX macro regime)
    3. Sector Rotation (Offensive vs Defensive sectors)
    4. Credit Spreads (HYG vs TLT - risk appetite)
    5. Market Breadth (RSP vs SPY - participation)
    6. VIX Term Structure (VIX vs VIX3M - sentiment)
    
    Each factor votes: -2 to +2
    Final bias is aggregate of all votes.
    
    Runs daily at 9:45 AM ET. Monday's reading becomes the weekly baseline.
    Subsequent days are compared to Monday's baseline to detect shifts.
    """
    global _weekly_baseline
    
    logger.info("📊 Refreshing Weekly Bias (6-Factor Model)...")
    
    # Check if it's Monday or if no baseline exists
    now = datetime.now()
    is_monday = now.weekday() == 0
    baseline_exists = _weekly_baseline.get("timestamp") is not None
    
    # Load baseline if not already loaded (in case of restart)
    if not baseline_exists:
        _weekly_baseline = _load_weekly_baseline()
        baseline_exists = _weekly_baseline.get("timestamp") is not None
    
    # Update baseline if it's Monday or no baseline exists
    if is_monday or not baseline_exists:
        logger.info("  📌 Setting new weekly baseline (Monday or first run)")
    
    factor_votes = []  # List of (factor_name, vote, details)
    
    # ========== FACTOR 1: Index Technicals ==========
    try:
        from scanners.hybrid_scanner import get_scanner
        
        scanner = get_scanner()
        indices = ["SPY", "QQQ", "IWM", "DIA"]
        
        bullish_count = 0
        bearish_count = 0
        
        for ticker in indices:
            try:
                tech = scanner.get_technical_analysis(ticker, interval="1W")
                signal = tech.get("signal", "NEUTRAL")
                
                if signal in ["BUY", "STRONG_BUY"]:
                    bullish_count += 1
                elif signal in ["SELL", "STRONG_SELL"]:
                    bearish_count += 1
            except:
                pass
        
        # Vote based on index technicals
        if bullish_count >= 3:
            factor_votes.append(("index_technicals", 2, {"bullish": bullish_count, "bearish": bearish_count}))
        elif bullish_count >= 2:
            factor_votes.append(("index_technicals", 1, {"bullish": bullish_count, "bearish": bearish_count}))
        elif bearish_count >= 3:
            factor_votes.append(("index_technicals", -2, {"bullish": bullish_count, "bearish": bearish_count}))
        elif bearish_count >= 2:
            factor_votes.append(("index_technicals", -1, {"bullish": bullish_count, "bearish": bearish_count}))
        else:
            factor_votes.append(("index_technicals", 0, {"bullish": bullish_count, "bearish": bearish_count}))
            
        logger.info(f"  📈 Index Technicals: bullish={bullish_count}, bearish={bearish_count}")
        
    except Exception as e:
        logger.warning(f"Error in index technicals factor: {e}")
        factor_votes.append(("index_technicals", 0, {"error": str(e)}))
    
    # ========== FACTOR 2: Dollar Smile ==========
    try:
        from bias_filters.dollar_smile import auto_fetch_and_update as fetch_dollar_smile, get_bias_for_scoring
        
        await fetch_dollar_smile()
        dollar_smile = get_bias_for_scoring()
        ds_level = dollar_smile.get("bias_level", 3)
        
        # Convert 1-5 scale to vote: 5->+2, 4->+1, 3->0, 2->-1, 1->-2
        ds_vote = ds_level - 3
        factor_votes.append(("dollar_smile", ds_vote, {"bias_level": ds_level, "bias": dollar_smile.get("bias")}))
        
        logger.info(f"  💵 Dollar Smile: {dollar_smile.get('bias')} (level {ds_level})")
        
    except Exception as e:
        logger.warning(f"Error in dollar smile factor: {e}")
        factor_votes.append(("dollar_smile", 0, {"error": str(e)}))
    
    # ========== FACTOR 3: Sector Rotation ==========
    try:
        from bias_filters.sector_rotation import auto_fetch_and_update as fetch_sector_rotation, get_bias_for_scoring as get_sector_bias
        
        await fetch_sector_rotation()
        sector_rotation = get_sector_bias()
        sr_level = sector_rotation.get("bias_level", 3)
        
        # Convert 1-5 scale to vote
        sr_vote = sr_level - 3
        factor_votes.append(("sector_rotation", sr_vote, {"bias_level": sr_level, "bias": sector_rotation.get("bias")}))
        
        logger.info(f"  📊 Sector Rotation: {sector_rotation.get('bias')} (level {sr_level})")
        
    except Exception as e:
        logger.warning(f"Error in sector rotation factor: {e}")
        factor_votes.append(("sector_rotation", 0, {"error": str(e)}))
    
    # ========== FACTOR 4: Credit Spreads ==========
    try:
        from bias_filters.credit_spreads import auto_fetch_and_update as fetch_credit_spreads, get_bias_for_scoring as get_credit_bias
        
        await fetch_credit_spreads()
        credit_spreads = get_credit_bias()
        cs_level = credit_spreads.get("bias_level", 3)
        
        cs_vote = cs_level - 3
        factor_votes.append(("credit_spreads", cs_vote, {"bias_level": cs_level, "bias": credit_spreads.get("bias")}))
        
        logger.info(f"  💳 Credit Spreads: {credit_spreads.get('bias')} (level {cs_level})")
        
    except Exception as e:
        logger.warning(f"Error in credit spreads factor: {e}")
        factor_votes.append(("credit_spreads", 0, {"error": str(e)}))
    
    # ========== FACTOR 5: Market Breadth ==========
    try:
        from bias_filters.market_breadth import auto_fetch_and_update as fetch_market_breadth, get_bias_for_scoring as get_breadth_bias
        
        await fetch_market_breadth()
        market_breadth = get_breadth_bias()
        mb_level = market_breadth.get("bias_level", 3)
        
        mb_vote = mb_level - 3
        factor_votes.append(("market_breadth", mb_vote, {"bias_level": mb_level, "bias": market_breadth.get("bias")}))
        
        logger.info(f"  📊 Market Breadth: {market_breadth.get('bias')} (level {mb_level})")
        
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
        
        logger.info(f"  📉 VIX Term Structure: {vix_term.get('bias')} (level {vt_level})")
        
    except Exception as e:
        logger.warning(f"Error in VIX term structure factor: {e}")
        factor_votes.append(("vix_term_structure", 0, {"error": str(e)}))
    
    # ========== AGGREGATE VOTES ==========
    total_vote = sum(v[1] for v in factor_votes)
    max_possible = len(factor_votes) * 2  # Each factor can vote -2 to +2
    
    # Map total vote to bias level
    # Range: -12 to +12 for 6 factors
    # Thresholds adjusted for 6 factors
    if total_vote >= 6:
        new_level = "TORO_MAJOR"
    elif total_vote >= 3:
        new_level = "TORO_MINOR"
    elif total_vote <= -6:
        new_level = "URSA_MAJOR"
    elif total_vote <= -3:
        new_level = "URSA_MINOR"
    else:
        new_level = "NEUTRAL"
    
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
        logger.info(f"  ✅ Weekly baseline set: {new_level} (vote: {total_vote})")
    
    # Calculate shift status compared to baseline (only on non-Monday days with existing baseline)
    shift_info = None
    if baseline_exists and not is_monday:
        baseline_vote = _weekly_baseline.get("total_vote", 0)
        shift_info = calculate_shift_status(baseline_vote, total_vote)
        logger.info(f"  📊 Shift vs baseline: {shift_info['status']} (delta: {shift_info['delta']})")
    
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
                    "message": f"Weekly bias shift detected: {baseline_level} → {new_level}",
                    "baseline_vote": _weekly_baseline.get("total_vote"),
                    "current_vote": total_vote,
                    "delta": shift_info["delta"],
                    "shift_status": shift_info["status"],
                    "baseline_level": baseline_level,
                    "current_level": new_level
                }
                await manager.broadcast({"type": "bias_alert", "data": alert})
                logger.info(f"  🚨 Alert broadcast: {shift_info['status']}")
            except Exception as e:
                logger.warning(f"Error broadcasting shift alert: {e}")
    
    logger.info(f"✅ Weekly Bias updated: {new_level} (total vote: {total_vote}/{max_possible})")
    return result


async def refresh_monthly_bias() -> Dict[str, Any]:
    """
    Refresh monthly bias based on:
    - Monthly technical signals
    - Macro indicators
    
    Scheduled: 9:45 AM ET on first trading day of month
    """
    logger.info("📊 Refreshing Monthly Bias...")
    
    try:
        from scanners.hybrid_scanner import get_scanner
        
        # Get monthly technical analysis for key indices
        scanner = get_scanner()
        indices = ["SPY", "QQQ", "IWM"]
        
        bullish_count = 0
        bearish_count = 0
        
        for ticker in indices:
            try:
                # Use monthly interval
                tech = scanner.get_technical_analysis(ticker, interval="1M")
                signal = tech.get("signal", "NEUTRAL")
                
                if signal in ["BUY", "STRONG_BUY"]:
                    bullish_count += 1
                elif signal in ["SELL", "STRONG_SELL"]:
                    bearish_count += 1
            except:
                pass
        
        # Determine monthly bias
        if bullish_count >= 2:
            new_level = "TORO_MAJOR" if bullish_count == 3 else "TORO_MINOR"
        elif bearish_count >= 2:
            new_level = "URSA_MAJOR" if bearish_count == 3 else "URSA_MINOR"
        else:
            new_level = "NEUTRAL"
        
        result = update_bias(
            BiasTimeframe.MONTHLY,
            new_level,
            details={
                "source": "monthly_index_technicals",
                "bullish_indices": bullish_count,
                "bearish_indices": bearish_count,
                "indices_checked": indices
            }
        )
        
        logger.info(f"✅ Monthly Bias updated: {new_level} (trend: {result.get('trend')})")
        return result
        
    except Exception as e:
        logger.error(f"Error refreshing monthly bias: {e}")
        return {"error": str(e)}


# =========================================================================
# SCHEDULER SETUP
# =========================================================================

_scheduler_started = False

def is_trading_day() -> bool:
    """Check if today is a trading day (Mon-Fri, not a holiday)"""
    today = datetime.now()
    # Simple check: Monday=0 through Friday=4
    return today.weekday() < 5


def is_first_trading_day_of_month() -> bool:
    """Check if today is the first trading day of the month"""
    today = datetime.now()
    
    # Find first weekday of month
    first_day = today.replace(day=1)
    while first_day.weekday() >= 5:  # Saturday or Sunday
        first_day += timedelta(days=1)
    
    return today.date() == first_day.date()


async def run_scheduled_refreshes():
    """
    Run appropriate refreshes based on current time/day
    Called by the scheduler at 9:45 AM ET
    """
    now = datetime.now()
    logger.info(f"⏰ Running scheduled bias refresh at {now}")
    
    if not is_trading_day():
        logger.info("Not a trading day, skipping refresh")
        return
    
    # Always refresh daily
    await refresh_daily_bias()
    
    # Always refresh weekly (runs daily, Monday sets baseline)
    await refresh_weekly_bias()
    
    # First trading day of month = refresh monthly
    if is_first_trading_day_of_month():
        await refresh_monthly_bias()


async def start_scheduler():
    """Start the background scheduler"""
    global _scheduler_started, _weekly_baseline
    
    if _scheduler_started:
        logger.info("Scheduler already running")
        return
    
    _scheduler_started = True
    logger.info("🚀 Starting bias scheduler...")
    
    # Load weekly baseline from disk
    _weekly_baseline = _load_weekly_baseline()
    if _weekly_baseline.get("timestamp"):
        logger.info(f"  📌 Loaded weekly baseline: {_weekly_baseline.get('level')} (from {_weekly_baseline.get('timestamp')})")
    else:
        logger.info("  📌 No weekly baseline found - will be set on next Monday")
    
    # Use APScheduler if available, otherwise use simple asyncio loop
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        scheduler = AsyncIOScheduler()
        
        # Daily refresh at 9:45 AM ET (Mon-Fri)
        scheduler.add_job(
            run_scheduled_refreshes,
            CronTrigger(hour=9, minute=45, day_of_week='mon-fri'),
            id='bias_refresh',
            name='Daily Bias Refresh',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("✅ APScheduler started - bias refresh scheduled for 9:45 AM ET")
        
    except ImportError:
        logger.warning("APScheduler not installed, using fallback scheduler")
        # Fallback: Simple asyncio-based scheduler
        asyncio.create_task(_fallback_scheduler())


async def _fallback_scheduler():
    """Fallback scheduler using asyncio (runs in background)"""
    logger.info("Starting fallback scheduler loop")
    
    last_cta_scan_hour = -1
    
    while True:
        now = datetime.now()
        
        # Check if it's 9:45 AM (within 1 minute window) - bias refresh
        if now.hour == 9 and 45 <= now.minute < 46:
            await run_scheduled_refreshes()
            # Wait 2 minutes to avoid duplicate runs
            await asyncio.sleep(120)
        
        # CTA scan: Run every hour during market hours (9:30 AM - 4:00 PM ET)
        elif is_trading_day() and 9 <= now.hour <= 16 and now.hour != last_cta_scan_hour:
            last_cta_scan_hour = now.hour
            await run_cta_scan_scheduled()
            await asyncio.sleep(60)
        else:
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
    logger.info("🎯 Running scheduled CTA scan...")
    
    try:
        from scanners.cta_scanner import run_cta_scan, CTA_SCANNER_AVAILABLE
        from websocket.broadcaster import manager
        from database.redis_client import cache_signal
        
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
        
        # Load watchlist for bonus scoring
        from scanners.cta_scanner import load_watchlist
        watchlist = load_watchlist()
        
        # Get current bias status for alignment check
        bias_status = get_bias_status()
        
        # Push each signal to Trade Ideas via WebSocket
        for signal in all_signals[:10]:  # Limit to top 10
            ticker = signal.get("symbol")
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
            trade_signal = {
                "signal_id": signal.get("signal_id"),
                "timestamp": signal.get("timestamp"),
                "ticker": ticker,
                "strategy": "CTA Scanner",
                "direction": signal.get("direction", "LONG"),
                "signal_type": signal.get("signal_type"),
                "entry_price": signal.get("setup", {}).get("entry"),
                "stop_loss": signal.get("setup", {}).get("stop"),
                "target_1": signal.get("setup", {}).get("target"),
                "risk_reward": signal.get("setup", {}).get("rr_ratio"),
                "timeframe": "DAILY",
                "asset_class": "EQUITY",
                "status": "ACTIVE",
                "score": base_score,
                "confidence": confidence,
                "notes": notes
            }
            
            # Cache in Redis
            await cache_signal(trade_signal["signal_id"], trade_signal, ttl=3600)
            
            # Broadcast to all connected devices
            await manager.broadcast_signal(trade_signal)
            
            logger.info(f"📡 CTA signal pushed: {ticker} {signal.get('signal_type')} (score: {base_score})")
        
        logger.info(f"✅ CTA scheduled scan complete - {len(all_signals)} signals pushed to Trade Ideas")
        
    except Exception as e:
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
        
        # Check for recent flow alerts for this ticker
        flow_key = f"flow:ticker:{ticker}"
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
