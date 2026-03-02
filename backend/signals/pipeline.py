"""
Unified Signal Processing Pipeline (Phase 4)

Single entry point for ALL signal sources. Each webhook handler normalizes
its payload into a standard signal dict, then calls process_signal_unified().
This replaces the duplicated log/score/cache/broadcast logic across handlers.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from database.postgres_client import log_signal, update_signal_with_score
from database.redis_client import cache_signal
from scoring.trade_ideas_scorer import calculate_signal_score, get_score_tier
from websocket.broadcaster import manager
from utils.bias_snapshot import get_bias_snapshot

logger = logging.getLogger(__name__)

COMMITTEE_SCORE_THRESHOLD = 75.0  # Minimum score_v2 to trigger committee


async def _maybe_flag_for_committee(signal_data: Dict[str, Any]) -> None:
    """
    Flag signal for committee review if it meets the threshold.
    Sets status=COMMITTEE_REVIEW and committee_requested_at.
    Skips Scout alerts and signals that already have committee data.
    """
    # Skip scouts and manual signals
    if signal_data.get("signal_type") in ("SCOUT_ALERT", "MANUAL"):
        return

    # Skip if already has committee data
    if signal_data.get("committee_data") or signal_data.get("committee_run_id"):
        return

    # Check score threshold (prefer score_v2, fall back to score)
    score = signal_data.get("score_v2") or signal_data.get("score") or 0
    if score < COMMITTEE_SCORE_THRESHOLD:
        return

    signal_id = signal_data.get("signal_id")
    if not signal_id:
        return

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE signals
                SET status = 'COMMITTEE_REVIEW',
                    committee_requested_at = NOW()
                WHERE signal_id = $1
                AND status = 'ACTIVE'
                """,
                signal_id,
            )
        signal_data["status"] = "COMMITTEE_REVIEW"
        logger.info(f"🧠 Flagged for committee: {signal_data.get('ticker')} (score={score})")
    except Exception as e:
        logger.warning(f"Failed to flag {signal_id} for committee: {e}")


def calculate_expiry(signal_data: Dict[str, Any]) -> Optional[datetime]:
    """
    Calculate signal expiry based on timeframe and asset class.
    Returns None for signals that shouldn't auto-expire.
    """
    timeframe = (signal_data.get("timeframe") or "1H").upper()

    # Intraday signals expire in 4 hours
    if timeframe in ("1", "3", "5", "15", "30", "1M", "3M", "5M", "15M", "30M", "1H"):
        return datetime.utcnow() + timedelta(hours=4)
    # Swing signals expire in 24 hours
    elif timeframe in ("4H", "D", "1D", "DAILY"):
        return datetime.utcnow() + timedelta(hours=24)
    # Weekly/monthly signals expire in 7 days
    elif timeframe in ("W", "1W", "WEEKLY", "M", "MONTHLY"):
        return datetime.utcnow() + timedelta(days=7)
    # Default: 4 hours
    return datetime.utcnow() + timedelta(hours=4)


