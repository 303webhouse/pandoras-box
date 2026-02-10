"""
Composite bias factor scoring orchestrator.
"""

from __future__ import annotations

import logging
from typing import Dict

from bias_engine.composite import FactorReading, store_factor_reading

logger = logging.getLogger(__name__)


async def score_all_factors() -> Dict[str, FactorReading]:
    """Run all 20 factor scoring functions."""
    results: Dict[str, FactorReading] = {}

    scorers = {
        # Intraday (6)
        "vix_term": "bias_filters.vix_term_structure",
        "tick_breadth": "bias_filters.tick_breadth",
        "vix_regime": "bias_filters.vix_regime",
        "spy_trend_intraday": "bias_filters.spy_trend_intraday",
        "breadth_momentum": "bias_filters.breadth_momentum",
        "options_sentiment": "bias_filters.options_sentiment",
        # Swing (7)
        "credit_spreads": "bias_filters.credit_spreads",
        "market_breadth": "bias_filters.market_breadth",
        "sector_rotation": "bias_filters.sector_rotation",
        "spy_200sma_distance": "bias_filters.spy_200sma_distance",
        "high_yield_oas": "bias_filters.high_yield_oas",
        "dollar_smile": "bias_filters.dollar_smile",
        "put_call_ratio": "bias_filters.put_call_ratio",
        # Macro (7)
        "yield_curve": "bias_filters.yield_curve",
        "initial_claims": "bias_filters.initial_claims",
        "sahm_rule": "bias_filters.sahm_rule",
        "copper_gold_ratio": "bias_filters.copper_gold_ratio",
        "excess_cape": "bias_filters.excess_cape_yield",
        "ism_manufacturing": "bias_filters.ism_manufacturing",
        "savita": "bias_filters.savita_indicator",
    }

    for factor_id, module_path in scorers.items():
        try:
            module = __import__(module_path, fromlist=["compute_score"])
            compute_score = getattr(module, "compute_score", None)
            if compute_score is None:
                logger.warning(f"Factor {factor_id} missing compute_score")
                continue
            reading = await compute_score()
            if reading:
                results[factor_id] = reading
                await store_factor_reading(reading)
        except Exception as exc:
            logger.error(f"Factor {factor_id} scoring failed: {exc}")

    return results
