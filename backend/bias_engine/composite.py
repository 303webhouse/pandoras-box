"""
Composite Bias Engine

Creates a unified bias score from multiple factors with graceful degradation.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field

from database.redis_client import get_redis_client, sanitize_for_json
from database.postgres_client import get_postgres_client
from websocket.broadcaster import manager
from bias_engine.anomaly_alerts import send_alert

logger = logging.getLogger(__name__)

FACTOR_CONFIG = {
    # =====================================================================
    # INTRADAY FACTORS (5 factors, total weight: 0.28)
    # Fast-moving indicators that change throughout the trading day.
    # =====================================================================
    "vix_term": {
        "weight": 0.07,
        "staleness_hours": 4,
        "description": "VIX vs VIX3M - near-term fear vs longer-term expectations",
        "timeframe": "intraday",
    },
    "tick_breadth": {
        "weight": 0.06,
        "staleness_hours": 4,
        "description": "Intraday TICK readings - buying/selling pressure",
        "timeframe": "intraday",
    },
    "vix_regime": {
        "weight": 0.06,
        "staleness_hours": 4,
        "description": "Absolute VIX level - overall market fear/complacency",
        "timeframe": "intraday",
    },
    "spy_trend_intraday": {
        "weight": 0.06,
        "staleness_hours": 4,
        "description": "SPY price vs 9 EMA - short-term momentum",
        "timeframe": "intraday",
    },
    "breadth_intraday": {
        "weight": 0.03,
        "staleness_hours": 4,
        "description": "$UVOL/$DVOL ratio - intraday up/down volume breadth via TradingView webhook",
        "timeframe": "intraday",
    },
    # =====================================================================
    # SWING FACTORS (9 factors, total weight: 0.41)
    # Multi-day trend indicators for swing trade alignment.
    # =====================================================================
    "credit_spreads": {
        "weight": 0.08,
        "staleness_hours": 48,
        "description": "HYG vs TLT ratio - measures credit market risk appetite",
        "timeframe": "swing",
    },
    "market_breadth": {
        "weight": 0.07,
        "staleness_hours": 48,
        "description": "RSP vs SPY ratio - equal-weight vs cap-weight divergence",
        "timeframe": "swing",
    },
    "sector_rotation": {
        "weight": 0.06,
        "staleness_hours": 48,
        "description": "XLK/XLY vs XLP/XLU - offensive vs defensive flows",
        "timeframe": "swing",
    },
    "spy_200sma_distance": {
        "weight": 0.08,
        "staleness_hours": 24,
        "description": "SPY percent distance from 200-day SMA - trend strength",
        "timeframe": "swing",
    },
    "high_yield_oas": {
        "weight": 0.02,
        "staleness_hours": 48,
        "description": "ICE BofA HY OAS - precise credit stress gauge (correlated with credit_spreads)",
        "timeframe": "swing",
    },
    "put_call_ratio": {
        "weight": 0.02,
        "staleness_hours": 72,
        "description": "CBOE equity put/call ratio - contrarian sentiment gauge (self-heals via Polygon fallback)",
        "timeframe": "swing",
    },
    "polygon_pcr": {
        "weight": 0.04,
        "staleness_hours": 8,
        "description": "Polygon SPY put/call volume ratio - automated flow sentiment (15-min delayed)",
        "timeframe": "swing",
    },
    "polygon_oi_ratio": {
        "weight": 0.02,
        "staleness_hours": 8,
        "description": "Polygon SPY put/call open interest ratio - contrarian positioning gauge",
        "timeframe": "swing",
    },
    "iv_regime": {
        "weight": 0.02,
        "staleness_hours": 24,
        "description": "SPY IV rank percentile from Polygon chain - options pricing regime",
        "timeframe": "swing",
    },
    # NOTE: breadth_momentum, options_sentiment, dollar_smile, iv_skew removed
    # (committee review: redundant, unreliable, or merged into other factors)
    # =====================================================================
    # MACRO FACTORS (8 factors, total weight: 0.31)
    # Long-term economic and structural indicators.
    # =====================================================================
    "yield_curve": {
        "weight": 0.05,
        "staleness_hours": 72,
        "description": "10Y-2Y Treasury spread - recession predictor",
        "timeframe": "macro",
    },
    "initial_claims": {
        "weight": 0.05,
        "staleness_hours": 168,
        "description": "Weekly initial jobless claims - labor market health",
        "timeframe": "macro",
    },
    "sahm_rule": {
        "weight": 0.04,
        "staleness_hours": 168,
        "description": "Sahm Rule - real-time recession probability",
        "timeframe": "macro",
    },
    "copper_gold_ratio": {
        "weight": 0.03,
        "staleness_hours": 48,
        "description": "COPX/GLD - economic activity vs safety demand",
        "timeframe": "macro",
    },
    "dxy_trend": {
        "weight": 0.06,
        "staleness_hours": 48,
        "description": "DXY 5d trend + SMA20 context + VIX interaction - strong USD risk-off signal",
        "timeframe": "macro",
    },
    "excess_cape": {
        "weight": 0.03,
        "staleness_hours": 168,
        "description": "Excess CAPE yield - valuation risk level",
        "timeframe": "macro",
    },
    "ism_manufacturing": {
        "weight": 0.03,
        "staleness_hours": 720,
        "description": "ISM Manufacturing PMI - leading economic indicator",
        "timeframe": "macro",
    },
    "savita": {
        "weight": 0.02,
        "staleness_hours": 1080,
        "description": "BofA Sell Side Indicator - monthly contrarian sentiment",
        "timeframe": "macro",
    },
}

# Permanent guardrail: weights must sum to 1.00 (±0.001 for floating-point)
_WEIGHT_SUM = sum(cfg["weight"] for cfg in FACTOR_CONFIG.values())
assert abs(_WEIGHT_SUM - 1.0) < 0.001, (
    f"FACTOR_CONFIG weights sum to {_WEIGHT_SUM:.4f}, expected 1.0000. "
    f"Fix weights before deploying."
)

BIAS_NUMERIC = {
    "URSA_MAJOR": 1,
    "URSA_MINOR": 2,
    "NEUTRAL": 3,
    "TORO_MINOR": 4,
    "TORO_MAJOR": 5,
}

REDIS_FACTOR_LATEST_TTL = 86400
REDIS_FACTOR_HISTORY_TTL = 86400 * 7
REDIS_COMPOSITE_TTL = 86400

REDIS_KEY_FACTOR_LATEST = "bias:factor:{factor_id}:latest"
REDIS_KEY_FACTOR_HISTORY = "bias:factor:{factor_id}:history"
REDIS_KEY_COMPOSITE_LATEST = "bias:composite:latest"
REDIS_KEY_OVERRIDE = "bias:override"

# Short-lived in-process cache to reduce Redis reads during frequent polling.
COMPOSITE_MEM_CACHE_TTL = int(os.getenv("COMPOSITE_MEM_CACHE_TTL", "15"))
_COMPOSITE_MEM_CACHE: Dict[str, Any] = {"payload": None, "expires_at": None}


class FactorReading(BaseModel):
    factor_id: str
    score: float = Field(..., ge=-1.0, le=1.0)
    signal: str = "NEUTRAL"
    detail: str = ""
    timestamp: datetime
    source: str = "unknown"
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositeResult(BaseModel):
    composite_score: float
    bias_level: str
    bias_numeric: int
    factors: Dict[str, Optional[FactorReading]]
    active_factors: List[str]
    stale_factors: List[str]
    velocity_multiplier: float
    rvol_modifier: float = 1.0
    override: Optional[str] = None
    override_expires: Optional[datetime] = None
    timestamp: datetime
    confidence: str
    unverifiable_factors: List[str] = Field(default_factory=list)
    circuit_breaker: Optional[Dict[str, Any]] = None


# Map circuit breaker's scheduler-style level names to composite's 5-level system.
# Circuit breaker uses: LEAN_TORO, MINOR_TORO, LEAN_URSA, MINOR_URSA
# Composite uses: TORO_MAJOR, TORO_MINOR, NEUTRAL, URSA_MINOR, URSA_MAJOR
_CB_LEVEL_MAP = {
    "MAJOR_TORO": "TORO_MAJOR",
    "MINOR_TORO": "TORO_MINOR",
    "LEAN_TORO": "TORO_MINOR",   # closest composite equivalent
    "LEAN_URSA": "URSA_MINOR",   # closest composite equivalent
    "MINOR_URSA": "URSA_MINOR",
    "MAJOR_URSA": "URSA_MAJOR",
    # In case composite-style names are used directly:
    "TORO_MAJOR": "TORO_MAJOR",
    "TORO_MINOR": "TORO_MINOR",
    "NEUTRAL": "NEUTRAL",
    "URSA_MINOR": "URSA_MINOR",
    "URSA_MAJOR": "URSA_MAJOR",
}


def _cb_level_to_numeric(level_name: str) -> Optional[int]:
    """Convert a circuit breaker level name to composite numeric (1-5)."""
    mapped = _CB_LEVEL_MAP.get(level_name.upper())
    if mapped:
        return BIAS_NUMERIC.get(mapped)
    return None


def _clamp_score(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _bias_name_to_numeric(level: str) -> int:
    if not level:
        return BIAS_NUMERIC["NEUTRAL"]
    return BIAS_NUMERIC.get(level.upper(), BIAS_NUMERIC["NEUTRAL"])


def score_to_bias(score: float) -> tuple[str, int]:
    if score >= 0.60:
        return "TORO_MAJOR", 5
    if score >= 0.20:
        return "TORO_MINOR", 4
    if score >= -0.20:
        return "NEUTRAL", 3
    if score >= -0.60:
        return "URSA_MINOR", 2
    return "URSA_MAJOR", 1


def _serialize_model(model: BaseModel) -> str:
    payload = model.model_dump(mode="json")
    payload = sanitize_for_json(payload)
    return json.dumps(payload)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _utc_naive(value)
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return _utc_naive(datetime.fromisoformat(text))
        except ValueError:
            return datetime.utcnow()
    return datetime.utcnow()


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def get_latest_reading(factor_id: str) -> Optional[FactorReading]:
    try:
        client = await get_redis_client()
        if not client:
            return None
        key = REDIS_KEY_FACTOR_LATEST.format(factor_id=factor_id)
        raw = await client.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        return FactorReading.model_validate(data)
    except Exception as exc:
        logger.warning(f"Failed to load factor reading {factor_id}: {exc}")
        return None


async def store_factor_reading(reading: FactorReading) -> None:
    payload = _serialize_model(reading)
    try:
        client = await get_redis_client()
        if client:
            key_latest = REDIS_KEY_FACTOR_LATEST.format(factor_id=reading.factor_id)
            # Use factor-specific TTL: at least the global default, or the factor's
            # staleness window — whichever is longer.  Fixes factors like savita
            # (1080 h) whose Redis key was expiring after only 24 h.
            staleness_hours = FACTOR_CONFIG.get(reading.factor_id, {}).get("staleness_hours", 0)
            factor_ttl = max(REDIS_FACTOR_LATEST_TTL, int(staleness_hours * 3600))
            await client.setex(key_latest, factor_ttl, payload)

            key_history = REDIS_KEY_FACTOR_HISTORY.format(factor_id=reading.factor_id)
            score_ts = _utc_naive(reading.timestamp).timestamp()
            await client.zadd(key_history, {payload: score_ts})
            await client.expire(key_history, REDIS_FACTOR_HISTORY_TTL)

            cutoff = datetime.utcnow() - timedelta(seconds=REDIS_FACTOR_HISTORY_TTL)
            await client.zremrangebyscore(key_history, 0, cutoff.timestamp())
        else:
            logger.debug("Redis unavailable; skipping factor reading cache for %s", reading.factor_id)
    except Exception as exc:
        logger.warning(f"Failed to store factor reading in Redis {reading.factor_id}: {exc}")

    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO factor_readings (factor_id, timestamp, score, signal, source, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                reading.factor_id,
                _utc_naive(reading.timestamp),
                reading.score,
                reading.signal,
                reading.source,
                json.dumps(
                    sanitize_for_json(
                        {
                            "raw_data": reading.raw_data or {},
                            "metadata": reading.metadata or {},
                        }
                    )
                ),
            )
    except Exception as exc:
        logger.warning(f"Failed to store factor reading in Postgres {reading.factor_id}: {exc}")


def build_factor_reading(payload: Dict[str, Any]) -> FactorReading:
    timestamp = _parse_timestamp(payload.get("timestamp"))
    return FactorReading(
        factor_id=payload["factor_id"],
        score=float(payload["score"]),
        signal=payload.get("signal", "NEUTRAL"),
        detail=payload.get("detail", ""),
        timestamp=timestamp,
        source=payload.get("source", "unknown"),
        raw_data=payload.get("raw_data") or {},
        metadata=payload.get("metadata") or {},
    )


async def record_factor_reading(payload: Dict[str, Any]) -> FactorReading:
    reading = build_factor_reading(payload)
    await store_factor_reading(reading)
    return reading


async def get_reading_before(factor_id: str, cutoff: datetime) -> Optional[FactorReading]:
    try:
        client = await get_redis_client()
        if not client:
            return None
        key = REDIS_KEY_FACTOR_HISTORY.format(factor_id=factor_id)
        cutoff_ts = _utc_naive(cutoff).timestamp()
        results = await client.zrevrangebyscore(key, max=cutoff_ts, min=0, start=0, num=1)
        if not results:
            return None
        data = json.loads(results[0])
        return FactorReading.model_validate(data)
    except Exception as exc:
        logger.warning(f"Failed to load historical reading {factor_id}: {exc}")
        return None


async def count_bearish_shifts(hours: int = 24) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    count = 0

    for factor_id in FACTOR_CONFIG:
        current = await get_latest_reading(factor_id)
        previous = await get_reading_before(factor_id, cutoff)
        if not current or not previous:
            continue
        delta = current.score - previous.score
        if delta <= -0.3:
            count += 1

    return count


async def get_cached_composite() -> Optional[CompositeResult]:
    now = datetime.utcnow()
    cached = _COMPOSITE_MEM_CACHE.get("payload")
    expires = _COMPOSITE_MEM_CACHE.get("expires_at")
    if cached and expires and now < expires:
        return cached

    try:
        client = await get_redis_client()
        if not client:
            return None
        raw = await client.get(REDIS_KEY_COMPOSITE_LATEST)
        if not raw:
            return None
        data = json.loads(raw)
        result = CompositeResult.model_validate(data)
        _COMPOSITE_MEM_CACHE["payload"] = result
        _COMPOSITE_MEM_CACHE["expires_at"] = now + timedelta(seconds=COMPOSITE_MEM_CACHE_TTL)
        return result
    except Exception as exc:
        logger.warning(f"Failed to load cached composite bias: {exc}")
        return None


async def cache_composite(result: CompositeResult) -> None:
    _COMPOSITE_MEM_CACHE["payload"] = result
    _COMPOSITE_MEM_CACHE["expires_at"] = datetime.utcnow() + timedelta(seconds=COMPOSITE_MEM_CACHE_TTL)
    try:
        client = await get_redis_client()
        if not client:
            return
        payload = _serialize_model(result)
        await client.setex(REDIS_KEY_COMPOSITE_LATEST, REDIS_COMPOSITE_TTL, payload)
    except Exception as exc:
        logger.warning(f"Failed to cache composite bias: {exc}")


async def log_composite(result: CompositeResult) -> None:
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            factor_scores = {
                factor_id: (reading.score if reading else None)
                for factor_id, reading in result.factors.items()
            }

            await conn.execute(
                """
                INSERT INTO bias_composite_history (
                    composite_score,
                    bias_level,
                    bias_numeric,
                    active_factors,
                    stale_factors,
                    velocity_multiplier,
                    override,
                    confidence,
                    factor_scores
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                result.composite_score,
                result.bias_level,
                result.bias_numeric,
                result.active_factors,
                result.stale_factors,
                result.velocity_multiplier,
                result.override,
                result.confidence,
                json.dumps(sanitize_for_json(factor_scores)),
            )
    except Exception as exc:
        logger.warning(f"Failed to log composite bias: {exc}")


