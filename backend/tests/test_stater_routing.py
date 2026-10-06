"""R-IV.645(d) / R-IV.637(d) — /crypto/market does not wait on dead venues.

The 8 s stall was Binance perps: production enables a perp proxy, three
proxied fapi.binance.com calls wait out the 8.0 s client timeout, and Agora
polls this every 5 s. The matrix cell is GEO_BLOCKED. Bybit never answers
from Railway. FARTCOIN is on neither Binance spot nor OKX spot. HYPE is on
Binance spot (confirmed from Railway 2026-10-06).
"""

import asyncio
import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api import crypto_market as cm  # noqa: E402


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Venues:
    prices = {"BTC": 84000.0, "HYPE": 31.5, "FARTCOIN": 0.42}
    seen = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None, follow_redirects=None):
        params = dict(params or {})
        Venues.seen.append((url, params))
        if "fapi.binance.com" in url or "bybit.com" in url:
            await asyncio.sleep(8)
            return _Resp(451, {"code": 0, "msg": "geo"})
        if "binance.vision" in url and "/ticker/price" in url:
            sym = params.get("symbol", "")
            base = sym.replace("USDT", "")
            if base in Venues.prices:
                return _Resp(200, {"price": str(Venues.prices[base])})
            return _Resp(400, {"code": -1121, "msg": "Invalid symbol."})
        if "/v2/prices/" in url:
            base = url.split("/v2/prices/")[1].split("-USD")[0]
            if base in Venues.prices:
                return _Resp(200, {"data": {"amount": str(Venues.prices[base])}})
            return _Resp(503, None)
        inst = params.get("instId", "")
        base = inst.split("-")[0]
        if "okx.com" in url and base in Venues.prices:
            px = Venues.prices[base]
            if url.endswith("/market/ticker"):
                bump = 1 if "SWAP" in inst else 0
                return _Resp(200, {"code": "0", "data": [{"last": str(px + bump)}]})
            if url.endswith("/public/funding-rate"):
                return _Resp(200, {"code": "0", "data": [{"fundingRate": "0.0001", "fundingTime": "1800000000000"}]})
            if url.endswith("/market/trades"):
                return _Resp(200, {"code": "0", "data": [
                    {"px": str(px), "sz": "2", "side": "buy", "ts": "1800000000000"},
                    {"px": str(px), "sz": "1", "side": "sell", "ts": "1800000001000"},
                ]})
        return _Resp(503, None)


@pytest.fixture(autouse=True)
def _reset():
    cm._cache_by_symbol.clear()
    cm._last_good_by_symbol.clear()
    Venues.seen = []
    yield
    cm._cache_by_symbol.clear()
    cm._last_good_by_symbol.clear()
    Venues.seen = []


@pytest.fixture(autouse=True)
def _quiet_perps():
    async def _empty(*a, **k):
        from bias_filters.crypto_perps import empty_snapshot
        return empty_snapshot()
    with patch.object(cm, "snapshot_for", _empty):
        yield


def _snap(sym):
    with patch.object(cm.httpx, "AsyncClient", Venues):
        return asyncio.run(cm.get_market_snapshot(symbol=sym, limit=200))


def _urls():
    return [u for u, _ in Venues.seen]


def test_a_hanging_binance_perp_proxy_cannot_delay_the_snapshot():
    t0 = time.perf_counter()
    snap = _snap("BTC")
    assert time.perf_counter() - t0 < 1.5
    assert snap["prices"]["coinbase_spot"] == 84000.0
    assert snap["prices"]["perps"]["source"] == "okx"
    assert snap["prices"]["perps"]["okx"] == 84001.0
    assert not any("fapi.binance.com" in u or "bybit.com" in u for u in _urls())
    assert not any(e.startswith("binance_perp") or e.startswith("bybit_") for e in snap["errors"])


def test_hype_asks_binance_spot():
    snap = _snap("HYPE")
    assert any("binance.vision" in u and p.get("symbol") == "HYPEUSDT" for u, p in Venues.seen)
    assert snap["prices"]["binance_spot"] == 31.5


def test_fartcoin_does_not_ask_unlisted_spot_venues():
    snap = _snap("FARTCOIN")
    assert not any("binance.vision" in u for u in _urls())
    assert not any(p.get("instId") == "FARTCOIN-USDT" for _, p in Venues.seen)
    assert any(p.get("instId") == "FARTCOIN-USDT-SWAP" for _, p in Venues.seen)
    assert any("/v2/prices/FARTCOIN-USD/spot" in u for u in _urls())
    assert snap["prices"]["coinbase_spot"] == 0.42
    assert snap["prices"]["binance_spot"] is None
    assert snap["prices"]["perps"]["source"] == "okx"
    assert not any("skipped" in e for e in snap["errors"])
