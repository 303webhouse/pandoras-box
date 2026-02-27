"""
IV Skew Factor — SPY put IV vs call IV using Polygon options snapshot.

Measures the implied volatility gap between near-the-money puts and calls.
Rising put IV relative to call IV signals hedging/fear demand (bearish).
Falling put IV relative to call IV signals speculative call buying (bullish).

Filter: ±5% of current SPY price, 7-45 DTE.
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
    from bias_engine.factor_utils import score_to_signal
    from integrations.polygon_options import get_options_snapshot, POLYGON_API_KEY
except ImportError:
    FactorReading = None
    score_to_signal = None
    get_options_snapshot = None
    POLYGON_API_KEY = ""

# Near-the-money filter parameters
NTM_BAND_PCT = 0.05   # ±5% of current price
MIN_DTE = 7
MAX_DTE = 45


async def compute_score() -> Optional[FactorReading]:
    """
    Compare average IV of near-the-money puts vs calls.
    Rising put IV = fear/hedging = bearish signal.
    """
    if not POLYGON_API_KEY:
        logger.warning("iv_skew: POLYGON_API_KEY not set — skipping")
        return None

    chain = await get_options_snapshot("SPY")
    if not chain:
        logger.warning("iv_skew: Polygon returned empty SPY chain")
        return None

    # Get underlying price from first contract with underlying_asset data
    underlying_price = None
    for contract in chain:
        ua = contract.get("underlying_asset", {})
        if ua and ua.get("price"):
            underlying_price = float(ua["price"])
            break

    if not underlying_price:
        logger.warning("iv_skew: Could not determine SPY underlying price")
        return None

    lower_bound = underlying_price * (1 - NTM_BAND_PCT)
    upper_bound = underlying_price * (1 + NTM_BAND_PCT)

    today = datetime.utcnow().date()
    min_exp = today + timedelta(days=MIN_DTE)
    max_exp = today + timedelta(days=MAX_DTE)

    put_ivs = []
    call_ivs = []

    for contract in chain:
        details = contract.get("details", {})
        contract_type = (details.get("contract_type") or "").lower()
        strike = details.get("strike_price")
        expiry_str = str(details.get("expiration_date", ""))[:10]
        iv = contract.get("implied_volatility")

        if strike is None or iv is None or iv <= 0:
            continue

        if not (lower_bound <= float(strike) <= upper_bound):
            continue

        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (min_exp <= expiry <= max_exp):
            continue

        if contract_type == "put":
            put_ivs.append(float(iv))
        elif contract_type == "call":
            call_ivs.append(float(iv))

    if len(put_ivs) < 3 or len(call_ivs) < 3:
        logger.warning(
            "iv_skew: insufficient NTM contracts (puts=%d, calls=%d) — skipping",
            len(put_ivs), len(call_ivs),
        )
        return None

    avg_put_iv = sum(put_ivs) / len(put_ivs)
    avg_call_iv = sum(call_ivs) / len(call_ivs)

    skew_pct = ((avg_put_iv - avg_call_iv) / avg_call_iv) * 100 if avg_call_iv > 0 else 0.0
    score = _score_skew(skew_pct)

    return FactorReading(
        factor_id="iv_skew",
        score=score,
        signal=score_to_signal(score),
        detail=(
            f"SPY IV skew: put IV {avg_put_iv:.1%} vs call IV {avg_call_iv:.1%} "
            f"(skew {skew_pct:+.1f}%, {len(put_ivs)}p/{len(call_ivs)}c NTM)"
        ),
        timestamp=datetime.utcnow(),
        source="polygon",
        raw_data={
            "avg_put_iv": round(float(avg_put_iv), 4),
            "avg_call_iv": round(float(avg_call_iv), 4),
            "skew_pct": round(float(skew_pct), 2),
            "put_count": len(put_ivs),
            "call_count": len(call_ivs),
            "underlying_price": round(float(underlying_price), 2),
        },
    )


def _score_skew(skew_pct: float) -> float:
    """
    Negative score when puts expensive vs calls (bearish fear signal).
    Positive score when calls expensive vs puts (speculative bullish).
    """
    if skew_pct >= 10:
        return -0.6   # Strong put premium = fear/hedging = bearish
    elif skew_pct >= 5:
        return -0.3   # Mild put premium = caution
    elif skew_pct >= 2:
        return -0.1   # Slight put bias
    elif skew_pct >= -2:
        return 0.0    # Roughly equal = neutral
    elif skew_pct >= -5:
        return 0.3    # Mild call premium = speculative bullish
    else:
        return 0.5    # Strong call premium = risk-on sentiment
