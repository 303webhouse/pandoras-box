"""
ISM Manufacturing PMI Factor — leading economic indicator.

ISM Manufacturing PMI above 50 indicates economic expansion.
Below 50 indicates contraction. This is a monthly indicator.

Source: FRED series NAPM (ISM Manufacturing PMI)
        Falls back to MANEMP (ISM Manufacturing Employment) if NAPM unavailable.
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
    """Score based on ISM Manufacturing data from FRED."""
    fred_api_key = os.environ.get("FRED_API_KEY")
    pmi_value: Optional[float] = None
    source_series: Optional[str] = None
    source = "fred"
    cache_fetched_at: Optional[str] = None

    if fred_api_key:
        try:
            from fredapi import Fred

            fred = Fred(api_key=fred_api_key)

            for series_id in ["NAPM", "MANEMP"]:
                try:
                    series = fred.get_series(series_id, observation_start="2024-01-01")
                    if series is not None and not series.empty:
                        pmi_value = float(series.dropna().iloc[-1])
                        source_series = series_id
                        break
                except Exception:
                    continue

            if pmi_value is not None:
                await cache_fred_snapshot(
                    FRED_CACHE_KEY,
                    {
                        "value": pmi_value,
                        "series": source_series,
                        "fetched_at": datetime.utcnow().isoformat(),
                    },
                )
            else:
                logger.warning("ism_manufacturing: no data from FRED (tried NAPM, MANEMP)")
        except ImportError:
            logger.warning("ism_manufacturing: fredapi not installed")
        except Exception as e:
            logger.error(f"ism_manufacturing: FRED fetch failed: {e}")
    else:
        logger.debug("ism_manufacturing: FRED_API_KEY not configured")

    if pmi_value is None:
        cached = await load_fred_snapshot(FRED_CACHE_KEY)
        if not cached:
            return None
        try:
            pmi_value = float(cached.get("value"))
            source_series = str(cached.get("series") or "cached")
            cache_fetched_at = cached.get("fetched_at")
            source = "fred_cache"
            logger.info("ism_manufacturing: using cached FRED snapshot (%s)", cache_fetched_at)
        except Exception:
            return None

    score = _score_ism(pmi_value)

    if pmi_value >= 55:
        state = "strong expansion"
    elif pmi_value >= 50:
        state = "expansion"
    elif pmi_value >= 47:
        state = "contraction risk"
    elif pmi_value >= 45:
        state = "contraction"
    else:
        state = "deep contraction"

    return FactorReading(
        factor_id="ism_manufacturing",
        score=score,
        signal=score_to_signal(score),
        detail=f"ISM Mfg ({source_series}): {pmi_value:.1f} ({state})",
        timestamp=datetime.utcnow(),
        source=source,
        raw_data={"pmi_value": pmi_value, "series": source_series, "cached_fetched_at": cache_fetched_at},
    )


def _score_ism(pmi: float) -> float:
    """
    Score based on ISM Manufacturing PMI.
    Above 50 = expansion = bullish.
    Below 50 = contraction = bearish.
    """
    if pmi >= 58:
        return 0.7
    elif pmi >= 55:
        return 0.5
    elif pmi >= 52:
        return 0.3
    elif pmi >= 50:
        return 0.1
    elif pmi >= 48:
        return -0.15
    elif pmi >= 46:
        return -0.3
    elif pmi >= 44:
        return -0.5
    elif pmi >= 42:
        return -0.7
    else:
        return -0.9
