"""
Sahm Rule Factor — real-time recession probability indicator.

The Sahm Rule identifies recessions when the 3-month moving average of the
national unemployment rate rises by 0.50 percentage points or more relative
to its low during the previous 12 months.

Source: FRED series SAHMREALTIME
Timeframe: Macro (staleness: 168h / 1 week — monthly data)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
FRED_CACHE_KEY = "fred:SAHMREALTIME:latest"

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
    from bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal
    from backend.bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot


async def compute_score() -> Optional[FactorReading]:
    """Score based on Sahm Rule indicator from FRED."""
    fred_api_key = os.environ.get("FRED_API_KEY")
    current: Optional[float] = None
    trend = "stable"
    source = "fred"
    cache_fetched_at: Optional[str] = None

    if fred_api_key:
        try:
            from fredapi import Fred

            fred = Fred(api_key=fred_api_key)
            series = fred.get_series("SAHMREALTIME", observation_start="2024-01-01")
            if series is not None and not series.empty:
                values = series.dropna()
                current = float(values.iloc[-1])
                if len(values) >= 2:
                    previous = float(values.iloc[-2])
                    if current > previous + 0.05:
                        trend = "rising"
                    elif current < previous - 0.05:
                        trend = "falling"
                await cache_fred_snapshot(
                    FRED_CACHE_KEY,
                    {
                        "value": current,
                        "trend": trend,
                        "series": "SAHMREALTIME",
                        "fetched_at": datetime.utcnow().isoformat(),
                    },
                )
            else:
                logger.warning("sahm_rule: no data from FRED")
        except ImportError:
            logger.warning("sahm_rule: fredapi not installed")
        except Exception as e:
            logger.error(f"sahm_rule: FRED fetch failed: {e}")
    else:
        logger.debug("sahm_rule: FRED_API_KEY not configured")

    if current is None:
        cached = await load_fred_snapshot(FRED_CACHE_KEY)
        if not cached:
            return None
        try:
            current = float(cached.get("value"))
            trend = str(cached.get("trend") or "stable")
            cache_fetched_at = cached.get("fetched_at")
            source = "fred_cache"
            logger.info("sahm_rule: using cached FRED snapshot (%s)", cache_fetched_at)
        except Exception:
            return None

    score = _score_sahm(current, trend)

    if current >= 0.50:
        state = "RECESSION TRIGGERED"
    elif current >= 0.30:
        state = "warning"
    else:
        state = "clear"

    return FactorReading(
        factor_id="sahm_rule",
        score=score,
        signal=score_to_signal(score),
        detail=f"Sahm Rule: {current:.2f} ({state}, {trend})",
        timestamp=datetime.utcnow(),
        source=source,
        raw_data={"sahm_value": current, "trend": trend, "cached_fetched_at": cache_fetched_at},
    )


def _score_sahm(value: float, trend: str) -> float:
    """
    Score based on Sahm Rule value.
    Low values = no recession risk = bullish.
    >= 0.50 = recession triggered = very bearish.
    """
    if value >= 0.70:
        return -0.9
    elif value >= 0.50:
        return -0.8
    elif value >= 0.40:
        return -0.5
    elif value >= 0.30:
        return -0.3
    elif value >= 0.20:
        score = 0.0
        if trend == "rising":
            score = -0.1
        return score
    elif value >= 0.10:
        score = 0.2
        if trend == "falling":
            score = 0.3
        return score
    else:
        return 0.5  # Very low — strong labor market
