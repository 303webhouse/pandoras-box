"""
Composite Bias Engine

Creates a unified bias score from multiple factors with graceful degradation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field

from database.redis_client import get_redis_client, sanitize_for_json
from database.postgres_client import get_postgres_client
from websocket.broadcaster import manager

logger = logging.getLogger(__name__)

FACTOR_CONFIG = {
    "credit_spreads": {
        "weight": 0.18,
        "staleness_hours": 48,
        "description": "HYG vs TLT ratio - measures credit market risk appetite",
    },
    "market_breadth": {
        "weight": 0.18,
        "staleness_hours": 48,
        "description": "RSP vs SPY ratio - equal-weight vs cap-weight divergence",
    },
    "vix_term": {
        "weight": 0.16,
        "staleness_hours": 4,
        "description": "VIX vs VIX3M - near-term fear vs longer-term expectations",
    },
    "tick_breadth": {
        "weight": 0.14,
        "staleness_hours": 4,
        "description": "Intraday TICK readings - buying/selling pressure",
    },
    "sector_rotation": {
        "weight": 0.14,
        "staleness_hours": 48,
        "description": "XLK/XLY vs XLP/XLU - offensive vs defensive flows",
    },
    "dollar_smile": {
        "weight": 0.08,
        "staleness_hours": 48,
        "description": "DXY trend - risk-on weakness vs risk-off strength",
    },
    "excess_cape": {
        "weight": 0.08,
        "staleness_hours": 168,
        "description": "Excess CAPE yield - valuation risk level",
    },
    "savita": {
        "weight": 0.04,
        "staleness_hours": 1080,
        "description": "BofA Sell Side Indicator - monthly contrarian sentiment",
    },
}

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


class FactorReading(BaseModel):
    factor_id: str
    score: float = Field(..., ge=-1.0, le=1.0)
    signal: str = "NEUTRAL"
    detail: str = ""
    timestamp: datetime
    source: str = "unknown"
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class CompositeResult(BaseModel):
    composite_score: float
    bias_level: str
    bias_numeric: int
    factors: Dict[str, Optional[FactorReading]]
    active_factors: List[str]
    stale_factors: List[str]
    velocity_multiplier: float
    override: Optional[str] = None
    override_expires: Optional[datetime] = None
    timestamp: datetime
    confidence: str


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
    if score >= -0.19:
        return "NEUTRAL", 3
    if score >= -0.59:
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
    try:
        client = await get_redis_client()
        if not client:
            return
        key_latest = REDIS_KEY_FACTOR_LATEST.format(factor_id=reading.factor_id)
        payload = _serialize_model(reading)
        await client.setex(key_latest, REDIS_FACTOR_LATEST_TTL, payload)

        key_history = REDIS_KEY_FACTOR_HISTORY.format(factor_id=reading.factor_id)
        score_ts = _utc_naive(reading.timestamp).timestamp()
        await client.zadd(key_history, {payload: score_ts})
        await client.expire(key_history, REDIS_FACTOR_HISTORY_TTL)

        cutoff = datetime.utcnow() - timedelta(seconds=REDIS_FACTOR_HISTORY_TTL)
        await client.zremrangebyscore(key_history, 0, cutoff.timestamp())
    except Exception as exc:
        logger.warning(f"Failed to store factor reading {reading.factor_id}: {exc}")


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
    try:
        client = await get_redis_client()
        if not client:
            return None
        raw = await client.get(REDIS_KEY_COMPOSITE_LATEST)
        if not raw:
            return None
        data = json.loads(raw)
        return CompositeResult.model_validate(data)
    except Exception as exc:
        logger.warning(f"Failed to load cached composite bias: {exc}")
        return None


async def cache_composite(result: CompositeResult) -> None:
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
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bias_composite_history (
                    id SERIAL PRIMARY KEY,
                    composite_score FLOAT NOT NULL,
                    bias_level VARCHAR(20) NOT NULL,
                    bias_numeric INTEGER NOT NULL,
                    active_factors TEXT[] NOT NULL,
                    stale_factors TEXT[] NOT NULL,
                    velocity_multiplier FLOAT NOT NULL DEFAULT 1.0,
                    override VARCHAR(20),
                    confidence VARCHAR(10) NOT NULL,
                    factor_scores JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_bias_history_created
                    ON bias_composite_history(created_at);
                """
            )

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


async def compute_composite() -> CompositeResult:
    now = datetime.utcnow()
    readings: Dict[str, FactorReading] = {}

    for factor_id in FACTOR_CONFIG:
        reading = await get_latest_reading(factor_id)
        if reading:
            readings[factor_id] = reading

    active: Dict[str, FactorReading] = {}
    stale_set = set()

    for factor_id in FACTOR_CONFIG:
        reading = readings.get(factor_id)
        if not reading:
            stale_set.add(factor_id)
            continue
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

    active_count = len(active)
    if active_count >= 6:
        confidence = "HIGH"
    elif active_count >= 4:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    factors = {factor_id: readings.get(factor_id) for factor_id in FACTOR_CONFIG}
    active_factors = [factor_id for factor_id in FACTOR_CONFIG if factor_id in active]
    stale_factors = [factor_id for factor_id in FACTOR_CONFIG if factor_id in stale_set]

    result = CompositeResult(
        composite_score=adjusted_score,
        bias_level=bias_level,
        bias_numeric=bias_numeric,
        factors=factors,
        active_factors=active_factors,
        stale_factors=stale_factors,
        velocity_multiplier=velocity_multiplier,
        override=override.get("level") if override else None,
        override_expires=override.get("expires") if override else None,
        timestamp=now,
        confidence=confidence,
    )

    previous = await get_cached_composite()
    await cache_composite(result)
    await log_composite(result)

    if previous is None or previous.bias_level != result.bias_level:
        changed_from = previous.bias_level if previous else None
        await broadcast_bias_update(result, changed_from)

    return result
