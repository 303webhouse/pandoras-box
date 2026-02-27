"""
Composite bias factor scoring orchestrator.
"""

from __future__ import annotations

import logging
from typing import Dict

from bias_engine.composite import (
    FactorReading, get_latest_reading, store_factor_reading,
    REDIS_KEY_FACTOR_LATEST,
)
from bias_engine.anomaly_alerts import send_alert

logger = logging.getLogger(__name__)

# Pivot collector is the single source of truth for these factors.
# Backend scorer intentionally does not write these keys.
PIVOT_OWNED_FACTORS = {
    "credit_spreads",
    "market_breadth",
    "vix_term",
    "tick_breadth",
    "sector_rotation",
    "excess_cape",
    "savita",
}


async def score_all_factors() -> Dict[str, FactorReading]:
    """Run all configured factor scoring functions."""
    results: Dict[str, FactorReading] = {}

    scorers = {
        # Intraday (5)
        "vix_term": "bias_filters.vix_term_structure",
        "tick_breadth": "bias_filters.tick_breadth",
        "vix_regime": "bias_filters.vix_regime",
        "spy_trend_intraday": "bias_filters.spy_trend_intraday",
        "breadth_intraday": "bias_filters.breadth_intraday",
        # Swing (9)
        "credit_spreads": "bias_filters.credit_spreads",
        "market_breadth": "bias_filters.market_breadth",
        "sector_rotation": "bias_filters.sector_rotation",
        "spy_200sma_distance": "bias_filters.spy_200sma_distance",
        "high_yield_oas": "bias_filters.high_yield_oas",
        "put_call_ratio": "bias_filters.put_call_ratio",
        "polygon_pcr": "bias_filters.polygon_pcr",
        "polygon_oi_ratio": "bias_filters.polygon_oi_ratio",
        "iv_regime": "bias_filters.iv_regime",
        # Macro (8)
        "yield_curve": "bias_filters.yield_curve",
        "initial_claims": "bias_filters.initial_claims",
        "sahm_rule": "bias_filters.sahm_rule",
        "copper_gold_ratio": "bias_filters.copper_gold_ratio",
        "excess_cape": "bias_filters.excess_cape_yield",
        "ism_manufacturing": "bias_filters.ism_manufacturing",
        "savita": "bias_filters.savita_indicator",
        "dxy_trend": "bias_filters.dxy_trend",
    }

    for factor_id, module_path in scorers.items():
        if factor_id in PIVOT_OWNED_FACTORS:
            logger.debug("Skipping backend scorer for %s (owned by Pivot collector)", factor_id)
            continue
        try:
            module = __import__(module_path, fromlist=["compute_score"])
            compute_score = getattr(module, "compute_score", None)
            if compute_score is None:
                logger.warning(f"Factor {factor_id} missing compute_score")
                continue
            reading = await compute_score()
            if reading:
                previous = await get_latest_reading(factor_id)
                results[factor_id] = reading
                await store_factor_reading(reading)
                if previous and abs(reading.score - previous.score) >= 0.8:
                    try:
                        await send_alert(
                            "Factor Score Spike",
                            (
                                f"{factor_id} moved from {previous.score:+.2f} "
                                f"to {reading.score:+.2f} in one cycle."
                            ),
                            severity="warning",
                        )
                    except Exception as alert_exc:
                        logger.warning("Score spike alert failed for %s: %s", factor_id, alert_exc)
            else:
                # compute_score() returned None — no data available.
                # Delete stale Redis key so composite excludes this factor
                # instead of using an old cached fallback reading.
                try:
                    from database.redis_client import get_redis_client
                    client = await get_redis_client()
                    if client:
                        key = REDIS_KEY_FACTOR_LATEST.format(factor_id=factor_id)
                        await client.delete(key)
                        logger.debug("Cleared stale Redis key for %s (compute_score returned None)", factor_id)
                except Exception as del_exc:
                    logger.warning("Failed to clear stale key for %s: %s", factor_id, del_exc)
        except Exception as exc:
            logger.error(f"Factor {factor_id} scoring failed: {exc}")

    return results
