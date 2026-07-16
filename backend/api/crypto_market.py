"""
Crypto market data proxy for the frontend.
Provides funding rates, CVD, order flow, and spot/perp basis without CORS issues.
"""
from fastapi import APIRouter, Query
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import asyncio
import logging
import os
import time
import httpx

from config.crypto_symbol_matrix import get_symbol_entry, get_tier, is_tracked
from jobs.crypto_bars import normalize_crypto_ticker

router = APIRouter(prefix="/crypto", tags=["crypto-market"])
logger = logging.getLogger(__name__)

BINANCE_SPOT_BASE = "https://data-api.binance.vision"  # geo-friendly mirror
_binance_perp_base = os.getenv("CRYPTO_BINANCE_PERP_BASE", "https://fapi.binance.com").rstrip("/")
BINANCE_PERP_API_ROOT = (
    _binance_perp_base if _binance_perp_base.endswith("/fapi/v1")
    else f"{_binance_perp_base}/fapi/v1"
)
BINANCE_PERP_HTTP_PROXY = os.getenv("CRYPTO_BINANCE_PERP_HTTP_PROXY", "").strip() or None
OKX_BASE = "https://www.okx.com"
BYBIT_BASE = "https://api.bybit.com"  # kept for potential future use
COINBASE_BASE = "https://api.coinbase.com"
BYBIT_ENABLED = os.getenv("CRYPTO_MARKET_ENABLE_BYBIT", "true").strip().lower() in {"1", "true", "yes", "on"}

# CVD smoothing/hysteresis to reduce top-bar whipsaw.
CVD_EMA_ALPHA = float(os.getenv("CRYPTO_CVD_EMA_ALPHA", "0.25"))
CVD_HI_THRESHOLD = float(os.getenv("CRYPTO_CVD_HI_THRESHOLD", "0.10"))
CVD_LO_THRESHOLD = float(os.getenv("CRYPTO_CVD_LO_THRESHOLD", "0.05"))
CVD_MIN_NOTIONAL_USD = float(os.getenv("CRYPTO_CVD_MIN_NOTIONAL_USD", "250000"))
CVD_CONFIRM_TICKS = int(os.getenv("CRYPTO_CVD_CONFIRM_TICKS", "2"))
CVD_FORCE_THRESHOLD = float(os.getenv("CRYPTO_CVD_FORCE_THRESHOLD", "0.15"))

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PandoraBot/1.0; +https://pandoras-box)",
    "Accept": "application/json,text/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.8",
}

_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}
CACHE_TTL_SECONDS = 4
_last_good: Dict[str, Any] = {}
_bybit_runtime_disabled = False
_cvd_trend_state: Dict[str, Any] = {
    "ema_ratio": None,
    "direction": "NEUTRAL",
    "pending_direction": None,
    "pending_count": 0,
    "updated_at": None,
}