async def broadcast_bias_update(result: CompositeResult, changed_from: Optional[str] = None) -> None:
    payload = {
        "bias_level": result.bias_level,
        "bias_numeric": result.bias_numeric,
        "composite_score": result.composite_score,
        "confidence": result.confidence,
        "override": result.override,
        "timestamp": result.timestamp.isoformat(),
    }

    if changed_from:
        payload["changed_from"] = changed_from

    try:
        await manager.broadcast_bias_update(payload)
    except Exception as exc:
        logger.warning(f"Failed to broadcast composite bias update: {exc}")


async def set_override(level: str, reason: Optional[str] = None, expires_hours: Optional[int] = None) -> Dict[str, Any]:
    payload = {
        "level": level.upper(),
        "reason": reason,
        "created_at": datetime.utcnow().isoformat(),
    }

    if expires_hours:
        payload["expires"] = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()

    try:
        client = await get_redis_client()
        if client:
            raw = json.dumps(sanitize_for_json(payload))
            if expires_hours:
                await client.setex(REDIS_KEY_OVERRIDE, int(expires_hours * 3600), raw)
            else:
                await client.set(REDIS_KEY_OVERRIDE, raw)
    except Exception as exc:
        logger.warning(f"Failed to set override: {exc}")

    return payload


async def clear_override(reason: Optional[str] = None) -> None:
    try:
        client = await get_redis_client()
        if client:
            await client.delete(REDIS_KEY_OVERRIDE)
        if reason:
            logger.info(f"Bias override cleared: {reason}")
    except Exception as exc:
        logger.warning(f"Failed to clear override: {exc}")


