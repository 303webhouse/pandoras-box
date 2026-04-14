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

# Factors scored by external sources (VPS collector, TradingView webhooks).
# Backend scorer skips these to avoid overwriting fresher data.
# NOTE: credit_spreads, market_breadth, sector_rotation removed 2026-03-05
# — VPS collector was producing NaN data from index-misaligned DataFrames.
# Railway's compute_score() functions handle alignment correctly.
PIVOT_OWNED_FACTORS = {
    "tick_breadth",
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
        "spy_trend_intraday": "bias_filters.spy_trend_intraday",
        "breadth_intraday": "bias_filters.breadth_intraday",
        "gex": "bias_filters.gex",
        # Swing (6)
        "credit_spreads": "bias_filters.credit_spreads",
        "market_breadth": "bias_filters.market_breadth",
        "sector_rotation": "bias_filters.sector_rotation",
        "spy_200sma_distance": "bias_filters.spy_200sma_distance",
        "spy_50sma_distance": "bias_filters.spy_50sma_distance",
        "iv_regime": "bias_filters.iv_regime",
        "mcclellan_oscillator": "bias_filters.mcclellan_oscillator",
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

    # ── DUAL SCORING: parallel UW API source comparison ──
    # When DATA_SOURCE_MODE=parallel, score GEX using both old (Polygon) and new (UW API)
    # and log comparison to source_score_comparisons table.
    import os
    if os.getenv("DATA_SOURCE_MODE", "") == "parallel":
        try:
            from bias_filters.gex import compute_score_uw
            uw_gex_reading = await compute_score_uw()

            # Get the Polygon reading we just computed
            polygon_gex = results.get("gex")

            if uw_gex_reading and polygon_gex:
                from api.bias_source_comparison import log_comparison
                await log_comparison(
                    factor_id="gex",
                    old_source="polygon",
                    old_score=polygon_gex.score,
                    new_source="uw_api",
                    new_score=uw_gex_reading.score,
                    old_detail=polygon_gex.detail or "",
                    new_detail=uw_gex_reading.detail or "",
                )
                logger.info(
                    "DUAL SCORING gex: polygon=%+.2f uw_api=%+.2f agree=%s",
                    polygon_gex.score, uw_gex_reading.score,
                    "YES" if (polygon_gex.score > 0) == (uw_gex_reading.score > 0) else "NO",
                )
            elif uw_gex_reading and not polygon_gex:
                logger.info("DUAL SCORING gex: polygon=NONE uw_api=%+.2f", uw_gex_reading.score)
            elif polygon_gex and not uw_gex_reading:
                logger.info("DUAL SCORING gex: polygon=%+.2f uw_api=NONE", polygon_gex.score)
        except Exception as dual_err:
            logger.debug("Dual scoring (GEX) skipped: %s", dual_err)

    return results
