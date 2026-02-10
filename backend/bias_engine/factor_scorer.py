"""
Composite bias factor scoring orchestrator.
"""

from __future__ import annotations

import logging
from typing import Dict

from bias_engine.composite import FactorReading, store_factor_reading

logger = logging.getLogger(__name__)


async def score_all_factors() -> Dict[str, FactorReading]:
    """Run all factor scoring functions including tick_breadth (reads from Redis)."""
    results: Dict[str, FactorReading] = {}

    scorers = {
        "credit_spreads": "bias_filters.credit_spreads",
        "market_breadth": "bias_filters.market_breadth",
        "vix_term": "bias_filters.vix_term_structure",
        "sector_rotation": "bias_filters.sector_rotation",
        "dollar_smile": "bias_filters.dollar_smile",
        "excess_cape": "bias_filters.excess_cape_yield",
        "savita": "bias_filters.savita_indicator",
        "tick_breadth": "bias_filters.tick_breadth",
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
