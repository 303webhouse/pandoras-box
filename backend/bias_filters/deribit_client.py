"""
Deribit API Client
Fetches options data for 25-delta skew calculation, per symbol.

S-3 Phase 1.5 (FA-7): get_25_delta_skew() is now per-symbol parametrized with
symbol="BTC" default — every existing caller is signature-compatible. Cache key
is per-symbol ("skew_25d:BTC"). Symbol-to-Deribit-currency mapping is 1:1 for
listed currencies; SOL trap guard: Deribit lists SOL as a currency but has zero
active option instruments (verified 2026-07-13) — the instrument-count check
prevents a silent "insufficient options data" error from masquerading as coverage.

API Documentation: https://docs.deribit.com/
No authentication required for public endpoints
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import httpx

from config.crypto_sanity_bounds import check_skew_25d
from bias_filters.crypto_vendor_health import record_observation

logger = logging.getLogger(__name__)

# API Configuration
DERIBIT_BASE_URL = "https://www.deribit.com/api/v2"

# Deribit currency for each tracked symbol.
# SOL/HYPE/ZEC/FARTCOIN are not covered (SOL has zero option instruments;
# the others aren't listed). Returns NA:NO_DERIBIT_COVERAGE for unlisted symbols.
_DERIBIT_CURRENCY: Dict[str, Optional[str]] = {
    "BTC":      "BTC",
    "ETH":      "ETH",
    "SOL":      None,  # Listed but ZERO active instruments (verified 2026-07-13)
    "HYPE":     None,  # Not present in Deribit get_currencies list
    "ZEC":      None,  # Not present in Deribit get_currencies list
    "FARTCOIN": None,  # Not present in Deribit get_currencies list
}

# Minimum instrument count before trusting a Deribit currency as "covered".
# SOL returned 0 instruments at verified time — below this threshold → NA.
_MIN_INSTRUMENT_COUNT = 1

# Cache for API responses
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    """Get cached response if not expired"""
    if key in _cache:
        cached = _cache[key]
        if datetime.now(timezone.utc) < cached["expires_at"]:
            return cached["data"]
    return None


def _set_cache(key: str, data: Any, ttl: int = CACHE_TTL_SECONDS):
    """Cache response with TTL"""
    _cache[key] = {
        "data": data,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl)
    }


def _na_cell(symbol: str, reason: str) -> Dict[str, Any]:
    """Return a §4.2-contract NA cell — never zeros, never nulls without reason."""
    return {
        "skew_25d": None,
        "sentiment": "unknown",
        "signal": "UNKNOWN",
        "state": "NA",
        "reason": reason,
        "symbol": symbol,
    }


async def _make_request(endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict]:
    """Make request to Deribit public API"""
    url = f"{DERIBIT_BASE_URL}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)

            if response.status_code != 200:
                logger.error(f"Deribit API error: {response.status_code} - {response.text}")
                return None

            data = response.json()
            if "result" in data:
                return data["result"]
            return data

    except Exception as e:
        logger.error(f"Deribit request failed: {e}")
        return None


async def get_25_delta_skew(symbol: str = "BTC") -> Dict[str, Any]:
    """
    Calculate 25-delta skew from options for the given symbol.

    symbol defaults to "BTC" — all existing callers are signature-compatible
    and behavior-identical. For BTC/ETH returns real computed skew. For SOL,
    returns NA:SOL_ZERO_INSTRUMENTS (instrument-count guard, the SOL trap).
    For HYPE/ZEC/FARTCOIN, returns NA:NO_DERIBIT_COVERAGE.

    25-delta skew = IV(25d put) - IV(25d call)
    - Positive skew: Higher demand for puts (bearish sentiment)
    - Negative skew: Higher demand for calls (bullish sentiment)

    Returns:
        {
            "skew_25d": -2.5,
            "sentiment": "bullish" | "bearish" | "neutral",
            "put_iv_25d": 45.2,
            "call_iv_25d": 47.7,
            "atm_iv": 46.5,
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    symbol = (symbol or "BTC").upper()

    # Symbol → Deribit currency mapping
    deribit_currency = _DERIBIT_CURRENCY.get(symbol)
    if deribit_currency is None:
        # Distinguish: SOL is listed but zero-instrument vs. not listed at all
        if symbol == "SOL":
            return _na_cell(symbol, "NA:SOL_ZERO_INSTRUMENTS")
        return _na_cell(symbol, "NA:NO_DERIBIT_COVERAGE")

    cache_key = f"skew_25d:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    # Get options book summary for this currency
    data = await _make_request("/public/get_book_summary_by_currency", {
        "currency": deribit_currency,
        "kind": "option"
    })

    if not data:
        await record_observation("deribit", "skew_25d", symbol, success=False, reason="Failed to fetch options data")
        return {
            "skew_25d": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": "Failed to fetch options data"
        }

    # Instrument-count guard: if zero option instruments, treat as NA (SOL trap).
    instrument_count = len(data) if isinstance(data, list) else 0
    if instrument_count < _MIN_INSTRUMENT_COUNT:
        reason = f"NA:ZERO_OPTION_INSTRUMENTS (Deribit {deribit_currency} returned {instrument_count} instruments)"
        await record_observation("deribit", "skew_25d", symbol, success=False, reason=reason)
        return _na_cell(symbol, reason)

    # Find options expiring in 7-30 days (most liquid for skew)
    now = datetime.now(timezone.utc)
    target_expiry_min = now + timedelta(days=7)
    target_expiry_max = now + timedelta(days=30)

    puts = []
    calls = []

    for instrument in data:
        instrument_name = instrument.get("instrument_name", "")

        # Parse instrument name: BTC-28JAN26-100000-P or BTC-28JAN26-100000-C
        parts = instrument_name.split("-")
        if len(parts) < 4:
            continue

        try:
            expiry_str = parts[1]
            day = int(expiry_str[:2])
            month_str = expiry_str[2:5]
            year = 2000 + int(expiry_str[5:7])

            month_map = {
                "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
            }
            month = month_map.get(month_str, 1)
            expiry = datetime(year, month, day, tzinfo=timezone.utc)

            if not (target_expiry_min <= expiry <= target_expiry_max):
                continue

            strike = float(parts[2])
            option_type = parts[3]  # P or C

            mark_iv = instrument.get("mark_iv", 0)
            underlying_price = instrument.get("underlying_price", 0)

            if mark_iv > 0 and underlying_price > 0:
                moneyness = strike / underlying_price

                option_data = {
                    "instrument": instrument_name,
                    "strike": strike,
                    "expiry": expiry,
                    "iv": mark_iv,
                    "moneyness": moneyness,
                    "underlying": underlying_price
                }

                if option_type == "P":
                    puts.append(option_data)
                elif option_type == "C":
                    calls.append(option_data)

        except (ValueError, KeyError, IndexError):
            continue

    if not puts or not calls:
        await record_observation("deribit", "skew_25d", symbol, success=False, reason="Insufficient options data for skew calculation")
        return {
            "skew_25d": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": "Insufficient options data for skew calculation"
        }

    put_25d_candidates = [p for p in puts if 0.85 <= p["moneyness"] <= 0.92]
    call_25d_candidates = [c for c in calls if 1.08 <= c["moneyness"] <= 1.15]

    if not put_25d_candidates or not call_25d_candidates:
        puts_sorted = sorted(puts, key=lambda x: abs(x["moneyness"] - 0.88))
        calls_sorted = sorted(calls, key=lambda x: abs(x["moneyness"] - 1.12))
        put_25d_candidates = puts_sorted[:3] if puts_sorted else []
        call_25d_candidates = calls_sorted[:3] if calls_sorted else []

    if not put_25d_candidates or not call_25d_candidates:
        await record_observation("deribit", "skew_25d", symbol, success=False, reason="Could not find 25-delta options")
        return {
            "skew_25d": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": "Could not find 25-delta options"
        }

    put_iv_25d = sum(p["iv"] for p in put_25d_candidates) / len(put_25d_candidates)
    call_iv_25d = sum(c["iv"] for c in call_25d_candidates) / len(call_25d_candidates)
    skew_25d = put_iv_25d - call_iv_25d

    atm_puts = [p for p in puts if 0.98 <= p["moneyness"] <= 1.02]
    atm_calls = [c for c in calls if 0.98 <= c["moneyness"] <= 1.02]
    atm_options = atm_puts + atm_calls
    atm_iv = sum(o["iv"] for o in atm_options) / len(atm_options) if atm_options else (put_iv_25d + call_iv_25d) / 2

    if skew_25d > 5:
        sentiment = "bearish"
        signal = "FIRING"
    elif skew_25d < -5:
        sentiment = "bullish"
        signal = "FIRING"
    else:
        sentiment = "neutral"
        signal = "NEUTRAL"

    result = {
        "skew_25d": round(skew_25d, 2),
        "sentiment": sentiment,
        "put_iv_25d": round(put_iv_25d, 2),
        "call_iv_25d": round(call_iv_25d, 2),
        "atm_iv": round(atm_iv, 2),
        "signal": signal,
        "options_analyzed": len(put_25d_candidates) + len(call_25d_candidates),
        "instrument_count": instrument_count,
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    ok, reason = check_skew_25d(symbol, result["skew_25d"])
    status = await record_observation("deribit", "skew_25d", symbol, success=True, value_valid=ok, reason=reason)
    if not ok:
        logger.warning("Deribit skew_25d[%s] bounds check failed, not caching: %s", symbol, reason)
        return {**result, "signal": "UNKNOWN", "error": reason, "health_status": status}

    _set_cache(cache_key, result)
    logger.info(f"Deribit 25d Skew[{symbol}]: {skew_25d:+.2f}% (put IV: {put_iv_25d:.1f}%, call IV: {call_iv_25d:.1f}%) -> {sentiment}")
    return {**result, "health_status": status}


async def get_options_summary(symbol: str = "BTC") -> Dict[str, Any]:
    """Get overall options market summary for symbol."""
    symbol = (symbol or "BTC").upper()
    deribit_currency = _DERIBIT_CURRENCY.get(symbol)
    if deribit_currency is None:
        return {"error": f"Deribit does not cover {symbol}", "symbol": symbol}

    cache_key = f"options_summary:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    index_name = f"{deribit_currency.lower()}_usd"
    index_data = await _make_request("/public/get_index_price", {"index_name": index_name})
    index_price = index_data.get("index_price", 0) if index_data else 0

    book_data = await _make_request("/public/get_book_summary_by_currency", {
        "currency": deribit_currency,
        "kind": "option"
    })

    if not book_data:
        return {"error": "Failed to fetch options summary", "symbol": symbol}

    total_volume = sum(i.get("volume", 0) for i in book_data)
    total_oi = sum(i.get("open_interest", 0) for i in book_data)

    put_oi = sum(i.get("open_interest", 0) for i in book_data if i.get("instrument_name", "").endswith("-P"))
    call_oi = sum(i.get("open_interest", 0) for i in book_data if i.get("instrument_name", "").endswith("-C"))
    put_call_ratio = put_oi / call_oi if call_oi > 0 else 1.0

    result = {
        "index_price": index_price,
        "total_volume_24h": total_volume,
        "total_open_interest": total_oi,
        "put_oi": put_oi,
        "call_oi": call_oi,
        "put_call_ratio": round(put_call_ratio, 3),
        "instrument_count": len(book_data),
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    _set_cache(cache_key, result)
    return result