async def get_active_override() -> Optional[Dict[str, Any]]:
    try:
        client = await get_redis_client()
        if not client:
            return None
        raw = await client.get(REDIS_KEY_OVERRIDE)
        if not raw:
            return None
        data = json.loads(raw)
        level = data.get("level")
        if not level:
            return None
        data["level"] = level.upper()

        expires = data.get("expires")
        if expires:
            expires_dt = _parse_timestamp(expires)
            if datetime.utcnow() >= expires_dt:
                await clear_override(reason="expired")
                return None
            data["expires"] = expires_dt

        return data
    except Exception as exc:
        logger.warning(f"Failed to load active override: {exc}")
        return None


# --- RVOL Conviction Modifier ---
# Relative volume amplifies or dampens bias conviction.
RVOL_ACTIVATE_THRESHOLD = 1.5    # Enter amplified state above this
RVOL_DEACTIVATE_THRESHOLD = 1.2  # Stay amplified until below this (hysteresis)
RVOL_LOW_THRESHOLD = 0.5         # Low volume dampening
RVOL_CACHE_TTL = 3600            # 60-minute cache (not 15)
RVOL_REDIS_KEY = "bias:rvol:state"
RVOL_CACHE_KEY = "bias:rvol:cache"


async def compute_rvol_modifier(adjusted_score: float, confidence: str) -> tuple[float, Dict[str, Any]]:
    """
    Compute RVOL conviction modifier with full guardrails.

    Guardrails:
    - Asymmetric: bearish amplification 1.20x, bullish 1.10x
    - Hysteresis: activate at 1.5, deactivate at 1.2
    - 60-minute cache TTL
    - Confidence gate: force 1.0 when confidence is LOW
    - Dead zone: force 1.0 when |score| <= 0.10
    - Data: Polygon snapshot + bars, yfinance fallback
    """
    import time

    meta: Dict[str, Any] = {"rvol": None, "modifier": 1.0, "reason": "not_computed"}

    # Confidence gate: no amplification when confidence is LOW
    if confidence == "LOW":
        meta["reason"] = "confidence_gate"
        return 1.0, meta

    # Dead zone: no amplification when score is near zero
    if abs(adjusted_score) <= 0.10:
        meta["reason"] = "dead_zone"
        return 1.0, meta

    try:
        from database.redis_client import get_redis_client
        import json

        client = await get_redis_client()
        if not client:
            return 1.0, meta

        # Check cache first (60-minute TTL)
        cached = await client.get(RVOL_CACHE_KEY)
        if cached:
            cache_data = json.loads(cached)
            cache_age = time.time() - cache_data.get("ts", 0)
            if cache_age < RVOL_CACHE_TTL:
                rvol = cache_data.get("rvol")
                if rvol is not None:
                    modifier = _apply_rvol_hysteresis(rvol, adjusted_score, client, cache_data.get("active", False))
                    meta.update({"rvol": round(rvol, 3), "modifier": modifier, "reason": "cached", "cache_age_min": round(cache_age / 60, 1)})
                    return modifier, meta

        # Fetch current SPY volume from Polygon snapshot
        rvol = await _fetch_rvol()
        if rvol is None:
            meta["reason"] = "fetch_failed"
            return 1.0, meta

        # Load hysteresis state
        state_raw = await client.get(RVOL_REDIS_KEY)
        was_active = False
        if state_raw:
            state = json.loads(state_raw)
            was_active = state.get("active", False)

        modifier = _apply_rvol_hysteresis(rvol, adjusted_score, None, was_active)

        # Determine if currently in active (amplified) state
        now_active = False
        if rvol >= RVOL_ACTIVATE_THRESHOLD:
            now_active = True
        elif was_active and rvol >= RVOL_DEACTIVATE_THRESHOLD:
            now_active = True  # Sticky — stays active until below deactivate threshold

        # Store hysteresis state + cache
        state_payload = json.dumps({"active": now_active, "rvol": round(rvol, 3), "ts": time.time()})
        await client.setex(RVOL_REDIS_KEY, 86400, state_payload)

        cache_payload = json.dumps({"rvol": round(rvol, 3), "active": now_active, "ts": time.time()})
        await client.setex(RVOL_CACHE_KEY, RVOL_CACHE_TTL, cache_payload)

        meta.update({"rvol": round(rvol, 3), "modifier": modifier, "reason": "computed", "hysteresis_active": now_active})
        return modifier, meta

    except Exception as exc:
        logger.warning("RVOL modifier computation failed: %s", exc)
        meta["reason"] = f"error: {exc}"
        return 1.0, meta


