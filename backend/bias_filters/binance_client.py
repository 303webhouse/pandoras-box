"""
Market Microstructure Client (Binance spot + OKX fallback)
Fetches spot orderbook depth and perp-vs-spot basis, per symbol.

S-3 Phase 1.5 (FA-7): get_spot_orderbook_skew() and get_quarterly_basis() are
now per-symbol parametrized with symbol="BTC" default — every existing caller
is signature-compatible and behavior-identical. Cache keys are per-symbol.
HYPE and FARTCOIN are not listed on Binance spot (HTTP 400, verified 2026-07-13)
and return NA:NOT_LISTED_BINANCE_SPOT for orderbook calls. OKX spot fallback
is available for those symbols for price/basis if needed.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import httpx

from config.crypto_sanity_bounds import check_price, check_basis_annualized
from bias_filters.crypto_vendor_health import record_observation

logger = logging.getLogger(__name__)

# API Configuration
BINANCE_SPOT_URL = "https://data-api.binance.vision/api/v3"  # geo-friendly mirror
_binance_perp_base = os.getenv("CRYPTO_BINANCE_PERP_BASE", "https://fapi.binance.com").rstrip("/")
BINANCE_FUTURES_URL = (
    _binance_perp_base if _binance_perp_base.endswith("/fapi/v1")
    else f"{_binance_perp_base}/fapi/v1"
)
BINANCE_PERP_HTTP_PROXY = os.getenv("CRYPTO_BINANCE_PERP_HTTP_PROXY", "").strip() or None
OKX_MARKET_URL = "https://www.okx.com/api/v5/market"

# Per-symbol Binance spot symbol (None = not listed on Binance spot).
# Verified 2026-07-13 via data-api.binance.vision.
_BINANCE_SPOT_SYMBOL: Dict[str, Optional[str]] = {
    "BTC":      "BTCUSDT",
    "ETH":      "ETHUSDT",
    "SOL":      "SOLUSDT",
    "HYPE":     None,       # HTTP 400 "Invalid symbol" (verified 2026-07-13)
    "ZEC":      "ZECUSDT",  # ZEC IS listed on Binance spot (verified 2026-07-13)
    "FARTCOIN": None,       # HTTP 400 "Invalid symbol" (verified 2026-07-13)
}

# Per-symbol OKX swap instrument ID for perp-price/basis fallback.
_OKX_SWAP_INSTID: Dict[str, str] = {
    "BTC":      "BTC-USDT-SWAP",
    "ETH":      "ETH-USDT-SWAP",
    "SOL":      "SOL-USDT-SWAP",
    "HYPE":     "HYPE-USDT-SWAP",
    "ZEC":      "ZEC-USDT-SWAP",
    "FARTCOIN": "FARTCOIN-USDT-SWAP",
}

# Per-symbol OKX spot instrument ID for spot-price fallback.
_OKX_SPOT_INSTID: Dict[str, str] = {
    "BTC":      "BTC-USDT",
    "ETH":      "ETH-USDT",
    "SOL":      "SOL-USDT",
    "HYPE":     "HYPE-USDT",
    "ZEC":      "ZEC-USDT",
    "FARTCOIN": "FARTCOIN-USDT",
}

# Per-symbol OKX spot orderbook instrument ID (HYPE/FARTCOIN: OKX spot only).
_OKX_SPOT_BOOK_INSTID: Dict[str, str] = {
    "BTC":      "BTC-USDT",
    "ETH":      "ETH-USDT",
    "SOL":      "SOL-USDT",
    "HYPE":     "HYPE-USDT",
    "ZEC":      "ZEC-USDT",
    "FARTCOIN": "FARTCOIN-USDT",
}

# Cache for API responses
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_ORDERBOOK = 60   # 1 minute for orderbook
CACHE_TTL_BASIS = 300      # 5 minutes for basis


def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    """Get cached response if not expired"""
    if key in _cache:
        cached = _cache[key]
        if datetime.now(timezone.utc) < cached["expires_at"]:
            return cached["data"]
    return None


def _set_cache(key: str, data: Any, ttl: int):
    """Cache response with TTL"""
    _cache[key] = {
        "data": data,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl)
    }


def _na_cell(symbol: str, reason: str) -> Dict[str, Any]:
    """Return a §4.2-contract NA cell — never zeros, never nulls without reason."""
    return {
        "state": "NA",
        "reason": reason,
        "symbol": symbol,
        "signal": "UNKNOWN",
    }


async def _make_request(url: str, params: Dict[str, Any] = None) -> Optional[Dict]:
    """Make request to a public market API endpoint"""
    try:
        client_kwargs: Dict[str, Any] = {"timeout": 10.0}
        if BINANCE_PERP_HTTP_PROXY and url.startswith(BINANCE_FUTURES_URL):
            client_kwargs["proxy"] = BINANCE_PERP_HTTP_PROXY

        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.get(url, params=params)

            if response.status_code not in (200,):
                if response.status_code == 451:
                    logger.debug(f"Market API geo-restricted ({url}): 451 - using fallback")
                else:
                    logger.warning(f"Market API error ({url}): {response.status_code} - {response.text}")
                return None

            return response.json()

    except Exception as e:
        logger.warning(f"Market API request failed ({url}): {e}")
        return None


def _normalize_okx_book(okx_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert OKX orderbook payload into Binance-like shape."""
    if not okx_data or okx_data.get("code") != "0":
        return None

    rows = okx_data.get("data") or []
    if not rows:
        return None

    row = rows[0]
    bids = row.get("bids") or []
    asks = row.get("asks") or []
    if not bids or not asks:
        return None

    return {
        "bids": [[b[0], b[1]] for b in bids if len(b) >= 2],
        "asks": [[a[0], a[1]] for a in asks if len(a) >= 2],
    }


