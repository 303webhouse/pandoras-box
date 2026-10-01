"""Stater Phase 0, item 2 (R-IV.619) — crypto bars come from free sources, not UW.

BTC/ETH/SOL bars were pulled from UW's metered OHLC (tagged `outcome_resolver`,
uncached) by the regime job, tape-health event detection, the outcome resolver,
the market-profile tool and every GET /api/crypto/state. They now come from
Coinbase Exchange public candles (free, keyless) with OKX public as the fallback.

Load-bearing assertions, each with a positive control (#30):
  * no tracked symbol routes bars to UW, and fetching all six spends zero UW
    calls -- while a symbol pointed at UW DOES trip the same guard;
  * GET /api/crypto/state spends zero UW calls end to end;
  * Coinbase's [time, LOW, HIGH, open, close] order is parsed into (ts, o, h, l, c);
    a row whose range does not contain its open/close is dropped;
  * an empty Coinbase answer falls back to OKX; the cache never stores an empty set.
"""

import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import crypto_symbol_matrix as matrix  # noqa: E402
from integrations import uw_api  # noqa: E402
from jobs import crypto_bars as cb  # noqa: E402

T0 = 1790812800  # 2026-10-01 00:00 UTC


def _run(coro):
    return asyncio.run(coro)


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeHTTP:
    """Stands in for httpx.AsyncClient; serves canned bodies by host and counts calls."""
    coinbase_rows = None
    okx_rows = None
    calls = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        FakeHTTP.calls.append(url)
        if "coinbase.com" in url:
            # second (older) page: empty, so the walk stops
            if params and "end" in params:
                return _Resp(200, [])
            return _Resp(200, FakeHTTP.coinbase_rows if FakeHTTP.coinbase_rows is not None else [])
        if "okx.com" in url:
            return _Resp(200, {"data": FakeHTTP.okx_rows or []})
        if "binance" in url:
            return _Resp(200, [])
        return _Resp(404, None)


@pytest.fixture(autouse=True)
def _fresh():
    cb._bars_cache.clear()
    FakeHTTP.calls = []
    FakeHTTP.coinbase_rows = [[T0, 99.0, 110.0, 100.0, 105.0, 1.0], [T0 - 900, 95.0, 101.0, 96.0, 100.0, 1.0]]
    FakeHTTP.okx_rows = [[str((T0 - 900) * 1000), "10", "11", "9", "10.5", "1"]]
    yield
    cb._bars_cache.clear()


def _uw_tripwire():
    calls = []

    async def _boom(*a, **k):
        calls.append(a)
        raise AssertionError("crypto bars reached the metered UW endpoint")
    return calls, _boom


def test_no_tracked_symbol_routes_bars_to_uw():
    vendors = {s: e["bar_walk_source"]["vendor"] for s, e in matrix.CRYPTO_SYMBOL_MATRIX.items()}
    assert "uw_crypto_ohlc" not in vendors.values(), vendors
    for s in ("BTC", "ETH", "SOL"):
        assert vendors[s] == "coinbase_exchange_candles"


def test_all_six_symbols_fetch_with_zero_uw_calls_and_uw_vendor_trips_the_guard():
    calls, boom = _uw_tripwire()
    with patch.object(uw_api, "_uw_request", boom), patch.object(cb.httpx, "AsyncClient", FakeHTTP):
        for sym in matrix.CRYPTO_SYMBOL_MATRIX:
            for daily in (False, True):
                _run(cb.fetch_crypto_ohlc(sym, use_daily=daily))
        assert calls == []
        # Positive control: point one symbol back at UW and the same guard fires.
        uw_entry = {"bar_walk_source": {"vendor": "uw_crypto_ohlc", "status": "LIVE"}}
        with patch.object(cb, "get_symbol_entry", lambda s: uw_entry):
            cb._bars_cache.clear()
            with pytest.raises(AssertionError):
                _run(cb.fetch_crypto_ohlc("BTC", use_daily=True))
    assert len(calls) == 1


def test_coinbase_row_order_is_parsed_low_high_open_close():
    with patch.object(cb.httpx, "AsyncClient", FakeHTTP):
        bars = _run(cb.fetch_crypto_ohlc("BTC", use_daily=False))
    # ascending by time, (ts, open, high, low, close)
    assert [b[1:] for b in bars] == [(96.0, 101.0, 95.0, 100.0), (100.0, 110.0, 99.0, 105.0)]


def test_incoherent_coinbase_row_is_dropped():
    FakeHTTP.coinbase_rows = [[T0, 120.0, 110.0, 100.0, 105.0, 1.0],   # low above high
                              [T0 - 900, 95.0, 101.0, 96.0, 100.0, 1.0]]
    with patch.object(cb.httpx, "AsyncClient", FakeHTTP):
        bars = _run(cb.fetch_crypto_ohlc("ETH", use_daily=True))
    assert len(bars) == 1 and bars[0][4] == 100.0


def test_empty_coinbase_falls_back_to_okx_and_empty_is_not_cached():
    FakeHTTP.coinbase_rows = []
    FakeHTTP.okx_rows = []
    with patch.object(cb.httpx, "AsyncClient", FakeHTTP):
        assert _run(cb.fetch_crypto_ohlc("SOL", use_daily=True)) == []
        assert any("okx.com" in u for u in FakeHTTP.calls)
        assert not any(k[:2] == ("SOL", True) for k in cb._bars_cache)   # nothing remembered
        FakeHTTP.okx_rows = [[str((T0 - 900) * 1000), "10", "11", "9", "10.5", "1"]]
        bars = _run(cb.fetch_crypto_ohlc("SOL", use_daily=True))
    assert bars and bars[0][4] == 10.5


def test_cache_reuses_a_bar_set_within_its_window():
    with patch.object(cb.httpx, "AsyncClient", FakeHTTP):
        _run(cb.fetch_crypto_ohlc("BTC", use_daily=False))
        n = len(FakeHTTP.calls)
        _run(cb.fetch_crypto_ohlc("BTC", use_daily=False))
        assert len(FakeHTTP.calls) == n                      # served from cache
        cb._bars_cache.clear()
        _run(cb.fetch_crypto_ohlc("BTC", use_daily=False))
        assert len(FakeHTTP.calls) > n                       # positive control: refetches


def test_crypto_state_get_spends_zero_uw_calls():
    from api import crypto_market

    class _Pool:
        def acquire(self):
            class _C:
                async def __aenter__(s):
                    return s

                async def __aexit__(s, *a):
                    return False

                async def fetchrow(s, *a):
                    return None
            return _C()

    async def _pool():
        return _Pool()

    async def _na(*a, **k):
        return {"state": "NA", "reason": "test"}

    calls, boom = _uw_tripwire()
    from bias_filters import binance_client, coinalyze_client
    with patch.object(uw_api, "_uw_request", boom), patch.object(cb.httpx, "AsyncClient", FakeHTTP), \
            patch("database.postgres_client.get_postgres_client", _pool), \
            patch.object(coinalyze_client, "get_funding_rate", _na), \
            patch.object(coinalyze_client, "get_open_interest", _na), \
            patch.object(coinalyze_client, "get_liquidations", _na), \
            patch.object(binance_client, "get_quarterly_basis", _na):
        body = _run(crypto_market.get_crypto_state("BTC"))
    assert calls == []
    assert body["symbol"] == "BTC" and "atr" in body
