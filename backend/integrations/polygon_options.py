"""
Polygon.io Options Integration

Fetches options chain snapshots for spread-level P&L calculation.
Uses the /v3/snapshot/options/{underlyingAsset} endpoint to get
bid/ask/last/greeks for all contracts on a ticker in one call.

Starter plan ($29/mo): 15-min delayed, unlimited calls.
"""

import os
import logging
import httpx
from typing import Dict, List, Optional, Any
from datetime import date

logger = logging.getLogger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY") or ""
POLYGON_BASE = "https://api.polygon.io"


async def get_options_snapshot(underlying: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch full options chain snapshot for a ticker.
    Returns list of contract snapshots with greeks, quotes, and underlying info.
    """
    if not POLYGON_API_KEY:
        logger.warning("POLYGON_API_KEY not set — skipping options snapshot")
        return None

    url = f"{POLYGON_BASE}/v3/snapshot/options/{underlying}"
    params = {"apiKey": POLYGON_API_KEY, "limit": 250}

    all_results = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            while url:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.error("Polygon snapshot %s: HTTP %s — %s", underlying, resp.status_code, resp.text[:200])
                    return None

                data = resp.json()
                all_results.extend(data.get("results", []))

                # Handle pagination
                next_url = data.get("next_url")
                if next_url:
                    url = next_url
                    params = {"apiKey": POLYGON_API_KEY}  # next_url includes other params
                else:
                    url = None

    except Exception as e:
        logger.error("Polygon snapshot %s failed: %s", underlying, e)
        return None

    return all_results


def find_contract(
    chain: List[Dict[str, Any]],
    strike: float,
    expiry: str,
    option_type: str,  # "call" or "put"
) -> Optional[Dict[str, Any]]:
    """
    Find a specific contract in the chain snapshot by strike, expiry, and type.
    Returns the contract dict or None.
    """
    # Polygon expiry format in ticker: O:TSLA260320P00380000
    # But the details.expiration_date field is "2026-03-20"
    exp_str = str(expiry)[:10]  # normalize to YYYY-MM-DD

    for contract in chain:
        details = contract.get("details", {})
        if not details:
            continue

        c_type = details.get("contract_type", "").lower()
        c_strike = details.get("strike_price")
        c_expiry = str(details.get("expiration_date", ""))[:10]

        if c_type == option_type and c_expiry == exp_str and c_strike is not None:
            if abs(float(c_strike) - strike) < 0.01:
                return contract

    return None


def get_contract_mid(contract: Dict[str, Any]) -> Optional[float]:
    """Get mid-price from a contract's last quote."""
    quote = contract.get("last_quote", {})
    if not quote:
        return None

    bid = quote.get("bid")
    ask = quote.get("ask")

    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return round((bid + ask) / 2, 4)

    # Fall back to last trade price
    trade = contract.get("last_trade", {})
    if trade and trade.get("price"):
        return float(trade["price"])

    return None


def get_contract_greeks(contract: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Extract greeks from a contract snapshot."""
    greeks = contract.get("greeks", {})
    return {
        "delta": greeks.get("delta"),
        "gamma": greeks.get("gamma"),
        "theta": greeks.get("theta"),
        "vega": greeks.get("vega"),
        "iv": contract.get("implied_volatility"),
    }


async def get_spread_value(
    underlying: str,
    long_strike: float,
    short_strike: float,
    expiry: str,
    structure: str,
) -> Optional[Dict[str, Any]]:
    """
    Calculate current spread value from Polygon options snapshot.

    Returns dict with:
        spread_value: current mid-price of the spread (per share)
        long_mid: mid of the long leg
        short_mid: mid of the short leg
        long_greeks: greeks of the long leg
        short_greeks: greeks of the short leg
        underlying_price: current underlying price
    """
    chain = await get_options_snapshot(underlying)
    if not chain:
        return None

    # Determine option types based on structure
    s = (structure or "").lower()

    if "put" in s:
        long_type = "put"
        short_type = "put"
    elif "call" in s:
        long_type = "call"
        short_type = "call"
    else:
        return None

    # Find both legs
    long_contract = find_contract(chain, long_strike, expiry, long_type)
    short_contract = find_contract(chain, short_strike, expiry, short_type)

    if not long_contract or not short_contract:
        logger.warning(
            "Could not find contracts for %s %s/%s %s %s",
            underlying, long_strike, short_strike, expiry, structure
        )
        return None

    long_mid = get_contract_mid(long_contract)
    short_mid = get_contract_mid(short_contract)

    if long_mid is None or short_mid is None:
        return None

    # For debit spreads: value = long_mid - short_mid
    # For credit spreads: value = short_mid - long_mid (what you'd pay to close)
    if "debit" in s:
        spread_value = round(long_mid - short_mid, 4)
    elif "credit" in s:
        spread_value = round(short_mid - long_mid, 4)
    else:
        # Default: assume debit (long is more expensive)
        spread_value = round(long_mid - short_mid, 4)

    # Extract underlying price from any contract
    underlying_price = None
    for c in [long_contract, short_contract]:
        ua = c.get("underlying_asset", {})
        if ua and ua.get("price"):
            underlying_price = float(ua["price"])
            break

    return {
        "spread_value": spread_value,
        "long_mid": long_mid,
        "short_mid": short_mid,
        "long_greeks": get_contract_greeks(long_contract),
        "short_greeks": get_contract_greeks(short_contract),
        "underlying_price": underlying_price,
    }


async def get_single_option_value(
    underlying: str,
    strike: float,
    expiry: str,
    option_type: str,  # "call" or "put"
) -> Optional[Dict[str, Any]]:
    """Get current value of a single option leg (for long_put, long_call, etc.)."""
    chain = await get_options_snapshot(underlying)
    if not chain:
        return None

    contract = find_contract(chain, strike, expiry, option_type)
    if not contract:
        return None

    mid = get_contract_mid(contract)
    if mid is None:
        return None

    underlying_price = None
    ua = contract.get("underlying_asset", {})
    if ua and ua.get("price"):
        underlying_price = float(ua["price"])

    return {
        "option_value": mid,
        "greeks": get_contract_greeks(contract),
        "underlying_price": underlying_price,
    }


async def get_ticker_greeks_summary(
    underlying: str,
    positions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Get aggregate greeks for all positions on a ticker.
    Used by committee context to provide greeks awareness.
    """
    chain = await get_options_snapshot(underlying)
    if not chain:
        return None

    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    underlying_price = None

    for pos in positions:
        structure = (pos.get("structure") or "").lower()
        qty = pos.get("quantity", 1)
        expiry = pos.get("expiry")
        long_strike = pos.get("long_strike")
        short_strike = pos.get("short_strike")

        if not expiry or not long_strike:
            continue

        # Determine option type
        if "put" in structure:
            opt_type = "put"
        elif "call" in structure:
            opt_type = "call"
        else:
            continue

        # Long leg
        long_c = find_contract(chain, float(long_strike), str(expiry), opt_type)
        if long_c:
            g = get_contract_greeks(long_c)
            total_delta += (g.get("delta") or 0) * qty * 100
            total_gamma += (g.get("gamma") or 0) * qty * 100
            total_theta += (g.get("theta") or 0) * qty * 100
            total_vega += (g.get("vega") or 0) * qty * 100

            if not underlying_price:
                ua = long_c.get("underlying_asset", {})
                if ua and ua.get("price"):
                    underlying_price = float(ua["price"])

        # Short leg (if spread)
        if short_strike:
            short_c = find_contract(chain, float(short_strike), str(expiry), opt_type)
            if short_c:
                g = get_contract_greeks(short_c)
                # Short leg: negate greeks
                total_delta -= (g.get("delta") or 0) * qty * 100
                total_gamma -= (g.get("gamma") or 0) * qty * 100
                total_theta -= (g.get("theta") or 0) * qty * 100
                total_vega -= (g.get("vega") or 0) * qty * 100

    return {
        "underlying_price": underlying_price,
        "net_delta": round(total_delta, 2),
        "net_gamma": round(total_gamma, 4),
        "net_theta": round(total_theta, 2),
        "net_vega": round(total_vega, 2),
    }
