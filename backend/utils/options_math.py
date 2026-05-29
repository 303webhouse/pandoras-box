"""Shared options-math helpers.

Single source of truth for mid-price / Greeks extraction / bid-ask spread
computation across the integrations layer (position-pricing via
`get_spread_value`, `get_single_option_value`, `get_multi_leg_value`,
`get_ticker_greeks_summary`) and the new hub_get_options_chain service
layer (chain-display).

Extracted from the prior private helpers `_get_contract_mid` and
`_get_contract_greeks` in `integrations.uw_api` (2026-05-26, Phase
hub_get_options_chain Task 3). Behavior preservation is byte-for-byte —
no semantic change to existing callers.

`compute_bid_ask_spread_pct` is genuinely new: it powers DAEDALUS's
"bid-ask spread > 10% of premium = liquidity flag" hard rule. Required
both bid AND ask present and > 0 (ATLAS Pass 1 finding M3) — when
either is missing, returns None so the >10% gate doesn't fire on a
contract whose liquidity is unknown rather than wide.

`bs_greeks_from_iv` is added in Tier 2 (2026-05-29): computes per-contract
Black-Scholes Greeks from UW-provided IV. Requires no new dependencies —
uses math.erf for the normal CDF approximation.

All functions operate on the normalized contract dict shape returned by
`integrations.uw_api.get_options_snapshot()` — keys:
    last_quote.{bid, ask}
    last_trade.price
    day.{close, vwap}
    greeks.{delta, gamma, theta, vega}
    implied_volatility
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erf (Abramowitz & Stegun identity)."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def compute_mid(contract: Dict[str, Any]) -> Optional[float]:
    """Mid-price from bid/ask, falling back to last trade, day close, vwap.

    Behavior identical to the prior `_get_contract_mid` in uw_api.py.
    Fallback chain on each step:
        1. bid/ask mid (both > 0)
        2. last_trade.price (> 0)
        3. day.close (> 0)
        4. day.vwap (> 0)
    Returns None when no fallback yields a usable price.
    """
    quote = contract.get("last_quote", {}) or {}
    bid = quote.get("bid")
    ask = quote.get("ask")
    if bid and ask and float(bid) > 0 and float(ask) > 0:
        return round((float(bid) + float(ask)) / 2, 4)
    trade = contract.get("last_trade", {}) or {}
    price = trade.get("price")
    if price and float(price) > 0:
        return float(price)
    day = contract.get("day", {}) or {}
    close = day.get("close")
    if close and float(close) > 0:
        return float(close)
    vwap = day.get("vwap")
    if vwap and float(vwap) > 0:
        return float(vwap)
    return None


def compute_bid_ask_spread_pct(contract: Dict[str, Any]) -> Optional[float]:
    """Bid-ask spread as % of mid. Used by DAEDALUS's >10% liquidity flag.

    ATLAS Pass 1 M3: REQUIRES both bid AND ask present and > 0; returns
    None otherwise — even when mid is computable from fallback chain
    (last_trade, day.close, vwap). When bid/ask are unknown, "wide spread"
    is the wrong concept; the liquidity status is "unknown" and the >10%
    flag should NOT fire on a None value. DAEDALUS treats None as
    "liquidity not assessable" rather than "fails the 10% gate."

    Returns None if:
    - last_quote.bid is missing / non-numeric / not > 0
    - last_quote.ask is missing / non-numeric / not > 0
    - computed mid is None or <= 0 (defense in depth; shouldn't happen
      when bid AND ask are both positive numerics)
    """
    quote = contract.get("last_quote", {}) or {}
    bid = quote.get("bid")
    ask = quote.get("ask")
    if bid is None or ask is None:
        return None
    try:
        bid_f = float(bid)
        ask_f = float(ask)
    except (TypeError, ValueError):
        return None
    if bid_f <= 0 or ask_f <= 0:
        return None
    mid = compute_mid(contract)
    if mid is None or mid <= 0:
        return None
    return round((abs(ask_f - bid_f) / mid) * 100, 2)


def extract_greeks(contract: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Greeks dict from normalized contract. Single source of truth.

    Returns {delta, gamma, theta, vega, iv} — float-or-None values
    propagated as-is from the normalized contract dict. The chain-display
    path surfaces these in the contracts[] array; the position-pricing
    path (get_spread_value etc.) consumes them via the same function.

    ATLAS Pass 1 L2 — Per-Greek nullability is INDEPENDENT. Each greek
    field reads via contract.get("greeks", {}).get(<field>) and propagates
    None when the upstream value is missing. A contract may legitimately
    return e.g. {delta: 0.52, gamma: 0.045, theta: -0.08, vega: None,
    iv: 0.28} if UW computed all Greeks except vega for that strike.
    Callers must null-check each Greek independently; do NOT treat
    any-None as "all-Greeks-unavailable."
    """
    greeks = contract.get("greeks", {}) or {}
    return {
        "delta": greeks.get("delta"),
        "gamma": greeks.get("gamma"),
        "theta": greeks.get("theta"),
        "vega": greeks.get("vega"),
        "iv": contract.get("implied_volatility"),
    }


