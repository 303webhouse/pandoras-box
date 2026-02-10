"""
Contrarian Signal Qualifier

Determines whether a counter-bias signal deserves to have its penalty removed.
A qualified contrarian signal gets its multiplier restored to 1.0x so it can
compete on technical merit alone. It does NOT get a bonus — it just stops
being penalized for going against the market direction.

Qualification criteria (any one is sufficient):
1. Exhaustion strategy (reversal by nature)
2. RSI extreme (>70 for shorts, <30 for longs)
3. High RVOL (>2.0x normal volume)
4. Sector divergence (signal's sector is moving against the market)
5. Options flow confirmation (UW data shows contra activity)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum number of qualifications to restore multiplier
MIN_QUALIFICATIONS = 1


async def qualify_contrarian(
    signal: Dict[str, Any],
    composite_score: float,
    direction: str,
) -> Dict[str, Any]:
    """
    Check if a counter-bias signal qualifies for penalty removal.

    Args:
        signal: The full signal data dict
        composite_score: Current composite bias score (-1.0 to 1.0)
        direction: Signal direction (LONG/SHORT)

    Returns:
        Dict with:
            - qualified: bool
            - reasons: list of qualification reasons
            - restored_multiplier: float (1.0 if qualified, None if not)
    """
    is_long = direction.upper() in ("LONG", "BUY")

    # Check if this is actually a counter-bias signal
    if is_long and composite_score >= 0:
        return {"qualified": False, "reasons": [], "restored_multiplier": None}
    if not is_long and composite_score <= 0:
        return {"qualified": False, "reasons": [], "restored_multiplier": None}

    reasons: List[str] = []

    # 1. Exhaustion strategy (inherently contrarian)
    strategy = (signal.get("strategy") or "").upper()
    signal_type = (signal.get("signal_type") or "").upper()
    trade_type = (signal.get("trade_type") or "").upper()

    if "EXHAUSTION" in strategy or "EXHAUSTION" in signal_type or trade_type == "REVERSAL":
        reasons.append("exhaustion_reversal")

    # 2. RSI extreme
    rsi = signal.get("rsi")
    if rsi is not None:
        try:
            rsi = float(rsi)
            if is_long and rsi < 30:
                reasons.append(f"rsi_oversold_{rsi:.1f}")
            elif not is_long and rsi > 70:
                reasons.append(f"rsi_overbought_{rsi:.1f}")
        except (TypeError, ValueError):
            pass

    # 3. High RVOL
    rvol = signal.get("rvol") or signal.get("volume_ratio")
    if rvol is not None:
        try:
            rvol = float(rvol)
            if rvol >= 2.0:
                reasons.append(f"high_rvol_{rvol:.1f}x")
        except (TypeError, ValueError):
            pass

    # 4. Sector divergence (sector moving against overall market)
    sector_reason = await _check_sector_divergence(signal, composite_score, is_long)
    if sector_reason:
        reasons.append(sector_reason)

    # 5. Options flow confirmation
    flow_reason = await _check_options_flow(signal, is_long)
    if flow_reason:
        reasons.append(flow_reason)

    qualified = len(reasons) >= MIN_QUALIFICATIONS

    if qualified:
        ticker = signal.get("ticker", "???")
        logger.info(
            f"🔄 Contrarian qualified: {ticker} {direction} "
            f"(composite={composite_score:+.2f}, reasons={reasons})"
        )

    return {
        "qualified": qualified,
        "reasons": reasons,
        "restored_multiplier": 1.0 if qualified else None,
    }


async def _check_sector_divergence(
    signal: Dict[str, Any],
    composite_score: float,
    is_long: bool,
) -> Optional[str]:
    """
    Check if the signal's sector is diverging from the overall market.
    A LONG signal in a SURGING sector qualifies even if market is bearish.
    A SHORT signal in a DUMPING sector qualifies even if market is bullish.
    """
    try:
        from database.redis_client import get_redis_client

        ticker = signal.get("ticker", "").upper()
        if not ticker:
            return None

        # Detect sector for this ticker
        try:
            from config.sectors import detect_sector, SECTOR_ETF_MAP
        except ImportError:
            from backend.config.sectors import detect_sector, SECTOR_ETF_MAP

        sector = detect_sector(ticker)
        if sector == "Uncategorized":
            return None

        # Read sector rotation data from Redis
        redis = await get_redis_client()
        if not redis:
            return None

        raw = await redis.get("sector:rotation:current")
        if not raw:
            return None

        rotation_data = json.loads(raw)
        sector_info = rotation_data.get(sector)
        if not sector_info:
            return None

        status = sector_info.get("status", "STEADY")

        if is_long and status == "SURGING":
            return f"sector_surging_{sector}"
        elif not is_long and status == "DUMPING":
            return f"sector_dumping_{sector}"

    except Exception as e:
        logger.debug(f"Sector divergence check failed: {e}")

    return None


async def _check_options_flow(
    signal: Dict[str, Any],
    is_long: bool,
) -> Optional[str]:
    """
    Check UW options flow data for contra activity in the signal's ticker.
    Heavy put activity on a LONG signal = institutional hedging confirms reversal potential.
    Heavy call activity on a SHORT signal = institutions positioning for upside.
    """
    try:
        from database.redis_client import get_redis_client

        ticker = signal.get("ticker", "").upper()
        if not ticker:
            return None

        redis = await get_redis_client()
        if not redis:
            return None

        # Check cached UW flow for this ticker
        raw = await redis.get(f"uw:flow:{ticker}")
        if not raw:
            return None

        flow = json.loads(raw)
        sentiment = (flow.get("sentiment") or "").upper()
        net_premium = flow.get("net_premium", 0)

        # For LONG counter-signal: bearish flow = institutional puts = confirms reversal thesis
        if is_long and sentiment == "BEARISH" and net_premium < -50000:
            return f"uw_bearish_flow_{ticker}"

        # For SHORT counter-signal: bullish flow = institutional calls = confirms exhaust thesis
        if not is_long and sentiment == "BULLISH" and net_premium > 50000:
            return f"uw_bullish_flow_{ticker}"

    except Exception as e:
        logger.debug(f"Options flow check failed: {e}")

    return None
