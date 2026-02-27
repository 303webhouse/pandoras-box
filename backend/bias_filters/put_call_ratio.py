"""
Put/Call Ratio Factor — scores CBOE equity put/call ratio for the composite bias engine.

Data source: TradingView webhook on $CPCE (CBOE equity put/call ratio).
Fires once daily at market close.

This is a CONTRARIAN indicator:
- High PCR (>= 1.0) = elevated fear = contrarian bullish
- Low PCR (<= 0.6) = complacency = contrarian bearish
- Normal PCR (0.7-0.9) = neutral
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REDIS_KEY_PCR_CURRENT = "pcr:current"
REDIS_TTL_SECONDS = 86400 * 3  # 3 days

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal


async def _polygon_pcr_fallback() -> Optional[Dict[str, Any]]:
    """
    Self-healing fallback: derive PCR from Polygon SPY options chain
    when the TradingView $CPCE webhook hasn't fired.
    """
    try:
        from bias_filters.polygon_pcr import compute_score as compute_polygon_pcr
        reading = await compute_polygon_pcr()
        if reading and reading.raw_data:
            pcr_value = reading.raw_data.get("pcr")
            if pcr_value and pcr_value > 0:
                return {
                    "pcr": pcr_value,
                    "source": "polygon_fallback",
                    "updated_at": datetime.utcnow().isoformat(),
                }
    except Exception as e:
        logger.debug("Polygon PCR fallback failed: %s", e)
    return None


async def store_pcr_data(pcr_value: float, date: Optional[str] = None) -> Dict[str, Any]:
    """
    Store put/call ratio data from TradingView webhook.
    """
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return {"error": "Redis not available"}

        data_date = date or datetime.utcnow().strftime("%Y-%m-%d")

        current_data = {
            "pcr": pcr_value,
            "date": data_date,
            "updated_at": datetime.utcnow().isoformat(),
        }

        await redis.setex(REDIS_KEY_PCR_CURRENT, REDIS_TTL_SECONDS, json.dumps(current_data))

        score = _score_pcr(pcr_value)
        logger.info(f"PCR data stored: {pcr_value:.3f}, score={score:+.2f}")

        return {
            "status": "success",
            "pcr": pcr_value,
            "date": data_date,
            "score": score,
            "updated_at": current_data["updated_at"],
        }

    except Exception as e:
        logger.error(f"Error storing PCR data: {e}")
        return {"error": str(e)}


async def compute_score(pcr_data: Optional[Dict[str, Any]] = None) -> Optional[FactorReading]:
    """
    Compute score from provided PCR data or latest stored values.
    """
    if pcr_data is None:
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis:
                raw = await redis.get(REDIS_KEY_PCR_CURRENT)
                pcr_data = json.loads(raw) if raw else None
        except Exception as e:
            logger.warning(f"Error loading PCR data for scoring: {e}")

    if not pcr_data:
        # Self-heal: try Polygon PCR as fallback when TV webhook hasn't fired
        pcr_data = await _polygon_pcr_fallback()
        if not pcr_data:
            logger.warning("Put/Call ratio: no PCR payload available (TV + Polygon both empty) — excluding from composite")
            return None
        logger.info("Put/Call ratio: self-healed via Polygon PCR fallback")

    pcr_value = float(pcr_data.get("pcr", 0) or 0)
    if pcr_value <= 0:
        logger.warning("Put/Call ratio: invalid PCR value — excluding from composite")
        return None

    score = _score_pcr(pcr_value)
    source_timestamp, timestamp_source = _extract_source_timestamp(pcr_data)
    if timestamp_source == "fallback":
        logger.warning(
            "No source timestamp for put_call_ratio; using utcnow fallback (staleness reliability reduced)"
        )

    data_source = "polygon_fallback" if pcr_data.get("source") == "polygon_fallback" else "tradingview"
    return FactorReading(
        factor_id="put_call_ratio",
        score=score,
        signal=score_to_signal(score),
        detail=f"CBOE P/C ratio: {pcr_value:.3f} ({'fear' if pcr_value >= 0.9 else 'complacency' if pcr_value <= 0.7 else 'normal'}){' [Polygon fallback]' if data_source == 'polygon_fallback' else ''}",
        timestamp=source_timestamp,
        source=data_source,
        raw_data=pcr_data,
        metadata={"timestamp_source": timestamp_source},
    )


def _extract_source_timestamp(payload: Dict[str, Any]) -> tuple[datetime, str]:
    for key in ("updated_at", "timestamp", "received_at"):
        raw = payload.get(key)
        if not raw:
            continue
        parsed = _parse_timestamp(raw)
        if parsed is not None:
            return parsed, key
    return datetime.utcnow(), "fallback"


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


def _score_pcr(pcr: float) -> float:
    """
    Contrarian scoring of put/call ratio.

    High PCR = lots of puts = fear = contrarian bullish (positive score).
    Low PCR = few puts = complacency = contrarian bearish (negative score).
    """
    if pcr >= 1.2:
        score = 0.8
    elif pcr >= 1.0:
        score = 0.5
    elif pcr >= 0.9:
        score = 0.3
    elif pcr >= 0.8:
        score = 0.1
    elif pcr >= 0.7:
        score = 0.0
    elif pcr >= 0.6:
        score = -0.3
    elif pcr >= 0.5:
        score = -0.5
    else:
        score = -0.8

    return max(-1.0, min(1.0, score))
