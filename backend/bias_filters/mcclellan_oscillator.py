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
    """Compute McClellan Oscillator from NYSE advance/decline data.

    Data source priority:
    1. Direct ADVN/DECLN from yfinance (ideal, but Yahoo dropped these symbols)
    2. NYSE Composite (^NYA) daily returns as breadth proxy
    3. Redis history from prior /webhook/mcclellan calls
    """
    # --- Source 1: Direct ADVN/DECLN (may return in future) ---
    combined = await _try_advn_decln()
    source_label = "yfinance"

    # --- Source 2: NYSE Composite proxy ---
    if combined is None or len(combined) < MIN_HISTORY_FOR_EMA:
        combined = await _try_nyse_proxy()
        source_label = "nyse_proxy"

    # --- Source 3: Redis history fallback ---
    if combined is None or len(combined) < MIN_HISTORY_FOR_EMA:
        logger.info("mcclellan: ADVN/DECLN and NYSE proxy unavailable — trying Redis history")
        return await _compute_from_redis_history()

    # Compute net advances column if not present
    if "net_advances" not in combined.columns:
        combined["net_advances"] = combined["advn"] - combined["decln"]

    # Store in Redis for fallback
    await _store_net_advances(combined)

    # Compute McClellan Oscillator
    mcclellan = _compute_mcclellan(combined["net_advances"])
    if mcclellan is None:
        return None

    score = _score_mcclellan(mcclellan)
    label = _label_mcclellan(mcclellan)
    logger.info("mcclellan: oscillator=%.1f (%s), score=%+.2f [%s]", mcclellan, label, score, source_label)

    return FactorReading(
        factor_id="mcclellan_oscillator",
        score=score,
        signal=score_to_signal(score),
        detail=f"McClellan Oscillator: {mcclellan:.1f} ({label})",
        timestamp=datetime.utcnow(),
        source=source_label,
        raw_data={
            "mcclellan": round(mcclellan, 2),
            "latest_net_advances": round(float(combined["net_advances"].iloc[-1]), 0),
            "data_points": len(combined),
        },
    )


async def _try_advn_decln() -> Optional[pd.DataFrame]:
    """Try fetching raw NYSE advancing/declining issue counts from yfinance."""
    advn_symbols = ["^ADVN", "^ADV", "ADVN"]
    decln_symbols = ["^DECLN", "^DEC", "DECLN"]

    advn_data = None
    for sym in advn_symbols:
        advn_data = await get_price_history(sym, days=60)
        if advn_data is not None and not advn_data.empty and "close" in advn_data.columns:
            break
        advn_data = None

    decln_data = None
    for sym in decln_symbols:
        decln_data = await get_price_history(sym, days=60)
        if decln_data is not None and not decln_data.empty and "close" in decln_data.columns:
            break
        decln_data = None

    if advn_data is None or decln_data is None:
        return None

    advn_vals = advn_data["close"].astype(float).dropna().reset_index(drop=True)
    decln_vals = decln_data["close"].astype(float).dropna().reset_index(drop=True)
    min_len = min(len(advn_vals), len(decln_vals))
    if min_len < 5:
        return None

    combined = pd.DataFrame({
        "advn": advn_vals.iloc[-min_len:].values,
        "decln": decln_vals.iloc[-min_len:].values,
    })
    combined["net_advances"] = combined["advn"] - combined["decln"]
    logger.debug("mcclellan: ADVN/DECLN fetched (%d rows)", len(combined))
    return combined


async def _try_nyse_proxy() -> Optional[pd.DataFrame]:
    """Derive breadth proxy from NYSE Composite (^NYA) daily returns.

    Uses daily return magnitude as a proxy for net advance/decline breadth.
    Positive return days approximate net advances, negative days net declines.
    The scale is normalized to ~1000 issues range (typical NYSE A-D range).
    """
    nya_data = await get_price_history("^NYA", days=70)
    if nya_data is None or nya_data.empty or "close" not in nya_data.columns:
        return None

    close = nya_data["close"].astype(float).dropna()
    if len(close) < MIN_HISTORY_FOR_EMA + 1:
        return None

    # Daily returns as breadth proxy, scaled to typical NYSE A-D magnitude
    returns = close.pct_change().dropna()
    # Scale: 1% move ~ 500 net advances (typical NYSE has ~3000 issues)
    proxy_net = (returns * 50000).reset_index(drop=True)

    combined = pd.DataFrame({
        "advn": proxy_net.clip(lower=0).values,
        "decln": (-proxy_net.clip(upper=0)).values,
        "net_advances": proxy_net.values,
    })
    logger.debug("mcclellan: NYSE proxy computed (%d rows)", len(combined))
    return combined


def _compute_mcclellan(net_advances: pd.Series) -> Optional[float]:
    """Compute McClellan Oscillator = 19-day EMA - 39-day EMA of net advances."""
    if len(net_advances) < MIN_HISTORY_FOR_EMA:
        return None

    ema_19 = net_advances.ewm(span=19, adjust=False).mean()
    ema_39 = net_advances.ewm(span=39, adjust=False).mean()
    mcclellan = ema_19 - ema_39

    return float(mcclellan.iloc[-1])


def _label_mcclellan(mcclellan: float) -> str:
    """Human-readable label for McClellan value."""
    if mcclellan > 100:
        return "strong breadth thrust"
    elif mcclellan > 50:
        return "healthy breadth momentum"
    elif mcclellan > 0:
        return "mildly positive breadth"
    elif mcclellan > -50:
        return "mildly negative breadth"
    elif mcclellan > -100:
        return "weakening breadth"
    else:
        return "severe breadth deterioration"


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
