"""
ISM Manufacturing PMI Factor — leading economic indicator.

ISM Manufacturing PMI above 50 indicates economic expansion.
Below 50 indicates contraction. This is a monthly indicator.

Source: FRED series MANEMP (ISM Manufacturing Employment Index)
        Falls back to NAPM (ISM PMI) if MANEMP unavailable.
Timeframe: Macro (staleness: 720h / 30 days — monthly data)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal


async def compute_score() -> Optional[FactorReading]:
    """Score based on ISM Manufacturing data from FRED."""
    fred_api_key = os.environ.get("FRED_API_KEY")
    if not fred_api_key:
        logger.debug("ism_manufacturing: FRED_API_KEY not configured")
        return None

    try:
        from fredapi import Fred
        fred = Fred(api_key=fred_api_key)

        # Try MANEMP first (ISM Manufacturing Employment), then NAPM (ISM PMI)
        pmi_value = None
        source_series = None

        for series_id in ["MANEMP", "NAPM"]:
            try:
                series = fred.get_series(series_id, observation_start="2024-01-01")
                if series is not None and not series.empty:
                    pmi_value = float(series.dropna().iloc[-1])
                    source_series = series_id
                    break
            except Exception:
                continue

        if pmi_value is None:
            logger.warning("ism_manufacturing: no data from FRED (tried MANEMP, NAPM)")
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
            source="fred",
            raw_data={"pmi_value": pmi_value, "series": source_series},
        )

    except ImportError:
        logger.warning("ism_manufacturing: fredapi not installed")
        return None
    except Exception as e:
        logger.error(f"ism_manufacturing: FRED fetch failed: {e}")
        return None


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
