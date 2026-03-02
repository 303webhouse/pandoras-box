"""
Score v2: Post-Enrichment Scoring Pass

Runs AFTER enrichment data is available (Brief 4C). Takes the flash score
(from trade_ideas_scorer.py) and adds enrichment-powered factors:
  - RVOL bonus (from enrichment_data.rvol)
  - Risk quality (from enrichment_data.risk_in_atr)

Writes to signals.score_v2 and signals.score_v2_factors.

This is the "full score" in the flash/full two-pass pattern.
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def compute_score_v2(signal_data: Dict[str, Any]) -> Tuple[Optional[float], Dict[str, Any]]:
    """
    Compute full score v2 from flash score + enrichment data.

    Args:
        signal_data: Signal dict with 'score' (flash) and 'enrichment_data' (from 4C).

    Returns:
        Tuple of (score_v2 float, factors dict) or (None, {}) if can't compute.
    """
    flash_score = signal_data.get("score")
    if flash_score is None:
        return None, {}

    enrichment = signal_data.get("enrichment_data") or {}
    factors: Dict[str, Any] = {"flash_score": flash_score}

    post_enrichment_bonus = 0.0

    # --- RVOL bonus (replaces raw signal rvol check) ---
    rvol = enrichment.get("rvol")
    rvol_bonus = 0
    if rvol is not None:
        if rvol >= 2.0:
            rvol_bonus = 5
        elif rvol >= 1.5:
            rvol_bonus = 3
        elif rvol >= 1.2:
            rvol_bonus = 1
        elif rvol < 0.5:
            rvol_bonus = -3  # Low volume = weak conviction
        factors["rvol"] = {"value": rvol, "bonus": rvol_bonus}
    else:
        factors["rvol"] = {"value": None, "bonus": 0, "note": "enrichment unavailable"}

    post_enrichment_bonus += rvol_bonus

    # --- Risk quality: risk in ATR units ---
    risk_in_atr = enrichment.get("risk_in_atr")
    risk_bonus = 0
    if risk_in_atr is not None:
        if risk_in_atr <= 0.5:
            risk_bonus = 5   # Tight risk = excellent
        elif risk_in_atr <= 1.0:
            risk_bonus = 3   # Under 1 ATR = good
        elif risk_in_atr <= 1.5:
            risk_bonus = 0   # Reasonable
        elif risk_in_atr <= 2.0:
            risk_bonus = -3  # Wide stop
        else:
            risk_bonus = -5  # Very wide stop = questionable
        factors["risk_in_atr"] = {"value": risk_in_atr, "bonus": risk_bonus}
    else:
        factors["risk_in_atr"] = {"value": None, "bonus": 0, "note": "enrichment unavailable"}

    post_enrichment_bonus += risk_bonus

    # --- IV rank context (informational, not scored yet) ---
    iv_rank = enrichment.get("iv_rank")
    if iv_rank is not None:
        factors["iv_rank"] = {"value": iv_rank, "note": "informational — affects options vs stock decision in 4E"}

    # --- Regime bonus (placeholder — degraded until Phase 3 X2) ---
    regime = signal_data.get("regime")
    regime_bonus = 0
    factors["regime"] = {"value": regime, "bonus": regime_bonus, "note": "degraded until Phase 3 X2 regime module"}

    # --- Confluence bonus (placeholder — degraded until Phase 3 X1) ---
    confluence_score = signal_data.get("confluence_score")
    confluence_bonus = 0
    factors["confluence"] = {"value": confluence_score, "bonus": confluence_bonus, "note": "degraded until Phase 3 X1 scanner"}

    # --- Compute final v2 score ---
    score_v2 = flash_score + post_enrichment_bonus
    score_v2 = min(100, max(0, round(score_v2, 2)))

    factors["post_enrichment_bonus"] = post_enrichment_bonus
    factors["score_v2"] = score_v2

    logger.info(
        f"📊 Score v2: {signal_data.get('ticker')} flash={flash_score} "
        f"+enrichment={post_enrichment_bonus} = {score_v2} "
        f"(RVOL={rvol}, risk_atr={risk_in_atr})"
    )

    return score_v2, factors


async def persist_score_v2(signal_id: str, score_v2: float, factors: Dict[str, Any]) -> None:
    """Write score_v2 and factors to the signals table."""
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE signals
                SET score_v2 = $2, score_v2_factors = $3
                WHERE signal_id = $1
                """,
                signal_id,
                score_v2,
                json.dumps(factors),
            )
    except Exception as e:
        logger.warning(f"Failed to persist score_v2 for {signal_id}: {e}")
