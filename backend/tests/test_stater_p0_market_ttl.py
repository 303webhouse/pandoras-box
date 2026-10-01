"""Stater Phase 0, item 3 follow-up (R-IV.623) — a last-good value expires.

P0.3 made the fallback store per symbol, but a coin's last-good value still
stood in for a dead feed forever, labelled only "using cached fallback". So a
price from an hour ago read as the current price on Agora, the Discord bot and
Stater alike. Each field now has a TTL (120 s prices, CVD and order flow; 900 s
funding). Past it the field is null and `errors` says "no fresh value".

Load-bearing assertions, each with its positive control in the same run (#30):
  * the repro: venues go dark, and 1 s past the TTL the price is null with a
    "no fresh value" error -- while 1 s inside it the held value is served;
  * funding holds for 900 s, not 120 s;
  * CVD and order flow expire, and a coin that never had trades reads null,
    not a measured-looking 0 / NEUTRAL;
  * the key shape is the same fresh, held and expired;
  * one coin expiring leaves another coin's held value alone.
"""

import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api import crypto_market as cm  # noqa: E402

T0 = 1_800_000_000.0


class _Clock:
    t = T0

    @classmethod
    def time(cls):
        return cls.t


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Venues:
    """Coinbase and OKX answer for coins in `up`; Binance perps 451 and Bybit 403, as from Railway."""
    prices = {"BTC": 84000.0, "HYPE": 31.5}
    up = set()

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None, follow_redirects=None):
        params = params or {}
        if "fapi.binance.com" in url:
            return _Resp(451, {"code": 0, "msg": "Service unavailable from a restricted location"})
        if "bybit.com" in url:
            return _Resp(403, None)
        if "/v2/prices/" in url:
            base = url.split("/v2/prices/")[1].split("-USD")[0]
            if base in Venues.up:
                return _Resp(200, {"data": {"amount": str(Venues.prices[base])}})
            return _Resp(503, None)
        inst = params.get("instId", "")
        base = inst.split("-")[0]
        if "okx.com" in url and base in Venues.up:
            px = Venues.prices[base]
            if url.endswith("/market/ticker"):
                return _Resp(200, {"code": "0", "data": [{"last": str(px + (1 if "SWAP" in inst else 0))}]})
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
    cm._bybit_runtime_disabled = False
    _Clock.t = T0
    Venues.up = set()
    yield
    cm._cache_by_symbol.clear()
    cm._last_good_by_symbol.clear()
    cm._bybit_runtime_disabled = False
    for state in cm._cvd_state_by_symbol.values():   # in place: _cvd_trend_state aliases BTC's
        state.update(cm._new_cvd_state())


def _snap(sym, at):
    _Clock.t = T0 + at
    cm._cache_by_symbol.clear()                 # each read is a real fetch, not the 4 s cache
    with patch.object(cm.httpx, "AsyncClient", Venues), patch.object(cm, "time", _Clock):
        return asyncio.run(cm.get_market_snapshot(symbol=sym, limit=200))


def _keys(d):
    return {k: _keys(v) if isinstance(v, dict) else None for k, v in d.items()}


def test_ttls_are_the_ruled_values():
    assert cm.FALLBACK_TTL_SECONDS == {"price": 120, "cvd": 120, "order_flow": 120, "funding": 900}