async def _fetch_json(client: httpx.AsyncClient, url: str, params: Optional[dict] = None) -> Dict[str, Any]:
    try:
        resp = await client.get(url, params=params, headers=DEFAULT_HEADERS, follow_redirects=True)
        # 403 = Bybit geo-block, 451 = Binance geo-block — both expected on Railway, fail silently
        if resp.status_code in (403, 451):
            return {"ok": False, "error": f"geo_restricted_{resp.status_code}"}
        resp.raise_for_status()
        return {"ok": True, "data": resp.json()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _is_geo_restriction(error: Optional[str]) -> bool:
    return bool(error and str(error).startswith("geo_restricted_"))


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _classify_cvd_direction(net_usd: float, gross_usd: float) -> Dict[str, Any]:
    """Return smoothed CVD direction using EMA + hysteresis deadband."""
    global _cvd_trend_state

    if gross_usd <= 0:
        return {
            "direction": _cvd_trend_state.get("direction", "NEUTRAL"),
            "confidence": "LOW",
            "raw_ratio": 0.0,
            "ema_ratio": _cvd_trend_state.get("ema_ratio"),
        }

    raw_ratio = net_usd / gross_usd
    prev_ema = _cvd_trend_state.get("ema_ratio")
    ema_ratio = raw_ratio if prev_ema is None else ((1 - CVD_EMA_ALPHA) * prev_ema + CVD_EMA_ALPHA * raw_ratio)

    prev_direction = _cvd_trend_state.get("direction", "NEUTRAL")
    direction_candidate = prev_direction

    # If flow is very small, keep the prior state unless we have a clear move.
    if gross_usd < CVD_MIN_NOTIONAL_USD and abs(ema_ratio) < CVD_HI_THRESHOLD:
        if prev_direction not in {"BULLISH", "BEARISH"}:
            direction_candidate = "NEUTRAL"
    else:
        if prev_direction == "BULLISH":
            if ema_ratio <= -CVD_HI_THRESHOLD:
                direction_candidate = "BEARISH"
            elif ema_ratio < CVD_LO_THRESHOLD:
                direction_candidate = "NEUTRAL"
            else:
                direction_candidate = "BULLISH"
        elif prev_direction == "BEARISH":
            if ema_ratio >= CVD_HI_THRESHOLD:
                direction_candidate = "BULLISH"
            elif ema_ratio > -CVD_LO_THRESHOLD:
                direction_candidate = "NEUTRAL"
            else:
                direction_candidate = "BEARISH"
        else:
            if ema_ratio >= CVD_HI_THRESHOLD:
                direction_candidate = "BULLISH"
            elif ema_ratio <= -CVD_HI_THRESHOLD:
                direction_candidate = "BEARISH"
            else:
                direction_candidate = "NEUTRAL"

    # Confirm direction changes to avoid whipsaw (5s poll can be noisy on low timeframes).
    confirm_ticks = max(1, int(CVD_CONFIRM_TICKS))
    force_threshold = abs(float(CVD_FORCE_THRESHOLD))
    pending_direction = _cvd_trend_state.get("pending_direction")
    pending_count = int(_cvd_trend_state.get("pending_count") or 0)

    if direction_candidate != prev_direction:
        if force_threshold and abs(ema_ratio) >= force_threshold:
            direction = direction_candidate
            pending_direction = None
            pending_count = 0
        else:
            if pending_direction == direction_candidate:
                pending_count += 1
            else:
                pending_direction = direction_candidate
                pending_count = 1

            if pending_count >= confirm_ticks:
                direction = direction_candidate
                pending_direction = None
                pending_count = 0
            else:
                direction = prev_direction
    else:
        direction = prev_direction
        pending_direction = None
        pending_count = 0

    abs_ratio = abs(ema_ratio)
    if abs_ratio >= 0.12:
        confidence = "HIGH"
    elif abs_ratio >= 0.07:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    _cvd_trend_state["ema_ratio"] = ema_ratio
    _cvd_trend_state["direction"] = direction
    _cvd_trend_state["pending_direction"] = pending_direction
    _cvd_trend_state["pending_count"] = pending_count
    _cvd_trend_state["updated_at"] = datetime.now(timezone.utc).isoformat()

    return {
        "direction": direction,
        "confidence": confidence,
        "raw_ratio": raw_ratio,
        "ema_ratio": ema_ratio,
    }


@router.get("/market")
async def get_market_snapshot(symbol: str = Query("BTCUSDT"), limit: int = Query(200, ge=50, le=1000)):
    global _bybit_runtime_disabled
    now = time.time()
    if _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL_SECONDS:
        return _cache["data"]

    # Derive exchange-specific symbol formats from input (e.g. BTCUSDT)
    # Strip "USDT" suffix to get base asset, then build per-exchange pairs
    base_asset = symbol.replace("USDT", "")  # BTC, ETH, etc.
    okx_spot_inst = f"{base_asset}-USDT"          # BTC-USDT
    okx_swap_inst = f"{base_asset}-USDT-SWAP"     # BTC-USDT-SWAP
    coinbase_pair = f"{base_asset}-USD"            # BTC-USD

    market_client_kwargs: Dict[str, Any] = {"timeout": 8.0, "follow_redirects": True}
    binance_client_kwargs: Dict[str, Any] = {"timeout": 8.0, "follow_redirects": True}
    if BINANCE_PERP_HTTP_PROXY:
        binance_client_kwargs["proxy"] = BINANCE_PERP_HTTP_PROXY

    async with httpx.AsyncClient(**market_client_kwargs) as client, httpx.AsyncClient(**binance_client_kwargs) as binance_client:
        use_bybit = BYBIT_ENABLED and not _bybit_runtime_disabled
        tasks = {
            # Spot prices
            "binance_spot_price": _fetch_json(client, f"{BINANCE_SPOT_BASE}/api/v3/ticker/price", {"symbol": symbol}),
            "coinbase_spot": _fetch_json(client, f"{COINBASE_BASE}/v2/prices/{coinbase_pair}/spot"),
            "okx_spot_price": _fetch_json(client, f"{OKX_BASE}/api/v5/market/ticker", {"instId": okx_spot_inst}),

            # Binance perp (PRIMARY): price, funding, and tape
            "binance_perp_price": _fetch_json(binance_client, f"{BINANCE_PERP_API_ROOT}/ticker/price", {"symbol": symbol}),
            "binance_funding": _fetch_json(binance_client, f"{BINANCE_PERP_API_ROOT}/premiumIndex", {"symbol": symbol}),
            "binance_trades": _fetch_json(binance_client, f"{BINANCE_PERP_API_ROOT}/trades", {"symbol": symbol, "limit": limit}),

            # Perp prices & funding via OKX (not geo-blocked)
            "okx_perp_price": _fetch_json(client, f"{OKX_BASE}/api/v5/market/ticker", {"instId": okx_swap_inst}),
            "okx_funding": _fetch_json(client, f"{OKX_BASE}/api/v5/public/funding-rate", {"instId": okx_swap_inst}),

            # Order flow / trades from OKX swap
            "okx_trades": _fetch_json(client, f"{OKX_BASE}/api/v5/market/trades", {"instId": okx_swap_inst, "limit": limit}),
        }
        if use_bybit:
            tasks.update({
                # Bybit funding + perp price retained; tolerate failures
                "bybit_funding": _fetch_json(client, f"{BYBIT_BASE}/v5/market/funding/history", {"category": "linear", "symbol": symbol, "limit": 1}),
                "bybit_perp_price": _fetch_json(client, f"{BYBIT_BASE}/v5/market/tickers", {"category": "linear", "symbol": symbol}),
            })

        results = await asyncio.gather(*tasks.values())
        data_map = dict(zip(tasks.keys(), results))
        if not use_bybit:
            data_map["bybit_funding"] = {"ok": False, "error": "disabled"}
            data_map["bybit_perp_price"] = {"ok": False, "error": "disabled"}

    errors: List[str] = []

    # Perp price preference: Binance futures first, then Bybit, then OKX.
    perp_price = None
    perp_source = None
    perp_source_detail = None

    if data_map["binance_perp_price"]["ok"]:
        try:
            perp_price = _safe_float(data_map["binance_perp_price"]["data"].get("price"))
            if perp_price is not None:
                perp_source = "binance"
                if BINANCE_PERP_HTTP_PROXY:
                    perp_source_detail = "binance_via_proxy"
                elif _binance_perp_base != "https://fapi.binance.com":
                    perp_source_detail = "binance_via_custom_base"
                else:
                    perp_source_detail = "binance_direct"
        except Exception:
            perp_price = None
    else:
        binance_perp_error = data_map["binance_perp_price"].get("error")
        if binance_perp_error:
            errors.append(f"binance_perp_price: {binance_perp_error}")

    if perp_price is None and data_map["bybit_perp_price"]["ok"]:
        try:
            rows = data_map["bybit_perp_price"]["data"].get("result", {}).get("list", [])
            if rows:
                perp_price = _safe_float(rows[0].get("lastPrice"))
                if perp_price is not None:
                    perp_source = "bybit"
                    perp_source_detail = "bybit_direct"
        except Exception:
            perp_price = None
    else:
        bybit_price_error = data_map["bybit_perp_price"].get("error")
        if _is_geo_restriction(bybit_price_error):
            _bybit_runtime_disabled = True
        elif BYBIT_ENABLED and bybit_price_error != "disabled":
            errors.append(f"bybit_perp_price: {bybit_price_error}")

    if perp_price is None and data_map["okx_perp_price"]["ok"]:
        try:
            row = data_map["okx_perp_price"]["data"].get("data", [])[0]
            perp_price = _safe_float(row.get("last"))
            if perp_price is not None:
                perp_source = "okx"
                perp_source_detail = "okx_direct"
        except Exception:
            perp_price = None
    elif perp_price is None and not data_map["okx_perp_price"]["ok"]:
        errors.append(f"okx_perp_price: {data_map['okx_perp_price'].get('error')}")

    if perp_price is None and _last_good.get("perp_price") is not None:
        perp_price = _last_good["perp_price"]
        perp_source = _last_good.get("perp_source")
        perp_source_detail = _last_good.get("perp_source_detail")
        errors.append("perp_price: using cached fallback")
    elif perp_price is not None:
        _last_good["perp_price"] = perp_price
        _last_good["perp_source"] = perp_source
        _last_good["perp_source_detail"] = perp_source_detail

    # Binance spot price
    binance_spot = None
    binance_spot_ts = datetime.now(timezone.utc).isoformat()
    if data_map["binance_spot_price"]["ok"]:
        binance_spot = _safe_float(data_map["binance_spot_price"]["data"].get("price"))
    else:
        errors.append(f"binance_spot_price: {data_map['binance_spot_price'].get('error')}")
    if binance_spot is None and data_map["okx_spot_price"]["ok"]:
        try:
            row = data_map["okx_spot_price"]["data"].get("data", [])[0]
            binance_spot = _safe_float(row.get("last"))
            if binance_spot is not None:
                errors.append("binance_spot_price: using OKX spot fallback")
        except Exception:
            pass
    if binance_spot is None and _last_good.get("binance_spot") is not None:
        binance_spot = _last_good["binance_spot"]
        errors.append("binance_spot_price: using cached fallback")
    elif binance_spot is not None:
        _last_good["binance_spot"] = binance_spot

    # Funding rates: Binance futures first, then OKX, then Bybit.
    funding_binance = None
    funding_binance_time = None
    if data_map["binance_funding"]["ok"]:
        fund_data = data_map["binance_funding"].get("data")
        if isinstance(fund_data, dict):
            funding_binance = _safe_float(fund_data.get("lastFundingRate"))
            try:
                funding_binance_time = datetime.fromtimestamp(int(fund_data.get("nextFundingTime", 0)) / 1000, timezone.utc).isoformat()
            except Exception:
                funding_binance_time = None
    else:
        binance_funding_error = data_map["binance_funding"].get("error")
        if binance_funding_error:
            errors.append(f"binance_funding: {binance_funding_error}")
    if funding_binance is None and _last_good.get("funding_binance") is not None:
        funding_binance = _last_good["funding_binance"]
        funding_binance_time = _last_good.get("funding_binance_time")
        errors.append("binance_funding: using cached fallback")
    elif funding_binance is not None:
        _last_good["funding_binance"] = funding_binance
        _last_good["funding_binance_time"] = funding_binance_time

    funding_okx = None
    funding_okx_time = None
    if data_map["okx_funding"]["ok"]:
        fund_data = data_map["okx_funding"].get("data")
        rows = fund_data.get("data", []) if isinstance(fund_data, dict) else []
        if rows:
            row = rows[0]
            funding_okx = _safe_float(row.get("fundingRate"))
            try:
                funding_okx_time = datetime.fromtimestamp(int(row.get("fundingTime", 0)) / 1000, timezone.utc).isoformat()
            except Exception:
                funding_okx_time = None
    else:
        errors.append(f"okx_funding: {data_map['okx_funding'].get('error')}")
    if funding_okx is None and _last_good.get("funding_okx") is not None:
        funding_okx = _last_good["funding_okx"]
        funding_okx_time = _last_good.get("funding_okx_time")
        errors.append("okx_funding: using cached fallback")
    elif funding_okx is not None:
        _last_good["funding_okx"] = funding_okx
        _last_good["funding_okx_time"] = funding_okx_time

    funding_bybit = None
    funding_bybit_time = None
    if data_map["bybit_funding"]["ok"]:
        bybit_data = data_map["bybit_funding"]["data"]
        rows = bybit_data.get("result", {}).get("list", []) if isinstance(bybit_data, dict) else []
        if rows:
            row = rows[0]
            funding_bybit = _safe_float(row.get("fundingRate"))
            try:
                funding_bybit_time = datetime.fromtimestamp(int(row.get("fundingRateTimestamp", 0)) / 1000, timezone.utc).isoformat()
            except Exception:
                funding_bybit_time = None
    else:
        bybit_funding_error = data_map["bybit_funding"].get("error")
        if _is_geo_restriction(bybit_funding_error):
            _bybit_runtime_disabled = True
        elif BYBIT_ENABLED and bybit_funding_error != "disabled":
            errors.append(f"bybit_funding: {bybit_funding_error}")
    if funding_bybit is None and _last_good.get("funding_bybit") is not None:
        funding_bybit = _last_good["funding_bybit"]
        funding_bybit_time = _last_good.get("funding_bybit_time")
    elif funding_bybit is not None:
        _last_good["funding_bybit"] = funding_bybit
        _last_good["funding_bybit_time"] = funding_bybit_time

    funding_primary_rate = funding_binance if funding_binance is not None else (funding_okx if funding_okx is not None else funding_bybit)
    funding_primary_source = "binance" if funding_binance is not None else ("okx" if funding_okx is not None else ("bybit" if funding_bybit is not None else None))

    # Coinbase spot
    coinbase_spot = None
    if data_map["coinbase_spot"]["ok"]:
        try:
            coinbase_spot = _safe_float(data_map["coinbase_spot"]["data"].get("data", {}).get("amount"))
        except Exception:
            coinbase_spot = None
    else:
        errors.append(f"coinbase_spot: {data_map['coinbase_spot'].get('error')}")
    if coinbase_spot is None and _last_good.get("coinbase_spot") is not None:
        coinbase_spot = _last_good["coinbase_spot"]
        errors.append("coinbase_spot: using cached fallback")
    elif coinbase_spot is not None:
        _last_good["coinbase_spot"] = coinbase_spot

    # Trades -> CVD + order flow
    cvd_btc = 0.0
    cvd_usd = 0.0
    taker_buy_qty = 0.0
    taker_sell_qty = 0.0
    taker_buy_usd = 0.0
    taker_sell_usd = 0.0
    trade_tape: List[Dict[str, Any]] = []
    cvd_series: List[float] = []
    cvd_source = None

    trades = []
    if data_map["binance_trades"]["ok"]:
        trade_rows = data_map["binance_trades"].get("data")
        if isinstance(trade_rows, list):
            trades = trade_rows
            cvd_source = "binance"
    else:
        binance_trades_error = data_map["binance_trades"].get("error")
        if binance_trades_error:
            errors.append(f"binance_trades: {binance_trades_error}")

    if not trades and data_map["okx_trades"]["ok"]:
        trades_data = data_map["okx_trades"].get("data")
        okx_rows = trades_data.get("data", []) if isinstance(trades_data, dict) else []
        if isinstance(okx_rows, list):
            trades = okx_rows
            cvd_source = "okx"
    elif not trades:
        errors.append(f"okx_trades: {data_map['okx_trades'].get('error')}")

    if trades:
        cumulative = 0.0
        for trade in trades:
            if cvd_source == "binance":
                price = _safe_float(trade.get("price"))
                qty = _safe_float(trade.get("qty"))
                is_sell = bool(trade.get("isBuyerMaker", False))  # buyer maker => sell taker
                ts = trade.get("time")
            else:
                price = _safe_float(trade.get("px"))
                qty = _safe_float(trade.get("sz"))
                is_sell = str(trade.get("side", "")).lower() == "sell"
                ts = trade.get("ts")

            if price is None or qty is None:
                continue

            sign = -1 if is_sell else 1
            notional = price * qty
            cvd_btc += sign * qty
            cvd_usd += sign * notional
            cumulative += sign * notional
            cvd_series.append(round(cumulative, 2))
            if is_sell:
                taker_sell_qty += qty
                taker_sell_usd += notional
            else:
                taker_buy_qty += qty
                taker_buy_usd += notional

        for trade in trades[-15:]:
            if cvd_source == "binance":
                price = _safe_float(trade.get("price"))
                qty = _safe_float(trade.get("qty"))
                is_sell = bool(trade.get("isBuyerMaker", False))
                ts = trade.get("time")
            else:
                price = _safe_float(trade.get("px"))
                qty = _safe_float(trade.get("sz"))
                is_sell = str(trade.get("side", "")).lower() == "sell"
                ts = trade.get("ts")

            if price is None or qty is None:
                continue
            try:
                time_iso = datetime.fromtimestamp(int(ts) / 1000, timezone.utc).isoformat() if ts else None
            except Exception:
                time_iso = None
            trade_tape.append({
                "price": price,
                "qty": qty,
                "side": "SELL" if is_sell else "BUY",
                "timestamp": time_iso
            })

    gross_notional_usd = taker_buy_usd + taker_sell_usd
    if not cvd_series and _last_good.get("cvd"):
        cached_cvd = _last_good["cvd"]
        cvd_btc = cached_cvd.get("net_btc", 0.0)
        cvd_usd = cached_cvd.get("net_usd", 0.0)
        cvd_direction = cached_cvd.get("direction", "NEUTRAL")
        taker_buy_qty = cached_cvd.get("taker_buy_qty", 0.0)
        taker_sell_qty = cached_cvd.get("taker_sell_qty", 0.0)
        taker_buy_usd = cached_cvd.get("taker_buy_usd", 0.0)
        taker_sell_usd = cached_cvd.get("taker_sell_usd", 0.0)
        gross_notional_usd = cached_cvd.get("gross_usd", 0.0)
        cvd_series = cached_cvd.get("cvd_series", [])
        cvd_source = cached_cvd.get("source")
        trade_tape = _last_good.get("order_flow", [])
        errors.append("trades: using cached fallback")
    elif cvd_series:
        trend_info = _classify_cvd_direction(cvd_usd, gross_notional_usd)
        _last_good["cvd"] = {
            "net_btc": round(cvd_btc, 4),
            "net_usd": round(cvd_usd, 2),
            "direction": trend_info.get("direction", "NEUTRAL"),
            "direction_confidence": trend_info.get("confidence", "LOW"),
            "raw_imbalance_pct": round((trend_info.get("raw_ratio", 0.0) * 100), 2),
            "ema_imbalance_pct": round((trend_info.get("ema_ratio", 0.0) * 100), 2),
            "taker_buy_qty": round(taker_buy_qty, 4),
            "taker_sell_qty": round(taker_sell_qty, 4),
            "taker_buy_usd": round(taker_buy_usd, 2),
            "taker_sell_usd": round(taker_sell_usd, 2),
            "gross_usd": round(gross_notional_usd, 2),
            "source": cvd_source,
            "cvd_series": cvd_series[-120:],
        }
        _last_good["order_flow"] = trade_tape

    basis = None
    basis_pct = None
    if coinbase_spot is not None and perp_price is not None:
        basis = coinbase_spot - perp_price
        if perp_price:
            basis_pct = basis / perp_price * 100

    perp_spread = None
    if perp_price is not None and binance_spot is not None:
        perp_spread = perp_price - binance_spot

    spot_spread = None
    if coinbase_spot is not None and binance_spot is not None:
        spot_spread = coinbase_spot - binance_spot

    cvd_snapshot = _last_good.get("cvd", {})
    cvd_direction = cvd_snapshot.get("direction", "NEUTRAL")
    cvd_confidence = cvd_snapshot.get("direction_confidence", "LOW")
    cvd_raw_imbalance_pct = cvd_snapshot.get("raw_imbalance_pct")
    cvd_ema_imbalance_pct = cvd_snapshot.get("ema_imbalance_pct")

    snapshot = {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prices": {
            "coinbase_spot": coinbase_spot,
            "binance_spot": binance_spot,
            "binance_spot_ts": binance_spot_ts,
            "perps": {
                "binance": perp_price if perp_source == "binance" else None,
                "okx": perp_price if perp_source == "okx" else None,
                "bybit": perp_price if perp_source == "bybit" else None,
                "spread": perp_spread,
                "source": perp_source,
                "source_detail": perp_source_detail,
                "routing": {
                    "binance_perp_api_root": BINANCE_PERP_API_ROOT,
                    "binance_perp_proxy_enabled": bool(BINANCE_PERP_HTTP_PROXY),
                },
                "note": "Binance perps prioritized, then Bybit, then OKX. Spread = perp - Binance spot."
            },
            "basis": basis,
            "basis_pct": basis_pct,
            "spot_spread": spot_spread
        },
        "funding": {
            "binance": {"rate": funding_binance, "timestamp": funding_binance_time},
            "okx": {"rate": funding_okx, "timestamp": funding_okx_time},
            "bybit": {"rate": funding_bybit, "timestamp": funding_bybit_time},
            "primary": {"rate": funding_primary_rate, "source": funding_primary_source}
        },
        "cvd": {
            "net_btc": round(cvd_btc, 4),
            "net_usd": round(cvd_usd, 2),
            "direction": cvd_direction,
            "direction_confidence": cvd_confidence,
            "raw_imbalance_pct": cvd_raw_imbalance_pct,
            "ema_imbalance_pct": cvd_ema_imbalance_pct,
            "taker_buy_qty": round(taker_buy_qty, 4),
            "taker_sell_qty": round(taker_sell_qty, 4),
            "taker_buy_usd": round(taker_buy_usd, 2),
            "taker_sell_usd": round(taker_sell_usd, 2),
            "gross_usd": round(gross_notional_usd, 2),
            "source": cvd_source or cvd_snapshot.get("source"),
            "cvd_series": cvd_series[-120:]
        },
        "order_flow": trade_tape,
        "errors": errors
    }

    _cache["data"] = snapshot
    _cache["timestamp"] = now

    return snapshot


