"""
Crypto market data proxy for the frontend.
Provides funding rates, CVD, order flow, and spot/perp basis without CORS issues.
"""
from fastapi import APIRouter, Query
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import asyncio
import time
import httpx

router = APIRouter(prefix="/crypto", tags=["crypto-market"])

BINANCE_SPOT_BASE = "https://data-api.binance.vision"  # geo-friendly mirror
OKX_BASE = "https://www.okx.com"
BYBIT_BASE = "https://api.bybit.com"  # kept for potential future use
COINBASE_BASE = "https://api.coinbase.com"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PandoraBot/1.0; +https://pandoras-box)",
    "Accept": "application/json,text/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.8",
}

_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}
CACHE_TTL_SECONDS = 5
_last_good: Dict[str, Any] = {}


async def _fetch_json(client: httpx.AsyncClient, url: str, params: Optional[dict] = None) -> Dict[str, Any]:
    try:
        resp = await client.get(url, params=params, headers=DEFAULT_HEADERS, follow_redirects=True)
        resp.raise_for_status()
        return {"ok": True, "data": resp.json()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


@router.get("/market")
async def get_market_snapshot(symbol: str = Query("BTCUSDT"), limit: int = Query(200, ge=50, le=1000)):
    now = time.time()
    if _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL_SECONDS:
        return _cache["data"]

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        tasks = {
            # Spot prices
            "binance_spot_price": _fetch_json(client, f"{BINANCE_SPOT_BASE}/api/v3/ticker/price", {"symbol": symbol}),
            "coinbase_spot": _fetch_json(client, f"{COINBASE_BASE}/v2/prices/BTC-USD/spot"),
            "okx_spot_price": _fetch_json(client, f"{OKX_BASE}/api/v5/market/ticker", {"instId": "BTC-USDT"}),

            # Perp prices & funding via OKX (not geo-blocked)
            "okx_perp_price": _fetch_json(client, f"{OKX_BASE}/api/v5/market/ticker", {"instId": "BTC-USDT-SWAP"}),
            "okx_funding": _fetch_json(client, f"{OKX_BASE}/api/v5/public/funding-rate", {"instId": "BTC-USDT-SWAP"}),

            # Bybit funding retained; tolerate failures
            "bybit_funding": _fetch_json(client, f"{BYBIT_BASE}/v5/market/funding/history", {"category": "linear", "symbol": symbol, "limit": 1}),

            # Order flow / trades from OKX swap
            "okx_trades": _fetch_json(client, f"{OKX_BASE}/api/v5/market/trades", {"instId": "BTC-USDT-SWAP", "limit": limit}),
        }

        results = await asyncio.gather(*tasks.values())
        data_map = dict(zip(tasks.keys(), results))

    errors: List[str] = []

    # OKX perp price
    perp_price = None
    if data_map["okx_perp_price"]["ok"]:
        try:
            row = data_map["okx_perp_price"]["data"].get("data", [])[0]
            perp_price = _safe_float(row.get("last"))
        except Exception:
            perp_price = None
    else:
        errors.append(f"okx_perp_price: {data_map['okx_perp_price'].get('error')}")
    if perp_price is None and _last_good.get("perp_price") is not None:
        perp_price = _last_good["perp_price"]
        errors.append("okx_perp_price: using cached fallback")
    elif perp_price is not None:
        _last_good["perp_price"] = perp_price

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

    # Funding rates
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
        errors.append(f"bybit_funding: {data_map['bybit_funding'].get('error')}")
    if funding_bybit is None and _last_good.get("funding_bybit") is not None:
        funding_bybit = _last_good["funding_bybit"]
        funding_bybit_time = _last_good.get("funding_bybit_time")
    elif funding_bybit is not None:
        _last_good["funding_bybit"] = funding_bybit
        _last_good["funding_bybit_time"] = funding_bybit_time

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
    trade_tape: List[Dict[str, Any]] = []
    cvd_series: List[float] = []

    if data_map["okx_trades"]["ok"]:
        trades_data = data_map["okx_trades"].get("data")
        trades = trades_data.get("data", []) if isinstance(trades_data, dict) else []
        cumulative = 0.0
        for trade in trades:
            price = _safe_float(trade.get("px"))
            qty = _safe_float(trade.get("sz"))
            if price is None or qty is None:
                continue
            is_sell = str(trade.get("side", "")).lower() == "sell"
            sign = -1 if is_sell else 1
            notional = price * qty
            cvd_btc += sign * qty
            cvd_usd += sign * notional
            cumulative += sign * notional
            cvd_series.append(round(cumulative, 2))
            if is_sell:
                taker_sell_qty += qty
            else:
                taker_buy_qty += qty

        for trade in trades[-15:]:
            price = _safe_float(trade.get("px"))
            qty = _safe_float(trade.get("sz"))
            if price is None or qty is None:
                continue
            is_sell = str(trade.get("side", "")).lower() == "sell"
            ts = trade.get("ts")
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
    else:
        errors.append(f"okx_trades: {data_map['okx_trades'].get('error')}")
    if not cvd_series and _last_good.get("cvd"):
        cached_cvd = _last_good["cvd"]
        cvd_btc = cached_cvd.get("net_btc", 0.0)
        cvd_usd = cached_cvd.get("net_usd", 0.0)
        cvd_direction = cached_cvd.get("direction", "NEUTRAL")
        taker_buy_qty = cached_cvd.get("taker_buy_qty", 0.0)
        taker_sell_qty = cached_cvd.get("taker_sell_qty", 0.0)
        cvd_series = cached_cvd.get("cvd_series", [])
        trade_tape = _last_good.get("order_flow", [])
        errors.append("okx_trades: using cached fallback")
    elif cvd_series:
        _last_good["cvd"] = {
            "net_btc": round(cvd_btc, 4),
            "net_usd": round(cvd_usd, 2),
            "direction": "BULLISH" if cvd_usd > 0 else "BEARISH" if cvd_usd < 0 else "NEUTRAL",
            "taker_buy_qty": round(taker_buy_qty, 4),
            "taker_sell_qty": round(taker_sell_qty, 4),
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

    cvd_direction = "NEUTRAL"
    if cvd_usd > 0:
        cvd_direction = "BULLISH"
    elif cvd_usd < 0:
        cvd_direction = "BEARISH"

    snapshot = {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prices": {
            "coinbase_spot": coinbase_spot,
            "binance_spot": binance_spot,
            "binance_spot_ts": binance_spot_ts,
            "perps": {
                "okx": perp_price,
                "bybit": None,  # unavailable due to geo restrictions
                "spread": perp_spread,
                "note": "OKX swap used as perp proxy; spread = OKX perp - Binance spot"
            },
            "basis": basis,
            "basis_pct": basis_pct,
            "spot_spread": spot_spread
        },
        "funding": {
            "okx": {"rate": funding_okx, "timestamp": funding_okx_time},
            "bybit": {"rate": funding_bybit, "timestamp": funding_bybit_time}
        },
        "cvd": {
            "net_btc": round(cvd_btc, 4),
            "net_usd": round(cvd_usd, 2),
            "direction": cvd_direction,
            "taker_buy_qty": round(taker_buy_qty, 4),
            "taker_sell_qty": round(taker_sell_qty, 4),
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
