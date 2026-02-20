"""
Yield Curve Factor — 10Y minus 2Y Treasury spread.

The single best recession predictor. An inverted yield curve (negative spread)
has preceded every US recession since 1955 with only one false positive.

Source: FRED series T10Y2Y
Timeframe: Macro (staleness: 72h)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
FRED_CACHE_KEY = "fred:T10Y2Y:latest"

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
    from bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal
    from backend.bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot


async def compute_score() -> Optional[FactorReading]:
    """Score based on 10Y-2Y Treasury spread from FRED."""
    fred_api_key = os.environ.get("FRED_API_KEY")
    spread: Optional[float] = None
    source = "fred"
    cache_fetched_at: Optional[str] = None

    if fred_api_key:
        try:
            from fredapi import Fred

            fred = Fred(api_key=fred_api_key)
            series = fred.get_series("T10Y2Y", observation_start="2024-01-01")
            if series is not None and not series.empty:
                spread = float(series.dropna().iloc[-1])
                await cache_fred_snapshot(
                    FRED_CACHE_KEY,
                    {"value": spread, "series": "T10Y2Y", "fetched_at": datetime.utcnow().isoformat()},
                )
            else:
                logger.warning("yield_curve: no data from FRED")
        except ImportError:
            logger.warning("yield_curve: fredapi not installed")
        except Exception as e:
            logger.error(f"yield_curve: FRED fetch failed: {e}")
    else:
        logger.debug("yield_curve: FRED_API_KEY not configured")

    if spread is None:
        cached = await load_fred_snapshot(FRED_CACHE_KEY)
        if not cached:
            return None
        try:
            spread = float(cached.get("value"))
            cache_fetched_at = cached.get("fetched_at")
            source = "fred_cache"
            logger.info("yield_curve: using cached FRED snapshot (%s)", cache_fetched_at)
        except Exception:
            return None

    score = _score_yield_curve(spread)

    if spread > 0:
        state = "normal"
    elif spread > -0.5:
        state = "flat/warning"
    else:
        state = "inverted"

    return FactorReading(
        factor_id="yield_curve",
        score=score,
        signal=score_to_signal(score),
        detail=f"10Y-2Y spread: {spread:+.2f}% ({state})",
        timestamp=datetime.utcnow(),
        source=source,
        raw_data={"spread_pct": spread, "cached_fetched_at": cache_fetched_at},
    )


def _score_yield_curve(spread: float) -> float:
    """
    Score based on 10Y-2Y spread.
    Positive spread = normal = bullish.
    Negative spread = inverted = recessionary.
    """
    if spread > 1.5:
        return 0.7
    elif spread > 1.0:
        return 0.5
    elif spread > 0.5:
        return 0.3
    elif spread > 0.0:
        return 0.1
    elif spread > -0.25:
        return -0.2
    elif spread > -0.5:
        return -0.4
    elif spread > -1.0:
        return -0.6
    else:
        return -0.8