async def get_spot_orderbook_skew(symbol: str = "BTC") -> Dict[str, Any]:
    """
    Get spot orderbook depth and calculate bid/ask imbalance for symbol.

    symbol defaults to "BTC" — all existing callers are signature-compatible.
    HYPE and FARTCOIN are not listed on Binance spot and return
    NA:NOT_LISTED_BINANCE_SPOT; OKX spot orderbook is used as fallback for
    those symbols.

    Returns:
        {
            "bid_depth": 150.5,
            "ask_depth": 120.3,
            "imbalance": 0.11,
            "imbalance_pct": 11.0,
            "sentiment": "bid_heavy" | "ask_heavy" | "balanced",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    symbol = (symbol or "BTC").upper()
    binance_spot_sym = _BINANCE_SPOT_SYMBOL.get(symbol)
    okx_spot_book = _OKX_SPOT_BOOK_INSTID.get(symbol)

    cache_key = f"orderbook_skew:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    data = None
    source = "unavailable"

    if binance_spot_sym is not None:
        # Try Binance spot depth first (geo-friendly mirror)
        data = await _make_request(f"{BINANCE_SPOT_URL}/depth", {
            "symbol": binance_spot_sym,
            "limit": 1000
        })
        if data and "bids" in data:
            source = "binance_vision"
        else:
            data = None

    if data is None and okx_spot_book:
        # OKX spot orderbook fallback (also primary for HYPE/FARTCOIN)
        okx_data = await _make_request(f"{OKX_MARKET_URL}/books", {
            "instId": okx_spot_book,
            "sz": 400
        })
        data = _normalize_okx_book(okx_data or {})
        if data:
            source = "okx_spot"

    if binance_spot_sym is None and not okx_spot_book:
        # Structurally impossible: all six symbols have an OKX spot entry.
        # Guard here for completeness.
        await record_observation("binance_spot", "orderbook_skew", symbol, success=False,
                                 reason=f"NA:NOT_LISTED_BINANCE_SPOT and no OKX spot entry for {symbol}")
        return _na_cell(symbol, "NA:NOT_LISTED_BINANCE_SPOT")

    if not data or "bids" not in data or "asks" not in data:
        if binance_spot_sym is None:
            # Symbol not on Binance spot AND OKX also failed
            reason = f"NA:NOT_LISTED_BINANCE_SPOT and OKX orderbook unavailable for {symbol}"
        else:
            reason = f"Failed to fetch orderbook from Binance Vision or OKX for {symbol}"
        await record_observation("binance_spot", "orderbook_skew", symbol, success=False, reason=reason)
        return {
            "bid_depth": None,
            "ask_depth": None,
            "imbalance": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "source": "unavailable",
            "symbol": symbol,
            "error": reason
        }

    bids = data["bids"]
    asks = data["asks"]

    if not bids or not asks:
        await record_observation("binance_spot", "orderbook_skew", symbol, success=False,
                                 reason="Empty bids/asks in orderbook response")
        return {
            "bid_depth": 0,
            "ask_depth": 0,
            "imbalance": 0,
            "sentiment": "balanced",
            "signal": "NEUTRAL",
            "symbol": symbol,
        }

    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    mid_price = (best_bid + best_ask) / 2

    bid_threshold = mid_price * 0.98
    ask_threshold = mid_price * 1.02

    bid_depth = sum(float(b[1]) for b in bids if float(b[0]) >= bid_threshold)
    ask_depth = sum(float(a[1]) for a in asks if float(a[0]) <= ask_threshold)

    total_depth = bid_depth + ask_depth
    imbalance = (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0
    imbalance_pct = imbalance * 100

    if imbalance > 0.15:
        sentiment = "bid_heavy"
        signal = "FIRING"
    elif imbalance < -0.15:
        sentiment = "ask_heavy"
        signal = "FIRING"
    else:
        sentiment = "balanced"
        signal = "NEUTRAL"

    result = {
        "bid_depth": round(bid_depth, 2),
        "ask_depth": round(ask_depth, 2),
        "total_depth": round(total_depth, 2),
        "imbalance": round(imbalance, 4),
        "imbalance_pct": round(imbalance_pct, 1),
        "mid_price": round(mid_price, 2),
        "spread": round(best_ask - best_bid, 2),
        "spread_bps": round((best_ask - best_bid) / mid_price * 10000, 2),
        "sentiment": sentiment,
        "signal": signal,
        "source": source,
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    ok, reason = check_price(symbol, result["mid_price"])
    status = await record_observation(source, "orderbook_skew", symbol, success=True, value_valid=ok, reason=reason)
    if not ok:
        logger.warning("Binance orderbook_skew[%s] bounds check failed, not caching: %s", symbol, reason)
        return {**result, "signal": "UNKNOWN", "error": reason, "health_status": status}

    _set_cache(cache_key, result, CACHE_TTL_ORDERBOOK)
    logger.info(f"Orderbook[{symbol}]: Bid {bid_depth:.1f}, Ask {ask_depth:.1f}, Imbalance {imbalance_pct:+.1f}% -> {sentiment}")
    return {**result, "health_status": status}


async def get_quarterly_basis(symbol: str = "BTC") -> Dict[str, Any]:
    """
    Calculate quarterly futures basis (futures premium over spot) for symbol.

    symbol defaults to "BTC" — all existing callers are signature-compatible.
    Binance Futures is geo-blocked from Railway (HTTP 451) for all symbols;
    OKX swap is used as the perp-price fallback.

    Returns:
        {
            "spot_price": 100000,
            "futures_price": 101500,
            "basis_pct": 1.5,
            "basis_annualized": 12.5,
            "sentiment": "contango" | "backwardation" | "neutral",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    symbol = (symbol or "BTC").upper()
    binance_spot_sym = _BINANCE_SPOT_SYMBOL.get(symbol)
    okx_spot = _OKX_SPOT_INSTID.get(symbol)
    okx_swap = _OKX_SWAP_INSTID.get(symbol)

    cache_key = f"quarterly_basis:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    # --- Spot price ---
    spot_data = None
    spot_source = "unavailable"

    if binance_spot_sym:
        spot_data = await _make_request(f"{BINANCE_SPOT_URL}/ticker/price", {
            "symbol": binance_spot_sym
        })
        if spot_data and "price" in spot_data:
            spot_source = "binance_vision"
        else:
            spot_data = None

    if spot_data is None and okx_spot:
        okx_spot_resp = await _make_request(f"{OKX_MARKET_URL}/ticker", {"instId": okx_spot})
        if okx_spot_resp and okx_spot_resp.get("code") == "0" and okx_spot_resp.get("data"):
            spot_data = {"price": okx_spot_resp["data"][0].get("last")}
            spot_source = "okx_spot"

    if not spot_data or "price" not in spot_data:
        vendor_label = "binance_vision" if binance_spot_sym else "okx_spot"
        await record_observation(vendor_label, "quarterly_basis", symbol, success=False,
                                 reason=f"Failed to fetch spot price for {symbol}")
        return {
            "spot_price": None,
            "basis_annualized": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "source": "unavailable",
            "symbol": symbol,
            "error": f"Failed to fetch spot price for {symbol}"
        }

    spot_price = float(spot_data["price"])

    # --- Perp/futures price (Binance Futures geo-blocked → OKX swap fallback) ---
    perp_data = await _make_request(f"{BINANCE_FUTURES_URL}/ticker/price", {
        "symbol": binance_spot_sym or (symbol + "USDT")
    })
    perp_source = "binance_futures"

    if not perp_data or "price" not in perp_data:
        if okx_swap:
            okx_perp_resp = await _make_request(f"{OKX_MARKET_URL}/ticker", {"instId": okx_swap})
            if okx_perp_resp and okx_perp_resp.get("code") == "0" and okx_perp_resp.get("data"):
                perp_data = {"price": okx_perp_resp["data"][0].get("last")}
                perp_source = "okx_swap"

    if not perp_data or "price" not in perp_data:
        await record_observation("binance_futures", "quarterly_basis", symbol, success=False,
                                 reason=f"Failed to fetch perp/futures price for {symbol} (likely geo-block — HTTP 451 confirmed from Railway)")
        return {
            "spot_price": spot_price,
            "basis_annualized": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "source": f"{spot_source}->unavailable",
            "symbol": symbol,
            "error": f"Failed to fetch perp/futures price for {symbol}"
        }

    futures_price = float(perp_data["price"])
    basis_pct = (futures_price - spot_price) / spot_price * 100
    basis_annualized = basis_pct * 365 / 7

    if basis_annualized > 15:
        sentiment = "extreme_contango"
        signal = "FIRING"
    elif basis_annualized > 5:
        sentiment = "contango"
        signal = "NEUTRAL"
    elif basis_annualized < -5:
        sentiment = "backwardation"
        signal = "FIRING"
    else:
        sentiment = "neutral"
        signal = "NEUTRAL"

    result = {
        "spot_price": round(spot_price, 2),
        "futures_price": round(futures_price, 2),
        "basis_pct": round(basis_pct, 4),
        "basis_annualized": round(basis_annualized, 2),
        "sentiment": sentiment,
        "signal": signal,
        "source": f"{spot_source}+{perp_source}",
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    price_ok, price_reason = check_price(symbol, result["spot_price"])
    basis_ok, basis_reason = check_basis_annualized(symbol, result["basis_annualized"])
    ok = price_ok and basis_ok
    reason = price_reason or basis_reason
    vendor_label = f"{spot_source}+{perp_source}"
    status = await record_observation(vendor_label, "quarterly_basis", symbol, success=True, value_valid=ok, reason=reason)
    if not ok:
        logger.warning("quarterly_basis[%s] bounds check failed, not caching: %s", symbol, reason)
        return {**result, "signal": "UNKNOWN", "error": reason, "health_status": status}

    _set_cache(cache_key, result, CACHE_TTL_BASIS)
    logger.info(f"Basis[{symbol}]: {basis_pct:.4f}% ({basis_annualized:.2f}% ann.) -> {sentiment}")
    return {**result, "health_status": status}


async def get_all_binance_data(symbol: str = "BTC") -> Dict[str, Any]:
    """Fetch all market microstructure data for symbol."""
    import asyncio

    results = await asyncio.gather(
        get_spot_orderbook_skew(symbol),
        get_quarterly_basis(symbol),
        return_exceptions=True
    )

    return {
        "orderbook": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
        "basis": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