@router.get("/binance/klines")
async def get_binance_klines(
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("1d"),
    limit: int = Query(3, ge=1, le=1000),
    startTime: Optional[int] = Query(None),
    endTime: Optional[int] = Query(None),
):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    if startTime is not None:
        params["startTime"] = startTime
    if endTime is not None:
        params["endTime"] = endTime

    async with httpx.AsyncClient(timeout=8.0) as client:
        result = await _fetch_json(client, f"{BINANCE_SPOT_BASE}/api/v3/klines", params)

    if not result["ok"]:
        return {"status": "error", "error": result.get("error")}

    return {"status": "success", "data": result["data"]}


@router.get("/circuit-breakers")
async def get_circuit_breakers():
    """Return status of all crypto-related circuit breakers (currently: STRC par monitor)."""
    from circuit_breakers.strc_monitor import check_strc_status

    strc = await check_strc_status()
    return {
        "status": "success",
        "breakers": [strc],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _parse_ts_field(v):
    if not v:
        return None
    try:
        s = str(v).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _age_seconds_field(as_of):
    if as_of is None:
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - as_of).total_seconds())


def _field_envelope(as_of_raw, degraded, **data):
    """Per-field house labeling contract (as_of, data_age_seconds, degraded) —
    mirrors board_state.py's _envelope(), reimplemented locally per the
    existing repo convention of no shared helper module for this pattern."""
    as_of = _parse_ts_field(as_of_raw)
    return {
        **data,
        "as_of": as_of.isoformat() if as_of else None,
        "data_age_seconds": _age_seconds_field(as_of),
        "degraded": bool(degraded) if degraded is not None else True,
    }


