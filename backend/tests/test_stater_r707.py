"""R-IV.707 — OKX liquidations fallback: request + units, never scores.

BTC's Coinalyze request and BTC's uly OKX path stay byte-identical.
"""

import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bias_filters import coinalyze_client as cz  # noqa: E402
from bias_filters.crypto_cycle_engine import _compute_composite  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    cz.reset_for_tests()
    yield
    cz.reset_for_tests()


def _cap_cfg():
    return {"min_live_cells_btc_eth": 1, "min_live_cells_others": 1}


@pytest.mark.asyncio
async def test_alt_okx_liq_uses_instfamily_and_ctval(monkeypatch):
    seen = []

    async def _cz(*a, **k):
        return None

    async def _okx(path, params=None):
        seen.append((path, dict(params or {})))
        if path == "/public/instruments":
            return {"code": "0", "data": [{"ctVal": "0.1", "ctValCcy": "HYPE", "instId": "HYPE-USDT-SWAP"}]}
        if path == "/public/liquidation-orders":
            return {"code": "0", "data": [{
                "instId": "HYPE-USDT-SWAP",
                "instFamily": "HYPE-USDT",
                "details": [{
                    "sz": "69", "bkPx": "88.477", "posSide": "short",
                    "ts": "1791388803616", "time": 1791388803616,
                }],
            }]}
        return {"code": "0", "data": []}

    recorded = []

    async def _obs(vendor, feed_type, symbol, success=True, **k):
        recorded.append((vendor, feed_type, symbol, success))
        return "LIVE"

    monkeypatch.setattr(cz, "_make_request", _cz)
    monkeypatch.setattr(cz, "_make_okx_request", _okx)
    monkeypatch.setattr(cz, "record_observation", _obs)

    got = await cz.get_liquidations("HYPE")
    liq_params = [p for path, p in seen if path == "/public/liquidation-orders"]
    assert liq_params and liq_params[0].get("instFamily") == "HYPE-USDT"
    assert "instId" not in liq_params[0]
    assert "uly" not in liq_params[0]
    assert got["source"] == "okx"
    assert got["signal"] == "NEUTRAL"
    assert got["total_liquidations"] == round(69 * 0.1 * 88.477, 2)
    assert got["window_start"] is not None
    assert got["window_end"] is not None
    assert got["ctVal"] == pytest.approx(0.1)
    assert recorded and recorded[0][0] == "okx"


@pytest.mark.asyncio
async def test_alt_okx_liq_never_firing_even_if_long_heavy(monkeypatch):
    async def _cz(*a, **k):
        return None

    async def _okx(path, params=None):
        if path == "/public/instruments":
            return {"code": "0", "data": [{"ctVal": "1"}]}
        return {"code": "0", "data": [{
            "details": [
                {"sz": "10000000", "bkPx": "1", "posSide": "long", "ts": "1791388803616"},
                {"sz": "1", "bkPx": "1", "posSide": "short", "ts": "1791388803617"},
            ]
        }]}

    monkeypatch.setattr(cz, "_make_request", _cz)
    monkeypatch.setattr(cz, "_make_okx_request", _okx)
    monkeypatch.setattr(cz, "record_observation", AsyncMock(return_value="LIVE"))

    got = await cz.get_liquidations("SOL")
    assert got["source"] == "okx"
    assert got["long_pct"] > 75
    assert got["composition"] == "long_heavy"
    assert got["signal"] == "NEUTRAL"


@pytest.mark.asyncio
async def test_btc_okx_fallback_still_uly(monkeypatch):
    seen = []

    async def _cz(*a, **k):
        return None

    async def _okx(path, params=None):
        seen.append((path, dict(params or {})))
        return {"code": "0", "data": [{
            "details": [{"sz": "0.07", "bkPx": "83576.5", "posSide": "short", "ts": "1"}]
        }]}

    monkeypatch.setattr(cz, "_make_request", _cz)
    monkeypatch.setattr(cz, "_make_okx_request", _okx)
    monkeypatch.setattr(cz, "record_observation", AsyncMock(return_value="LIVE"))

    got = await cz.get_liquidations("BTC")
    liq_params = [p for path, p in seen if path == "/public/liquidation-orders"]
    assert liq_params[0].get("uly") == "BTC-USDT"
    assert "instFamily" not in liq_params[0]
    assert got["source"] == "okx_fallback"
    assert got["total_liquidations"] == round(0.07 * 0.01 * 83576.5, 2)
    assert not any(path == "/public/instruments" for path, _ in seen)


@pytest.mark.asyncio
async def test_btc_coinalyze_primary_request_unchanged(monkeypatch):
    captured = []

    async def _cz(endpoint, params=None):
        captured.append((endpoint, dict(params or {})))
        return [{"symbol": "BTCUSD_PERP.A", "history": [
            {"t": 1, "l": 100.0, "s": 50.0},
            {"t": 2, "l": 100.0, "s": 50.0},
        ]}]

    monkeypatch.setattr(cz, "_make_request", _cz)
    monkeypatch.setattr(cz, "_make_okx_request", AsyncMock(side_effect=AssertionError("BTC primary hit; no OKX")))
    monkeypatch.setattr(cz, "record_observation", AsyncMock(return_value="LIVE"))

    got = await cz.get_liquidations("BTC")
    assert captured[0][0] == "/liquidation-history"
    assert captured[0][1]["symbols"] == "BTCUSD_PERP.A"
    assert captured[0][1]["interval"] == "1hour"
    assert "from" in captured[0][1] and "to" in captured[0][1]
    assert captured[0][1]["from"] > 10_000_000_000  # still milliseconds, as production sends
    assert got["source"] == "coinalyze"
    assert got["total_liquidations"] == 300.0


def test_okx_liq_cell_does_not_move_composite():
    """NA + source okx is excluded from live_cap / live_cap_all (LIVE-only)."""
    froth = [{"state": "LIVE", "signal_id": "funding_blowout", "column": "FROTH", "firing": True}]
    cap_without = [{"state": "LIVE", "signal_id": "perp_funding", "column": "CAPITULATION", "signal": "NEUTRAL"}]
    cap_with = cap_without + [{
        "state": "NA", "signal_id": "liquidations", "column": "CAPITULATION",
        "signal": "NEUTRAL", "source": "okx", "value": 610.49,
    }]
    a = _compute_composite(cap_without, froth, _cap_cfg(), "SOL")
    b = _compute_composite(cap_with, froth, _cap_cfg(), "SOL")
    assert a[0] == b[0]
    assert a[1] == b[1]
    assert a[4] == b[4]