def test_repro_a_dead_feeds_price_expires_instead_of_standing_in_forever():
    Venues.up = {"BTC"}
    fresh = _snap("BTC", 0)
    assert fresh["prices"]["coinbase_spot"] == 84000.0 and fresh["prices"]["perps"]["okx"] == 84001.0
    Venues.up = set()
    # Positive control: inside the TTL the held value is served, and says so.
    held = _snap("BTC", 119)
    assert held["prices"]["coinbase_spot"] == 84000.0
    assert held["prices"]["perps"]["okx"] == 84001.0 and held["prices"]["perps"]["source"] == "okx"
    assert held["prices"]["binance_spot"] == 84000.0
    assert "coinbase_spot: using cached fallback" in held["errors"]
    # The repro: one second past it, null and "no fresh value" -- not an hour-old price.
    gone = _snap("BTC", 121)
    assert gone["prices"]["coinbase_spot"] is None
    assert gone["prices"]["binance_spot"] is None
    assert gone["prices"]["perps"]["okx"] is None and gone["prices"]["perps"]["source"] is None
    assert gone["prices"]["basis"] is None and gone["prices"]["basis_pct"] is None
    msgs = [e for e in gone["errors"] if "no fresh value" in e]
    assert {m.split(":")[0] for m in msgs} >= {"coinbase_spot", "binance_spot_price", "perp_price"}
    assert any("limit 120s" in m and "last good 121s ago" in m for m in msgs)
    assert not any("using cached fallback" in e and e.startswith("coinbase_spot") for e in gone["errors"])


def test_funding_holds_for_900s_not_120s():
    Venues.up = {"BTC"}
    assert _snap("BTC", 0)["funding"]["okx"]["rate"] == 0.0001
    Venues.up = set()
    held = _snap("BTC", 899)                                  # positive control: past 120, inside 900
    assert held["funding"]["okx"]["rate"] == 0.0001
    assert held["funding"]["primary"] == {"rate": 0.0001, "source": "okx"}
    assert held["prices"]["coinbase_spot"] is None            # the price TTL already ran out
    gone = _snap("BTC", 901)
    assert gone["funding"]["okx"] == {"rate": None, "timestamp": None}
    assert gone["funding"]["primary"] == {"rate": None, "source": None}
    assert any(e.startswith("okx_funding: no fresh value") for e in gone["errors"])


def test_cvd_and_order_flow_expire():
    Venues.up = {"BTC"}
    fresh = _snap("BTC", 0)
    assert fresh["cvd"]["net_btc"] == 1.0 and fresh["cvd"]["source"] == "okx"
    assert len(fresh["order_flow"]) == 2
    Venues.up = set()
    held = _snap("BTC", 119)                                  # positive control
    assert held["cvd"] == fresh["cvd"] and held["order_flow"] == fresh["order_flow"]
    assert "trades: using cached fallback" in held["errors"]
    gone = _snap("BTC", 121)
    assert all(gone["cvd"][k] is None for k in cm._CVD_FIELDS if k != "cvd_series")
    assert gone["cvd"]["cvd_series"] == [] and gone["order_flow"] == []
    assert any(e.startswith("trades: no fresh value") for e in gone["errors"])
    assert any(e.startswith("order_flow: no fresh value") for e in gone["errors"])


def test_a_coin_that_never_traded_reads_null_not_zero():
    snap = _snap("HYPE", 0)                                   # every venue down from the start
    assert snap["cvd"]["net_usd"] is None and snap["cvd"]["direction"] is None
    assert snap["cvd"]["gross_usd"] is None and snap["cvd"]["cvd_series"] == []
    # Positive control: once the coin trades, the reading is a number again.
    Venues.up = {"HYPE"}
    live = _snap("HYPE", 1)
    assert live["cvd"]["net_usd"] == round(31.5 * 2 - 31.5, 2) and live["cvd"]["direction"] is not None


def test_shape_is_the_same_fresh_held_and_expired():
    Venues.up = {"BTC"}
    fresh = _snap("BTC", 0)
    Venues.up = set()
    held, gone = _snap("BTC", 60), _snap("BTC", 1000)
    assert _keys(fresh) == _keys(held) == _keys(gone)
    assert set(gone) == {"status", "timestamp", "prices", "funding", "cvd", "order_flow", "errors"}


def test_one_coin_expiring_leaves_another_coins_held_value_alone():
    Venues.up = {"BTC"}
    _snap("BTC", 0)
    Venues.up = {"HYPE"}
    _snap("HYPE", 100)
    Venues.up = set()
    assert _snap("BTC", 150)["prices"]["coinbase_spot"] is None       # 150 s old: expired
    assert _snap("HYPE", 150)["prices"]["coinbase_spot"] == 31.5      # 50 s old: still held
