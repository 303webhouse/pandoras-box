"""
McClellan Oscillator Factor — NYSE breadth momentum.

Computes the difference between 19-day EMA and 39-day EMA of daily NYSE
net advances (advancing issues - declining issues). Positive = healthy
breadth momentum, negative = deteriorating breadth.

Data source: yfinance ^ADVN / ^DECLN (NYSE advancing/declining issues).
Redis history: sorted set storing daily net advance readings for EMA calc.
Staleness: 48h — swing timeframe.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

REDIS_KEY_MCCLELLAN_HISTORY = "mcclellan:net_advances:history"
REDIS_MCCLELLAN_TTL = 86400 * 60  # 60 days
MIN_HISTORY_FOR_EMA = 40  # Need at least 40 days for 39-day EMA

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal, get_price_history, neutral_reading
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal, get_price_history, neutral_reading


async def compute_score() -> Optional[FactorReading]:
    """Compute McClellan Oscillator from NYSE advance/decline data."""
    # Fetch advancing and declining issues
    advn_data = await get_price_history("^ADVN", days=60)
    decln_data = await get_price_history("^DECLN", days=60)

    if advn_data is None or advn_data.empty or decln_data is None or decln_data.empty:
        logger.warning("mcclellan: cannot fetch ADVN/DECLN data — trying Redis history")
        return await _compute_from_redis_history()

    # Extract close prices (daily values)
    advn_col = "close" if "close" in advn_data.columns else None
    decln_col = "close" if "close" in decln_data.columns else None
    if not advn_col or not decln_col:
        logger.warning("mcclellan: missing 'close' column in ADVN/DECLN data")
        return None

    advn = advn_data[advn_col].astype(float)
    decln = decln_data[decln_col].astype(float)

    # Align indices (both should be date-indexed)
    combined = pd.DataFrame({"advn": advn, "decln": decln}).dropna()
    if len(combined) < MIN_HISTORY_FOR_EMA:
        logger.info("mcclellan: insufficient data (%d days, need %d) — building baseline",
                     len(combined), MIN_HISTORY_FOR_EMA)
        # Store what we have in Redis for next time
        await _store_net_advances(combined)
        return neutral_reading(
            "mcclellan_oscillator",
            f"McClellan: building baseline ({len(combined)}/{MIN_HISTORY_FOR_EMA} days)",
            source="yfinance",
        )

    # Compute net advances
    combined["net_advances"] = combined["advn"] - combined["decln"]

    # Store in Redis for fallback
    await _store_net_advances(combined)

    # Compute McClellan Oscillator
    mcclellan = _compute_mcclellan(combined["net_advances"])
    if mcclellan is None:
        return None

    score = _score_mcclellan(mcclellan)

    if mcclellan > 100:
        label = "strong breadth thrust"
    elif mcclellan > 50:
        label = "healthy breadth momentum"
    elif mcclellan > 0:
        label = "mildly positive breadth"
    elif mcclellan > -50:
        label = "mildly negative breadth"
    elif mcclellan > -100:
        label = "weakening breadth"
    else:
        label = "severe breadth deterioration"

    logger.info("mcclellan: oscillator=%.1f (%s), score=%+.2f", mcclellan, label, score)

    return FactorReading(
        factor_id="mcclellan_oscillator",
        score=score,
        signal=score_to_signal(score),
        detail=f"McClellan Oscillator: {mcclellan:.1f} ({label})",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "mcclellan": round(mcclellan, 2),
            "latest_net_advances": round(float(combined["net_advances"].iloc[-1]), 0),
            "data_points": len(combined),
        },
    )


def _compute_mcclellan(net_advances: pd.Series) -> Optional[float]:
    """Compute McClellan Oscillator = 19-day EMA - 39-day EMA of net advances."""
    if len(net_advances) < MIN_HISTORY_FOR_EMA:
        return None

    ema_19 = net_advances.ewm(span=19, adjust=False).mean()
    ema_39 = net_advances.ewm(span=39, adjust=False).mean()
    mcclellan = ema_19 - ema_39

    return float(mcclellan.iloc[-1])


def _score_mcclellan(mcclellan: float) -> float:
    """Score McClellan Oscillator value."""
    if mcclellan > 100:
        return 0.5    # Strong breadth thrust
    elif mcclellan > 50:
        return 0.3    # Healthy momentum
    elif mcclellan > 0:
        return 0.1    # Mildly positive
    elif mcclellan > -50:
        return -0.1   # Mildly negative
    elif mcclellan > -100:
        return -0.3   # Weakening breadth
    else:
        return -0.6   # Severe deterioration


async def _store_net_advances(combined: pd.DataFrame) -> None:
    """Store daily net advance readings in Redis sorted set."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return

        for idx, row in combined.iterrows():
            ts = idx.timestamp() if hasattr(idx, 'timestamp') else datetime.utcnow().timestamp()
            entry = json.dumps({
                "net": round(float(row["net_advances"]), 0),
                "advn": round(float(row["advn"]), 0),
                "decln": round(float(row["decln"]), 0),
                "date": str(idx)[:10] if hasattr(idx, 'strftime') else str(idx),
            })
            await redis.zadd(REDIS_KEY_MCCLELLAN_HISTORY, {entry: ts})

        await redis.expire(REDIS_KEY_MCCLELLAN_HISTORY, REDIS_MCCLELLAN_TTL)

        # Trim to last 90 entries
        total = await redis.zcard(REDIS_KEY_MCCLELLAN_HISTORY)
        if total > 90:
            await redis.zremrangebyrank(REDIS_KEY_MCCLELLAN_HISTORY, 0, total - 91)

    except Exception as e:
        logger.warning("mcclellan: error storing history: %s", e)


async def _compute_from_redis_history() -> Optional[FactorReading]:
    """Fallback: compute McClellan from Redis-stored history when yfinance fails."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return None

        entries = await redis.zrangebyscore(REDIS_KEY_MCCLELLAN_HISTORY, "-inf", "+inf")
        if len(entries) < MIN_HISTORY_FOR_EMA:
            logger.info("mcclellan: Redis history too short (%d entries)", len(entries))
            return None

        net_advances = []
        for entry in entries:
            data = json.loads(entry)
            net_advances.append(float(data["net"]))

        series = pd.Series(net_advances)
        mcclellan = _compute_mcclellan(series)
        if mcclellan is None:
            return None

        score = _score_mcclellan(mcclellan)
        logger.info("mcclellan (redis fallback): oscillator=%.1f, score=%+.2f", mcclellan, score)

        return FactorReading(
            factor_id="mcclellan_oscillator",
            score=score,
            signal=score_to_signal(score),
            detail=f"McClellan Oscillator: {mcclellan:.1f} (from cached history, {len(entries)} days)",
            timestamp=datetime.utcnow(),
            source="redis_cache",
            raw_data={
                "mcclellan": round(mcclellan, 2),
                "data_points": len(entries),
                "source": "redis_fallback",
            },
            metadata={"timestamp_source": "fallback"},
        )

    except Exception as e:
        logger.warning("mcclellan: Redis fallback failed: %s", e)
        return None
