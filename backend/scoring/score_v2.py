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

    # --- Regime alignment penalty/bonus ---
    # Uses bias_level from bias_at_signal snapshot.
    # Penalizes counter-regime signals, rewards aligned signals.
    regime_bonus = 0
    bias_snapshot = signal_data.get("bias_at_signal") or {}
    if isinstance(bias_snapshot, str):
        try:
            bias_snapshot = json.loads(bias_snapshot)
        except Exception:
            bias_snapshot = {}
    if not isinstance(bias_snapshot, dict):
        bias_snapshot = {}

    # Extract bias_level from the nested snapshot structure
    bias_level = ""
    summary = bias_snapshot.get("summary") or {}
    if isinstance(summary, dict):
        bias_level = (summary.get("composite_bias") or summary.get("overall_macro_bias") or "").upper()
    if not bias_level:
        bias_level = (bias_snapshot.get("bias_level") or "").upper()

    direction = (signal_data.get("direction") or "").upper()
    is_long = direction in ("LONG", "BUY")
    is_short = direction in ("SHORT", "SELL")

    # Bearish regimes: penalize LONG, reward SHORT
    if "URSA" in bias_level:
        if is_long:
            if "EXTREME" in bias_level:
                regime_bonus = -20
            elif "MAJOR" in bias_level:
                regime_bonus = -15
            else:  # URSA_MINOR
                regime_bonus = -10
        elif is_short:
            regime_bonus = 5

    # Bullish regimes: penalize SHORT, reward LONG
    elif "TORO" in bias_level:
        if is_short:
            if "EXTREME" in bias_level:
                regime_bonus = -20
            elif "MAJOR" in bias_level:
                regime_bonus = -15
            else:  # TORO_MINOR
                regime_bonus = -10
        elif is_long:
            regime_bonus = 5

    factors["regime"] = {
        "bias_level": bias_level,
        "direction": direction,
        "bonus": regime_bonus,
    }

    post_enrichment_bonus += regime_bonus

    # ── OPTIONS VIABILITY LAYER ──────────────────────────────────────
    # Evaluates whether this chart signal makes a good options swing trade.
    # Only applies to equity signals (crypto skipped).
    options_bonus = 0
    options_factors = {}
    asset_class = (signal_data.get("asset_class") or "EQUITY").upper()

    if asset_class != "CRYPTO":
        entry_price = signal_data.get("entry_price") or enrichment.get("current_price")
        target_price = signal_data.get("target_1")
        atr = enrichment.get("atr_14")
        rr = signal_data.get("risk_reward")
        avg_vol = enrichment.get("avg_volume_20d")
        iv_rank = enrichment.get("iv_rank")

        # Factor 1: Underlying price floor
        price_penalty = 0
        if entry_price is not None:
            entry_f = float(entry_price)
            if entry_f < 15:
                price_penalty = -10
            elif entry_f < 25:
                price_penalty = -7
            elif entry_f < 40:
                price_penalty = -3
        options_factors["underlying_price"] = {"value": entry_price, "bonus": price_penalty}
        options_bonus += price_penalty

        # Factor 2: Target move vs ATR
        move_bonus = 0
        target_in_atr = None
        if entry_price and target_price and atr and float(atr) > 0:
            target_move = abs(float(target_price) - float(entry_price))
            target_in_atr = round(target_move / float(atr), 2)
            if target_in_atr >= 3.0:
                move_bonus = 5
            elif target_in_atr >= 2.0:
                move_bonus = 3
            elif target_in_atr >= 1.5:
                move_bonus = 0
            elif target_in_atr >= 1.0:
                move_bonus = -3
            else:
                move_bonus = -7
        options_factors["target_move_atr"] = {"value": target_in_atr, "bonus": move_bonus}
        options_bonus += move_bonus

        # Factor 3: R:R minimum for options
        rr_bonus = 0
        if rr is not None:
            rr_val = float(rr)
            if rr_val >= 3.0:
                rr_bonus = 5
            elif rr_val >= 2.5:
                rr_bonus = 3
            elif rr_val >= 2.0:
                rr_bonus = 0
            elif rr_val >= 1.5:
                rr_bonus = -5
            else:
                rr_bonus = -8
        options_factors["risk_reward"] = {"value": rr, "bonus": rr_bonus}
        options_bonus += rr_bonus

        # Factor 4: Options liquidity proxy (underlying volume)
        liquidity_bonus = 0
        if avg_vol is not None:
            avg_vol_f = float(avg_vol)
            if avg_vol_f >= 5_000_000:
                liquidity_bonus = 3
            elif avg_vol_f >= 2_000_000:
                liquidity_bonus = 1
            elif avg_vol_f >= 500_000:
                liquidity_bonus = 0
            elif avg_vol_f >= 100_000:
                liquidity_bonus = -5
            else:
                liquidity_bonus = -8
        options_factors["liquidity"] = {"value": avg_vol, "bonus": liquidity_bonus}
        options_bonus += liquidity_bonus

        # Factor 5: IV rank — high IV penalizes debit spreads
        iv_bonus = 0
        if iv_rank is not None:
            iv_val = float(iv_rank)
            if iv_val <= 20:
                iv_bonus = 3
            elif iv_val <= 40:
                iv_bonus = 1
            elif iv_val <= 60:
                iv_bonus = 0
            elif iv_val <= 80:
                iv_bonus = -2
            else:
                iv_bonus = -5
        options_factors["iv_rank"] = {"value": iv_rank, "bonus": iv_bonus}
        options_bonus += iv_bonus

    factors["options_viability"] = {
        "total_bonus": options_bonus,
        "components": options_factors,
    }
    post_enrichment_bonus += options_bonus

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
