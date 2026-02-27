"""
IV Regime Factor — SPY implied volatility rank from Polygon options chain.

Tracks aggregate NTM IV and computes IV rank against a 20-day rolling history
stored in Redis. High IV rank = expensive options = caution. Low IV rank =
cheap options = favorable for debit strategies.

Data source: Polygon /v3/snapshot/options/SPY (15-min delayed, Starter plan).
Staleness: 24h — swing timeframe.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

REDIS_KEY_IV_HISTORY = "iv_regime:spy_iv_history"
REDIS_KEY_IV_LATEST = "iv_regime:spy_iv_latest"
REDIS_IV_HISTORY_TTL = 86400 * 30  # 30 days
IV_HISTORY_LOOKBACK = 20  # 20 data points for rank calculation

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal, get_price_history
    from integrations.polygon_options import get_options_snapshot, POLYGON_API_KEY
except ImportError:
    FactorReading = None
    score_to_signal = None
    get_options_snapshot = None
    get_price_history = None
    POLYGON_API_KEY = ""


async def _get_spy_price() -> Optional[float]:
    """Get current SPY price for NTM filtering."""
    try:
        if get_price_history:
            data = await get_price_history("SPY", days=5)
            if data is not None and not data.empty and "close" in data.columns:
                return float(data["close"].iloc[-1])
    except Exception as e:
        logger.warning("iv_regime: failed to get SPY price: %s", e)
    return None


async def _compute_aggregate_iv(spy_price: float) -> Optional[float]:
    """
    Compute aggregate NTM IV from Polygon SPY chain.
    Uses VWAP of available IVs weighted by open interest.
    Falls back to simple average if OI is unavailable.
    """
    strike_lo = round(spy_price * 0.90, 0)  # ±10% NTM (wider to ensure enough IV data)
    strike_hi = round(spy_price * 1.10, 0)

    chain = await get_options_snapshot(
        "SPY",
        strike_gte=strike_lo,
        strike_lte=strike_hi,
    )
    if not chain:
        return None

    today = datetime.utcnow().date()
    min_exp = today + timedelta(days=7)
    max_exp = today + timedelta(days=60)

    ivs = []
    iv_missing = 0

    for contract in chain:
        details = contract.get("details", {})
        expiry_str = str(details.get("expiration_date", ""))[:10]

        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (min_exp <= expiry <= max_exp):
            continue

        iv = contract.get("implied_volatility")
        if iv is None:
            greeks = contract.get("greeks") or {}
            iv = greeks.get("iv") or greeks.get("implied_volatility")

        if iv is None or iv <= 0:
            iv_missing += 1
            continue

        ivs.append(float(iv))

    if iv_missing > 0:
        logger.debug("iv_regime: %d/%d NTM contracts missing IV", iv_missing, len(chain))

    if len(ivs) < 5:
        logger.warning("iv_regime: insufficient NTM contracts with IV (%d) — skipping", len(ivs))
        return None

    return sum(ivs) / len(ivs)


async def _get_iv_history() -> List[float]:
    """Load IV history from Redis sorted set."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return []

        entries = await redis.zrangebyscore(REDIS_KEY_IV_HISTORY, "-inf", "+inf")
        return [float(json.loads(e)["iv"]) for e in entries]
    except Exception as e:
        logger.warning("iv_regime: failed to load IV history: %s", e)
        return []


async def _store_iv_reading(iv: float) -> None:
    """Append current IV reading to Redis sorted set (keyed by timestamp)."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return

        now = datetime.utcnow()
        entry = json.dumps({"iv": round(iv, 6), "ts": now.isoformat()})
        await redis.zadd(REDIS_KEY_IV_HISTORY, {entry: now.timestamp()})
        await redis.expire(REDIS_KEY_IV_HISTORY, REDIS_IV_HISTORY_TTL)

        # Trim to last 30 entries (keep ~30 days of daily readings)
        total = await redis.zcard(REDIS_KEY_IV_HISTORY)
        if total > 30:
            await redis.zremrangebyrank(REDIS_KEY_IV_HISTORY, 0, total - 31)
    except Exception as e:
        logger.warning("iv_regime: failed to store IV reading: %s", e)


def _compute_iv_rank(current_iv: float, history: List[float]) -> Optional[float]:
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

    return ((current_iv - iv_min) / (iv_max - iv_min)) * 100


async def compute_score() -> Optional[FactorReading]:
    """
    Compute IV regime score from SPY aggregate IV rank.
    High IV rank = expensive options = caution.
    Low IV rank = cheap options = favorable for debit.
    """
    if not POLYGON_API_KEY:
        logger.warning("iv_regime: POLYGON_API_KEY not set — skipping")
        return None

    spy_price = await _get_spy_price()
    if not spy_price:
        logger.warning("iv_regime: cannot determine SPY price — skipping")
        return None

    current_iv = await _compute_aggregate_iv(spy_price)
    if current_iv is None:
        logger.warning("iv_regime: failed to compute aggregate IV — skipping")
        return None

    # Store this reading and load history
    await _store_iv_reading(current_iv)
    history = await _get_iv_history()

    iv_rank = _compute_iv_rank(current_iv, history)
    if iv_rank is None:
        logger.info("iv_regime: insufficient history (%d readings) — building baseline", len(history))
        return FactorReading(
            factor_id="iv_regime",
            score=0.0,
            signal="NEUTRAL",
            detail=f"IV regime: building baseline ({len(history)}/{IV_HISTORY_LOOKBACK} readings, current IV {current_iv:.1%})",
            timestamp=datetime.utcnow(),
            source="polygon",
            raw_data={
                "current_iv": round(current_iv, 6),
                "history_count": len(history),
                "iv_rank": None,
                "spy_price": round(spy_price, 2),
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

    logger.info("iv_regime: IV=%0.1f%%, rank=%.0f%% (%s), score=%+.2f", current_iv * 100, iv_rank, label, score)

    return FactorReading(
        factor_id="iv_regime",
        score=score,
        signal=score_to_signal(score),
        detail=f"SPY IV rank: {iv_rank:.0f}% (IV {current_iv:.1%}, {label})",
        timestamp=datetime.utcnow(),
        source="polygon",
        raw_data={
            "current_iv": round(current_iv, 6),
            "iv_rank": round(iv_rank, 1),
            "history_count": len(history),
            "iv_min": round(min(history), 6) if history else None,
            "iv_max": round(max(history), 6) if history else None,
            "spy_price": round(spy_price, 2),
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
