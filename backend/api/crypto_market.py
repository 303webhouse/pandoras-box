"""
Crypto market data proxy for the frontend.
Provides funding rates, CVD, order flow, and spot/perp basis without CORS issues.
"""
from fastapi import APIRouter, Query
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import asyncio
import os
import time
import httpx

router = APIRouter(prefix="/crypto", tags=["crypto-market"])

BINANCE_SPOT_BASE = "https://data-api.binance.vision"  # geo-friendly mirror
_binance_perp_base = os.getenv("CRYPTO_BINANCE_PERP_BASE", "https://fapi.binance.com").rstrip("/")
BINANCE_PERP_API_ROOT = (
    _binance_perp_base if _binance_perp_base.endswith("/fapi/v1")
    else f"{_binance_perp_base}/fapi/v1"
)
OKX_BASE = "https://www.okx.com"
BYBIT_BASE = "https://api.bybit.com"  # kept for potential future use
COINBASE_BASE = "https://api.coinbase.com"
BYBIT_ENABLED = os.getenv("CRYPTO_MARKET_ENABLE_BYBIT", "true").strip().lower() in {"1", "true", "yes", "on"}

# CVD smoothing/hysteresis to reduce top-bar whipsaw.
CVD_EMA_ALPHA = float(os.getenv("CRYPTO_CVD_EMA_ALPHA", "0.35"))
CVD_HI_THRESHOLD = float(os.getenv("CRYPTO_CVD_HI_THRESHOLD", "0.08"))
CVD_LO_THRESHOLD = float(os.getenv("CRYPTO_CVD_LO_THRESHOLD", "0.03"))
CVD_MIN_NOTIONAL_USD = float(os.getenv("CRYPTO_CVD_MIN_NOTIONAL_USD", "250000"))

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PandoraBot/1.0; +https://pandoras-box)",
    "Accept": "application/json,text/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.8",
}

_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}
CACHE_TTL_SECONDS = 5
_last_good: Dict[str, Any] = {}
_bybit_runtime_disabled = False
_cvd_trend_state: Dict[str, Any] = {
    "ema_ratio": None,
    "direction": "NEUTRAL",
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
    direction = prev_direction

    # If flow is very small, keep the prior state unless we have a clear move.
    if gross_usd < CVD_MIN_NOTIONAL_USD and abs(ema_ratio) < CVD_HI_THRESHOLD:
        if prev_direction not in {"BULLISH", "BEARISH"}:
            direction = "NEUTRAL"
    else:
        if prev_direction == "BULLISH":
            if ema_ratio <= -CVD_HI_THRESHOLD:
                direction = "BEARISH"
            elif ema_ratio < CVD_LO_THRESHOLD:
                direction = "NEUTRAL"
            else:
                direction = "BULLISH"
        elif prev_direction == "BEARISH":
            if ema_ratio >= CVD_HI_THRESHOLD:
                direction = "BULLISH"
            elif ema_ratio > -CVD_LO_THRESHOLD:
                direction = "NEUTRAL"
            else:
                direction = "BEARISH"
        else:
            if ema_ratio >= CVD_HI_THRESHOLD:
                direction = "BULLISH"
            elif ema_ratio <= -CVD_HI_THRESHOLD:
                direction = "BEARISH"
            else:
                direction = "NEUTRAL"

    abs_ratio = abs(ema_ratio)
    if abs_ratio >= 0.12:
        confidence = "HIGH"
    elif abs_ratio >= 0.07:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    _cvd_trend_state["ema_ratio"] = ema_ratio
    _cvd_trend_state["direction"] = direction
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

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        use_bybit = BYBIT_ENABLED and not _bybit_runtime_disabled
        tasks = {
            # Spot prices
            "binance_spot_price": _fetch_json(client, f"{BINANCE_SPOT_BASE}/api/v3/ticker/price", {"symbol": symbol}),
            "coinbase_spot": _fetch_json(client, f"{COINBASE_BASE}/v2/prices/BTC-USD/spot"),
            "okx_spot_price": _fetch_json(client, f"{OKX_BASE}/api/v5/market/ticker", {"instId": "BTC-USDT"}),

            # Binance perp (PRIMARY): price, funding, and tape
            "binance_perp_price": _fetch_json(client, f"{BINANCE_PERP_API_ROOT}/ticker/price", {"symbol": symbol}),
            "binance_funding": _fetch_json(client, f"{BINANCE_PERP_API_ROOT}/premiumIndex", {"symbol": symbol}),
            "binance_trades": _fetch_json(client, f"{BINANCE_PERP_API_ROOT}/trades", {"symbol": symbol, "limit": limit}),

            # Perp prices & funding via OKX (not geo-blocked)
            "okx_perp_price": _fetch_json(client, f"{OKX_BASE}/api/v5/market/ticker", {"instId": "BTC-USDT-SWAP"}),
            "okx_funding": _fetch_json(client, f"{OKX_BASE}/api/v5/public/funding-rate", {"instId": "BTC-USDT-SWAP"}),

            # Order flow / trades from OKX swap
            "okx_trades": _fetch_json(client, f"{OKX_BASE}/api/v5/market/trades", {"instId": "BTC-USDT-SWAP", "limit": limit}),
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

    if data_map["binance_perp_price"]["ok"]:
        try:
            perp_price = _safe_float(data_map["binance_perp_price"]["data"].get("price"))
            if perp_price is not None:
                perp_source = "binance"
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
        except Exception:
            perp_price = None
    elif perp_price is None and not data_map["okx_perp_price"]["ok"]:
        errors.append(f"okx_perp_price: {data_map['okx_perp_price'].get('error')}")

    if perp_price is None and _last_good.get("perp_price") is not None:
        perp_price = _last_good["perp_price"]
        perp_source = _last_good.get("perp_source")
        errors.append("perp_price: using cached fallback")
    elif perp_price is not None:
        _last_good["perp_price"] = perp_price
        _last_good["perp_source"] = perp_source

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
