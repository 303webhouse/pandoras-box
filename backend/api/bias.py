"""
Bias Indicators API
Provides endpoints for all macro bias filters including:
- Savita Indicator (BofA Sell Side)
- TICK Breadth (intraday)
- Future: VIX, Put/Call Ratio, etc.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

# Import bias filters
try:
    from bias_filters.savita_indicator import (
        get_savita_reading,
        update_savita_reading,
        set_savita_enabled,
        get_savita_config,
        check_savita_bias
    )
    SAVITA_AVAILABLE = True
except ImportError:
    SAVITA_AVAILABLE = False
    logger.warning("Savita indicator module not available")

# Import composite bias engine
try:
    from bias_engine.composite import (
        FACTOR_CONFIG,
        compute_composite,
        record_factor_reading,
        get_cached_composite,
        set_override,
        clear_override,
        score_to_bias
    )
    from database.redis_client import get_redis_client, sanitize_for_json
    COMPOSITE_AVAILABLE = True
except ImportError as e:
    COMPOSITE_AVAILABLE = False
    logger.warning(f"Composite bias engine not available: {e}")

from backend.utils.pivot_auth import verify_pivot_key


class SavitaUpdate(BaseModel):
    """Request model for updating Savita reading"""
    reading: float  # The new reading (e.g., 55.9)
    date: Optional[str] = None  # Optional date string


class BiasCheckRequest(BaseModel):
    """Request model for checking bias confluence"""
    direction: str  # "LONG" or "SHORT"


# ====================
# SAVITA INDICATOR
# ====================

@router.get("/bias/savita")
async def get_savita():
    """
    Get the current Savita Indicator reading
    
    The Savita Indicator measures Wall Street strategists' average recommended
    equity allocation. It's a CONTRARIAN indicator:
    - High readings (>57.7%): Crowd too bullish = BEARISH signal
    - Low readings (<51.3%): Crowd too bearish = BULLISH signal
    
    Updated monthly by Bank of America.
    """
    if not SAVITA_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Savita indicator module not loaded"
        }
    
    return {
        "status": "success",
        **get_savita_reading()
    }


@router.put("/bias/savita")
async def update_savita(update: SavitaUpdate):
    """
    Update the Savita Indicator with a new reading from BofA monthly report
    
    Example:
    {
        "reading": 56.2,
        "date": "2026-02-01"
    }
    """
    if not SAVITA_AVAILABLE:
        raise HTTPException(status_code=503, detail="Savita indicator not available")
    
    try:
        result = update_savita_reading(update.reading, update.date)
        logger.info(f"Savita updated to {update.reading}%")
        return {
            "status": "success",
            "message": f"Savita Indicator updated to {update.reading}%",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bias/savita/check")
async def check_savita_direction(request: BiasCheckRequest):
    """
    Check if a trade direction aligns with Savita sentiment
    
    Request:
    {
        "direction": "LONG" or "SHORT"
    }
    
    Response includes whether the direction has sentiment confluence
    """
    if not SAVITA_AVAILABLE:
        raise HTTPException(status_code=503, detail="Savita indicator not available")
    
    direction = request.direction.upper()
    if direction not in ["LONG", "SHORT"]:
        raise HTTPException(status_code=400, detail="Direction must be LONG or SHORT")
    
    result = check_savita_bias(direction)
    return {
        "status": "success",
        "direction": direction,
        **result
    }


@router.post("/bias/savita/enable")
async def enable_savita(enabled: bool = True):
    """Enable or disable the Savita indicator filter"""
    if not SAVITA_AVAILABLE:
        raise HTTPException(status_code=503, detail="Savita indicator not available")
    
    set_savita_enabled(enabled)
    return {
        "status": "success",
        "savita_enabled": enabled
    }


@router.get("/bias/savita/config")
async def get_savita_configuration():
    """Get full Savita indicator configuration including thresholds"""
    if not SAVITA_AVAILABLE:
        return {"status": "unavailable"}
    
    return {
        "status": "success",
        **get_savita_config()
    }


# ====================
# TICK RANGE BREADTH
# ====================

@router.get("/bias/tick")
async def get_tick_bias():
    """
    Get current TICK Range Breadth indicator status
    
    TICK data comes from TradingView webhook to /webhook/tick
    
    Returns:
        - tick_high: Daily TICK high
        - tick_low: Daily TICK low  
        - daily_bias: TORO/URSA based on today's range
        - weekly_bias: TORO/URSA based on last 5 days
        - history: Recent TICK values
    """
    try:
        from bias_filters.tick_breadth import get_tick_status
        return await get_tick_status()
    except Exception as e:
        logger.error(f"Error getting TICK status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bias/tick/alignment/{direction}")
async def check_tick_alignment(direction: str, timeframe: str = "DAILY"):
    """
    Check if a trade direction aligns with TICK bias
    
    Args:
        direction: LONG or SHORT
        timeframe: DAILY or WEEKLY
    
    Returns:
        - bias: Current TICK bias
        - aligned: Whether direction aligns
    """
    try:
        from bias_filters.tick_breadth import check_bias_alignment
        
        direction = direction.upper()
        if direction not in ["LONG", "SHORT"]:
            raise HTTPException(status_code=400, detail="Direction must be LONG or SHORT")
        
        bias, aligned = await check_bias_alignment(direction, timeframe)
        
        return {
            "direction": direction,
            "timeframe": timeframe,
            "tick_bias": bias,
            "aligned": aligned,
            "recommendation": "PROCEED" if aligned else "CAUTION"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking TICK alignment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ====================
# ALL BIAS SUMMARY
# ====================

@router.get("/bias/summary")
async def get_all_bias_indicators():
    """
    Get a summary of all active bias indicators
    
    Returns:
    - Savita (monthly sentiment)
    - Future: TICK, VIX, Put/Call, etc.
    """
    summary = {
        "status": "success",
        "indicators": {}
    }
    
    # Savita
    if SAVITA_AVAILABLE:
        savita = get_savita_reading()
        summary["indicators"]["savita"] = {
            "name": "Savita (BofA Sell Side)",
            "timeframe": "MONTHLY",
            "reading": savita["reading"],
            "bias": savita["bias"],
            "signal": savita["signal"],
            "interpretation": savita["interpretation"],
            "last_updated": savita["last_updated"]
        }
    
    composite = None
    if COMPOSITE_AVAILABLE:
        composite = await get_cached_composite()
        if not composite:
            composite = await compute_composite()
        summary["composite"] = composite.model_dump(mode="json")
        summary["composite_score"] = round(composite.composite_score, 3)
        summary["composite_bias"] = composite.bias_level
        summary["factors_reporting"] = len(composite.active_factors)
        summary["factors_total"] = len(FACTOR_CONFIG)

    if composite:
        summary["overall_macro_bias"] = composite.bias_level
    else:
        biases = [ind.get("bias") for ind in summary["indicators"].values() if ind.get("bias")]

        if biases:
            bullish_count = sum(1 for b in biases if "TORO" in b)
            bearish_count = sum(1 for b in biases if "URSA" in b)

            if bullish_count > bearish_count:
                summary["overall_macro_bias"] = "TORO" if bullish_count > 1 else "TORO_MINOR"
            elif bearish_count > bullish_count:
                summary["overall_macro_bias"] = "URSA" if bearish_count > 1 else "URSA_MINOR"
            else:
                summary["overall_macro_bias"] = "NEUTRAL"
        else:
            summary["overall_macro_bias"] = "UNKNOWN"

    summary["pivot_status"] = await _get_pivot_status()
    
    return summary

# ====================
# COMPOSITE BIAS ENGINE
# ====================

VALID_BIAS_LEVELS = {
    "URSA_MAJOR",
    "URSA_MINOR",
    "NEUTRAL",
    "TORO_MINOR",
    "TORO_MAJOR"
}

REDIS_PIVOT_HEALTH_KEY = "pivot:last_heartbeat"
REDIS_PIVOT_HEALTH_LEGACY_KEY = "bias:pivot:health"
REDIS_PIVOT_HEALTH_TTL = 86400


class FactorUpdateRequest(BaseModel):
    """Request model for updating a factor reading"""
    factor_id: str
    score: float
    signal: Optional[str] = "NEUTRAL"
    detail: Optional[str] = ""
    source: Optional[str] = "unknown"
    raw_data: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


class BiasOverrideRequest(BaseModel):
    """Request model for manual bias override"""
    level: str
    reason: Optional[str] = None
    expires_hours: Optional[int] = None


class PivotHealthRequest(BaseModel):
    """Request model for pivot health heartbeat"""
    agent: Optional[str] = "pivot"
    timestamp: Optional[datetime] = None
    status: Optional[str] = "ok"
    factors_collected: Optional[int] = None


class PivotFactorUpdate(BaseModel):
    """Request model for Pivot factor updates"""
    score: float
    bias: Optional[str] = None
    signal: Optional[str] = None
    detail: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    scoring_details: Optional[Dict[str, Any]] = None
    collected_at: Optional[datetime] = None
    stale_after_hours: Optional[int] = None
    source: Optional[str] = "pivot"


@router.get("/bias/composite")
async def get_composite_bias():
    """Get the latest composite bias reading with factor breakdown"""
    if not COMPOSITE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Composite bias engine not available")

    result = await get_cached_composite()
    if not result:
        result = await compute_composite()

    return result.model_dump(mode="json")


@router.post("/bias/factors/{factor_name}")
async def update_factor_from_pivot(
    factor_name: str,
    payload: PivotFactorUpdate,
    _: str = Depends(verify_pivot_key)
):
    """Store a new factor reading from Pivot and recompute composite bias."""
    if not COMPOSITE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Composite bias engine not available")

    factor_id = factor_name.strip().lower()
    if factor_id not in FACTOR_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown factor_name: {factor_id}")

    score = float(payload.score)
    if score < -1.0 or score > 1.0:
        raise HTTPException(status_code=400, detail="Score must be between -1.0 and 1.0")

    signal = (payload.bias or payload.signal or score_to_bias(score)[0]).upper()
    collected_at = payload.collected_at or datetime.utcnow()

    raw_data: Dict[str, Any] = {}
    if payload.data is not None:
        raw_data["data"] = payload.data
    if payload.scoring_details is not None:
        raw_data["scoring_details"] = payload.scoring_details

    record_payload = {
        "factor_id": factor_id,
        "score": score,
        "signal": signal,
        "detail": payload.detail or "",
        "source": payload.source or "pivot",
        "raw_data": raw_data,
        "timestamp": collected_at,
    }

    await record_factor_reading(record_payload)
    await _log_factor_history(
        factor_id=factor_id,
        score=score,
        bias=signal,
        data=raw_data,
        collected_at=collected_at,
    )

    result = await compute_composite()
    return result.model_dump(mode="json")


@router.post("/bias/factor-update")
async def update_factor_reading(update: FactorUpdateRequest):
    """Store a new factor reading and recompute composite bias"""
    if not COMPOSITE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Composite bias engine not available")

    factor_id = update.factor_id.strip().lower()
    if factor_id not in FACTOR_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown factor_id: {factor_id}")

    if update.score < -1.0 or update.score > 1.0:
        raise HTTPException(status_code=400, detail="Score must be between -1.0 and 1.0")

    payload = update.model_dump(exclude_none=True)
    payload["factor_id"] = factor_id

    await record_factor_reading(payload)
    result = await compute_composite()

    return result.model_dump(mode="json")


@router.post("/bias/override")
async def set_bias_override(request: BiasOverrideRequest):
    """Manually override composite bias"""
    if not COMPOSITE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Composite bias engine not available")

    level = request.level.strip().upper()
    if level not in VALID_BIAS_LEVELS:
        raise HTTPException(status_code=400, detail="Invalid bias level")

    await set_override(level=level, reason=request.reason, expires_hours=request.expires_hours)
    result = await compute_composite()

    return result.model_dump(mode="json")


@router.delete("/bias/override")
async def clear_bias_override():
    """Clear any active manual bias override"""
    if not COMPOSITE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Composite bias engine not available")

    await clear_override(reason="manual_clear")
    result = await compute_composite()

    return result.model_dump(mode="json")


@router.get("/bias/history")
async def get_bias_history(hours: int = 24):
    """Get historical composite bias readings"""
    if not COMPOSITE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Composite bias engine not available")

    if hours <= 0:
        raise HTTPException(status_code=400, detail="Hours must be a positive integer")

    from database.postgres_client import get_postgres_client, serialize_db_row

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    pool = await get_postgres_client()

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    composite_score,
                    bias_level,
                    bias_numeric,
                    active_factors,
                    stale_factors,
                    velocity_multiplier,
                    override,
                    confidence,
                    factor_scores,
                    created_at
                FROM bias_composite_history
                WHERE created_at >= $1
                ORDER BY created_at DESC
                """,
                cutoff
            )
    except Exception as e:
        logger.warning(f"Error fetching composite bias history: {e}")
        rows = []

    history = [serialize_db_row(dict(row)) for row in rows]

    return {
        "hours": hours,
        "count": len(history),
        "history": history
    }