async def write_signal_outcome(signal_data: Dict[str, Any]) -> None:
    """
    Write a PENDING outcome record for outcome tracking.
    Extracted from tradingview.py._write_signal_outcome() for shared use.
    """
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO signal_outcomes
                    (signal_id, symbol, signal_type, direction, cta_zone,
                     entry, stop, t1, t2, invalidation_level, created_at, outcome)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), 'PENDING')
                ON CONFLICT (signal_id) DO NOTHING
                """,
                signal_data.get("signal_id"),
                signal_data.get("ticker"),
                signal_data.get("signal_type"),
                signal_data.get("direction"),
                signal_data.get("cta_zone"),
                signal_data.get("entry_price"),
                signal_data.get("stop_loss"),
                signal_data.get("target_1"),
                signal_data.get("target_2"),
                signal_data.get("invalidation_level"),
            )
    except Exception as e:
        logger.warning(f"Failed to record signal outcome: {e}")


async def apply_scoring(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply Trade Ideas Scorer to a signal.

    Extracted from tradingview.py.apply_signal_scoring() for shared use.
    Includes composite bias lookup, contrarian qualification, and sector rotation.
    """
    try:
        # Get composite bias score
        composite_score = None
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached:
                composite_score = cached.composite_score
        except Exception as comp_err:
            logger.warning(f"Composite bias unavailable: {comp_err}")

        # Build bias data
        if composite_score is not None:
            current_bias = {"composite_score": composite_score}
        else:
            from scheduler.bias_scheduler import get_bias_status
            bias_status = get_bias_status()
            current_bias = {
                "daily": bias_status.get("daily", {}),
                "weekly": bias_status.get("weekly", {}),
                "cyclical": bias_status.get("cyclical", {}),
            }

        # Calculate score
        score, bias_alignment, triggering_factors = calculate_signal_score(
            signal_data, current_bias
        )

        # Contrarian qualification
        if bias_alignment in ("COUNTER_BIAS", "STRONG_COUNTER") and composite_score is not None:
            try:
                from scoring.contrarian_qualifier import qualify_contrarian
                direction = signal_data.get("direction", "").upper()
                cq = await qualify_contrarian(signal_data, composite_score, direction)
                if cq["qualified"]:
                    original_multiplier = triggering_factors.get("bias_alignment", {}).get("multiplier", 1.0)
                    if original_multiplier < 1.0:
                        raw_score = triggering_factors.get("calculation", {}).get("raw_score", score)
                        score = min(100, max(0, raw_score * 1.0))
                        score = round(score, 2)
                    signal_data["contrarian_qualified"] = True
                    signal_data["contrarian_reasons"] = cq["reasons"]
                    triggering_factors["contrarian"] = {
                        "qualified": True,
                        "reasons": cq["reasons"],
                        "original_multiplier": original_multiplier,
                        "restored_multiplier": 1.0,
                    }
                    bias_alignment = "CONTRARIAN_QUALIFIED"
            except Exception as cq_err:
                logger.warning(f"Contrarian check failed: {cq_err}")

        # Sector rotation bonus
        try:
            from scoring.sector_rotation_bonus import get_sector_bonus
            sector_rot_bonus = await get_sector_bonus(signal_data)
            if sector_rot_bonus != 0:
                score = min(100, max(0, score + sector_rot_bonus))
                score = round(score, 2)
                triggering_factors["sector_rotation_bonus"] = sector_rot_bonus
        except ImportError:
            pass
        except Exception as sr_err:
            logger.debug(f"Sector rotation bonus failed: {sr_err}")

        # Update signal
        signal_data["score"] = score
        signal_data["bias_alignment"] = bias_alignment
        signal_data["triggering_factors"] = triggering_factors
        signal_data["scoreTier"] = get_score_tier(score)

        # Set confidence/priority based on score
        direction = signal_data.get("direction", "").upper()
        if score >= 85:
            signal_data["confidence"] = "HIGH"
            signal_data["priority"] = "HIGH"
            if direction in ("LONG", "BUY"):
                signal_data["signal_type"] = "APIS_CALL"
                logger.info(f"🐝 APIS CALL: {signal_data.get('ticker')} (score: {score})")
            elif direction in ("SHORT", "SELL"):
                signal_data["signal_type"] = "KODIAK_CALL"
                logger.info(f"🐻 KODIAK CALL: {signal_data.get('ticker')} (score: {score})")
        elif score >= 75:
            signal_data["confidence"] = "HIGH"
            signal_data["priority"] = "HIGH"
        elif score >= 55:
            signal_data["confidence"] = "MEDIUM"
            signal_data["priority"] = "MEDIUM"
        else:
            signal_data["confidence"] = "LOW"
            signal_data["priority"] = "LOW"

        logger.info(f"📊 Scored: {signal_data.get('ticker')} = {score} ({bias_alignment})")
        return signal_data

    except Exception as e:
        logger.warning(f"Scoring failed: {e}")
        signal_data["score"] = 50
        signal_data["bias_alignment"] = "NEUTRAL"
        signal_data["confidence"] = "MEDIUM"
        return signal_data


