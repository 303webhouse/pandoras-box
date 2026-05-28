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

All three functions operate on the normalized contract dict shape
returned by `integrations.uw_api.get_options_snapshot()` — keys:
    last_quote.{bid, ask}
    last_trade.price
    day.{close, vwap}
    greeks.{delta, gamma, theta, vega}
    implied_volatility
"""

from __future__ import annotations

from typing import Any, Dict, Optional


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
