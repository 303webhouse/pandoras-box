"""
Intraday Breadth Factor — $UVOL/$DVOL ratio from TradingView webhook.

Measures real-time up-volume vs down-volume across NYSE stocks.
UVOL/DVOL > 2.0 = strong breadth thrust (bullish).
UVOL/DVOL < 0.5 = heavy selling breadth (bearish).

Data source: TradingView webhook on $UVOL and $DVOL (fires every 15 min).
Staleness: 4h — intraday timeframe.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REDIS_KEY_BREADTH = "breadth:uvol_dvol:current"
REDIS_TTL_SECONDS = 86400  # 24h

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal


async def store_breadth_data(uvol: float, dvol: float) -> Dict[str, Any]:
    """Store UVOL/DVOL data from TradingView webhook."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return {"error": "Redis not available"}

        ratio = uvol / dvol if dvol > 0 else 0.0
        data = {
            "uvol": uvol,
            "dvol": dvol,
            "ratio": round(ratio, 4),
            "updated_at": datetime.utcnow().isoformat(),
        }

        await redis.setex(REDIS_KEY_BREADTH, REDIS_TTL_SECONDS, json.dumps(data))

        score = _score_breadth_ratio(ratio)
        logger.info("breadth_intraday: stored UVOL=%.0f DVOL=%.0f ratio=%.3f score=%+.2f", uvol, dvol, ratio, score)

        return {
            "status": "success",
            "uvol": uvol,
            "dvol": dvol,
            "ratio": round(ratio, 4),
            "score": score,
            "updated_at": data["updated_at"],
        }

    except Exception as e:
        logger.error("breadth_intraday: error storing data: %s", e)
        return {"error": str(e)}


async def compute_score() -> Optional[FactorReading]:
    """Compute score from latest UVOL/DVOL data in Redis."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return None

        raw = await redis.get(REDIS_KEY_BREADTH)
        if not raw:
            logger.warning("breadth_intraday: no UVOL/DVOL data in Redis — skipping")
            return None

        data = json.loads(raw)
    except Exception as e:
        logger.warning("breadth_intraday: error loading data: %s", e)
        return None

    ratio = float(data.get("ratio", 0))
    if ratio <= 0:
        return None

    score = _score_breadth_ratio(ratio)

    # Parse source timestamp
    updated_at = data.get("updated_at", "")
    try:
        ts = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        ts = datetime.utcnow()

    if ratio > 2.0:
        label = "strong breadth thrust"
    elif ratio > 1.5:
        label = "healthy breadth"
    elif ratio > 1.2:
        label = "mild positive breadth"
    elif ratio > 0.8:
        label = "balanced"
    elif ratio > 0.5:
        label = "mild selling pressure"
    else:
        label = "heavy selling breadth"

    return FactorReading(
        factor_id="breadth_intraday",
        score=score,
        signal=score_to_signal(score),
        detail=f"UVOL/DVOL ratio: {ratio:.3f} ({label})",
        timestamp=ts,
        source="tradingview",
        raw_data=data,
        metadata={"timestamp_source": "updated_at"},
    )


def _score_breadth_ratio(ratio: float) -> float:
    """Score UVOL/DVOL ratio. Symmetric thresholds."""
    if ratio > 2.0:
        return 0.7    # Strong breadth thrust
    elif ratio > 1.5:
        return 0.4    # Healthy breadth
    elif ratio > 1.2:
        return 0.2    # Mildly positive
    elif ratio > 0.8:
        return 0.0    # Balanced / neutral
    elif ratio > 0.5:
        return -0.3   # Mild selling
    else:
        return -0.7   # Heavy selling breadth