async def process_signal_unified(
    signal_data: Dict[str, Any],
    source: str = "tradingview",
    skip_scoring: bool = False,
    cache_ttl: int = 3600,
    priority_threshold: float = 75.0,
) -> Dict[str, Any]:
    """
    Unified signal processing pipeline. Every signal source calls this
    after normalizing its payload into the standard signal_data dict.

    Pipeline steps:
    1. Set source and lifecycle fields
    2. Attach bias snapshot
    3. Score signal (unless skip_scoring=True, e.g. for Scout alerts)
    4. Persist to PostgreSQL (signals table + signal_outcomes table)
    5. Cache in Redis
    6. Broadcast via WebSocket
    7. Return enriched signal_data

    Args:
        signal_data: Normalized signal dict (must have signal_id, ticker, direction, etc.)
        source: Signal origin ('tradingview', 'whale', 'cta_scanner', 'manual')
        skip_scoring: True for signals that handle their own scoring (Scout alerts)
        cache_ttl: Redis cache TTL in seconds (default 1 hour)
        priority_threshold: Min score for priority WebSocket broadcast

    Returns:
        Enriched signal_data dict with score, bias, status, etc.
    """
    start = datetime.utcnow()

    # 1. Set lifecycle fields
    signal_data["source"] = source
    signal_data["status"] = signal_data.get("status", "ACTIVE")
    signal_data["expires_at"] = signal_data.get("expires_at") or calculate_expiry(signal_data)

    # 2. Attach bias snapshot
    if not signal_data.get("bias_at_signal"):
        try:
            signal_data["bias_at_signal"] = await get_bias_snapshot()
        except Exception as err:
            logger.warning(f"Bias snapshot failed: {err}")

    # 3. Score signal
    if not skip_scoring:
        signal_data = await apply_scoring(signal_data)

    # 4. Persist to PostgreSQL
    try:
        await log_signal(signal_data)
    except Exception as e:
        logger.error(f"Failed to log signal: {e}")

    # Write PENDING outcome record for accuracy tracking
    try:
        await write_signal_outcome(signal_data)
    except Exception as e:
        logger.warning(f"Failed to write signal outcome: {e}")

    # Update score in DB (log_signal may have written without score if scoring was async)
    if signal_data.get("score") and signal_data.get("signal_id"):
        try:
            await update_signal_with_score(
                signal_data["signal_id"],
                signal_data["score"],
                signal_data.get("bias_alignment", "NEUTRAL"),
                signal_data.get("triggering_factors", {}),
            )
        except Exception as e:
            logger.warning(f"Failed to update score in DB: {e}")

    # 4b. Calculate R:R if entry, stop, and target are available (H9)
    entry = signal_data.get("entry_price") or signal_data.get("entry")
    stop = signal_data.get("stop_loss") or signal_data.get("stop")
    target = signal_data.get("target_price") or signal_data.get("target") or signal_data.get("tp1")
    if entry and stop and target:
        try:
            risk = abs(float(entry) - float(stop))
            reward = abs(float(target) - float(entry))
            if risk > 0:
                signal_data["risk_reward"] = round(reward / risk, 2)
                signal_data["risk_reward_display"] = f"{signal_data['risk_reward']}:1"
            else:
                signal_data["risk_reward"] = None
        except (ValueError, TypeError):
            signal_data["risk_reward"] = None
    else:
        signal_data["risk_reward"] = signal_data.get("risk_reward")

    # 4c. Enrich signal with market context data
    try:
        from enrichment.signal_enricher import enrich_signal, persist_enrichment
        signal_data = await enrich_signal(signal_data)
        # Persist enrichment to DB (non-blocking — don't fail the pipeline)
        if signal_data.get("enrichment_data"):
            await persist_enrichment(signal_data["signal_id"], signal_data["enrichment_data"])
    except Exception as e:
        logger.warning(f"Enrichment failed (signal still processed): {e}")

    # 4d. Compute score v2 (full score with enrichment data)
    try:
        from scoring.score_v2 import compute_score_v2, persist_score_v2
        score_v2, v2_factors = compute_score_v2(signal_data)
        if score_v2 is not None:
            signal_data["score_v2"] = score_v2
            signal_data["score_v2_factors"] = v2_factors
            await persist_score_v2(signal_data["signal_id"], score_v2, v2_factors)
    except Exception as e:
        logger.warning(f"Score v2 computation failed (flash score still valid): {e}")

    # 5. Cache in Redis
    try:
        await cache_signal(signal_data["signal_id"], signal_data, ttl=cache_ttl)
    except Exception as e:
        logger.warning(f"Failed to cache signal: {e}")

    # 6. Broadcast via WebSocket
    try:
        await manager.broadcast_signal_smart(signal_data, priority_threshold=priority_threshold)
    except Exception as e:
        logger.warning(f"Failed to broadcast signal: {e}")

    # 7. Flag for committee review if score warrants it
    try:
        await _maybe_flag_for_committee(signal_data)
    except Exception as e:
        logger.warning(f"Committee flagging failed: {e}")

    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000
    logger.info(
        f"✅ Pipeline complete: {signal_data.get('ticker')} "
        f"({source}, score={signal_data.get('score')}) in {elapsed_ms:.1f}ms"
    )

    return signal_data