def _apply_rvol_hysteresis(rvol: float, score: float, _client: Any, was_active: bool) -> float:
    """Apply asymmetric RVOL modifier with hysteresis."""
    is_bearish = score < 0

    # High RVOL amplification (with hysteresis)
    if rvol >= RVOL_ACTIVATE_THRESHOLD or (was_active and rvol >= RVOL_DEACTIVATE_THRESHOLD):
        if is_bearish:
            return 1.20  # Bearish + high volume = stronger conviction
        else:
            return 1.10  # Bullish + high volume = moderate amplification

    # Low RVOL dampening
    if rvol < RVOL_LOW_THRESHOLD:
        return 0.85  # Low volume = reduced conviction

    return 1.0  # Normal volume = no adjustment


async def _fetch_rvol() -> Optional[float]:
    """
    Fetch relative volume for SPY.
    RVOL = current session volume / average volume (20-day).
    Uses Polygon snapshot for current volume, bars for history.
    Falls back to yfinance if Polygon unavailable.
    """
    try:
        # Try Polygon first
        from integrations.polygon_equities import get_snapshot, get_bars
        from datetime import date

        snapshot = await get_snapshot("SPY")
        if snapshot:
            # Polygon snapshot has day.volume for current session
            day_data = snapshot.get("day", {})
            current_vol = day_data.get("v") or day_data.get("volume") or 0

            if current_vol > 0:
                # Get 20-day average volume from bars
                today = date.today()
                from_date = (today - timedelta(days=35)).isoformat()
                to_date = (today - timedelta(days=1)).isoformat()
                bars = await get_bars("SPY", 1, "day", from_date, to_date)

                if bars and len(bars) >= 10:
                    volumes = [b.get("v", 0) for b in bars[-20:] if b.get("v", 0) > 0]
                    if volumes:
                        avg_vol = sum(volumes) / len(volumes)
                        if avg_vol > 0:
                            return current_vol / avg_vol

    except ImportError:
        pass
    except Exception as exc:
        logger.debug("RVOL Polygon fetch failed, trying yfinance: %s", exc)

    # yfinance fallback
    try:
        from bias_engine.factor_utils import get_price_history
        data = await get_price_history("SPY", days=25)
        if data is not None and not data.empty and "volume" in data.columns:
            volumes = data["volume"].dropna()
            if len(volumes) >= 10:
                current_vol = float(volumes.iloc[-1])
                avg_vol = float(volumes.iloc[-21:-1].mean())
                if avg_vol > 0 and current_vol > 0:
                    return current_vol / avg_vol
    except Exception as exc:
        logger.debug("RVOL yfinance fallback failed: %s", exc)

    return None


