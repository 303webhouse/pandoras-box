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

BINANCE_SPOT_BASE = "https://api.binance.com"
BINANCE_FUTURES_BASE = "https://fapi.binance.com"
BYBIT_BASE = "https://api.bybit.com"
COINBASE_BASE = "https://api.coinbase.com"

_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}
CACHE_TTL_SECONDS = 5


async def _fetch_json(client: httpx.AsyncClient, url: str, params: Optional[dict] = None) -> Dict[str, Any]:
    try:
        resp = await client.get(url, params=params)
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

    async with httpx.AsyncClient(timeout=8.0) as client:
        tasks = {
            "binance_perp_price": _fetch_json(client, f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/price", {"symbol": symbol}),
            "binance_funding": _fetch_json(client, f"{BINANCE_FUTURES_BASE}/fapi/v1/fundingRate", {"symbol": symbol, "limit": 1}),
            "bybit_funding": _fetch_json(client, f"{BYBIT_BASE}/v5/market/funding/history", {"category": "linear", "symbol": symbol, "limit": 1}),
            "coinbase_spot": _fetch_json(client, f"{COINBASE_BASE}/v2/prices/BTC-USD/spot"),
            "agg_trades": _fetch_json(client, f"{BINANCE_FUTURES_BASE}/fapi/v1/aggTrades", {"symbol": symbol, "limit": limit}),
        }

        results = await asyncio.gather(*tasks.values())
        data_map = dict(zip(tasks.keys(), results))

    errors: List[str] = []

    # Binance perp price
    perp_price = None
    if data_map["binance_perp_price"]["ok"]:
        perp_price = _safe_float(data_map["binance_perp_price"]["data"].get("price"))
    else:
        errors.append(f"binance_perp_price: {data_map['binance_perp_price'].get('error')}")

    # Funding rates
    funding_binance = None
    funding_binance_time = None
    if data_map["binance_funding"]["ok"] and data_map["binance_funding"]["data"]:
        item = data_map["binance_funding"]["data"][0]
        funding_binance = _safe_float(item.get("fundingRate"))
        try:
            funding_binance_time = datetime.fromtimestamp(int(item.get("fundingTime", 0)) / 1000, timezone.utc).isoformat()
        except Exception:
            funding_binance_time = None
    else:
        errors.append(f"binance_funding: {data_map['binance_funding'].get('error')}")

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

    # Coinbase spot
    coinbase_spot = None
    if data_map["coinbase_spot"]["ok"]:
        try:
            coinbase_spot = _safe_float(data_map["coinbase_spot"]["data"].get("data", {}).get("amount"))
        except Exception:
            coinbase_spot = None
    else:
        errors.append(f"coinbase_spot: {data_map['coinbase_spot'].get('error')}")

    # Agg trades -> CVD + order flow
    cvd_btc = 0.0
    cvd_usd = 0.0
    taker_buy_qty = 0.0
    taker_sell_qty = 0.0
    trade_tape: List[Dict[str, Any]] = []
    cvd_series: List[float] = []

    if data_map["agg_trades"]["ok"]:
        trades = data_map["agg_trades"]["data"]
        cumulative = 0.0
        for trade in trades:
            price = _safe_float(trade.get("p"))
            qty = _safe_float(trade.get("q"))
            if price is None or qty is None:
                continue
            is_sell = bool(trade.get("m"))  # buyer is maker => sell aggressor
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

        # Build trade tape from last 15 trades
        for trade in trades[-15:]:
            price = _safe_float(trade.get("p"))
            qty = _safe_float(trade.get("q"))
            if price is None or qty is None:
                continue
            is_sell = bool(trade.get("m"))
            ts = trade.get("T")
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
        errors.append(f"agg_trades: {data_map['agg_trades'].get('error')}")

    basis = None
    basis_pct = None
    if coinbase_spot is not None and perp_price is not None:
        basis = coinbase_spot - perp_price
        if perp_price:
            basis_pct = basis / perp_price * 100

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
            "binance_perp": perp_price,
            "basis": basis,
            "basis_pct": basis_pct
        },
        "funding": {
            "binance": {"rate": funding_binance, "timestamp": funding_binance_time},
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
