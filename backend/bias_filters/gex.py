"""
GEX (Gamma Exposure) Factor — SPY net dealer gamma.

Positive GEX = dealers long gamma → they sell rallies, buy dips → compression/dampening.
Negative GEX = dealers short gamma → they amplify moves → increased volatility.

Primary data source: UW API /greek-exposure (full chain, no contract limit).
Fallback: Polygon.io options snapshot (Starter plan, 15-min delayed, 150 contract cap).
Staleness: 4h — intraday timeframe.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal, get_latest_price, neutral_reading
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal, get_latest_price, neutral_reading

# Normalization baselines
GEX_SCALE_FACTOR = 2_000_000_000  # $2B — for Polygon contract-level calculation
UW_GEX_SCALE = 50_000_000_000    # $50B — for UW pre-aggregated gamma values


async def compute_score() -> Optional[FactorReading]:
    """Compute GEX score. UW API is primary, Polygon is fallback."""
    # Try UW API first
    reading = await compute_score_uw()
    if reading:
        return reading

    # Fallback to Polygon
    logger.info("gex: UW API unavailable, falling back to Polygon")
    return await _compute_score_polygon()


async def _compute_score_polygon() -> Optional[FactorReading]:
    """Compute GEX score from SPY options chain via Polygon snapshot (fallback)."""
    try:
        from integrations.polygon_options import get_options_snapshot
    except ImportError:
        try:
            from backend.integrations.polygon_options import get_options_snapshot
        except ImportError:
            logger.warning("gex: Polygon options module not available")
            return None

    spy_price = await get_latest_price("SPY")
    if not spy_price or spy_price <= 0:
        logger.warning("gex: cannot get SPY price — skipping")
        return None

    strike_lo = spy_price * 0.90
    strike_hi = spy_price * 1.10
    chain = await get_options_snapshot(
        "SPY",
        strike_gte=strike_lo,
        strike_lte=strike_hi,
    )
    if not chain:
        logger.warning("gex: no Polygon chain data for SPY — skipping")
        return None

    net_gex = 0.0
    contracts_used = 0
    for contract in chain:
        details = contract.get("details", {})
        greeks = contract.get("greeks", {})
        oi = contract.get("open_interest", 0)
        gamma = greeks.get("gamma")

        if not gamma or not oi or oi <= 0:
            continue

        contract_type = (details.get("contract_type") or "").lower()
        contribution = abs(gamma) * oi * 100 * spy_price
        if contract_type == "call":
            net_gex += contribution
        elif contract_type == "put":
            net_gex -= contribution

        contracts_used += 1

    if contracts_used < 10:
        return neutral_reading("gex", f"GEX: insufficient contracts ({contracts_used})", source="polygon")

    normalized = net_gex / GEX_SCALE_FACTOR
    score = _score_gex(normalized)

    if normalized > 0.5:
        label = "strong compression (dealers long gamma)"
    elif normalized > 0.05:
        label = "mild compression"
    elif normalized > -0.05:
        label = "neutral/transition"
    elif normalized > -0.2:
        label = "mild amplification"
    else:
        label = "strong amplification (dealers short gamma)"

    logger.info(
        "gex: net_gex=$%.0fM, normalized=%.3f (%s), score=%+.2f, contracts=%d [polygon fallback]",
        net_gex / 1e6, normalized, label, score, contracts_used,
    )

    return FactorReading(
        factor_id="gex",
        score=score,
        signal=score_to_signal(score),
        detail=f"GEX: ${net_gex/1e9:.2f}B ({label}), {contracts_used} contracts",
        timestamp=datetime.utcnow(),
        source="polygon",
        raw_data={
            "net_gex": round(net_gex, 0),
            "normalized": round(normalized, 4),
            "spy_price": round(spy_price, 2),
            "contracts_used": contracts_used,
        },
    )


async def compute_score_uw() -> Optional[FactorReading]:
    """Compute GEX score from SPY options chain via UW API (shadow/parallel mode)."""
    try:
        from integrations.uw_api import get_greek_exposure, get_snapshot
    except ImportError:
        from backend.integrations.uw_api import get_greek_exposure, get_snapshot

    # Get SPY price
    snap = await get_snapshot("SPY")
    spy_price = snap.get("day", {}).get("c") if snap else None
    if not spy_price or spy_price <= 0:
        spy_price = await get_latest_price("SPY")
    if not spy_price or spy_price <= 0:
        logger.warning("gex_uw: cannot get SPY price — skipping")
        return None

    # UW GEX endpoint returns pre-computed gamma exposure per expiry
    gex_data = await get_greek_exposure("SPY")
    if not gex_data:
        logger.warning("gex_uw: no UW GEX data for SPY — skipping")
        return None

    # Sum net GEX across all expirations
    # UW returns: call_gamma, put_gamma as strings per expiry date
    net_gex = 0.0
    expirations_used = 0
    for entry in gex_data:
        try:
            call_g = float(entry.get("call_gamma") or 0)
            put_g = float(entry.get("put_gamma") or 0)
            # Net GEX = call gamma - |put gamma| (put gamma is already negative conceptually)
            net_gex += call_g + put_g  # put_gamma from UW is already negative
            expirations_used += 1
        except (ValueError, TypeError):
            continue

    if expirations_used < 3:
        return neutral_reading("gex", f"GEX(UW): insufficient expirations ({expirations_used})", source="uw_api")

    # UW gamma values are much larger scale than Polygon (pre-multiplied by OI*100*price)
    # Use a larger scale factor
    uw_scale = 50_000_000_000  # $50B — calibrated for UW's aggregate gamma values
    normalized = net_gex / uw_scale
    score = _score_gex(normalized)

    if normalized > 0.5:
        label = "strong compression (dealers long gamma)"
    elif normalized > 0.05:
        label = "mild compression"
    elif normalized > -0.05:
        label = "neutral/transition"
    elif normalized > -0.2:
        label = "mild amplification"
    else:
        label = "strong amplification (dealers short gamma)"

    logger.info(
        "gex_uw: net_gex=$%.0fM, normalized=%.3f (%s), score=%+.2f, expirations=%d",
        net_gex / 1e6, normalized, label, score, expirations_used,
    )

    return FactorReading(
        factor_id="gex",
        score=score,
        signal=score_to_signal(score),
        detail=f"GEX(UW): ${net_gex/1e9:.2f}B ({label}), {expirations_used} expirations",
        timestamp=datetime.utcnow(),
        source="uw_api",
        raw_data={
            "net_gex": round(net_gex, 0),
            "normalized": round(normalized, 4),
            "spy_price": round(spy_price, 2),
            "expirations_used": expirations_used,
        },
    )


def _score_gex(normalized: float) -> float:
    """
    Score normalized GEX value.

    Positive GEX = compression = bullish (dealers dampen moves).
    Negative GEX = amplification = bearish skew (dealers amplify moves).

    Bands tightened for Polygon Starter plan contract set (~150 contracts).
    """
    if normalized > 0.4:
        return 0.5    # Strong compression — significant dampening
    elif normalized > 0.2:
        return 0.3    # Moderate compression
    elif normalized > 0.05:
        return 0.1    # Mild compression
    elif normalized > -0.05:
        return 0.0    # Neutral / transition zone
    elif normalized > -0.15:
        return -0.2   # Mild amplification — dealers slightly short gamma
    elif normalized > -0.3:
        return -0.3   # Moderate amplification
    else:
        return -0.5   # Strong amplification — bearish volatility risk
