"""
Derivatives Data Client (Coinalyze + OKX fallback)
Fetches BTC funding, OI, liquidation, and term-structure signals.
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger(__name__)

# API Configuration
COINALYZE_BASE_URL = "https://api.coinalyze.net/v1"
OKX_PUBLIC_URL = "https://www.okx.com/api/v5"

# BTC perpetual symbols across major exchanges (aggregated)
BTC_PERP_SYMBOLS = [
    "BTCUSDT_PERP.A",  # Aggregated across all exchanges
]
OKX_SWAP_SYMBOL = "BTC-USDT-SWAP"

# Cache for API responses (avoid hitting rate limits)
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_api_key() -> str:
    """Read Coinalyze key with common env aliases and sanitize quoting."""
    for env_name in ("COINALYZE_API_KEY", "COINALYZE_KEY", "COINALYZE_TOKEN"):
        value = os.getenv(env_name, "")
        if value:
            return value.strip().strip("'").strip('"')
    return ""


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


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def _make_request(endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict]:
    """Make authenticated request to Coinalyze API"""
    api_key = _get_api_key()
    if not api_key:
        logger.warning("COINALYZE_API_KEY not set - cannot fetch data")
        return None
    
    url = f"{COINALYZE_BASE_URL}{endpoint}"
    headers = {
        "api_key": api_key,
        "X-API-KEY": api_key,
    }
    query = dict(params or {})
    # Keep key in query as compatibility fallback when proxies strip custom headers.
    query.setdefault("api_key", api_key)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=query)
            
            if response.status_code == 429:
                logger.warning("Coinalyze rate limit hit - waiting 60s")
                await asyncio.sleep(60)
                return None
            
            if response.status_code != 200:
                logger.error(f"Coinalyze API error: {response.status_code} - {response.text}")
                return None
            
            return response.json()
    
    except Exception as e:
        logger.error(f"Coinalyze request failed: {e}")
        return None


async def _make_okx_request(endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """Query OKX public endpoints used as fallback for restricted providers."""
    url = f"{OKX_PUBLIC_URL}{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params or {})
            if response.status_code != 200:
                logger.warning(f"OKX API error: {response.status_code} - {response.text}")
                return None
            payload = response.json()
            if isinstance(payload, dict) and payload.get("code") not in (None, "0", 0):
                logger.warning(f"OKX API returned non-zero code: {payload}")
                return None
            return payload
    except Exception as exc:
        logger.warning(f"OKX request failed: {exc}")
        return None


async def get_funding_rate() -> Dict[str, Any]:
    """
    Get current BTC perpetual funding rate (aggregated)
    
    Returns:
        {
            "funding_rate": 0.0123,  # Current 8h funding rate (%)
            "predicted_rate": 0.0098,  # Predicted next funding
            "sentiment": "overleveraged_longs" | "overleveraged_shorts" | "neutral",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "2026-01-28T08:00:00Z"
        }
    """
    cache_key = "funding_rate"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get current funding rate
    data = await _make_request("/funding-rate", {
        "symbols": ",".join(BTC_PERP_SYMBOLS)
    })
    
    if not data or not isinstance(data, list) or len(data) == 0:
        # Fallback: OKX current funding snapshot.
        okx_data = await _make_okx_request("/public/funding-rate", {"instId": OKX_SWAP_SYMBOL})
        rows = okx_data.get("data", []) if isinstance(okx_data, dict) else []
        if rows:
            row = rows[0]
            funding_rate = (_to_float(row.get("fundingRate")) or 0.0) * 100
            predicted_rate = _to_float(row.get("nextFundingRate"))
            predicted_rate = predicted_rate * 100 if predicted_rate is not None else None
            if funding_rate > 0.05:
                sentiment = "overleveraged_longs"
                signal = "FIRING"
            elif funding_rate < -0.03:
                sentiment = "overleveraged_shorts"
                signal = "FIRING"
            else:
                sentiment = "neutral"
                signal = "NEUTRAL"
            result = {
                "funding_rate": round(funding_rate, 4),
                "predicted_rate": round(predicted_rate, 4) if predicted_rate is not None else None,
                "sentiment": sentiment,
                "signal": signal,
                "source": "okx_fallback",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _set_cache(cache_key, result)
            return result
        return {
            "funding_rate": None,
            "predicted_rate": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch funding rate from Coinalyze and OKX"
        }
    
    # Parse response - Coinalyze returns array of symbols
    item = data[0]
    funding_rate = item.get("value", 0) * 100  # Convert to percentage
    predicted_rate = item.get("predictedValue", 0) * 100 if "predictedValue" in item else None
    
    # Determine sentiment and signal
    # High positive funding = longs paying shorts = overleveraged longs
    # High negative funding = shorts paying longs = overleveraged shorts
    if funding_rate > 0.05:
        sentiment = "overleveraged_longs"
        signal = "FIRING"  # Potential short squeeze / reversal setup
    elif funding_rate < -0.03:
        sentiment = "overleveraged_shorts"
        signal = "FIRING"  # Potential long squeeze / reversal setup
    else:
        sentiment = "neutral"
        signal = "NEUTRAL"
    
    result = {
        "funding_rate": round(funding_rate, 4),
        "predicted_rate": round(predicted_rate, 4) if predicted_rate else None,
        "sentiment": sentiment,
        "signal": signal,
        "source": "coinalyze",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Coinalyze Funding Rate: {funding_rate:.4f}% -> {signal}")
    return result


async def get_open_interest() -> Dict[str, Any]:
    """
    Get BTC open interest data and detect divergences
    
    Divergence logic:
    - OI rising + price falling = accumulation (bullish)
    - OI falling + price rising = distribution (bearish)
    
    Returns:
        {
            "current_oi": 12500000000,  # Current OI in USD
            "oi_change_4h": -2.5,  # % change in last 4 hours
            "price_change_4h": 1.2,  # % change in last 4 hours
            "divergence": "accumulation" | "distribution" | "none",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "open_interest"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get OI history (last 6 hours for 4h comparison)
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=6)).timestamp() * 1000)
    
    to_ts = int(now.timestamp() * 1000)
    data = await _make_request("/open-interest-history", {
        "symbols": ",".join(BTC_PERP_SYMBOLS),
        "interval": "1hour",
        "from": from_ts,
        "to": to_ts,
    })
    
    if not data or not isinstance(data, list) or len(data) == 0:
        # Fallback: OKX open-interest snapshot + 1H candles for price context.
        oi_data = await _make_okx_request("/public/open-interest", {"instId": OKX_SWAP_SYMBOL})
        oi_rows = oi_data.get("data", []) if isinstance(oi_data, dict) else []
        if oi_rows:
            current_oi = _to_float(oi_rows[0].get("oi"))
            now_ts = datetime.now(timezone.utc)
            prev_snapshot = _get_cached("okx_oi_snapshot")
            _set_cache("okx_oi_snapshot", {"oi": current_oi, "ts": now_ts.isoformat()}, ttl=8 * 3600)

            oi_change_4h = None
            if prev_snapshot and isinstance(prev_snapshot, dict):
                prev_oi = _to_float(prev_snapshot.get("oi"))
                prev_ts_raw = prev_snapshot.get("ts")
                prev_ts = None
                if isinstance(prev_ts_raw, str):
                    try:
                        prev_ts = datetime.fromisoformat(prev_ts_raw)
                    except Exception:
                        prev_ts = None
                if prev_oi and current_oi and prev_oi > 0 and prev_ts:
                    age_hours = max((now_ts - prev_ts).total_seconds() / 3600.0, 0.25)
                    raw_change = (current_oi - prev_oi) / prev_oi * 100
                    oi_change_4h = raw_change * (4.0 / age_hours)

            candles = await _make_okx_request("/market/candles", {
                "instId": OKX_SWAP_SYMBOL,
                "bar": "1H",
                "limit": 6
            })
            candle_rows = candles.get("data", []) if isinstance(candles, dict) else []
            price_change_4h = None
            if len(candle_rows) >= 5:
                # OKX candles are newest-first: [ts,o,h,l,c,...]
                newest = _to_float(candle_rows[0][4]) if len(candle_rows[0]) > 4 else None
                older = _to_float(candle_rows[4][4]) if len(candle_rows[4]) > 4 else None
                if newest and older and older > 0:
                    price_change_4h = (newest - older) / older * 100

            divergence = "none"
            signal = "NEUTRAL"
            if oi_change_4h is not None and price_change_4h is not None and abs(oi_change_4h) > 2 and abs(price_change_4h) > 0.5:
                if oi_change_4h > 0 and price_change_4h < 0:
                    divergence = "accumulation"
                    signal = "FIRING"
                elif oi_change_4h < 0 and price_change_4h > 0:
                    divergence = "distribution"
                    signal = "FIRING"

            result = {
                "current_oi": current_oi,
                "oi_change_4h": round(oi_change_4h, 2) if oi_change_4h is not None else None,
                "price_change_4h": round(price_change_4h, 2) if price_change_4h is not None else None,
                "divergence": divergence if (oi_change_4h is not None and price_change_4h is not None) else "unknown",
                "signal": signal if (oi_change_4h is not None and price_change_4h is not None) else "NEUTRAL",
                "source": "okx_fallback",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _set_cache(cache_key, result)
            return result
        return {
            "current_oi": None,
            "oi_change_4h": None,
            "price_change_4h": None,
            "divergence": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch OI data from Coinalyze and OKX"
        }
    
    # Parse OI history
    item = data[0]
    history = item.get("history", [])
    
    if len(history) < 4:
        return {
            "current_oi": None,
            "oi_change_4h": None,
            "divergence": "unknown",
            "signal": "UNKNOWN",
            "error": "Insufficient OI history"
        }
    
    # Get current and 4h ago values
    current_oi = history[-1].get("o", 0)  # 'o' is open interest value
    oi_4h_ago = history[-5].get("o", current_oi) if len(history) >= 5 else history[0].get("o", current_oi)
    
    # Calculate changes
    oi_change_4h = ((current_oi - oi_4h_ago) / oi_4h_ago * 100) if oi_4h_ago > 0 else 0
    
    # Get price change (from close prices in history)
    current_price = history[-1].get("c", 0)  # 'c' is close price
    price_4h_ago = history[-5].get("c", current_price) if len(history) >= 5 else history[0].get("c", current_price)
    price_change_4h = ((current_price - price_4h_ago) / price_4h_ago * 100) if price_4h_ago > 0 else 0
    
    # Detect divergence
    divergence = "none"
    signal = "NEUTRAL"
    
    # Significant thresholds
    if abs(oi_change_4h) > 2 and abs(price_change_4h) > 0.5:
        if oi_change_4h > 0 and price_change_4h < 0:
            divergence = "accumulation"  # OI up, price down = smart money buying
            signal = "FIRING"
        elif oi_change_4h < 0 and price_change_4h > 0:
            divergence = "distribution"  # OI down, price up = smart money selling
            signal = "FIRING"
    
    result = {
        "current_oi": current_oi,
        "oi_change_4h": round(oi_change_4h, 2),
        "price_change_4h": round(price_change_4h, 2),
        "divergence": divergence,
        "signal": signal,
        "source": "coinalyze",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Coinalyze OI: {oi_change_4h:+.2f}% vs Price: {price_change_4h:+.2f}% -> {divergence}")
    return result


async def get_liquidations() -> Dict[str, Any]:
    """
    Get BTC liquidation data (last hour)
    
    High one-sided liquidations often mark local tops/bottoms
    
    Returns:
        {
            "long_liquidations": 5000000,  # USD value
            "short_liquidations": 2000000,
            "total_liquidations": 7000000,
            "long_pct": 71.4,
            "composition": "long_heavy" | "short_heavy" | "balanced",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "liquidations"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get liquidation history (last 2 hours)
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=2)).timestamp() * 1000)
    
    to_ts = int(now.timestamp() * 1000)
    data = await _make_request("/liquidation-history", {
        "symbols": ",".join(BTC_PERP_SYMBOLS),
        "interval": "1hour",
        "from": from_ts,
        "to": to_ts,
    })
    
    if not data or not isinstance(data, list) or len(data) == 0:
        # Fallback: OKX liquidation feed (filled liquidation orders).
        okx_data = await _make_okx_request("/public/liquidation-orders", {
            "instType": "SWAP",
            "state": "filled",
            "uly": "BTC-USDT",
            "limit": 100
        })
        rows = okx_data.get("data", []) if isinstance(okx_data, dict) else []
        if rows:
            long_contracts = 0.0
            short_contracts = 0.0
            for row in rows:
                size = _to_float(row.get("sz")) or 0.0
                pos_side = str(row.get("posSide", "")).lower()
                if pos_side == "long":
                    long_contracts += size
                elif pos_side == "short":
                    short_contracts += size

            total_contracts = long_contracts + short_contracts
            long_pct = (long_contracts / total_contracts * 100) if total_contracts > 0 else 50.0
            composition = "balanced"
            signal = "NEUTRAL"
            if total_contracts > 100:
                if long_pct > 75:
                    composition = "long_heavy"
                    signal = "FIRING"
                elif long_pct < 25:
                    composition = "short_heavy"
                    signal = "FIRING"

            result = {
                "long_liquidations": round(long_contracts, 2),
                "short_liquidations": round(short_contracts, 2),
                "total_liquidations": round(total_contracts, 2),
                "long_pct": round(long_pct, 1),
                "composition": composition,
                "signal": signal,
                "source": "okx_fallback",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            _set_cache(cache_key, result)
            return result
        return {
            "long_liquidations": None,
            "short_liquidations": None,
            "total_liquidations": None,
            "long_pct": None,
            "composition": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch liquidation data from Coinalyze and OKX"
        }
    
    # Parse liquidation data
    item = data[0]
    history = item.get("history", [])
    
    if not history:
        return {
            "long_liquidations": 0,
            "short_liquidations": 0,
            "total_liquidations": 0,
            "long_pct": 50,
            "composition": "balanced",
            "signal": "NEUTRAL"
        }
    
    # Sum liquidations from last hour
    long_liq = sum(h.get("l", 0) for h in history[-2:])  # 'l' is long liquidations
    short_liq = sum(h.get("s", 0) for h in history[-2:])  # 's' is short liquidations
    total_liq = long_liq + short_liq
    
    # Calculate composition
    long_pct = (long_liq / total_liq * 100) if total_liq > 0 else 50
    
    # Determine signal
    # Significant liquidation cascade (>$5M) with one-sided composition
    composition = "balanced"
    signal = "NEUTRAL"
    
    if total_liq > 5_000_000:  # $5M threshold
        if long_pct > 75:
            composition = "long_heavy"
            signal = "FIRING"  # Longs got rekt = potential bottom
        elif long_pct < 25:
            composition = "short_heavy"
            signal = "FIRING"  # Shorts got rekt = potential top
    
    result = {
        "long_liquidations": long_liq,
        "short_liquidations": short_liq,
        "total_liquidations": total_liq,
        "long_pct": round(long_pct, 1),
        "composition": composition,
        "signal": signal,
        "source": "coinalyze",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Coinalyze Liquidations: ${total_liq/1e6:.1f}M ({long_pct:.0f}% long) -> {composition}")
    return result


async def get_term_structure() -> Dict[str, Any]:
    """
    Derive term structure signal from funding rate trend
    
    Contango (positive funding) + price weakness = bearish divergence
    Backwardation (negative funding) + price strength = bullish divergence
    
    Returns:
        {
            "structure": "contango" | "backwardation" | "flat",
            "funding_trend": "rising" | "falling" | "stable",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    cache_key = "term_structure"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    
    # Get funding rate history
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=24)).timestamp() * 1000)
    
    to_ts = int(now.timestamp() * 1000)
    data = await _make_request("/funding-rate-history", {
        "symbols": ",".join(BTC_PERP_SYMBOLS),
        "interval": "6hour",
        "from": from_ts,
        "to": to_ts,
    })
    
    if not data or not isinstance(data, list) or len(data) == 0:
        # Fallback: OKX funding-rate history.
        okx_data = await _make_okx_request("/public/funding-rate-history", {
            "instId": OKX_SWAP_SYMBOL,
            "limit": 12
        })
        rows = okx_data.get("data", []) if isinstance(okx_data, dict) else []
        if len(rows) >= 2:
            # OKX returns newest-first.
            rates = [(_to_float(r.get("fundingRate")) or 0.0) * 100 for r in reversed(rows)]
            current_funding = rates[-1]
            avg_funding = sum(rates) / len(rates)
            if avg_funding > 0.02:
                structure = "contango"
            elif avg_funding < -0.01:
                structure = "backwardation"
            else:
                structure = "flat"

            recent_avg = sum(rates[-2:]) / 2
            older_len = max(len(rates) - 2, 1)
            older_avg = sum(rates[:-2]) / older_len if len(rates) > 2 else rates[0]
            if recent_avg > older_avg + 0.01:
                funding_trend = "rising"
            elif recent_avg < older_avg - 0.01:
                funding_trend = "falling"
            else:
                funding_trend = "stable"

            signal = "NEUTRAL"
            if structure == "contango" and funding_trend == "rising":
                signal = "FIRING"
            elif structure == "backwardation" and funding_trend == "falling":
                signal = "FIRING"

            result = {
                "structure": structure,
                "funding_trend": funding_trend,
                "current_funding": round(current_funding, 4),
                "avg_funding_24h": round(avg_funding, 4),
                "signal": signal,
                "source": "okx_fallback",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            _set_cache(cache_key, result)
            return result

        return {
            "structure": "unknown",
            "funding_trend": "unknown",
            "signal": "UNKNOWN",
            "error": "Failed to fetch funding history from Coinalyze and OKX"
        }
    
    # Parse funding history
    item = data[0]
    history = item.get("history", [])
    
    if len(history) < 2:
        return {
            "structure": "unknown",
            "funding_trend": "unknown",
            "signal": "UNKNOWN",
            "error": "Insufficient funding history"
        }
    
    # Get current and average funding
    current_funding = history[-1].get("v", 0) * 100  # Convert to %
    avg_funding = sum(h.get("v", 0) for h in history) / len(history) * 100
    
    # Determine structure
    if avg_funding > 0.02:
        structure = "contango"
    elif avg_funding < -0.01:
        structure = "backwardation"
    else:
        structure = "flat"
    
    # Determine trend
    if len(history) >= 3:
        recent_avg = sum(h.get("v", 0) for h in history[-2:]) / 2 * 100
        older_avg = sum(h.get("v", 0) for h in history[:-2]) / max(len(history) - 2, 1) * 100
        
        if recent_avg > older_avg + 0.01:
            funding_trend = "rising"
        elif recent_avg < older_avg - 0.01:
            funding_trend = "falling"
        else:
            funding_trend = "stable"
    else:
        funding_trend = "stable"
    
    # Signal: divergence between structure and price action
    # This is derived - would need price data too for full logic
    signal = "NEUTRAL"
    if structure == "contango" and funding_trend == "rising":
        signal = "FIRING"  # Extreme bullish positioning = potential reversal
    elif structure == "backwardation" and funding_trend == "falling":
        signal = "FIRING"  # Extreme bearish positioning = potential reversal
    
    result = {
        "structure": structure,
        "funding_trend": funding_trend,
        "current_funding": round(current_funding, 4),
        "avg_funding_24h": round(avg_funding, 4),
        "signal": signal,
        "source": "coinalyze",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    _set_cache(cache_key, result)
    logger.info(f"Coinalyze Term Structure: {structure}, trend: {funding_trend} -> {signal}")
    return result


async def get_all_coinalyze_data() -> Dict[str, Any]:
    """Fetch all Coinalyze data in parallel"""
    results = await asyncio.gather(
        get_funding_rate(),
        get_open_interest(),
        get_liquidations(),
        get_term_structure(),
        return_exceptions=True
    )
    
    return {
        "funding": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
        "open_interest": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
        "liquidations": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
        "term_structure": results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