@router.post("/bias/health")
async def update_pivot_health(payload: PivotHealthRequest, _: str = Depends(verify_pivot_key)):
    """Store heartbeat from Pivot data collector"""
    if not COMPOSITE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Composite bias engine not available")

    timestamp = payload.timestamp or datetime.utcnow()
    data = {
        "agent": payload.agent or "pivot",
        "last_heartbeat": timestamp.isoformat(),
        "timestamp": timestamp.isoformat(),
        "status": payload.status or "ok",
        "factors_collected": payload.factors_collected,
    }

    try:
        client = await get_redis_client()
        if client:
            payload_json = json.dumps(sanitize_for_json(data))
            await client.setex(REDIS_PIVOT_HEALTH_KEY, REDIS_PIVOT_HEALTH_TTL, payload_json)
            await client.setex(REDIS_PIVOT_HEALTH_LEGACY_KEY, REDIS_PIVOT_HEALTH_TTL, payload_json)
    except Exception as e:
        logger.warning(f"Failed to store pivot health: {e}")

    return data


@router.get("/bias/health")
async def get_pivot_health():
    """Read last Pivot heartbeat for UI health indicator"""
    if not COMPOSITE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Composite bias engine not available")

    try:
        client = await get_redis_client()
        if not client:
            return {"status": "unavailable", "last_heartbeat": None}
        raw = await client.get(REDIS_PIVOT_HEALTH_KEY)
        if not raw:
            raw = await client.get(REDIS_PIVOT_HEALTH_LEGACY_KEY)
        if not raw:
            return {"status": "unknown", "last_heartbeat": None}
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Failed to read pivot health: {e}")
        return {"status": "unknown", "last_heartbeat": None}


