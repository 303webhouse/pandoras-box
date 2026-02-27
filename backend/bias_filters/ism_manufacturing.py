"""
Manufacturing Health Factor — leading economic indicator via employment trends.

NAPM (ISM Manufacturing PMI) was removed from FRED in 2016. We use MANEMP
(All Employees, Manufacturing) as a proxy — rising manufacturing employment
signals expansion, declining signals contraction. Scored on 12-month YoY change.

Source: FRED series MANEMP (All Employees, Manufacturing, thousands)
Timeframe: Macro (staleness: 720h / 30 days — monthly data)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
FRED_CACHE_KEY = "fred:ISM_MANUFACTURING:latest"

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
    from bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal
    from backend.bias_filters.fred_cache import cache_fred_snapshot, load_fred_snapshot


async def compute_score() -> Optional[FactorReading]:
    """Score based on manufacturing employment trend from FRED (MANEMP)."""
    fred_api_key = os.environ.get("FRED_API_KEY")
    yoy_pct: Optional[float] = None
    latest_value: Optional[float] = None
    source = "fred"
    cache_fetched_at: Optional[str] = None

    if fred_api_key:
        try:
            from fredapi import Fred

            fred = Fred(api_key=fred_api_key)

            # Fetch 14 months of data to compute YoY change
            series = fred.get_series("MANEMP", observation_start="2024-10-01")
            if series is not None and not series.empty:
                clean = series.dropna()
                if len(clean) >= 2:
                    latest_value = float(clean.iloc[-1])
                    # Find reading ~12 months ago (monthly data, so index -12 or -13)
                    if len(clean) >= 12:
                        year_ago = float(clean.iloc[-12])
                    else:
                        year_ago = float(clean.iloc[0])
                    if year_ago > 0:
                        yoy_pct = ((latest_value - year_ago) / year_ago) * 100

            if yoy_pct is not None:
                await cache_fred_snapshot(
                    FRED_CACHE_KEY,
                    {
                        "yoy_pct": yoy_pct,
                        "latest_value": latest_value,
                        "series": "MANEMP",
                        "fetched_at": datetime.utcnow().isoformat(),
                    },
                )
            else:
                logger.warning("ism_manufacturing: insufficient MANEMP data for YoY calculation")
        except ImportError:
            logger.warning("ism_manufacturing: fredapi not installed")
        except Exception as e:
            logger.error("ism_manufacturing: FRED fetch failed: %s", e)
    else:
        logger.debug("ism_manufacturing: FRED_API_KEY not configured")

    if yoy_pct is None:
        cached = await load_fred_snapshot(FRED_CACHE_KEY)
        if not cached:
            return None
        try:
            yoy_pct = float(cached.get("yoy_pct"))
            latest_value = float(cached.get("latest_value") or 0)
            cache_fetched_at = cached.get("fetched_at")
            source = "fred_cache"
            logger.info("ism_manufacturing: using cached FRED snapshot (%s)", cache_fetched_at)
        except Exception:
            return None

    score = _score_mfg_employment(yoy_pct)

    if yoy_pct >= 2.0:
        state = "strong expansion"
    elif yoy_pct >= 0.5:
        state = "expansion"
    elif yoy_pct >= -0.5:
        state = "flat"
    elif yoy_pct >= -2.0:
        state = "contraction"
    else:
        state = "deep contraction"

    latest_k = f"{latest_value / 1000:.1f}M" if latest_value else "?"

    return FactorReading(
        factor_id="ism_manufacturing",
        score=score,
        signal=score_to_signal(score),
        detail=f"Mfg Employment: {latest_k}, YoY {yoy_pct:+.1f}% ({state})",
        timestamp=datetime.utcnow(),
        source=source,
        raw_data={
            "yoy_pct": round(yoy_pct, 2),
            "latest_value": latest_value,
            "series": "MANEMP",
            "cached_fetched_at": cache_fetched_at,
        },
    )


def _score_mfg_employment(yoy_pct: float) -> float:
    """
    Score manufacturing employment YoY change.
    Rising employment = expansion = bullish.
    Declining employment = contraction = bearish.
    """
    if yoy_pct >= 3.0:
        return 0.7   # Strong hiring = robust expansion
    elif yoy_pct >= 1.5:
        return 0.5
    elif yoy_pct >= 0.5:
        return 0.3
    elif yoy_pct >= 0.0:
        return 0.1   # Barely growing
    elif yoy_pct >= -0.5:
        return -0.1  # Flat/stagnating
    elif yoy_pct >= -1.5:
        return -0.3  # Mild contraction
    elif yoy_pct >= -3.0:
        return -0.5  # Moderate contraction
    elif yoy_pct >= -5.0:
        return -0.7  # Severe contraction
    else:
        return -0.9  # Recession-level decline
