"""
Polygon SPY Put/Call Volume Ratio — automated contrarian sentiment factor.

Data source: Polygon /v3/snapshot/options/SPY (15-min delayed, Starter plan).
Fetches NTM contracts (±10% of current price, 0-60 DTE) to get a representative
sample within the pagination limit. Aggregates put vs call volume.
Supplements the TradingView-webhook-dependent put_call_ratio factor.

Staleness: 8h — designed for swing timeframe.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal, get_price_history
    from integrations.polygon_options import get_options_snapshot, POLYGON_API_KEY
except ImportError:
    FactorReading = None
    score_to_signal = None
    get_options_snapshot = None
    get_price_history = None
    POLYGON_API_KEY = ""


async def _get_spy_price() -> Optional[float]:
    """Get current SPY price for NTM filtering."""
    try:
        if get_price_history:
            data = await get_price_history("SPY", days=5)
            if data is not None and not data.empty and "close" in data.columns:
                return float(data["close"].iloc[-1])
    except Exception as e:
        logger.warning("polygon_pcr: failed to get SPY price: %s", e)
    return None


async def compute_score() -> Optional[FactorReading]:
    """
    Aggregate SPY option volume from Polygon snapshot.
    Contrarian scoring: high put volume = fear = bullish signal.

    Uses NTM-filtered chain (±10% of current price, 0-60 DTE) for
    representative put/call volume sampling within pagination limits.
    """
    if not POLYGON_API_KEY:
        logger.warning("polygon_pcr: POLYGON_API_KEY not set — skipping")
        return None

    # Get current SPY price for NTM filtering
    spy_price = await _get_spy_price()
    if not spy_price:
        logger.warning("polygon_pcr: cannot determine SPY price — skipping")
        return None

    # Filter to ±10% of current price to get a representative NTM sample
    strike_lo = round(spy_price * 0.90, 0)
    strike_hi = round(spy_price * 1.10, 0)

    chain = await get_options_snapshot(
        "SPY",
        strike_gte=strike_lo,
        strike_lte=strike_hi,
    )
    if not chain:
        logger.warning("polygon_pcr: Polygon returned empty SPY chain")
        return None

    put_volume = 0
    call_volume = 0
    contracts_with_volume = 0

    # Log first contract's fields for diagnostic (check if implied_volatility exists)
    if chain and len(chain) > 0:
        sample = chain[0]
        has_iv = sample.get("implied_volatility") is not None
        has_greeks = bool(sample.get("greeks"))
        logger.info(
            "polygon_pcr: sample contract fields — has_iv=%s, has_greeks=%s, keys=%s",
            has_iv, has_greeks, list(sample.keys())[:10]
        )

    for contract in chain:
        details = contract.get("details", {})
        contract_type = (details.get("contract_type") or "").lower()
        day = contract.get("day", {})
        vol = day.get("volume") or 0

        if contract_type == "put":
            put_volume += vol
        elif contract_type == "call":
            call_volume += vol

        if vol > 0:
            contracts_with_volume += 1

    total_volume = put_volume + call_volume
    if total_volume == 0:
        logger.warning("polygon_pcr: zero total volume (market closed?)")
        return None

    pcr = put_volume / call_volume if call_volume > 0 else 0.0
    score = _score_pcr(pcr)

    logger.info(
        "polygon_pcr: PCR=%.3f (puts=%d, calls=%d, contracts=%d/%d NTM range=%.0f-%.0f)",
        pcr, put_volume, call_volume, contracts_with_volume, len(chain),
        strike_lo, strike_hi,
    )

    return FactorReading(
        factor_id="polygon_pcr",
        score=score,
        signal=score_to_signal(score),
        detail=(
            f"SPY P/C volume ratio: {pcr:.3f} "
            f"(puts {put_volume:,} / calls {call_volume:,}, "
            f"{contracts_with_volume} active contracts, NTM ±10%)"
        ),
        timestamp=datetime.utcnow(),
        source="polygon",
        raw_data={
            "pcr": round(float(pcr), 4),
            "put_volume": int(put_volume),
            "call_volume": int(call_volume),
            "total_volume": int(total_volume),
            "contracts_with_volume": contracts_with_volume,
            "contracts_total": len(chain),
            "strike_range": [strike_lo, strike_hi],
            "spy_price": round(float(spy_price), 2),
        },
    )


def _score_pcr(pcr: float) -> float:
    """
    Contrarian scoring. High PCR = fear = bullish.
    Thresholds calibrated to SPY options (higher baseline than CBOE $CPCE).
    """
    if pcr >= 1.2:
        return 0.8    # Extreme fear — contrarian strong bullish
    elif pcr >= 1.0:
        return 0.4    # Elevated fear — mildly bullish
    elif pcr >= 0.8:
        return 0.2    # Slightly elevated
    elif pcr >= 0.6:
        return 0.0    # Normal territory
    elif pcr >= 0.5:
        return -0.4   # Complacency
    else:
        return -0.8   # Extreme complacency — contrarian bearish
