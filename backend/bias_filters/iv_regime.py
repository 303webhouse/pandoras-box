"""
IV Regime Factor — VIX-based implied volatility rank for options pricing context.

Tracks VIX (SPY 30-day implied volatility) and computes IV rank against a
20-day rolling history stored in Redis. High IV rank = expensive options =
caution for debit strategies. Low IV rank = cheap options = favorable.

Data source: VIX via yfinance (real-time).
Staleness: 24h — swing timeframe.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

REDIS_KEY_IV_HISTORY = "iv_regime:vix_history"
REDIS_KEY_IV_LATEST = "iv_regime:vix_latest"
REDIS_IV_HISTORY_TTL = 86400 * 30  # 30 days
IV_HISTORY_LOOKBACK = 20  # 20 data points for rank calculation

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal, get_latest_price
except ImportError:
    FactorReading = None
    score_to_signal = None
    get_latest_price = None


async def _get_vix() -> Optional[float]:
    """Get current VIX level (SPY 30-day implied volatility)."""
    try:
        if get_latest_price:
            vix = await get_latest_price("^VIX")
            if vix and vix > 0:
                return float(vix)
    except Exception as e:
        logger.warning("iv_regime: failed to get VIX: %s", e)
    return None


async def _get_iv_history() -> List[float]:
    """Load VIX history from Redis sorted set."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return []

        entries = await redis.zrangebyscore(REDIS_KEY_IV_HISTORY, "-inf", "+inf")
        return [float(json.loads(e)["vix"]) for e in entries]
    except Exception as e:
        logger.warning("iv_regime: failed to load VIX history: %s", e)
        return []


async def _store_vix_reading(vix: float) -> None:
    """Append current VIX reading to Redis sorted set (keyed by timestamp)."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return

        now = datetime.utcnow()
        entry = json.dumps({"vix": round(vix, 2), "ts": now.isoformat()})
        await redis.zadd(REDIS_KEY_IV_HISTORY, {entry: now.timestamp()})
        await redis.expire(REDIS_KEY_IV_HISTORY, REDIS_IV_HISTORY_TTL)

        # Trim to last 30 entries (keep ~30 days of daily readings)
        total = await redis.zcard(REDIS_KEY_IV_HISTORY)
        if total > 30:
            await redis.zremrangebyrank(REDIS_KEY_IV_HISTORY, 0, total - 31)
    except Exception as e:
        logger.warning("iv_regime: failed to store VIX reading: %s", e)


def _compute_iv_rank(current: float, history: List[float]) -> Optional[float]:
    """
    IV Rank = (current - min) / (max - min) * 100.
    Returns percentile 0-100, or None if insufficient history.
    """
    if len(history) < 5:
        return None

    iv_min = min(history)
    iv_max = max(history)

    if iv_max == iv_min:
        return 50.0  # All readings identical

    return ((current - iv_min) / (iv_max - iv_min)) * 100


async def compute_score() -> Optional[FactorReading]:
    """
    Compute IV regime score from VIX rank.
    High VIX rank = expensive options = caution for debit strategies.
    Low VIX rank = cheap options = favorable environment.
    """
    vix = await _get_vix()
    if not vix:
        logger.warning("iv_regime: cannot get VIX — skipping")
        return None

    # Store this reading and load history
    await _store_vix_reading(vix)
    history = await _get_iv_history()

    iv_rank = _compute_iv_rank(vix, history)
    if iv_rank is None:
        logger.info("iv_regime: insufficient history (%d readings) — building baseline", len(history))
        return FactorReading(
            factor_id="iv_regime",
            score=0.0,
            signal="NEUTRAL",
            detail=f"IV regime: building baseline ({len(history)}/{IV_HISTORY_LOOKBACK} readings, VIX {vix:.1f})",
            timestamp=datetime.utcnow(),
            source="yfinance",
            raw_data={
                "vix": round(vix, 2),
                "history_count": len(history),
                "iv_rank": None,
            },
        )

    score = _score_iv_rank(iv_rank)

    if iv_rank > 80:
        label = "high IV regime (expensive options)"
    elif iv_rank > 60:
        label = "above-average IV"
    elif iv_rank > 40:
        label = "normal IV"
    elif iv_rank > 20:
        label = "below-average IV"
    else:
        label = "low IV regime (cheap options)"

    logger.info("iv_regime: VIX=%.1f, rank=%.0f%% (%s), score=%+.2f", vix, iv_rank, label, score)

    return FactorReading(
        factor_id="iv_regime",
        score=score,
        signal=score_to_signal(score),
        detail=f"IV rank: {iv_rank:.0f}% (VIX {vix:.1f}, {label})",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={
            "vix": round(vix, 2),
            "iv_rank": round(iv_rank, 1),
            "history_count": len(history),
            "vix_min": round(min(history), 2) if history else None,
            "vix_max": round(max(history), 2) if history else None,
        },
    )


def _score_iv_rank(iv_rank: float) -> float:
    """
    Score based on IV rank percentile.
    High IV rank = expensive options = caution for debit strategies.
    Low IV rank = cheap options = favorable environment.
    """
    if iv_rank > 80:
        return -0.3   # Expensive options — caution
    elif iv_rank > 60:
        return -0.1   # Slightly elevated
    elif iv_rank > 40:
        return 0.0    # Normal
    elif iv_rank > 20:
        return 0.1    # Below average — mildly favorable
    else:
        return 0.2    # Cheap options — favorable for debit
