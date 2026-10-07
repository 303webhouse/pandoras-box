"""R-IV.700 — cycle remaps are in test_s3_phase2_cycle_engine.

This file covers the other two queue items: the strategy engine must not
wait on fapi.binance.com, and HYPE's cold /market path must not ask
Coinalyze's OI / liquidation history.
"""

import os
import sys
from datetime import datetime, timezone
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bias_filters import coinalyze_client, crypto_perps as perps  # noqa: E402
from integrations import binance_futures as bf  # noqa: E402
from integrations import hyperliquid_info as hl  # noqa: E402


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _reset():
    perps.reset_for_tests()
    coinalyze_client.reset_for_tests()
    hl.reset_for_tests()
    bf.reset_for_tests()
    yield
    perps.reset_for_tests()
    coinalyze_client.reset_for_tests()
    hl.reset_for_tests()
    bf.reset_for_tests()


@pytest.mark.asyncio
async def test_hype_snapshot_skips_coinalyze_history(monkeypatch):
    called = []

    async def _empty():
        return {}

    def _track(name):
        async def _fn(sym):
            called.append(name)
            if name == "funding":
                return {"funding_rate": 0.01, "timestamp": _now().isoformat()}
            return {}
        return _fn

    monkeypatch.setattr(hl, "asset_ctxs", _empty)
    monkeypatch.setattr(hl, "predicted_fundings", _empty)
    monkeypatch.setattr(coinalyze_client, "get_funding_rate", _track("funding"))
    monkeypatch.setattr(coinalyze_client, "get_open_interest", _track("oi"))
    monkeypatch.setattr(coinalyze_client, "get_liquidations", _track("liq"))
    monkeypatch.setattr(coinalyze_client, "get_long_short_ratio", _track("lsr"))

    await perps.snapshot_for("HYPE")
    assert "funding" in called
    assert "oi" not in called
    assert "liq" not in called


@pytest.mark.asyncio
async def test_btc_snapshot_still_asks_coinalyze_history(monkeypatch):
    called = []

    async def _empty():
        return {}

    def _track(name):
        async def _fn(sym):
            called.append(name)
            return {}
        return _fn

    monkeypatch.setattr(hl, "asset_ctxs", _empty)
    monkeypatch.setattr(hl, "predicted_fundings", _empty)
    monkeypatch.setattr(coinalyze_client, "get_funding_rate", _track("funding"))
    monkeypatch.setattr(coinalyze_client, "get_open_interest", _track("oi"))
    monkeypatch.setattr(coinalyze_client, "get_liquidations", _track("liq"))
    monkeypatch.setattr(coinalyze_client, "get_long_short_ratio", _track("lsr"))

    await perps.snapshot_for("BTC")
    assert {"funding", "oi", "liq", "lsr"} <= set(called)


@pytest.mark.asyncio
async def test_binance_futures_never_asks_fapi(monkeypatch):
    seen = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            seen.append(url)
            if "fapi.binance.com" in url or "binance.com" in url:
                raise AssertionError(f"must not ask {url}")

            class _Resp:
                status_code = 200

                def json(self):
                    if "funding-rate" in url:
                        return {"code": "0", "data": [{"fundingRate": "0.0004", "fundingTime": "1800000000000"}]}
                    if url.endswith("/market/ticker"):
                        return {"code": "0", "data": [{"last": "84000", "open24h": "83000", "high24h": "85000", "low24h": "82000", "vol24h": "1", "volCcyQuote24h": "2"}]}
                    if "candles" in url:
                        return {"code": "0", "data": [
                            ["1700000600000", "101", "102", "100", "101.5", "3", "0", "4", "1"],
                            ["1700000300000", "100", "101", "99", "100.5", "2", "0", "3", "1"],
                        ]}
                    if "trades" in url:
                        return {"code": "0", "data": [{"px": "84000", "sz": "1", "side": "buy", "ts": "1700000000000"}]}
                    if "books" in url:
                        return {"code": "0", "data": [{"bids": [["83999", "1"]], "asks": [["84001", "1"]]}]}
                    return {"code": "0", "data": []}

            return _Resp()

    async def _cz(sym):
        return {"funding_rate": 0.04, "source": "coinalyze"}  # percent → 0.0004 fraction

    async def _hl():
        return {"BTC": {"mark": 84100.0, "funding": 0.0001, "oracle": 84050.0}}

    monkeypatch.setattr(bf.httpx, "AsyncClient", _Client)
    monkeypatch.setattr("bias_filters.coinalyze_client.get_funding_rate", _cz)
    monkeypatch.setattr(hl, "asset_ctxs", _hl)

    funding = await bf.get_funding_rate("BTCUSDT")
    assert funding is not None
    assert funding["funding_rate"] == pytest.approx(0.0004)
    assert funding["mark_price"] == 84100.0
    assert not any("fapi" in u for u in seen)

    klines = await bf.get_klines("BTCUSDT", "5m", limit=2)
    assert klines is not None
    assert int(klines[0][0]) < int(klines[-1][0])
    assert float(klines[0][4]) == 100.5

    ticker = await bf.get_ticker_24h("BTCUSDT")
    assert ticker["last_price"] == 84000.0
    assert ticker["source"] == "okx"

    trades = await bf.get_recent_agg_trades("BTCUSDT", limit=10)
    assert trades[0]["is_buyer_maker"] is False

    book = await bf.get_orderbook_depth("BTCUSDT", limit=20)
    assert book["bids"][0][0] == 83999.0
    assert not any("fapi.binance.com" in u for u in seen)
