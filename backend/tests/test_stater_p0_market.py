"""Stater Phase 0, item 3 (R-IV.619) — /api/crypto/market keeps each coin's state separate.

The response cache, the last-good fallbacks and the CVD trend state were one
global each. Stater polls six coins in parallel, so within 4 s a caller asking
for BTC could be handed HYPE's snapshot, and a failed HYPE feed was "filled" with
BTC's last price. The page also sent bare "BTC", which every venue rejects.

Load-bearing assertions (positive controls in the same run, #30):
  * a coin whose feeds fail gets NO price -- never another coin's -- while the
    same coin's own last-good fallback still works;
  * the 4 s cache serves a coin only its own snapshot;
  * 'BTC', 'BTC-USD', 'BTCUSDT' and 'btc' all reach the venues as BTCUSDT;
  * BTC's response keeps the exact key shape Agora and the Discord bot read.
"""

import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api import crypto_market as cm  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeVenues:
    """Coinbase answers with a per-coin price; everything else fails. `down` coins fail too."""
    prices = {"BTC": 84000.0, "HYPE": 31.5}
    down = set()
    seen = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None, follow_redirects=None):
        FakeVenues.seen.append((url, dict(params or {})))
        if "/v2/prices/" in url:
            base = url.split("/v2/prices/")[1].split("-USD")[0]
            if base in FakeVenues.down or base not in FakeVenues.prices:
                return _Resp(503, None)
            return _Resp(200, {"data": {"amount": str(FakeVenues.prices[base])}})
        return _Resp(503, None)


def _reset_cvd_state():
    """Reset the per-symbol CVD trend state, BTC's dict IN PLACE.

    R-IV.638(d): the fixture cleared the cache and the fallbacks but not this third global,
    so `test_cvd_trend_state_is_per_symbol` passed alone and FAILED in the full suite --
    `tests/test_frontend_routes.py` sorts earlier and drives /api/crypto/market through a
    TestClient, leaving BTC's ema_ratio at -0.93 where the test expects None. A test that
    asserts on module state has to own that state.

    In place, not replaced: `cm._cvd_trend_state` is an alias for the dict at "BTCUSDT" and
    the test asserts that identity. `_cvd_state_by_symbol.clear()` would orphan the alias
    and the assertion would then fail for a different reason.
    """
    for pair in list(cm._cvd_state_by_symbol):
        if pair == "BTCUSDT":
            cm._cvd_state_by_symbol[pair].update(cm._new_cvd_state())
        else:
            del cm._cvd_state_by_symbol[pair]


@pytest.fixture(autouse=True)
def _reset():
    cm._cache_by_symbol.clear()
    cm._last_good_by_symbol.clear()
    _reset_cvd_state()
    FakeVenues.down = set()
    FakeVenues.seen = []
    yield
    cm._cache_by_symbol.clear()
    cm._last_good_by_symbol.clear()
    _reset_cvd_state()


@pytest.fixture(autouse=True)
def _quiet_perps():
    async def _empty(*a, **k):
        from bias_filters.crypto_perps import empty_snapshot
        return empty_snapshot()
    with patch.object(cm, "snapshot_for", _empty):
        yield


def _snap(sym):
    with patch.object(cm.httpx, "AsyncClient", FakeVenues):
        return _run(cm.get_market_snapshot(symbol=sym, limit=200))


@pytest.mark.parametrize("raw", ["BTC", "btc", "BTC-USD", "BTCUSDT", "BTC-USDT-SWAP", "BTCUSDT.P"])
def test_symbol_forms_reach_venues_as_the_full_pair(raw):
    assert cm._canonical_pair(raw) == "BTCUSDT"


def test_untracked_symbol_keeps_its_own_quote():
    assert cm._canonical_pair("XRP") == "XRPUSDT"
    assert cm._canonical_pair("XRPUSDT") == "XRPUSDT"


def test_failed_coin_never_borrows_another_coins_price_but_keeps_its_own_fallback():
    btc = _snap("BTC")
    assert btc["prices"]["coinbase_spot"] == 84000.0
    FakeVenues.down = {"HYPE"}
    cm._cache_by_symbol.clear()
    hype = _snap("HYPE")
    assert hype["prices"]["coinbase_spot"] is None            # not BTC's 84000
    # Positive control: HYPE's OWN last-good still fills a later failure.
    FakeVenues.down = set()
    cm._cache_by_symbol.clear()
    assert _snap("HYPE")["prices"]["coinbase_spot"] == 31.5
    FakeVenues.down = {"HYPE"}
    cm._cache_by_symbol.clear()
    again = _snap("HYPE")
    assert again["prices"]["coinbase_spot"] == 31.5
    assert "coinbase_spot: using cached fallback" in again["errors"]


def test_cache_serves_each_coin_only_its_own_snapshot():
    btc = _snap("BTC")
    hype = _snap("HYPE")                                      # within the 4 s window
    assert hype is not btc and hype["prices"]["coinbase_spot"] == 31.5
    # Positive control: a repeat BTC call inside the window IS the cached object.
    assert _snap("BTC") is btc


def test_bare_btc_queries_venues_with_btcusdt():
    _snap("BTC")
    binance = [p for u, p in FakeVenues.seen if "ticker/price" in u]
    assert binance and all(p.get("symbol") == "BTCUSDT" for p in binance)
    assert any("/v2/prices/BTC-USD/spot" in u for u, _ in FakeVenues.seen)


def test_btc_response_shape_is_unchanged():
    snap = _snap("BTCUSDT")
    # R-IV.658 added `derivatives` (venue+age envelopes). Existing keys stay.
    assert set(snap) == {"status", "timestamp", "prices", "funding", "cvd", "order_flow", "derivatives", "errors"}
    assert set(snap["prices"]) == {"coinbase_spot", "binance_spot", "binance_spot_ts", "perps", "basis", "basis_pct", "spot_spread"}
    assert set(snap["funding"]) == {"binance", "okx", "bybit", "primary"}
    assert {"net_btc", "net_usd", "direction", "direction_confidence", "gross_usd", "source", "cvd_series"} <= set(snap["cvd"])


def test_cvd_trend_state_is_per_symbol():
    a, b = cm._cvd_state_for("BTCUSDT"), cm._cvd_state_for("HYPEUSDT")
    assert a is not b and a is cm._cvd_trend_state
    cm._classify_cvd_direction(5e6, 6e6, b)                   # strong HYPE buying
    assert b["ema_ratio"] is not None and a["ema_ratio"] is None
