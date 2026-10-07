"""Perp helpers used by the crypto strategy engine.

fapi.binance.com returns HTTP 451 from Railway. The VPN route is gone
(R-IV.658) and is not rebuilt. These functions keep the old return
shapes so crypto_setups.py does not change, and they read venues that
answer from Railway: Coinalyze, Hyperliquid, and OKX public.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

OKX_BASE = "https://www.okx.com/api/v5"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PivotHub/1.0)",
    "Accept": "application/json",
}

_cache: Dict[str, Any] = {}
_CACHE_TTL = 30

_OKX_BAR = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6H",
    "12h": "12H",
    "1d": "1D",
    "1w": "1W",
    "1M": "1M",
}


def _cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data: Any) -> None:
    _cache[key] = {"data": data, "ts": time.time()}


def reset_for_tests() -> None:
    _cache.clear()


def _base_from_pair(symbol: str) -> str:
    pair = (symbol or "BTCUSDT").upper()
    if pair.endswith("USDT"):
        return pair[:-4]
    if pair.endswith("-USDT-SWAP"):
        return pair.split("-")[0]
    return pair


def _okx_swap(symbol: str) -> str:
    return f"{_base_from_pair(symbol)}-USDT-SWAP"


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def _okx_get(path: str, params: Optional[dict] = None) -> Optional[Any]:
    try:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=8.0,
            follow_redirects=True,
        ) as client:
            resp = await client.get(f"{OKX_BASE}{path}", params=params)
            if resp.status_code != 200:
                logger.warning("OKX %s HTTP %s", path, resp.status_code)
                return None
            body = resp.json()
    except Exception as exc:
        logger.warning("OKX %s failed: %s", path, exc)
        return None
    if not isinstance(body, dict):
        return None
    if str(body.get("code", "0")) != "0":
        logger.warning("OKX %s code %s", path, body.get("code"))
        return None
    return body.get("data")


def _minutes_to_next_funding(next_ms: Optional[int] = None) -> float:
    now_ms = int(time.time() * 1000)
    if isinstance(next_ms, (int, float)) and next_ms > now_ms:
        return max(0.0, (float(next_ms) - now_ms) / 60000.0)
    now = datetime.now(timezone.utc)
    hour = now.hour
    next_hour = 8 if hour < 8 else (16 if hour < 16 else 24)
    nxt = now.replace(minute=0, second=0, microsecond=0)
    if next_hour == 24:
        nxt = nxt.replace(hour=0) + timedelta(days=1)
    else:
        nxt = nxt.replace(hour=next_hour)
    return max(0.0, (nxt.timestamp() - now.timestamp()) / 60.0)


async def get_funding_rate(symbol: str = "BTCUSDT") -> Optional[Dict]:
    """Current funding as a Binance-style fraction, plus minutes to settlement."""
    cache_key = f"funding:{symbol}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    base = _base_from_pair(symbol)
    inst = _okx_swap(symbol)
    rate = None
    mark = None
    index = None
    next_ms = None
    source = None

    try:
        from bias_filters import coinalyze_client as cz
        from integrations import hyperliquid_info as hl

        cz_row, ctxs, okx_fund, okx_ticker = await _gather_funding(cz, hl, base, inst)
    except Exception as exc:
        logger.warning("funding gather failed for %s: %s", symbol, exc)
        cz_row, ctxs, okx_fund, okx_ticker = {}, {}, None, None

    if isinstance(cz_row, dict) and cz_row.get("funding_rate") is not None:
        # Coinalyze value is already a percent (0.0123 == 0.0123% / 8h).
        rate = float(cz_row["funding_rate"]) / 100.0
        source = "coinalyze"

    hl_row = ctxs.get(base) if isinstance(ctxs, dict) else None
    if isinstance(hl_row, dict):
        if mark is None:
            mark = _to_float(hl_row.get("mark"))
        if index is None:
            index = _to_float(hl_row.get("oracle"))
        if rate is None and hl_row.get("funding") is not None:
            rate = float(hl_row["funding"])
            source = "hyperliquid"

    if isinstance(okx_fund, list) and okx_fund:
        row = okx_fund[0] if isinstance(okx_fund[0], dict) else {}
        if rate is None:
            rate = _to_float(row.get("fundingRate"))
            if rate is not None:
                source = "okx"
        next_ms = _to_float(row.get("fundingTime"))
        if next_ms is not None:
            next_ms = int(next_ms)

    if isinstance(okx_ticker, list) and okx_ticker:
        trow = okx_ticker[0] if isinstance(okx_ticker[0], dict) else {}
        if mark is None:
            mark = _to_float(trow.get("last"))

    if rate is None or mark is None:
        return None

    minutes = _minutes_to_next_funding(next_ms)
    next_dt = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    result = {
        "funding_rate": rate,
        "funding_rate_pct": rate * 100,
        "next_funding_time": next_dt.isoformat(),
        "minutes_to_settlement": round(minutes, 1),
        "mark_price": mark,
        "index_price": index if index is not None else mark,
        "source": source,
    }
    _cache_set(cache_key, result)
    return result


async def _gather_funding(cz, hl, base: str, inst: str):
    import asyncio

    async def _cz():
        try:
            return await cz.get_funding_rate(base)
        except Exception:
            return {}

    async def _hl():
        try:
            return await hl.asset_ctxs()
        except Exception:
            return {}

    async def _okx_fund():
        return await _okx_get("/public/funding-rate", {"instId": inst})

    async def _okx_tick():
        return await _okx_get("/market/ticker", {"instId": inst})

    return await asyncio.gather(_cz(), _hl(), _okx_fund(), _okx_tick())


async def get_klines(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    limit: int = 100,
) -> Optional[List[List]]:
    """OHLCV in Binance kline shape, oldest first, from OKX swap candles."""
    cache_key = f"klines:{symbol}:{interval}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    bar = _OKX_BAR.get(interval)
    if bar is None:
        logger.warning("unsupported kline interval %s", interval)
        return None

    data = await _okx_get(
        "/market/candles",
        {"instId": _okx_swap(symbol), "bar": bar, "limit": limit},
    )
    if not isinstance(data, list) or not data:
        return None

    rows: List[List] = []
    for raw in reversed(data):
        if not isinstance(raw, list) or len(raw) < 5:
            continue
        ts = _to_float(raw[0])
        o, h, l, c = _to_float(raw[1]), _to_float(raw[2]), _to_float(raw[3]), _to_float(raw[4])
        vol = _to_float(raw[5]) if len(raw) > 5 else 0.0
        quote = _to_float(raw[7]) if len(raw) > 7 else 0.0
        if ts is None or o is None or h is None or l is None or c is None:
            continue
        rows.append([int(ts), str(o), str(h), str(l), str(c), str(vol or 0), int(ts), str(quote or 0), 0, "0", "0", "0"])
    if not rows:
        return None
    _cache_set(cache_key, rows)
    return rows


async def get_ticker_24h(symbol: str = "BTCUSDT") -> Optional[Dict]:
    cache_key = f"ticker24h:{symbol}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = await _okx_get("/market/ticker", {"instId": _okx_swap(symbol)})
    if not isinstance(data, list) or not data:
        return None
    row = data[0] if isinstance(data[0], dict) else {}
    last = _to_float(row.get("last"))
    open24 = _to_float(row.get("open24h"))
    if last is None:
        return None
    change_pct = ((last - open24) / open24 * 100.0) if open24 else 0.0
    result = {
        "last_price": last,
        "volume_24h": _to_float(row.get("vol24h")) or 0.0,
        "quote_volume_24h": _to_float(row.get("volCcyQuote24h")) or 0.0,
        "price_change_pct": change_pct,
        "high_24h": _to_float(row.get("high24h")) or last,
        "low_24h": _to_float(row.get("low24h")) or last,
        "source": "okx",
    }
    _cache_set(cache_key, result)
    return result


async def get_recent_agg_trades(
    symbol: str = "BTCUSDT",
    limit: int = 500,
) -> Optional[List[Dict]]:
    cache_key = f"aggtrades:{symbol}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = await _okx_get(
        "/market/trades",
        {"instId": _okx_swap(symbol), "limit": min(limit, 500)},
    )
    if not isinstance(data, list) or not data:
        return None

    trades: List[Dict] = []
    for t in data:
        if not isinstance(t, dict):
            continue
        price = _to_float(t.get("px"))
        qty = _to_float(t.get("sz"))
        ts = _to_float(t.get("ts"))
        if price is None or qty is None or ts is None:
            continue
        side = str(t.get("side") or "").lower()
        trades.append({
            "price": price,
            "qty": qty,
            "time": int(ts),
            "is_buyer_maker": side != "buy",
        })
    trades.sort(key=lambda row: row["time"])
    if not trades:
        return None
    _cache_set(cache_key, trades)
    return trades


async def get_orderbook_depth(symbol: str = "BTCUSDT", limit: int = 20) -> Optional[Dict]:
    cache_key = f"depth:{symbol}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = await _okx_get(
        "/market/books",
        {"instId": _okx_swap(symbol), "sz": min(limit, 400)},
    )
    if not isinstance(data, list) or not data:
        return None
    book = data[0] if isinstance(data[0], dict) else {}
    bids = []
    asks = []
    for side, dest in (("bids", bids), ("asks", asks)):
        for level in book.get(side) or []:
            if not isinstance(level, list) or len(level) < 2:
                continue
            px, qty = _to_float(level[0]), _to_float(level[1])
            if px is None or qty is None:
                continue
            dest.append([px, qty])
    if not bids and not asks:
        return None
    result = {"bids": bids, "asks": asks, "source": "okx"}
    _cache_set(cache_key, result)
    return result
