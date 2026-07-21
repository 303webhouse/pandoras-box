"""
Derivatives Data Client (Coinalyze + OKX fallback)
Fetches perp funding, OI, liquidation, and term-structure signals.

S-3 Phase 1.5 (FA-7): all four functions (get_funding_rate, get_open_interest,
get_liquidations, get_term_structure) are now per-symbol parametrized with
symbol="BTC" default — every existing caller is signature-compatible and
behavior-identical. Cache keys are per-symbol (e.g. "funding_rate:BTC") to
prevent cross-symbol cache poisoning. Symbol→Coinalyze aggregate and OKX swap
instrument IDs sourced from crypto_symbol_matrix.py.
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

import httpx

from config.crypto_sanity_bounds import check_funding_rate, check_open_interest
from bias_filters.crypto_vendor_health import record_observation

logger = logging.getLogger(__name__)

# API Configuration
COINALYZE_BASE_URL = "https://api.coinalyze.net/v1"
OKX_PUBLIC_URL = "https://www.okx.com/api/v5"

# Per-symbol Coinalyze aggregate symbols sourced from crypto_symbol_matrix.py
# (live-verified 2026-07-13; see symbol-capability-matrix.md for raw HTTP evidence).
# UNAVAILABLE symbols must return NA rather than a mislabeled BTC value.
_COINALYZE_PERP_SYMBOL: Dict[str, Optional[str]] = {
    "BTC":      "BTCUSD_PERP.A",
    "ETH":      "ETHUSD_PERP.A",
    "SOL":      "SOLUSD_PERP.A",
    "HYPE":     "HYPEUSDT_PERP.A",
    "ZEC":      "ZECUSDT_PERP.A",
    "FARTCOIN": "FARTCOINUSDT_PERP.A",
}

# Per-symbol OKX swap instrument IDs used as Coinalyze fallback.
_OKX_SWAP_INSTID: Dict[str, Optional[str]] = {
    "BTC":      "BTC-USDT-SWAP",
    "ETH":      "ETH-USDT-SWAP",
    "SOL":      "SOL-USDT-SWAP",
    "HYPE":     "HYPE-USDT-SWAP",
    "ZEC":      "ZEC-USDT-SWAP",
    "FARTCOIN": "FARTCOIN-USDT-SWAP",
}

# OKX BTC-USDT-SWAP contract size is 0.01 BTC per contract.
OKX_BTC_SWAP_CTVAL_BTC = 0.01
# For OKX liquidation notional on non-BTC symbols we use the USD face value
# via the oiUsd field where available. Contract sizes vary; stablecoin-margined
# contracts are typically 1 USD per lot for most alts on OKX.
OKX_ALT_SWAP_CTVAL_USD = 1.0

# Cache for API responses (avoid hitting rate limits). Keys are per-symbol.
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


def _na_cell(symbol: str, reason: str) -> Dict[str, Any]:
    """Return a §4.2-contract NA cell. Never zeros, never nulls without reason."""
    return {
        "state": "NA",
        "reason": reason,
        "symbol": symbol,
        "signal": "UNKNOWN",
        "as_of": None,
    }


async def _finalize_result(
    result: Dict[str, Any],
    cache_key: str,
    checker,
    value_key: str,
    feed_type: str,
    symbol: str,
) -> Dict[str, Any]:
    """Sanity-bound result[value_key], record vendor health, and only cache
    the result if it passes. An out-of-bounds value is never cached and is
    replaced with the module's existing 'unknown' error shape rather than
    handed to callers — S-1 Phase 1.4/1.5 (AEGIS)."""
    value = result.get(value_key)
    ok, reason = checker(symbol, value)
    status = await record_observation("coinalyze", feed_type, symbol, success=True, value_valid=ok, reason=reason)
    if not ok:
        logger.warning("Coinalyze %s[%s] bounds check failed, not caching: %s", feed_type, symbol, reason)
        return {**result, "signal": "UNKNOWN", "error": reason, "health_status": status}
    # DEF-FUNDING-CACHE-HEALTH (2026-07-21): attach health_status BEFORE the
    # cache write, not after. The prior order cached `result` without the
    # field, so every cache hit inside the CACHE_TTL_SECONDS window returned a
    # dict missing health_status. The funding consumer reads it with a bare
    # .get("health_status") (crypto_market.py:716), so a cache hit yielded
    # None -> None != "LIVE" -> degraded=true on perfectly healthy data
    # (fake-degraded; production repro at 04a1983: false,true,true with an
    # identical rate). Build ONE merged dict and use it for both the cache and
    # the return so the cache-hit and cache-miss paths can never diverge again.
    # This preserves honest degradation: when the feed is genuinely stale,
    # `status` is DEGRADED/DEAD and the cached copy now carries that truthfully
    # rather than a consumer-side default masking it. Shared by funding, OI and
    # term_structure -- all three route through here -- but only funding was
    # exposed, because OI/basis consumers pass a "LIVE" default (:740/:752).
    result_with_health = {**result, "health_status": status}
    _set_cache(cache_key, result_with_health)
    return result_with_health


async def _record_failure(feed_type: str, reason: str, symbol: str) -> None:
    await record_observation("coinalyze", feed_type, symbol, success=False, reason=reason)


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


async def get_funding_rate(symbol: str = "BTC") -> Dict[str, Any]:
    """
    Get current perpetual funding rate (aggregated) for the given symbol.

    symbol defaults to "BTC" — all existing callers (btc_bottom_signals.py,
    btc_market_structure.py) are signature-compatible and behavior-identical.

    Returns:
        {
            "funding_rate": 0.0123,  # Current 8h funding rate (%)
            "predicted_rate": 0.0098,
            "sentiment": "overleveraged_longs" | "overleveraged_shorts" | "neutral",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "2026-01-28T08:00:00Z"
        }
    """
    symbol = (symbol or "BTC").upper()
    perp_sym = _COINALYZE_PERP_SYMBOL.get(symbol)
    if perp_sym is None:
        return _na_cell(symbol, "NA:NOT_IN_COINALYZE_SYMBOL_MAP")

    cache_key = f"funding_rate:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    okx_swap = _OKX_SWAP_INSTID.get(symbol)

    # Get current funding rate
    data = await _make_request("/funding-rate", {"symbols": perp_sym})

    if not data or not isinstance(data, list) or len(data) == 0:
        # Fallback: OKX current funding snapshot.
        if okx_swap:
            okx_data = await _make_okx_request("/public/funding-rate", {"instId": okx_swap})
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
                    "symbol": symbol,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return await _finalize_result(result, cache_key, check_funding_rate, "funding_rate", "funding_rate", symbol)
        await _record_failure("funding_rate", f"Failed to fetch funding rate from Coinalyze and OKX for {symbol}", symbol)
        return {
            "funding_rate": None,
            "predicted_rate": None,
            "sentiment": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": f"Failed to fetch funding rate from Coinalyze and OKX for {symbol}"
        }

    # Parse response - Coinalyze returns array of symbols
    # DEF-FEED-TRIAGE D1 (2026-07-20): Coinalyze's "value" is ALREADY a
    # percentage (confirmed live: raw value=0.001058 for a real ~0.001%/8h
    # BTC rate, cross-checked against OKX's raw fraction 0.0000121... at the
    # same moment). The OKX fallback below (and in get_term_structure) is a
    # true fraction and correctly needs *100 -- Coinalyze does not. Applying
    # the same *100 to both vendors was a ~100x unit-error inflating every
    # Coinalyze-sourced funding read (this function AND get_term_structure's
    # history-derived values share the identical Coinalyze "v"/"value" unit).
    item = data[0]
    funding_rate = item.get("value", 0)
    predicted_rate = item.get("predictedValue") if "predictedValue" in item else None

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
        "predicted_rate": round(predicted_rate, 4) if predicted_rate else None,
        "sentiment": sentiment,
        "signal": signal,
        "source": "coinalyze",
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    logger.info(f"Coinalyze Funding Rate[{symbol}]: {funding_rate:.4f}% -> {signal}")
    return await _finalize_result(result, cache_key, check_funding_rate, "funding_rate", "funding_rate", symbol)


async def get_open_interest(symbol: str = "BTC") -> Dict[str, Any]:
    """
    Get open interest data and detect divergences for the given symbol.

    symbol defaults to "BTC" — all existing callers are signature-compatible.

    Returns:
        {
            "current_oi": 12500000000,  # Current OI in USD
            "oi_change_4h": -2.5,
            "price_change_4h": 1.2,
            "divergence": "accumulation" | "distribution" | "none",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    symbol = (symbol or "BTC").upper()
    perp_sym = _COINALYZE_PERP_SYMBOL.get(symbol)
    if perp_sym is None:
        return _na_cell(symbol, "NA:NOT_IN_COINALYZE_SYMBOL_MAP")

    cache_key = f"open_interest:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    okx_swap = _OKX_SWAP_INSTID.get(symbol)

    # OI snapshot key is per-symbol to prevent cross-symbol cache poisoning
    okx_snapshot_key = f"okx_oi_snapshot:{symbol}"

    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=6)).timestamp() * 1000)
    to_ts = int(now.timestamp() * 1000)

    data = await _make_request("/open-interest-history", {
        "symbols": perp_sym,
        "interval": "1hour",
        "from": from_ts,
        "to": to_ts,
    })

    if not data or not isinstance(data, list) or len(data) == 0:
        if okx_swap:
            oi_data = await _make_okx_request("/public/open-interest", {"instId": okx_swap})
            oi_rows = oi_data.get("data", []) if isinstance(oi_data, dict) else []
            if oi_rows:
                current_oi = _to_float(oi_rows[0].get("oiUsd")) or _to_float(oi_rows[0].get("oi"))
                now_ts = datetime.now(timezone.utc)
                prev_snapshot = _get_cached(okx_snapshot_key)
                _set_cache(okx_snapshot_key, {"oi": current_oi, "ts": now_ts.isoformat()}, ttl=8 * 3600)

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
                    "instId": okx_swap,
                    "bar": "1H",
                    "limit": 6
                })
                candle_rows = candles.get("data", []) if isinstance(candles, dict) else []
                price_change_4h = None
                if len(candle_rows) >= 5:
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
                    "symbol": symbol,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return await _finalize_result(result, cache_key, check_open_interest, "current_oi", "open_interest", symbol)
        await _record_failure("open_interest", f"Failed to fetch OI data from Coinalyze and OKX for {symbol}", symbol)
        return {
            "current_oi": None,
            "oi_change_4h": None,
            "price_change_4h": None,
            "divergence": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": f"Failed to fetch OI data from Coinalyze and OKX for {symbol}"
        }

    item = data[0]
    history = item.get("history", [])

    if len(history) < 4:
        await _record_failure("open_interest", f"Insufficient OI history from Coinalyze for {symbol}", symbol)
        return {
            "current_oi": None,
            "oi_change_4h": None,
            "divergence": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": "Insufficient OI history"
        }

    current_oi = history[-1].get("o", 0)
    oi_4h_ago = history[-5].get("o", current_oi) if len(history) >= 5 else history[0].get("o", current_oi)
    oi_change_4h = ((current_oi - oi_4h_ago) / oi_4h_ago * 100) if oi_4h_ago > 0 else 0

    current_price = history[-1].get("c", 0)
    price_4h_ago = history[-5].get("c", current_price) if len(history) >= 5 else history[0].get("c", current_price)
    price_change_4h = ((current_price - price_4h_ago) / price_4h_ago * 100) if price_4h_ago > 0 else 0

    divergence = "none"
    signal = "NEUTRAL"
    if abs(oi_change_4h) > 2 and abs(price_change_4h) > 0.5:
        if oi_change_4h > 0 and price_change_4h < 0:
            divergence = "accumulation"
            signal = "FIRING"
        elif oi_change_4h < 0 and price_change_4h > 0:
            divergence = "distribution"
            signal = "FIRING"

    result = {
        "current_oi": current_oi,
        "oi_change_4h": round(oi_change_4h, 2),
        "price_change_4h": round(price_change_4h, 2),
        "divergence": divergence,
        "signal": signal,
        "source": "coinalyze",
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    logger.info(f"Coinalyze OI[{symbol}]: {oi_change_4h:+.2f}% vs Price: {price_change_4h:+.2f}% -> {divergence}")
    return await _finalize_result(result, cache_key, check_open_interest, "current_oi", "open_interest", symbol)


async def get_liquidations(symbol: str = "BTC") -> Dict[str, Any]:
    """
    Get liquidation data (last hour) for the given symbol.

    symbol defaults to "BTC" — all existing callers are signature-compatible.

    Returns:
        {
            "long_liquidations": 5000000,
            "short_liquidations": 2000000,
            "total_liquidations": 7000000,
            "long_pct": 71.4,
            "composition": "long_heavy" | "short_heavy" | "balanced",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    symbol = (symbol or "BTC").upper()
    perp_sym = _COINALYZE_PERP_SYMBOL.get(symbol)
    if perp_sym is None:
        return _na_cell(symbol, "NA:NOT_IN_COINALYZE_SYMBOL_MAP")

    cache_key = f"liquidations:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    okx_swap = _OKX_SWAP_INSTID.get(symbol)

    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=2)).timestamp() * 1000)
    to_ts = int(now.timestamp() * 1000)

    data = await _make_request("/liquidation-history", {
        "symbols": perp_sym,
        "interval": "1hour",
        "from": from_ts,
        "to": to_ts,
    })

    if not data or not isinstance(data, list) or len(data) == 0:
        if okx_swap:
            # OKX liquidation feed: use BTC-USDT uly for BTC; alt symbols may not
            # support uly filter — fall back to instId query.
            okx_params: Dict[str, Any] = {"instType": "SWAP", "state": "filled", "limit": 100}
            # For BTC we use uly=BTC-USDT (original working param); for alts, use instId.
            if symbol == "BTC":
                okx_params["uly"] = "BTC-USDT"
            else:
                okx_params["instId"] = okx_swap

            okx_data = await _make_okx_request("/public/liquidation-orders", okx_params)
            rows = okx_data.get("data", []) if isinstance(okx_data, dict) else []
            if rows:
                long_usd = 0.0
                short_usd = 0.0
                parsed_rows = 0

                # OKX returns liquidation entries nested under each row["details"].
                for row in rows:
                    details = row.get("details") or []
                    if not isinstance(details, list):
                        continue
                    for entry in details:
                        size_contracts = _to_float(entry.get("sz")) or 0.0
                        price = _to_float(entry.get("bkPx")) or 0.0
                        if size_contracts <= 0 or price <= 0:
                            continue

                        # BTC: 0.01 BTC per contract; alts: treat sz as USD lots
                        if symbol == "BTC":
                            notional_usd = size_contracts * OKX_BTC_SWAP_CTVAL_BTC * price
                        else:
                            notional_usd = size_contracts * OKX_ALT_SWAP_CTVAL_USD

                        pos_side = str(entry.get("posSide", "")).lower()
                        if pos_side == "long":
                            long_usd += notional_usd
                            parsed_rows += 1
                        elif pos_side == "short":
                            short_usd += notional_usd
                            parsed_rows += 1

                total_usd = long_usd + short_usd
                long_pct = (long_usd / total_usd * 100) if total_usd > 0 else 50.0
                composition = "balanced"
                signal = "NEUTRAL"

                if total_usd > 5_000_000:
                    if long_pct > 75:
                        composition = "long_heavy"
                        signal = "FIRING"
                    elif long_pct < 25:
                        composition = "short_heavy"
                        signal = "FIRING"

                result = {
                    "long_liquidations": round(long_usd, 2),
                    "short_liquidations": round(short_usd, 2),
                    "total_liquidations": round(total_usd, 2),
                    "long_pct": round(long_pct, 1),
                    "composition": composition,
                    "signal": signal,
                    "parsed_rows": parsed_rows,
                    "source": "okx_fallback",
                    "symbol": symbol,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                _set_cache(cache_key, result)
                await record_observation("coinalyze", "liquidations", symbol, success=True)
                return result
        await _record_failure("liquidations", f"Failed to fetch liquidation data from Coinalyze and OKX for {symbol}", symbol)
        return {
            "long_liquidations": None,
            "short_liquidations": None,
            "total_liquidations": None,
            "long_pct": None,
            "composition": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": f"Failed to fetch liquidation data from Coinalyze and OKX for {symbol}"
        }

    item = data[0]
    history = item.get("history", [])

    if not history:
        await record_observation("coinalyze", "liquidations", symbol, success=True)
        return {
            "long_liquidations": 0,
            "short_liquidations": 0,
            "total_liquidations": 0,
            "long_pct": 50,
            "composition": "balanced",
            "signal": "NEUTRAL",
            "symbol": symbol,
        }

    long_liq = sum(h.get("l", 0) for h in history[-2:])
    short_liq = sum(h.get("s", 0) for h in history[-2:])
    total_liq = long_liq + short_liq

    long_pct = (long_liq / total_liq * 100) if total_liq > 0 else 50
    composition = "balanced"
    signal = "NEUTRAL"

    if total_liq > 5_000_000:
        if long_pct > 75:
            composition = "long_heavy"
            signal = "FIRING"
        elif long_pct < 25:
            composition = "short_heavy"
            signal = "FIRING"

    result = {
        "long_liquidations": long_liq,
        "short_liquidations": short_liq,
        "total_liquidations": total_liq,
        "long_pct": round(long_pct, 1),
        "composition": composition,
        "signal": signal,
        "source": "coinalyze",
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    _set_cache(cache_key, result)
    await record_observation("coinalyze", "liquidations", symbol, success=True)
    logger.info(f"Coinalyze Liquidations[{symbol}]: ${total_liq/1e6:.1f}M ({long_pct:.0f}% long) -> {composition}")
    return result


async def get_term_structure(symbol: str = "BTC") -> Dict[str, Any]:
    """
    Derive term structure signal from funding rate trend for the given symbol.

    symbol defaults to "BTC" — all existing callers are signature-compatible.

    Returns:
        {
            "structure": "contango" | "backwardation" | "flat",
            "funding_trend": "rising" | "falling" | "stable",
            "signal": "FIRING" | "NEUTRAL",
            "timestamp": "..."
        }
    """
    symbol = (symbol or "BTC").upper()
    perp_sym = _COINALYZE_PERP_SYMBOL.get(symbol)
    if perp_sym is None:
        return _na_cell(symbol, "NA:NOT_IN_COINALYZE_SYMBOL_MAP")

    cache_key = f"term_structure:{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    okx_swap = _OKX_SWAP_INSTID.get(symbol)

    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=24)).timestamp() * 1000)
    to_ts = int(now.timestamp() * 1000)

    data = await _make_request("/funding-rate-history", {
        "symbols": perp_sym,
        "interval": "6hour",
        "from": from_ts,
        "to": to_ts,
    })

    if not data or not isinstance(data, list) or len(data) == 0:
        if okx_swap:
            okx_data = await _make_okx_request("/public/funding-rate-history", {
                "instId": okx_swap,
                "limit": 12
            })
            rows = okx_data.get("data", []) if isinstance(okx_data, dict) else []
            if len(rows) >= 2:
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
                    "symbol": symbol,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                return await _finalize_result(result, cache_key, check_funding_rate, "current_funding", "term_structure", symbol)

        await _record_failure("term_structure", f"Failed to fetch funding history from Coinalyze and OKX for {symbol}", symbol)
        return {
            "structure": "unknown",
            "funding_trend": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": f"Failed to fetch funding history from Coinalyze and OKX for {symbol}"
        }

    item = data[0]
    history = item.get("history", [])

    if len(history) < 2:
        await _record_failure("term_structure", f"Insufficient funding history from Coinalyze for {symbol}", symbol)
        return {
            "structure": "unknown",
            "funding_trend": "unknown",
            "signal": "UNKNOWN",
            "symbol": symbol,
            "error": "Insufficient funding history"
        }

    # DEF-FEED-TRIAGE D1: Coinalyze's "v" is the same already-a-percentage
    # unit as get_funding_rate()'s "value" -- no *100 here either.
    current_funding = history[-1].get("v", 0)
    avg_funding = sum(h.get("v", 0) for h in history) / len(history)

    if avg_funding > 0.02:
        structure = "contango"
    elif avg_funding < -0.01:
        structure = "backwardation"
    else:
        structure = "flat"

    if len(history) >= 3:
        recent_avg = sum(h.get("v", 0) for h in history[-2:]) / 2
        older_avg = sum(h.get("v", 0) for h in history[:-2]) / max(len(history) - 2, 1)

        if recent_avg > older_avg + 0.01:
            funding_trend = "rising"
        elif recent_avg < older_avg - 0.01:
            funding_trend = "falling"
        else:
            funding_trend = "stable"
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
        "source": "coinalyze",
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    logger.info(f"Coinalyze Term Structure[{symbol}]: {structure}, trend: {funding_trend} -> {signal}")
    return await _finalize_result(result, cache_key, check_funding_rate, "current_funding", "term_structure", symbol)


async def get_all_coinalyze_data(symbol: str = "BTC") -> Dict[str, Any]:
    """Fetch all Coinalyze data in parallel for the given symbol."""
    results = await asyncio.gather(
        get_funding_rate(symbol),
        get_open_interest(symbol),
        get_liquidations(symbol),
        get_term_structure(symbol),
        return_exceptions=True
    )

    return {
        "funding": results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])},
        "open_interest": results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])},
        "liquidations": results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])},
        "term_structure": results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])},
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
