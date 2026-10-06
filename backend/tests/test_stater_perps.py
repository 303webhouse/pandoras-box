"""R-IV.658 / R-IV.663 — US-serving perps. No Binance VPN. OKX is labelled when it is the live reading."""

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api import crypto_market as cm  # noqa: E402
from bias_filters import binance_client, coinalyze_client, crypto_perps as perps  # noqa: E402
from integrations import hyperliquid_info as hl  # noqa: E402


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _reset():
    perps.reset_for_tests()
    coinalyze_client.reset_for_tests()
    hl.reset_for_tests()
    binance_client._cache.clear()
    cm._cache_by_symbol.clear()
    yield
    perps.reset_for_tests()
    coinalyze_client.reset_for_tests()
    hl.reset_for_tests()
    binance_client._cache.clear()
    cm._cache_by_symbol.clear()


def test_okx_alone_is_labelled_not_nulled():
    got = perps.pick([(0.01, "okx", _now())], perps.TTL_FUNDING)
    assert got["value"] == 0.01
    assert got["venue"] == "okx"
    assert "okx_only" not in got


def test_coinalyze_beats_okx():
    n = _now()
    got = perps.pick(
        [(0.01, "okx", n), (0.02, "coinalyze", n)],
        perps.TTL_FUNDING,
    )
    assert got["value"] == 0.02
    assert got["venue"] == "coinalyze"
    assert got["stale"] is False


def test_past_ttl_is_null():
    old = _now() - timedelta(seconds=121)
    got = perps.envelope(100.0, "hyperliquid", old, perps.TTL_PRICE)
    assert got["value"] is None
    assert got["stale"] is True
    assert got["venue"] == "hyperliquid"
    assert got["age_s"] >= 121


def test_stale_candidate_is_not_picked():
    old = _now() - timedelta(seconds=200)
    got = perps.pick([(100.0, "hyperliquid", old)], perps.TTL_PRICE)
    assert got["value"] is None
    assert got["venue"] is None


def test_coinalyze_budget_refuses_without_sleeping():
    for _ in range(coinalyze_client.COINALYZE_LIMIT_PER_MINUTE):
        assert coinalyze_client._coinalyze_allow() is True
    t0 = time.perf_counter()
    assert coinalyze_client._coinalyze_allow() is False
    assert time.perf_counter() - t0 < 0.05


def test_hyperliquid_parses_mark_and_predicted():
    meta = [
        {"universe": [{"name": "BTC"}]},
        [{"markPx": "100000.5", "funding": "0.0001", "openInterest": "12.5", "oraclePx": "99900"}],
    ]
    parsed = hl._parse_meta(meta)
    assert parsed["BTC"]["mark"] == 100000.5
    assert parsed["BTC"]["venue"] == "hyperliquid"
    pred = hl._parse_predicted([
        ["BTC", [
            ["BinPerp", {"fundingRate": "0.00011", "nextFundingTime": 1}],
            ["BybitPerp", {"fundingRate": "0.00012", "nextFundingTime": 2}],
            ["HlPerp", {"fundingRate": "0.00013", "nextFundingTime": 3}],
        ]],
    ])
    assert pred["BTC"]["binance"] == pytest.approx(0.00011)
    assert pred["BTC"]["bybit"] == pytest.approx(0.00012)
    assert pred["BTC"]["hyperliquid"] == pytest.approx(0.00013)


@pytest.mark.asyncio
async def test_snapshot_never_asks_binance(monkeypatch):
    seen = []

    async def _no_hl():
        return {}

    async def _cz_funding(sym):
        seen.append("funding")
        return {"funding_rate": 0.01, "predicted_rate": 0.009, "source": "coinalyze",
                "timestamp": _now().isoformat()}

    async def _cz_oi(sym):
        return {"current_oi": 1.0, "timestamp": _now().isoformat()}

    async def _cz_liq(sym):
        return {"total_liquidations": 2.0, "timestamp": _now().isoformat()}

    async def _cz_lsr(sym):
        return {"ratio": 1.1, "timestamp": _now().isoformat()}

    monkeypatch.setattr(hl, "asset_ctxs", _no_hl)
    monkeypatch.setattr(hl, "predicted_fundings", _no_hl)
    monkeypatch.setattr(coinalyze_client, "get_funding_rate", _cz_funding)
    monkeypatch.setattr(coinalyze_client, "get_open_interest", _cz_oi)
    monkeypatch.setattr(coinalyze_client, "get_liquidations", _cz_liq)
    monkeypatch.setattr(coinalyze_client, "get_long_short_ratio", _cz_lsr)

    pack = await perps.snapshot_for("BTC")
    assert pack["funding"]["value"] == 0.01
    assert pack["funding"]["venue"] == "coinalyze"
    assert pack["funding"]["predicted"]["value"] == 0.009
    assert "fapi" not in str(pack)


