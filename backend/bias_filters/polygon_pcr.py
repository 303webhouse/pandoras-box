"""
Polygon SPY Put/Call Volume Ratio — automated contrarian sentiment factor.

Data source: Polygon /v3/snapshot/options/SPY (15-min delayed, Starter plan).
Aggregates total put volume vs call volume across all SPY contracts.
Supplements the TradingView-webhook-dependent put_call_ratio factor.

Staleness: 8h — designed for swing timeframe.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal
    from integrations.polygon_options import get_options_snapshot, POLYGON_API_KEY
except ImportError:
    FactorReading = None
    score_to_signal = None
    get_options_snapshot = None
    POLYGON_API_KEY = ""


async def compute_score() -> Optional[FactorReading]:
    """
    Aggregate SPY option volume from Polygon snapshot.
    Contrarian scoring: high put volume = fear = bullish signal.
    """
    if not POLYGON_API_KEY:
        logger.warning("polygon_pcr: POLYGON_API_KEY not set — skipping")
        return None

    chain = await get_options_snapshot("SPY")
    if not chain:
        logger.warning("polygon_pcr: Polygon returned empty SPY chain")
        return None

    put_volume = 0
    call_volume = 0
    contracts_with_volume = 0

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

    return FactorReading(
        factor_id="polygon_pcr",
        score=score,
        signal=score_to_signal(score),
        detail=(
            f"SPY P/C volume ratio: {pcr:.3f} "
            f"(puts {put_volume:,} / calls {call_volume:,}, "
            f"{contracts_with_volume} active contracts)"
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