async def _log_factor_history(
    factor_id: str,
    score: float,
    bias: str,
    data: Dict[str, Any],
    collected_at: datetime,
) -> None:
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS factor_history (
                    id SERIAL PRIMARY KEY,
                    factor_name VARCHAR(50) NOT NULL,
                    score FLOAT NOT NULL,
                    bias VARCHAR(20) NOT NULL,
                    data JSONB,
                    collected_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_factor_history_name_time
                    ON factor_history (factor_name, collected_at DESC);
                """
            )
            await conn.execute(
                """
                INSERT INTO factor_history (factor_name, score, bias, data, collected_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                factor_id,
                score,
                bias,
                json.dumps(sanitize_for_json(data or {})),
                collected_at,
            )
    except Exception as exc:
        logger.warning(f"Failed to log factor history for {factor_id}: {exc}")


async def _get_pivot_status() -> str:
    try:
        from scheduler.bias_scheduler import get_eastern_now, is_trading_day

        client = await get_redis_client()
        if not client:
            return "unknown"

        raw = await client.get(REDIS_PIVOT_HEALTH_KEY)
        if not raw:
            raw = await client.get(REDIS_PIVOT_HEALTH_LEGACY_KEY)
        if not raw:
            return "unknown"

        payload = json.loads(raw)
        timestamp = payload.get("timestamp") or payload.get("last_heartbeat")
        if not timestamp:
            return "unknown"

        if isinstance(timestamp, str):
            timestamp = timestamp.replace("Z", "+00:00")
            last_time = datetime.fromisoformat(timestamp).replace(tzinfo=None)
        else:
            last_time = timestamp

        now_et = get_eastern_now()
        is_market_hours = is_trading_day() and (
            (now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30))
            and (now_et.hour < 16 or (now_et.hour == 16 and now_et.minute == 0))
        )

        minutes_ago = (datetime.utcnow() - last_time).total_seconds() / 60.0
        if minutes_ago < 30:
            return "online"
        if is_market_hours:
            return "offline"
        return "unknown"
    except Exception:
        return "unknown"
