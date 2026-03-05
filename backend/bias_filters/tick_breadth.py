"""
TICK Range Breadth Model Bias Filter
Based on Linda Raschke's method using NYSE TICK ($TICK) data

Data comes from TradingView webhook alerts.
Target: <5ms execution time
"""

import json
import logging
from typing import Tuple, Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta

from bias_engine.composite import FactorReading
from bias_engine.factor_utils import score_to_signal

logger = logging.getLogger(__name__)

# Redis keys for TICK data
REDIS_KEY_TICK_CURRENT = "tick:current"
REDIS_KEY_TICK_HISTORY = "tick:history"
REDIS_TTL_SECONDS = 86400 * 7  # 7 days


async def store_tick_data(
    tick_high: float,
    tick_low: float,
    date: Optional[str] = None,
    tick_close: Optional[float] = None,
    tick_avg: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Store TICK high/low data from TradingView webhook
    
    Args:
        tick_high: Daily TICK high value (typically +500 to +1500)
        tick_low: Daily TICK low value (typically -500 to -1500)
        date: Optional date string (defaults to today)
    
    Returns:
        Dict with stored data and calculated bias
    """
    try:
        from database.redis_client import get_redis_client
        
        redis = await get_redis_client()
        if not redis:
            return {"error": "Redis not available"}
        
        # Use provided date or today
        if date:
            data_date = date
        else:
            data_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Calculate daily bias
        daily_bias = await calculate_daily_bias(tick_high, tick_low)
        
        # Store current TICK data
        current_data = {
            "tick_high": tick_high,
            "tick_low": tick_low,
            "tick_close": tick_close,
            "tick_avg": tick_avg,
            "date": data_date,
            "daily_bias": daily_bias,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await redis.setex(
            REDIS_KEY_TICK_CURRENT,
            REDIS_TTL_SECONDS,
            json.dumps(current_data)
        )
        
        # Add to history (keep last 10 days)
        history_raw = await redis.get(REDIS_KEY_TICK_HISTORY)
        history = json.loads(history_raw) if history_raw else []
        
        # Remove existing entry for same date
        history = [h for h in history if h.get("date") != data_date]
        
        # Add new entry
        history.append({
            "tick_high": tick_high,
            "tick_low": tick_low,
            "date": data_date
        })
        
        # Keep only last 10 days
        history = sorted(history, key=lambda x: x["date"])[-10:]
        
        await redis.setex(
            REDIS_KEY_TICK_HISTORY,
            REDIS_TTL_SECONDS,
            json.dumps(history)
        )
        
        # Calculate weekly + composite bias
        weekly_bias = await calculate_weekly_bias(history)
        composite_bias = await calculate_composite_bias(tick_high, tick_low, history)
        
        logger.info(f"TICK data stored: high={tick_high}, low={tick_low}, daily={daily_bias}, weekly={weekly_bias}")
        
        return {
            "status": "success",
            "tick_high": tick_high,
            "tick_low": tick_low,
            "tick_close": tick_close,
            "tick_avg": tick_avg,
            "date": data_date,
            "daily_bias": daily_bias,
            "weekly_bias": weekly_bias,
            "composite_bias": composite_bias,
            "history_days": len(history)
        }
        
    except Exception as e:
        logger.error(f"Error storing TICK data: {e}")
        return {"error": str(e)}


async def get_tick_status() -> Dict[str, Any]:
    """
    Get current TICK status and bias
    
    Returns:
        Dict with current TICK data, daily/weekly bias
    """
    try:
        from database.redis_client import get_redis_client
        
        redis = await get_redis_client()
        if not redis:
            return {"error": "Redis not available", "daily_bias": "NEUTRAL", "weekly_bias": "NEUTRAL"}
        
        # Get current data
        current_raw = await redis.get(REDIS_KEY_TICK_CURRENT)
        current = json.loads(current_raw) if current_raw else None
        
        # Get history
        history_raw = await redis.get(REDIS_KEY_TICK_HISTORY)
        history = json.loads(history_raw) if history_raw else []
        
        if not current:
            return {
                "status": "no_data",
                "message": "No TICK data available. Send from TradingView webhook.",
                "daily_bias": "NEUTRAL",
                "weekly_bias": "NEUTRAL",
                "history_days": len(history)
            }
        
        # Recalculate biases
        daily_bias = await calculate_daily_bias(current["tick_high"], current["tick_low"])
        weekly_bias = await calculate_weekly_bias(history)
        composite_bias = await calculate_composite_bias(current["tick_high"], current["tick_low"], history)
        
        return {
            "status": "ok",
            "tick_high": current["tick_high"],
            "tick_low": current["tick_low"],
            "tick_close": current.get("tick_close"),
            "tick_avg": current.get("tick_avg"),
            "date": current["date"],
            "daily_bias": daily_bias,
            "weekly_bias": weekly_bias,
            "composite_bias": composite_bias,
            "updated_at": current.get("updated_at"),
            "history_days": len(history),
            "history": history[-5:]  # Last 5 days
        }
        
    except Exception as e:
        logger.error(f"Error getting TICK status: {e}")
        return {"error": str(e), "daily_bias": "NEUTRAL", "weekly_bias": "NEUTRAL"}


async def check_bias_alignment(direction: str, timeframe: str = "DAILY") -> Tuple[str, bool]:
    """
    Check if signal direction aligns with current TICK-based bias
    
    Args:
        direction: "LONG" or "SHORT"
        timeframe: "DAILY" or "WEEKLY"
    
    Returns:
        (bias_level, is_aligned): Current bias and whether signal aligns
    """
    
    # Get current TICK status
    tick_status = await get_tick_status()
    
    if tick_status.get("status") != "ok":
        return "NEUTRAL", False
    
    # Get bias for requested timeframe
    if timeframe.upper() == "WEEKLY":
        bias_level = tick_status.get("weekly_bias", "NEUTRAL")
    else:
        bias_level = tick_status.get("daily_bias", "NEUTRAL")
    
    # Determine alignment
    is_aligned = False
    
    if direction == "LONG":
        # Long signals align with bullish bias (wide TICK range)
        if bias_level in ["TORO_MINOR", "TORO_MAJOR"]:
            is_aligned = True
    
    elif direction == "SHORT":
        # Short signals align with bearish bias (narrow TICK range)
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

async def calculate_daily_bias(tick_high: float, tick_low: float) -> str:
    """
    Calculate daily bias based on TICK range width.
    Uses the same graduated scoring as compute_tick_score for consistency (C2, M13).

    Wide range = Bullish breadth (strong participation)
    Narrow range = Bearish breadth (weak participation)
    """
    tick_range = tick_high - tick_low

    # Graduated classification matching compute_tick_score thresholds
    if tick_range >= 2000:
        return "TORO_MAJOR_DAILY"  # Very wide — strong daily bullish breadth
    elif tick_range >= 1500:
        return "TORO_MINOR"  # Wide — bullish breadth
    elif tick_range >= 700:
        return "NEUTRAL"  # Normal range
    elif tick_range >= 400:
        return "URSA_MINOR"  # Narrow — bearish breadth
    else:
        return "URSA_MAJOR_DAILY"  # Very narrow — strong daily bearish breadth

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


async def calculate_composite_bias(tick_high: float, tick_low: float, tick_history: list) -> str:
    """
    Full 5-level bias mapping per approved spec.
    Combines daily + weekly signals into final bias level.

    TORO_MAJOR: 4+ wide days in past week AND current day wide range
    TORO_MINOR: 3 wide days OR bullish daily but mixed weekly
    NEUTRAL: Mixed signals or mid-range TICK
    URSA_MINOR: 3 narrow days OR bearish daily but mixed weekly
    URSA_MAJOR: 4+ narrow days in past week AND current day narrow range
    """
    daily = await calculate_daily_bias(tick_high, tick_low)
    weekly = await calculate_weekly_bias(tick_history)

    # TORO_MAJOR: weekly strongly bullish AND daily confirms
    if weekly == "TORO_MAJOR" and daily in ("TORO_MAJOR_DAILY", "TORO_MINOR"):
        return "TORO_MAJOR"

    # URSA_MAJOR: weekly strongly bearish AND daily confirms
    if weekly == "URSA_MAJOR" and daily in ("URSA_MAJOR_DAILY", "URSA_MINOR"):
        return "URSA_MAJOR"

    # TORO_MINOR: weekly bullish OR daily bullish with mixed weekly
    if weekly in ("TORO_MAJOR", "TORO_MINOR") or daily in ("TORO_MAJOR_DAILY", "TORO_MINOR"):
        return "TORO_MINOR"

    # URSA_MINOR: weekly bearish OR daily bearish with mixed weekly
    if weekly in ("URSA_MAJOR", "URSA_MINOR") or daily in ("URSA_MAJOR_DAILY", "URSA_MINOR"):
        return "URSA_MINOR"

    return "NEUTRAL"


async def compute_tick_score(tick_data: Dict[str, Any]) -> Optional[FactorReading]:
    """
    Score based on TICK readings received from TradingView.
    tick_data should contain:
      - tick_high: highest TICK reading in session
      - tick_low: lowest TICK reading in session
      - tick_close: latest TICK value
      - tick_avg: session average TICK
    """
    if not tick_data:
        return None

    tick_high = float(tick_data.get("tick_high", 0) or 0)
    tick_low = float(tick_data.get("tick_low", 0) or 0)
    tick_close = float(tick_data.get("tick_close", 0) or 0)
    tick_avg = float(tick_data.get("tick_avg", tick_close) or 0)

    # --- Breadth scoring (range width, NOT direction) ---
    # Wide range = bullish breadth (strong participation) → positive score
    # Narrow range = bearish breadth (weak participation) → negative score
    tick_range = tick_high - tick_low

    # Graduated scoring based on range width (M10, M11)
    # Typical ranges: narrow < 1000, normal 1000-2000, wide > 2000
    if tick_range >= 2500:
        base = 1.0   # Extremely wide — very strong participation
    elif tick_range >= 2000:
        base = 0.8   # Wide range — strong participation
    elif tick_range >= 1500:
        base = 0.5   # Above-average range — moderate bullish breadth
    elif tick_range >= 1000:
        base = 0.2   # Normal range — slight bullish lean
    elif tick_range >= 700:
        base = 0.0   # Neutral zone
    elif tick_range >= 500:
        base = -0.3  # Below-average — slight bearish breadth
    elif tick_range >= 300:
        base = -0.6  # Narrow range — weak participation
    else:
        base = -0.9  # Very narrow — extremely weak participation

    # Extreme modifier: bonus for reaching beyond ±1000 thresholds
    # Per spec: wide = high > +1000 OR low < -1000
    extreme_mod = 0.0
    if tick_high > 1000:
        extreme_mod += 0.1
    if tick_low < -1000:
        extreme_mod += 0.1  # ALSO bullish — wide range = participation

    score = max(-1.0, min(1.0, base + extreme_mod))

    # ── DIRECTIONAL MODIFIER ──────────────────────────────────────
    # Range width alone is insufficient. TICK close and average tell you
    # whether the participation was buying or selling.
    # Wide range + negative close = heavy selling (bearish), not bullish.
    # Wide range + positive close = real bullish breadth.
    dir_mod = 0.0
    if tick_close < -400:
        dir_mod = -0.8  # Heavy selling pressure
    elif tick_close < -200:
        dir_mod = -0.5  # Moderate selling
    elif tick_close < -50:
        dir_mod = -0.2  # Slight selling lean
    elif tick_close > 400:
        dir_mod = 0.4   # Strong buying pressure
    elif tick_close > 200:
        dir_mod = 0.2   # Moderate buying
    elif tick_close > 50:
        dir_mod = 0.1   # Slight buying lean

    # Average TICK confirms sustained direction (not just a spike)
    if tick_avg < -100 and dir_mod < 0:
        dir_mod -= 0.15  # Sustained selling — amplify bearish
    elif tick_avg > 100 and dir_mod > 0:
        dir_mod += 0.1   # Sustained buying — amplify bullish

    # Blend: range-based score gets 40% weight, directional gets 60%
    # This ensures a wide-range selloff reads bearish, not bullish
    score = (score * 0.4) + (dir_mod * 0.6)

    # VIX context adjustment (M7)
    # During high VIX (>25), wide TICK is less meaningful — everyone is moving
    # During low VIX (<15), wide TICK is MORE meaningful — real conviction
    vix_val = float(tick_data.get("vix", 0) or 0)
    if vix_val > 25 and score > 0:
        score *= 0.7  # Discount bullish breadth during high vol
    elif vix_val < 15 and score > 0:
        score = min(1.0, score * 1.2)  # Amplify bullish breadth during low vol
    score = max(-1.0, min(1.0, round(score, 4)))

    source_timestamp, timestamp_source = _extract_source_timestamp(tick_data)
    if timestamp_source == "fallback":
        logger.warning(
            "No source timestamp for tick_breadth; using utcnow fallback (staleness reliability reduced)"
        )

    return FactorReading(
        factor_id="tick_breadth",
        score=score,
        signal=score_to_signal(score),
        detail=f"TICK avg: {tick_avg:+.0f}, range: [{tick_low:.0f}, {tick_high:.0f}], close: {tick_close:+.0f}",
        timestamp=source_timestamp,
        source="tradingview",
        raw_data=tick_data,
        metadata={"timestamp_source": timestamp_source},
    )


async def compute_score(tick_data: Optional[Dict[str, Any]] = None) -> Optional[FactorReading]:
    """
    Compute score from provided tick_data or latest stored values.
    """
    if tick_data is None:
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if not redis:
                return None
            current_raw = await redis.get(REDIS_KEY_TICK_CURRENT)
            tick_data = json.loads(current_raw) if current_raw else None
        except Exception as e:
            logger.warning(f"Error loading tick data for scoring: {e}")
            return None

    return await compute_tick_score(tick_data or {})


def _extract_source_timestamp(payload: Dict[str, Any]) -> tuple[datetime, str]:
    for key in ("updated_at", "timestamp", "received_at"):
        raw = payload.get(key)
        if not raw:
            continue
        parsed = _parse_timestamp(raw)
        if parsed is not None:
            return parsed, key
    return datetime.now(timezone.utc).replace(tzinfo=None), "fallback"


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            return None
    return None
