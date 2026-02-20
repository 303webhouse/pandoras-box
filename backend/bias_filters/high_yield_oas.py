"""
High Yield OAS Factor — ICE BofA US High Yield Option-Adjusted Spread.

More precise credit stress measure than HYG/TLT ratio.
Low spreads = risk-on, tight credit = bullish.
High spreads = credit stress = bearish.

Source: FRED series BAMLH0A0HYM2
Timeframe: Swing (staleness: 48h)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
FRED_CACHE_KEY = "fred:BAMLH0A0HYM2:latest"

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
    from bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal
    from backend.bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot


async def compute_score() -> Optional[FactorReading]:
    """Score based on high yield OAS spread from FRED."""
    fred_api_key = os.environ.get("FRED_API_KEY")
    if not fred_api_key:
        logger.debug("high_yield_oas: FRED_API_KEY not configured")
    oas: Optional[float] = None
    source = "fred"
    cache_fetched_at: Optional[str] = None

    if fred_api_key:
        try:
            from fredapi import Fred

            fred = Fred(api_key=fred_api_key)
            series = fred.get_series("BAMLH0A0HYM2", observation_start="2024-01-01")
            if series is not None and not series.empty:
                oas = float(series.dropna().iloc[-1])
                await cache_fred_snapshot(
                    FRED_CACHE_KEY,
                    {"value": oas, "series": "BAMLH0A0HYM2", "fetched_at": datetime.utcnow().isoformat()},
                )
            else:
                logger.warning("high_yield_oas: no data from FRED")
        except ImportError:
            logger.warning("high_yield_oas: fredapi not installed")
        except Exception as e:
            logger.error(f"high_yield_oas: FRED fetch failed: {e}")

    if oas is None:
        cached = await load_fred_snapshot(FRED_CACHE_KEY)
        if not cached:
            return None
        try:
            oas = float(cached.get("value"))
            cache_fetched_at = cached.get("fetched_at")
            source = "fred_cache"
            logger.info("high_yield_oas: using cached FRED snapshot (%s)", cache_fetched_at)
        except Exception:
            return None

    score = _score_oas(oas)
    return FactorReading(
        factor_id="high_yield_oas",
        score=score,
        signal=score_to_signal(score),
        detail=f"HY OAS: {oas:.2f}% ({'crisis' if oas > 7 else 'stress' if oas > 5 else 'caution' if oas > 4 else 'normal' if oas > 3 else 'risk-on'})",
        timestamp=datetime.utcnow(),
        source=source,
        raw_data={"oas_pct": oas, "cached_fetched_at": cache_fetched_at},
    )


def _score_oas(oas: float) -> float:
    """
    Score based on high yield OAS spread (in percentage points).
    Lower spreads = risk appetite = bullish.
    Higher spreads = credit stress = bearish.
    """
    if oas < 2.5:
        return 0.6   # Very tight — strong risk-on
    elif oas < 3.0:
        return 0.4
    elif oas < 3.5:
        return 0.2
    elif oas < 4.0:
        return 0.0
    elif oas < 4.5:
        return -0.2
    elif oas < 5.0:
        return -0.4
    elif oas < 6.0:
        return -0.6
    elif oas < 7.0:
        return -0.75
    else:
        return -0.9   # Crisis-level stress