_NOT_YET_WIRED = "not yet wired"  # retired: S-3 Phase 1.5 parametrized all six symbols
_NOT_YET_BUILT_R1 = "not yet built (R-1 scope)"
_NOT_YET_BUILT_R2 = "not yet built (R-2 scope)"


@router.get("/state/{symbol}")
async def get_crypto_state(symbol: str):
    """Consolidated per-symbol crypto state envelope — S-1 Phase 3 (F-3.3).

    Ships now (with honest nulls where later phases haven't built yet) so
    R-1 (session/regime) and R-2 (tape-health) integrate against a stable
    payload shape exactly once, rather than each phase inventing its own.
    Every field carries as_of/data_age_seconds/degraded independently —
    funding/OI/basis are real for BTC (the only symbol the underlying
    bias_filters vendor clients currently support) and honest
    null+degraded for every other tracked symbol, never a silently
    mislabeled BTC value.
    """
    base_symbol = normalize_crypto_ticker(symbol)
    if base_symbol is None or not is_tracked(base_symbol):
        return {
            "symbol": (symbol or "").upper(),
            "error": (
                f"'{symbol}' is not in the tracked crypto universe "
                "(BTC, ETH, SOL, HYPE, ZEC, FARTCOIN)"
            ),
        }

    entry = get_symbol_entry(base_symbol) or {}
    tier = get_tier(base_symbol)

    funding_field = _field_envelope(None, True, rate_pct=None, signal=None)
    oi_field = _field_envelope(None, True, current_oi_usd=None, signal=None)
    basis_field = _field_envelope(None, True, basis_annualized_pct=None, signal=None)

    # S-3 Phase 1.5 (FA-7): vendor clients are now per-symbol parametrized;
    # funding/OI/basis data available for all six tracked symbols.
    from bias_filters import coinalyze_client, binance_client

    try:
        funding_data = await coinalyze_client.get_funding_rate(base_symbol)
        is_na = funding_data.get("state") == "NA"
        funding_field = _field_envelope(
            funding_data.get("timestamp"),
            is_na or bool(funding_data.get("error")) or funding_data.get("health_status") != "LIVE",
            rate_pct=funding_data.get("funding_rate"), signal=funding_data.get("signal"),
            na_reason=funding_data.get("reason") if is_na else None,
        )
    except Exception as exc:
        logger.warning("crypto state: funding fetch failed for %s: %s", base_symbol, exc)

    try:
        oi_data = await coinalyze_client.get_open_interest(base_symbol)
        is_na = oi_data.get("state") == "NA"
        oi_field = _field_envelope(
            oi_data.get("timestamp"),
            is_na or bool(oi_data.get("error")) or oi_data.get("health_status", "LIVE") != "LIVE",
            current_oi_usd=oi_data.get("current_oi"), signal=oi_data.get("signal"),
            na_reason=oi_data.get("reason") if is_na else None,
        )
    except Exception as exc:
        logger.warning("crypto state: OI fetch failed for %s: %s", base_symbol, exc)

    try:
        basis_data = await binance_client.get_quarterly_basis(base_symbol)
        is_na = basis_data.get("state") == "NA"
        basis_field = _field_envelope(
            basis_data.get("timestamp"),
            is_na or bool(basis_data.get("error")) or basis_data.get("health_status", "LIVE") != "LIVE",
            basis_annualized_pct=basis_data.get("basis_annualized"), signal=basis_data.get("signal"),
            na_reason=basis_data.get("reason") if is_na else None,
        )
    except Exception as exc:
        logger.warning("crypto state: basis fetch failed for %s: %s", base_symbol, exc)

    # S-3 Phase 4 (§6.2, FA-5): wire session, regime, and tape-health fields
    # from real S-2 + S-3 data. Previously _NOT_YET_BUILT_R1 / _NOT_YET_BUILT_R2.
    now_utc = datetime.now(timezone.utc)

    # Session (S-2 R-1): from get_session_state
    session_field: Dict[str, Any] = _field_envelope(None, True, state=None)
    try:
        from config.crypto_gate_loader import get_gate_config
        from utils.crypto_sessions import get_session_state as _get_session
        _cv, _scfg = await get_gate_config()
        _sess = _get_session(now_utc, _scfg)
        session_field = _field_envelope(
            now_utc.isoformat(), False,
            state=_sess.get("current_session"),
            session_label=_sess.get("label"),
            partition=_sess.get("partition"),
        )
    except Exception as exc:
        logger.warning("crypto state: session fetch failed: %s", exc)
        session_field = _field_envelope(None, True, state=None, error=str(exc))

    # Regime (S-2 R-1): latest row from crypto_regime_log for this symbol
    regime_field: Dict[str, Any] = _field_envelope(None, True, state=None)
    try:
        from database.postgres_client import get_postgres_client
        _pool = await get_postgres_client()
        async with _pool.acquire() as _conn:
            _row = await _conn.fetchrow(
                """
                SELECT regime_state, computed_at, degraded, degrade_reason
                FROM crypto_regime_log
                WHERE symbol = $1
                ORDER BY computed_at DESC
                LIMIT 1
                """,
                base_symbol,
            )
        if _row:
            _ca = _row["computed_at"]
            _ca = _ca if _ca.tzinfo else _ca.replace(tzinfo=timezone.utc)
            _age = int((now_utc - _ca).total_seconds())
            _stale = _age > 7200
            regime_field = _field_envelope(
                _ca.isoformat(), _row["degraded"] or _stale,
                state=_row["regime_state"],
                data_age_seconds=_age,
                degrade_reason=_row["degrade_reason"],
            )
        else:
            regime_field = _field_envelope(None, True, state=None, note="no regime rows yet")
    except Exception as exc:
        logger.warning("crypto state: regime fetch failed for %s: %s", base_symbol, exc)
        regime_field = _field_envelope(None, True, state=None, error=str(exc))

    # Tape-health (S-3 R-2): latest row from crypto_tape_health_log
    # §5.1 hard-stop: spot feed unavailable — currently returns NA for all symbols.
    tape_health_field: Dict[str, Any] = _field_envelope(None, True, state=None)
    try:
        from database.postgres_client import get_postgres_client
        _pool2 = await get_postgres_client()
        async with _pool2.acquire() as _conn2:
            _th_row = await _conn2.fetchrow(
                """
                SELECT state, slope, spot_cvd, perp_cvd, degraded, degrade_reason, computed_at
                FROM crypto_tape_health_log
                WHERE symbol = $1
                ORDER BY computed_at DESC
                LIMIT 1
                """,
                base_symbol,
            )
        if _th_row:
            _th_ca = _th_row["computed_at"]
            _th_ca = _th_ca if _th_ca.tzinfo else _th_ca.replace(tzinfo=timezone.utc)
            _th_age = int((now_utc - _th_ca).total_seconds())
            tape_health_field = _field_envelope(
                _th_ca.isoformat(), _th_row["degraded"] or _th_age > 600,
                state=_th_row["state"],
                slope=_th_row["slope"],
                spot_cvd=_th_row["spot_cvd"],
                perp_cvd=_th_row["perp_cvd"],
                data_age_seconds=_th_age,
            )
        else:
            tape_health_field = _field_envelope(
                None, True, state="NA", note="no tape-health rows yet (S-3 Phase 3 §5.1 hard-stop: spot feed unavailable)"
            )
    except Exception as exc:
        logger.warning("crypto state: tape-health fetch failed for %s: %s", base_symbol, exc)
        tape_health_field = _field_envelope(None, True, state=None, error=str(exc))

    return {
        "symbol": base_symbol,
        "tier": tier,
        "capabilities": entry,
        "session": session_field,
        "funding": funding_field,
        "open_interest": oi_field,
        "basis": basis_field,
        "tape_health": tape_health_field,
        "regime": regime_field,
        "generated_at": now_utc.isoformat(),
    }