async def compute_composite() -> CompositeResult:
    now = datetime.utcnow()
    readings: Dict[str, FactorReading] = {}

    for factor_id in FACTOR_CONFIG:
        reading = await get_latest_reading(factor_id)
        if reading:
            readings[factor_id] = reading

    active: Dict[str, FactorReading] = {}
    stale_set = set()
    unverifiable_factors: List[str] = []

    for factor_id in FACTOR_CONFIG:
        reading = readings.get(factor_id)
        if not reading:
            stale_set.add(factor_id)
            continue
        timestamp_source = (reading.metadata or {}).get("timestamp_source")
        if timestamp_source == "fallback":
            unverifiable_factors.append(factor_id)
        max_age = timedelta(hours=FACTOR_CONFIG[factor_id]["staleness_hours"])
        reading_ts = _utc_naive(reading.timestamp)
        if (now - reading_ts) <= max_age:
            active[factor_id] = reading
        else:
            stale_set.add(factor_id)

    active_weight_sum = sum(FACTOR_CONFIG[f]["weight"] for f in active)

    if active_weight_sum == 0:
        raw_score = 0.0
        velocity_multiplier = 1.0
        adjusted_score = 0.0
    else:
        normalized_weights = {
            f: FACTOR_CONFIG[f]["weight"] / active_weight_sum
            for f in active
        }
        raw_score = sum(active[f].score * normalized_weights[f] for f in active)
        raw_score = _clamp_score(raw_score)

        velocity_multiplier = 1.0
        try:
            bearish_shifts_24h = await count_bearish_shifts(hours=24)
            if bearish_shifts_24h >= 3:
                velocity_multiplier = 1.3
        except Exception as exc:
            logger.warning(f"Velocity multiplier check failed: {exc}")

        adjusted_score = _clamp_score(raw_score * velocity_multiplier)

    # --- RVOL Conviction Modifier ---
    # Applied after velocity multiplier, before circuit breaker.
    active_count = len(active)
    if active_count >= 6:
        _conf = "HIGH"
    elif active_count >= 4:
        _conf = "MEDIUM"
    else:
        _conf = "LOW"

    rvol_modifier = 1.0
    rvol_meta: Dict[str, Any] = {}
    try:
        rvol_modifier, rvol_meta = await compute_rvol_modifier(adjusted_score, _conf)
        if rvol_modifier != 1.0:
            adjusted_score = _clamp_score(adjusted_score * rvol_modifier)
            logger.info("RVOL modifier applied: %.2fx (rvol=%.2f, reason=%s)",
                        rvol_modifier, rvol_meta.get("rvol", 0), rvol_meta.get("reason", ""))
    except Exception as exc:
        logger.warning("RVOL modifier failed: %s", exc)

    bias_level, bias_numeric = score_to_bias(adjusted_score)

    override = await get_active_override()
    if override:
        override_level = override.get("level")
        override_level_num = _bias_name_to_numeric(override_level)
        if (override_level_num > 3 and bias_numeric <= 2) or (override_level_num < 3 and bias_numeric >= 4):
            await clear_override(reason="composite_crossed_opposite")
            override = None
        else:
            bias_level = override_level
            bias_numeric = override_level_num

    # --- Circuit Breaker Integration ---
    # Apply score penalties and bias caps/floors from circuit breaker state.
    # Also runs decay check on every scoring cycle.
    cb_meta: Optional[Dict[str, Any]] = None
    try:
        from webhooks.circuit_breaker import get_circuit_breaker_state, check_decay
        cb_state = get_circuit_breaker_state()

        # Run decay check (condition-verified) on every scoring cycle
        if cb_state.get("active"):
            try:
                await check_decay()
                # Re-read state after decay check (may have transitioned to pending_reset)
                cb_state = get_circuit_breaker_state()
            except Exception as decay_exc:
                logger.debug("CB decay check failed: %s", decay_exc)

        if cb_state.get("active"):
            trigger = cb_state.get("trigger", "unknown")
            scoring_mod = float(cb_state.get("scoring_modifier", 1.0))
            bias_cap_name = cb_state.get("bias_cap")
            bias_floor_name = cb_state.get("bias_floor")

            # During pending_reset: fade scoring modifier linearly toward 1.0
            # but keep bias cap/floor until Nick accepts
            if cb_state.get("pending_reset"):
                decay_fade = float(cb_state.get("decay_fade", 1.0))
                # Interpolate: scoring_mod fades toward 1.0
                scoring_mod = 1.0 + (scoring_mod - 1.0) * decay_fade

            # Apply scoring modifier to composite score.
            # For bearish CB events (scoring_mod > 1.0): multiply to amplify bearishness.
            # For bullish CB events (scoring_mod < 1.0 won't happen, but spy_up_2pct
            # uses scoring_mod=1.1 to boost bullishness): use additive offset so
            # negative scores move toward zero instead of becoming more negative.
            if scoring_mod != 1.0:
                is_bullish_trigger = trigger in ("spy_up_2pct", "spy_recovery")
                if is_bullish_trigger:
                    # Additive: shift score toward bullish direction
                    adjusted_score = _clamp_score(adjusted_score + (scoring_mod - 1.0) * 0.5)
                else:
                    adjusted_score = _clamp_score(adjusted_score * scoring_mod)
                bias_level, bias_numeric = score_to_bias(adjusted_score)

            # Enforce bias cap (max bullishness allowed)
            if bias_cap_name:
                cap_num = _cb_level_to_numeric(bias_cap_name)
                if cap_num and bias_numeric > cap_num:
                    bias_numeric = cap_num
                    bias_level = [k for k, v in BIAS_NUMERIC.items() if v == cap_num][0]

            # Enforce bias floor (min bearishness enforced)
            if bias_floor_name:
                floor_num = _cb_level_to_numeric(bias_floor_name)
                if floor_num and bias_numeric < floor_num:
                    bias_numeric = floor_num
                    bias_level = [k for k, v in BIAS_NUMERIC.items() if v == floor_num][0]

            cb_meta = {
                "active": True,
                "trigger": trigger,
                "scoring_modifier": scoring_mod,
                "bias_cap": bias_cap_name,
                "bias_floor": bias_floor_name,
                "triggered_at": cb_state.get("triggered_at"),
                "pending_reset": cb_state.get("pending_reset", False),
                "decay_fade": cb_state.get("decay_fade", 1.0),
            }
            logger.info(
                "Circuit breaker applied to composite: trigger=%s mod=%.2f cap=%s floor=%s → %s",
                trigger, scoring_mod, bias_cap_name, bias_floor_name, bias_level,
            )
    except ImportError:
        pass  # circuit breaker module not available
    except Exception as exc:
        logger.warning("Circuit breaker integration failed: %s", exc)

    # Confidence was already computed before RVOL; reuse _conf
    confidence = _conf

    factors = {factor_id: readings.get(factor_id) for factor_id in FACTOR_CONFIG}
    active_factors = [factor_id for factor_id in FACTOR_CONFIG if factor_id in active]
    stale_factors = [factor_id for factor_id in FACTOR_CONFIG if factor_id in stale_set]

    # Attach RVOL metadata to circuit breaker dict for frontend visibility
    if rvol_meta and rvol_meta.get("rvol") is not None:
        if cb_meta is None:
            cb_meta = {}
        cb_meta["rvol"] = rvol_meta

    result = CompositeResult(
        composite_score=adjusted_score,
        bias_level=bias_level,
        bias_numeric=bias_numeric,
        factors=factors,
        active_factors=active_factors,
        stale_factors=stale_factors,
        velocity_multiplier=velocity_multiplier,
        rvol_modifier=rvol_modifier,
        override=override.get("level") if override else None,
        override_expires=override.get("expires") if override else None,
        timestamp=now,
        confidence=confidence,
        unverifiable_factors=sorted(unverifiable_factors),
        circuit_breaker=cb_meta,
    )

    previous = await get_cached_composite()
    await cache_composite(result)
    await log_composite(result)

    # Only alert on staleness during market hours (Mon-Fri 9:00-17:00 ET)
    # Factors are expected to be stale on weekends/overnight
    _et_now = datetime.now(timezone.utc).astimezone()
    try:
        import zoneinfo
        _et_now = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    except Exception:
        pass
    _market_session = _et_now.weekday() < 5 and 9 <= _et_now.hour <= 17

    if len(stale_set) >= 5 and _market_session:
        try:
            stale_preview = ", ".join(sorted(stale_set)[:10])
            await send_alert(
                "Mass Factor Staleness",
                f"{len(stale_set)} factors stale: {stale_preview}",
                severity="warning",
            )
        except Exception as exc:
            logger.warning(f"Mass staleness alert failed: {exc}")

    if previous and previous.confidence == "HIGH" and result.confidence == "LOW" and _market_session:
        try:
            await send_alert(
                "Bias Confidence Collapsed",
                (
                    "Composite confidence dropped from HIGH to LOW. "
                    f"Active factors: {active_count}/{len(FACTOR_CONFIG)}"
                ),
                severity="critical",
            )
        except Exception as exc:
            logger.warning(f"Confidence collapse alert failed: {exc}")

    if previous is None or previous.bias_level != result.bias_level:
        changed_from = previous.bias_level if previous else None
        await broadcast_bias_update(result, changed_from)
        if previous is not None:
            try:
                await send_alert(
                    "Bias Level Changed",
                    (
                        f"Composite bias changed: {previous.bias_level} -> {result.bias_level} "
                        f"(score {result.composite_score:+.3f})"
                    ),
                    severity="info",
                )
            except Exception as exc:
                logger.warning(f"Bias level change alert failed: {exc}")

    return result
