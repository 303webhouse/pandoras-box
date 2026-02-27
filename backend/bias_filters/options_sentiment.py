"""
Options Sentiment Factor — scores UW Market Tide data for the composite bias engine.

Data source: Unusual Whales Market Tide via Pivot Discord bot.
Posts arrive at /bias/uw/market_tide 3x/day during market hours (9:35 AM, 12:00 PM, 3:30 PM ET).

This is a CONTRARIAN indicator:
- Extreme bullish consensus → bearish score (crowd is often wrong at extremes)
- Extreme bearish consensus → bullish score
- Moderate readings → directional score following the tide
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
REDIS_KEY_MARKET_TIDE = "uw:market_tide:latest"

# Import FactorReading and helpers from composite engine
try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal


async def compute_score(tide_data: Optional[Dict[str, Any]] = None) -> Optional[FactorReading]:
    """
    Score options sentiment from UW Market Tide data.

    If tide_data is not provided, tries to read from the in-memory store.
    """
    if tide_data is None:
        tide_data = await _get_latest_tide()

    if not tide_data:
        logger.warning("Options sentiment: no Market Tide data available — excluding from composite")
        return None

    sentiment = (tide_data.get("sentiment") or "").upper()
    bullish_pct = tide_data.get("bullish_pct")
    bearish_pct = tide_data.get("bearish_pct")
    call_premium = tide_data.get("call_premium") or 0
    put_premium = tide_data.get("put_premium") or 0

    score = _compute_tide_score(sentiment, bullish_pct, bearish_pct, call_premium, put_premium)

    # Build detail string
    parts = [f"Sentiment: {sentiment}"]
    if bullish_pct is not None:
        parts.append(f"Bull {bullish_pct:.0f}%")
    if bearish_pct is not None:
        parts.append(f"Bear {bearish_pct:.0f}%")
    if call_premium or put_premium:
        net = call_premium - put_premium
        parts.append(f"Net premium: {'call' if net > 0 else 'put'} ${abs(net):,.0f}")
    detail = ", ".join(parts)
    source_timestamp, timestamp_source = _extract_source_timestamp(tide_data)
    if timestamp_source == "fallback":
        logger.warning(
            "No source timestamp for options_sentiment; using utcnow fallback (staleness reliability reduced)"
        )

    return FactorReading(
        factor_id="options_sentiment",
        score=score,
        signal=score_to_signal(score),
        detail=detail,
        timestamp=source_timestamp,
        source="unusual_whales",
        raw_data=tide_data,
        metadata={"timestamp_source": timestamp_source},
    )


def _compute_tide_score(
    sentiment: str,
    bullish_pct: Optional[float],
    bearish_pct: Optional[float],
    call_premium: int,
    put_premium: int,
) -> float:
    """
    Scoring logic — blends sentiment label with percentage data.

    The indicator is contrarian at extremes:
    - > 70% bullish → contrarian bearish (score negative)
    - > 70% bearish → contrarian bullish (score positive)
    - Moderate readings follow the direction
    """
    score = 0.0

    # Primary: use percentage data if available (more granular)
    if bullish_pct is not None and bearish_pct is not None:
        diff = bullish_pct - bearish_pct  # range roughly -100 to +100

        if bullish_pct >= 70:
            # Extreme bullish consensus → contrarian bearish
            score = -0.3 - (bullish_pct - 70) / 100  # -0.3 to -0.6
        elif bearish_pct >= 70:
            # Extreme bearish consensus → contrarian bullish
            score = 0.3 + (bearish_pct - 70) / 100  # +0.3 to +0.6
        else:
            # Moderate: follow the tide direction, scaled gently
            score = diff / 200  # range: -0.5 to +0.5
    else:
        # Fallback: use sentiment label only
        label_scores = {
            "STRONGLY_BULLISH": -0.4,   # Contrarian at extreme
            "BULLISH": 0.2,
            "NEUTRAL": 0.0,
            "BEARISH": -0.2,
            "STRONGLY_BEARISH": 0.4,    # Contrarian at extreme
        }
        score = label_scores.get(sentiment, 0.0)

    # Secondary: net premium direction as a small modifier
    if call_premium and put_premium:
        total = call_premium + put_premium
        if total > 0:
            net_ratio = (call_premium - put_premium) / total  # -1 to +1
            # At extremes, contrarian; at moderate levels, follow
            if abs(net_ratio) > 0.6:
                premium_mod = -net_ratio * 0.15  # Contrarian
            else:
                premium_mod = net_ratio * 0.1  # Follow
            score += premium_mod

    return max(-1.0, min(1.0, score))


async def _get_latest_tide() -> Optional[Dict[str, Any]]:
    """Read latest Market Tide from in-memory store, then Redis fallback."""
    try:
        from api.uw_integration import get_uw_data
        data = get_uw_data()
        market_tide = data.get("market_tide")
        if market_tide:
            return market_tide
    except Exception:
        pass

    try:
        from backend.api.uw_integration import get_uw_data
        data = get_uw_data()
        market_tide = data.get("market_tide")
        if market_tide:
            return market_tide
    except Exception:
        pass

    # Process-resilient fallback for restarts.
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            raw = await redis.get(REDIS_KEY_MARKET_TIDE)
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass

    return None


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
