"""
Deribit API Client
Fetches BTC options data for 25-delta skew calculation

API Documentation: https://docs.deribit.com/
No authentication required for public endpoints
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger(__name__)

# API Configuration
DERIBIT_BASE_URL = "https://www.deribit.com/api/v2"

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


async def get_25_delta_skew() -> Dict[str, Any]:
    """
    Calculate 25-delta skew from BTC options
    
    25-delta skew = IV(25d put) - IV(25d call)
    - Positive skew: Higher demand for puts (bearish sentiment)
    - Negative skew: Higher demand for calls (bullish sentiment)
    
    Returns:
        {
            "skew_25d": -2.5,  # Percentage points
            "sentiment": "bullish" | "bearish" | "neutral",
            "put_iv_25d": 45.2,
            "call_iv_25d": 47.7,
            "atm_iv": 46.5,
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "skew_25d"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get BTC options book summary
    data = await _make_request("/public/get_book_summary_by_currency", {
        "currency": "BTC",
        "kind": "option"
    })
    
    if not data:
        return {
            "skew_25d": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch options data"
        }
    
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
            # Parse expiry date
            expiry_str = parts[1]
            # Format: 28JAN26
            day = int(expiry_str[:2])
            month_str = expiry_str[2:5]
            year = 2000 + int(expiry_str[5:7])
            
            month_map = {
                "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
            }
            month = month_map.get(month_str, 1)
            
            expiry = datetime(year, month, day, tzinfo=timezone.utc)
            
            # Filter by expiry range
            if not (target_expiry_min <= expiry <= target_expiry_max):
                continue
            
            strike = float(parts[2])
            option_type = parts[3]  # P or C
            
            # Get mark IV
            mark_iv = instrument.get("mark_iv", 0)
            underlying_price = instrument.get("underlying_price", 0)
            
            if mark_iv > 0 and underlying_price > 0:
                # Calculate delta approximation
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
        
        except (ValueError, KeyError, IndexError) as e:
            continue
    
    if not puts or not calls:
        return {
            "skew_25d": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "error": "Insufficient options data for skew calculation"
        }
    
    # Find 25-delta options (approximately 0.85-0.90 moneyness for puts, 1.10-1.15 for calls)
    # 25-delta put is OTM put with delta ~ -0.25 (strike ~ 10-15% below spot)
    # 25-delta call is OTM call with delta ~ 0.25 (strike ~ 10-15% above spot)
    
    put_25d_candidates = [p for p in puts if 0.85 <= p["moneyness"] <= 0.92]
    call_25d_candidates = [c for c in calls if 1.08 <= c["moneyness"] <= 1.15]
    
    if not put_25d_candidates or not call_25d_candidates:
        # Fallback: use closest available
        puts_sorted = sorted(puts, key=lambda x: abs(x["moneyness"] - 0.88))
        calls_sorted = sorted(calls, key=lambda x: abs(x["moneyness"] - 1.12))
        put_25d_candidates = puts_sorted[:3] if puts_sorted else []
        call_25d_candidates = calls_sorted[:3] if calls_sorted else []
    
    if not put_25d_candidates or not call_25d_candidates:
        return {
            "skew_25d": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "error": "Could not find 25-delta options"
        }
    
    # Average IV for 25-delta options
    put_iv_25d = sum(p["iv"] for p in put_25d_candidates) / len(put_25d_candidates)
    call_iv_25d = sum(c["iv"] for c in call_25d_candidates) / len(call_25d_candidates)
    
    # Calculate skew
    skew_25d = put_iv_25d - call_iv_25d
    
    # Find ATM options (moneyness ~ 1.0)
    atm_puts = [p for p in puts if 0.98 <= p["moneyness"] <= 1.02]
    atm_calls = [c for c in calls if 0.98 <= c["moneyness"] <= 1.02]
    atm_options = atm_puts + atm_calls
    atm_iv = sum(o["iv"] for o in atm_options) / len(atm_options) if atm_options else (put_iv_25d + call_iv_25d) / 2
    
    # Determine sentiment and signal
    # Skew > 5% = strong put demand (bearish)
    # Skew < -5% = strong call demand (bullish)
    if skew_25d > 5:
        sentiment = "bearish"
        signal = "FIRING"  # Extreme put demand = potential bottom signal
    elif skew_25d < -5:
        sentiment = "bullish"
        signal = "FIRING"  # Extreme call demand = potential top signal
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
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Deribit 25d Skew: {skew_25d:+.2f}% (put IV: {put_iv_25d:.1f}%, call IV: {call_iv_25d:.1f}%) -> {sentiment}")
    return result


async def get_options_summary() -> Dict[str, Any]:
    """Get overall BTC options market summary"""
    cache_key = "options_summary"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get index price
    index_data = await _make_request("/public/get_index_price", {
        "index_name": "btc_usd"
    })
    
    index_price = index_data.get("index_price", 0) if index_data else 0
    
    # Get book summary
    book_data = await _make_request("/public/get_book_summary_by_currency", {
        "currency": "BTC",
        "kind": "option"
    })
    
    if not book_data:
        return {
            "error": "Failed to fetch options summary"
        }
    
    # Calculate totals
    total_volume = sum(i.get("volume", 0) for i in book_data)
    total_oi = sum(i.get("open_interest", 0) for i in book_data)
    
    # Count puts vs calls
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
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    return result
