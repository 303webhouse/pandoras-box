"""
Initial Jobless Claims Factor — weekly initial unemployment claims.

The most responsive leading indicator for labor market health.
Low claims = strong employment = bullish for markets.
Rising claims = weakening labor market = bearish.

Source: FRED series ICSA
Timeframe: Macro (staleness: 168h / 1 week)
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
    """Score based on initial jobless claims from FRED."""
    fred_api_key = os.environ.get("FRED_API_KEY")
    if not fred_api_key:
        logger.debug("initial_claims: FRED_API_KEY not configured")
        return None

    try:
        from fredapi import Fred
        fred = Fred(api_key=fred_api_key)

        series = fred.get_series("ICSA", observation_start="2024-01-01")
        if series is None or series.empty:
            logger.warning("initial_claims: no data from FRED")
            return None

        values = series.dropna()
        if len(values) < 4:
            return None

        # 4-week moving average (standard way to smooth weekly noise)
        recent = values.iloc[-4:]
        avg_4w = float(recent.mean())
        latest = float(values.iloc[-1])

        # Trend: compare 4-week avg to prior 4-week avg
        trend = "stable"
        if len(values) >= 8:
            prior_avg = float(values.iloc[-8:-4].mean())
            if avg_4w > prior_avg * 1.05:
                trend = "rising"
            elif avg_4w < prior_avg * 0.95:
                trend = "falling"

        score = _score_claims(avg_4w, trend)

        # Express in thousands for readability
        avg_k = avg_4w / 1000
        latest_k = latest / 1000

        return FactorReading(
            factor_id="initial_claims",
            score=score,
            signal=score_to_signal(score),
            detail=f"Claims 4w avg: {avg_k:.0f}k (latest: {latest_k:.0f}k, {trend})",
            timestamp=datetime.utcnow(),
            source="fred",
            raw_data={
                "latest": latest,
                "avg_4w": avg_4w,
                "trend": trend,
            },
        )

    except ImportError:
        logger.warning("initial_claims: fredapi not installed")
        return None
    except Exception as e:
        logger.error(f"initial_claims: FRED fetch failed: {e}")
        return None


def _score_claims(avg_4w: float, trend: str) -> float:
    """
    Score based on 4-week average initial claims level and trend.
    Lower = stronger labor market = bullish.
    """
    # Base score from level
    if avg_4w < 200_000:
        base = 0.6
    elif avg_4w < 220_000:
        base = 0.4
    elif avg_4w < 250_000:
        base = 0.2
    elif avg_4w < 280_000:
        base = 0.0
    elif avg_4w < 300_000:
        base = -0.2
    elif avg_4w < 350_000:
        base = -0.5
    elif avg_4w < 400_000:
        base = -0.7
    else:
        base = -0.9

    # Trend modifier
    if trend == "rising":
        base -= 0.1
    elif trend == "falling":
        base += 0.1

    return max(-1.0, min(1.0, base))