@router.get("/regime")
async def get_crypto_regime():
    """S-2 (R-1): per-symbol crypto regime state, data contract only (no UI
    ships in this brief). Read from the latest crypto_regime_log row per
    symbol. `data_age_seconds` is computed at REQUEST time, not cached from
    write time -- a frozen job must LOOK frozen. No auth dependency, mirrors
    /api/btc/sessions' public-GET posture (S-2 Phase-0 finding 0.4).
    """
    from database.postgres_client import get_postgres_client
    from config.crypto_gate_loader import get_gate_config

    config_version, _config = await get_gate_config()
    pool = await get_postgres_client()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (symbol) symbol, tier, is_master, regime_state,
                   computed_at, degraded, degrade_reason
            FROM crypto_regime_log
            ORDER BY symbol, computed_at DESC
            """
        )

    def _shape(row) -> Dict[str, Any]:
        computed_at = row["computed_at"]
        age = None
        if computed_at is not None:
            ca = computed_at if computed_at.tzinfo else computed_at.replace(tzinfo=timezone.utc)
            age = int((now - ca).total_seconds())
        return {
            "symbol": row["symbol"],
            "tier": row["tier"],
            "regime_state": row["regime_state"],
            "computed_at": computed_at.isoformat() if computed_at else None,
            "data_age_seconds": age,
            "degraded": row["degraded"],
            "degrade_reason": row["degrade_reason"],
        }

    master = None
    symbols = []
    for row in rows:
        shaped = _shape(row)
        if row["is_master"]:
            master = shaped
        symbols.append(shaped)

    return {
        "as_of": now.isoformat(),
        "config_version": config_version,
        "master": master,
        "symbols": symbols,
    }


@router.get("/clock")
async def get_crypto_clock():
    """S-2 (R-1): session clock, dual-labeled (utc + america_denver) per
    the HELIOS carry-forward -- the UI renders time, it never computes it.
    No auth dependency, mirrors /api/btc/sessions' public-GET posture.
    """
    from config.crypto_gate_loader import get_gate_config
    from utils.crypto_sessions import get_session_state

    _config_version, config = await get_gate_config()
    now = datetime.now(timezone.utc)
    return get_session_state(now, config)


@router.get("/cycle-extremes")
async def get_cycle_extremes(symbol: Optional[str] = Query(None)):
    """S-3 Phase 4 (§6.1) — Cycle Extremes dial.

    Returns per-symbol composite + full cell set with §4.2 staleness contracts,
    coverage headers, and canonical copy strings. Optional ?symbol= filters to
    a single symbol; omitting returns all six.

    The dial writes ZERO rows to the signals table (D3 rule). Data-layer only.
    """
    from bias_filters.crypto_cycle_engine import evaluate_cycle_extremes, evaluate_all_symbols

    if symbol:
        from jobs.crypto_bars import normalize_crypto_ticker
        canon = normalize_crypto_ticker(symbol)
        if not canon:
            return {
                "error": f"'{symbol}' is not a recognized crypto symbol",
                "valid_symbols": ["BTC", "ETH", "SOL", "HYPE", "ZEC", "FARTCOIN"],
            }
        return await evaluate_cycle_extremes(canon)

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "symbols": await evaluate_all_symbols(),
    }


@router.get("/tape-health")
async def get_tape_health(symbol: Optional[str] = Query(None)):
    """S-3 Phase 4 (§6.1) — CVD tape-health state.

    Returns spot-vs-perp CVD split, state (SPOT_LED / PERP_LED / MIXED / NA),
    and slope per covered symbol. Uncovered symbols return explicit NA state.

    §5.1 HARD-STOP NOTE (2026-07-16): spot CVD feed is unavailable on Railway
    (Binance spot trades geo-blocked; OKX spot trade feed not yet wired).
    All symbols currently return NA:SPOT_FEED_UNAVAILABLE. CVD events (§5.3)
    cannot fire until a spot feed is wired. Flagged for Fable review.
    Optional ?symbol= filters to a single symbol.
    """
    from bias_filters.crypto_tape_health_engine import compute_tape_health, compute_all_tape_health

    if symbol:
        from jobs.crypto_bars import normalize_crypto_ticker
        canon = normalize_crypto_ticker(symbol)
        if not canon:
            return {
                "error": f"'{symbol}' is not a recognized crypto symbol",
                "valid_symbols": ["BTC", "ETH", "SOL", "HYPE", "ZEC", "FARTCOIN"],
            }
        try:
            from config.crypto_cycle_loader import get_cycle_config
            _, config = await get_cycle_config()
        except Exception:
            config = {}
        return await compute_tape_health(canon, config)

    results = await compute_all_tape_health()
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "note": "All symbols NA:SPOT_FEED_UNAVAILABLE — see §5.1 hard-stop in S-3 completion report",
        "symbols": results,
    }