@pytest.mark.asyncio
async def test_okx_fallback_funding_is_labelled(monkeypatch):
    async def _no_hl():
        return {}

    async def _okx(sym):
        return {"funding_rate": 0.05, "source": "okx_fallback", "timestamp": _now().isoformat()}

    async def _none(sym):
        return {}

    monkeypatch.setattr(hl, "asset_ctxs", _no_hl)
    monkeypatch.setattr(hl, "predicted_fundings", _no_hl)
    monkeypatch.setattr(coinalyze_client, "get_funding_rate", _okx)
    monkeypatch.setattr(coinalyze_client, "get_open_interest", _none)
    monkeypatch.setattr(coinalyze_client, "get_liquidations", _none)
    monkeypatch.setattr(coinalyze_client, "get_long_short_ratio", _none)

    pack = await perps.snapshot_for("ETH")
    assert pack["funding"]["value"] == 0.05
    assert pack["funding"]["venue"] == "okx"


class Venues:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None, follow_redirects=None):
        class _Resp:
            status_code = 200

            def json(self):
                if "/v2/prices/" in url:
                    return {"data": {"amount": "84000"}}
                if "okx.com" in url and str(url).endswith("/market/ticker"):
                    return {"code": "0", "data": [{"last": "84001"}]}
                if "okx.com" in url and "funding-rate" in url:
                    return {"code": "0", "data": [{"fundingRate": "0.0001", "fundingTime": "1800000000000"}]}
                if "okx.com" in url and "trades" in url:
                    return {"code": "0", "data": [
                        {"px": "84000", "sz": "2", "side": "buy", "ts": "1800000000000"},
                        {"px": "84000", "sz": "1", "side": "sell", "ts": "1800000001000"},
                    ]}
                return {}

            def raise_for_status(self):
                return None

        if "fapi.binance.com" in url or "bybit.com" in url:
            raise AssertionError(f"must not ask {url}")
        return _Resp()


def test_hung_perps_cannot_stall_market():
    async def _slow(*a, **k):
        await asyncio.sleep(8)
        return perps.empty_snapshot()

    t0 = time.perf_counter()
    with patch.object(cm.httpx, "AsyncClient", Venues), patch.object(cm, "snapshot_for", _slow):
        snap = asyncio.run(cm.get_market_snapshot(symbol="BTC", limit=200))
    assert time.perf_counter() - t0 < 5.5
    assert snap["derivatives"]["mark"]["value"] is None
    assert snap["prices"]["perps"]["okx"] == 84001.0


def test_market_fills_binance_funding_from_hl_predicted_not_fapi():
    async def _pack(*a, **k):
        return {
            **perps.empty_snapshot(),
            "mark": perps.envelope(84100.0, "hyperliquid", _now(), perps.TTL_PRICE),
            "predicted_by_venue": {
                "binance": perps.envelope(0.00011, "hyperliquid:BinPerp", _now(), perps.TTL_FUNDING, extra={"kind": "predicted"}),
                "bybit": perps.envelope(0.00012, "hyperliquid:BybitPerp", _now(), perps.TTL_FUNDING, extra={"kind": "predicted"}),
                "hyperliquid": perps.envelope(0.00013, "hyperliquid:HlPerp", _now(), perps.TTL_FUNDING, extra={"kind": "predicted"}),
            },
        }

    with patch.object(cm.httpx, "AsyncClient", Venues), patch.object(cm, "snapshot_for", _pack):
        snap = asyncio.run(cm.get_market_snapshot(symbol="BTC", limit=200))
    assert snap["prices"]["perps"]["binance"] is None
    assert snap["prices"]["perps"]["hyperliquid"] == 84100.0
    assert snap["funding"]["binance"]["rate"] == pytest.approx(0.00011)
    assert snap["funding"]["bybit"]["rate"] == pytest.approx(0.00012)
    assert snap["derivatives"]["predicted_by_venue"]["binance"]["venue"] == "hyperliquid:BinPerp"


@pytest.mark.asyncio
async def test_quarterly_basis_does_not_call_fapi(monkeypatch):
    seen = []

    async def _req(url, params=None):
        seen.append(url)
        if "binance.vision" in url:
            return {"price": "100000"}
        return None

    async def _ctxs():
        return {"BTC": {"mark": 101000.0, "as_of": _now()}}

    monkeypatch.setattr(binance_client, "_make_request", _req)
    monkeypatch.setattr(binance_client, "record_observation", AsyncMock(return_value="LIVE"))
    monkeypatch.setattr(hl, "asset_ctxs", _ctxs)
    result = await binance_client.get_quarterly_basis("BTC")
    assert not any("fapi.binance.com" in u for u in seen)
    assert "hyperliquid" in result["source"]
    assert result["futures_price"] == 101000.0


@pytest.mark.asyncio
async def test_quarterly_basis_uses_okx_when_hyperliquid_misses(monkeypatch):
    seen = []

    async def _req(url, params=None):
        seen.append(url)
        if "binance.vision" in url:
            return {"price": "100000"}
        if "okx.com" in url:
            return {"code": "0", "data": [{"last": "100500"}]}
        return None

    async def _empty():
        return {}

    monkeypatch.setattr(binance_client, "_make_request", _req)
    monkeypatch.setattr(binance_client, "record_observation", AsyncMock(return_value="LIVE"))
    monkeypatch.setattr(hl, "asset_ctxs", _empty)
    result = await binance_client.get_quarterly_basis("BTC")
    assert not any("fapi.binance.com" in u for u in seen)
    assert "okx_swap" in result["source"]
    assert result["futures_price"] == 100500.0