def bs_greeks_from_iv(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    iv: Optional[float],
    option_type: str,
) -> Dict[str, Optional[float]]:
    """Black-Scholes Greeks from UW-provided implied volatility.

    Returns {delta, gamma, theta, vega} as floats, or all None when inputs
    are invalid. Never raises — returns nulls on any degenerate input so the
    chain envelope's per-contract null-rendering works correctly.

    Conventions:
        - vega is per 1% change in IV (divide by 100 from raw BSM vega)
        - theta is per calendar day (divide by 365)
        - delta (put) is negative: range [-1, 0]
        - gamma is always positive
        - theta is always negative for long positions

    Limitations (v1, Tier 2):
        - Assumes European exercise and zero dividends. For American-style
          equity options with dividend-paying underlyings, modeled Greeks will
          differ from broker-displayed Greeks at the margins — typically <5%
          on delta/gamma for ATM contracts, larger for deep ITM puts on
          high-yield underlyings. Tier 3 separate brief for dividend-yield
          input and American-exercise adjustment.

    Args:
        spot: Underlying price.
        strike: Option strike price.
        time_to_expiry_years: Calendar days to expiry / 365. Must be > 0.
        risk_free_rate: Annualized risk-free rate as a decimal (e.g. 0.0368).
        iv: Implied volatility as a decimal (e.g. 0.25 for 25%). None / <=0 → all None.
        option_type: "call" or "put" (case-insensitive).
    """
    _null = {"delta": None, "gamma": None, "theta": None, "vega": None}

    if iv is None or iv <= 0:
        return _null
    if time_to_expiry_years <= 0:
        return _null
    if spot is None or spot <= 0 or strike is None or strike <= 0:
        return _null

    S = float(spot)
    K = float(strike)
    T = float(time_to_expiry_years)
    r = float(risk_free_rate)
    sigma = float(iv)
    opt = option_type.lower()

    try:
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        phi_d1 = _norm_pdf(d1)
        N_d1 = _norm_cdf(d1)
        N_d2 = _norm_cdf(d2)
        N_neg_d1 = 1.0 - N_d1
        N_neg_d2 = 1.0 - N_d2

        if opt == "call":
            delta = N_d1
            theta = (
                -S * phi_d1 * sigma / (2.0 * sqrt_T)
                - r * K * math.exp(-r * T) * N_d2
            ) / 365.0
        else:
            delta = N_d1 - 1.0
            theta = (
                -S * phi_d1 * sigma / (2.0 * sqrt_T)
                + r * K * math.exp(-r * T) * N_neg_d2
            ) / 365.0

        gamma = phi_d1 / (S * sigma * sqrt_T)
        vega = S * phi_d1 * sqrt_T / 100.0

        return {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "theta": round(theta, 6),
            "vega": round(vega, 6),
        }
    except (ValueError, ZeroDivisionError, OverflowError):
        return _null
