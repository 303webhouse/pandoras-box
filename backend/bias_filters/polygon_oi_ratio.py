"""
Polygon SPY Put/Call Open Interest Ratio — contrarian positioning gauge.

Measures the ratio of put OI to call OI on SPY NTM options.
High put OI = institutional hedging/fear = contrarian bullish.
Low put OI = complacency = contrarian bearish.

OI thresholds calibrated higher than volume PCR (OI is stickier/more persistent).

Data source: Polygon /v3/snapshot/options/SPY (15-min delayed, Starter plan).
Staleness: 8h — swing timeframe.
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

# NTM filter: ±10% of current price, 0-60 DTE
NTM_BAND_PCT = 0.10
MAX_DTE = 60


async def _get_spy_price() -> Optional[float]:
    """Get current SPY price for NTM filtering."""
    try:
        if get_price_history:
            data = await get_price_history("SPY", days=5)
            if data is not None and not data.empty and "close" in data.columns:
                return float(data["close"].iloc[-1])
    except Exception as e:
        logger.warning("polygon_oi_ratio: failed to get SPY price: %s", e)
    return None


async def compute_score() -> Optional[FactorReading]:
    """
    Aggregate SPY option open interest from Polygon snapshot.
    Contrarian scoring: high put OI = hedging/fear = bullish signal.
    """
    if not POLYGON_API_KEY:
        logger.warning("polygon_oi_ratio: POLYGON_API_KEY not set — skipping")
        return None

    spy_price = await _get_spy_price()
    if not spy_price:
        logger.warning("polygon_oi_ratio: cannot determine SPY price — skipping")
        return None

    strike_lo = round(spy_price * (1 - NTM_BAND_PCT), 0)
    strike_hi = round(spy_price * (1 + NTM_BAND_PCT), 0)

    chain = await get_options_snapshot(
        "SPY",
        strike_gte=strike_lo,
        strike_lte=strike_hi,
    )
    if not chain:
        logger.warning("polygon_oi_ratio: Polygon returned empty SPY chain")
        return None

    today = datetime.utcnow().date()
    max_exp = today + timedelta(days=MAX_DTE)

    put_oi = 0
    call_oi = 0
    contracts_counted = 0

    for contract in chain:
        details = contract.get("details", {})
        contract_type = (details.get("contract_type") or "").lower()
        expiry_str = str(details.get("expiration_date", ""))[:10]

        # Filter by DTE
        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if expiry > max_exp:
            continue

        day = contract.get("day", {})
        oi = day.get("open_interest") or 0

        if contract_type == "put":
            put_oi += oi
        elif contract_type == "call":
            call_oi += oi

        if oi > 0:
            contracts_counted += 1

    if put_oi == 0 and call_oi == 0:
        logger.warning("polygon_oi_ratio: zero OI (market closed?)")
        return None

    oi_ratio = put_oi / call_oi if call_oi > 0 else 0.0
    score = _score_oi_ratio(oi_ratio)

    logger.info(
        "polygon_oi_ratio: OI ratio=%.3f (puts=%d, calls=%d, %d contracts, NTM %.0f-%.0f)",
        oi_ratio, put_oi, call_oi, contracts_counted, strike_lo, strike_hi,
    )

    return FactorReading(
        factor_id="polygon_oi_ratio",
        score=score,
        signal=score_to_signal(score),
        detail=(
            f"SPY P/C OI ratio: {oi_ratio:.3f} "
            f"(puts {put_oi:,} / calls {call_oi:,}, "
            f"{contracts_counted} contracts, NTM ±10%)"
        ),
        timestamp=datetime.utcnow(),
        source="polygon",
        raw_data={
            "oi_ratio": round(float(oi_ratio), 4),
            "put_oi": int(put_oi),
            "call_oi": int(call_oi),
            "contracts_counted": contracts_counted,
            "contracts_total": len(chain),
            "strike_range": [strike_lo, strike_hi],
            "spy_price": round(float(spy_price), 2),
        },
    )


def _score_oi_ratio(oi_ratio: float) -> float:
    """
    Contrarian scoring of put/call OI ratio.
    OI thresholds are higher than volume PCR — OI is stickier.
    """
    if oi_ratio >= 1.5:
        return 0.7    # Extreme hedging — strong contrarian bullish
    elif oi_ratio >= 1.2:
        return 0.4    # Elevated hedging — mildly bullish
    elif oi_ratio >= 1.0:
        return 0.2    # Above parity
    elif oi_ratio >= 0.8:
        return 0.0    # Normal territory
    elif oi_ratio >= 0.6:
        return -0.3   # Low hedging — complacency
    else:
        return -0.6   # Extreme complacency — contrarian bearish
