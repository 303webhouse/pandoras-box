"""R-IV.742 — stale is age; cap/froth share one funding and one OI call."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bias_filters import coinalyze_client as cz  # noqa: E402
from bias_filters import crypto_perps as perps  # noqa: E402
from bias_filters.crypto_cycle_engine import _make_cell, _result_to_state  # noqa: E402


THRESH = {"coinalyze": 360}


@pytest.fixture(autouse=True)
def _reset():
    cz.reset_for_tests()
    perps.reset_for_tests()
    yield
    cz.reset_for_tests()
    perps.reset_for_tests()


def test_vendor_error_with_fresh_as_of_is_not_stale():
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "current_oi": 1.0,
        "error": "bounds",
        "signal": "UNKNOWN",
        "timestamp": now,
        "health_status": "DEGRADED",
    }
    state, val, as_of, stale = _result_to_state(result, "coinalyze", "current_oi", THRESH)
    assert stale is False
    assert state == "DEGRADED"
    assert val == 1.0
    cell = _make_cell(
        "open_interest", "CAPITULATION", val, state, "coinalyze", as_of, stale,
        reason="bounds", health_status="DEGRADED", signal="FIRING",
    )
    assert cell["stale"] is False
    assert cell["signal"] == "UNKNOWN"
    assert cell["health_status"] == "DEGRADED"


def test_vendor_health_without_error_does_not_set_stale():
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "oi_change_4h": 6.0,
        "signal": "UNKNOWN",
        "timestamp": now,
        "health_status": "DEGRADED",
    }
    state, val, as_of, stale = _result_to_state(result, "coinalyze", "oi_change_4h", THRESH)
    assert stale is False
    assert state == "LIVE"
    cell = _make_cell(
        "oi_extreme", "FROTH", val, state, "coinalyze", as_of, stale,
        health_status="DEGRADED", signal="FIRING",
    )
    assert cell["stale"] is False
    assert cell["signal"] == "FIRING"
    assert cell["health_status"] == "DEGRADED"


def test_old_as_of_is_stale_and_signal_unknown():
    result = {
        "current_oi": 1.0,
        "signal": "NEUTRAL",
        "timestamp": "1970-01-01T00:00:00Z",
    }
    state, val, as_of, stale = _result_to_state(result, "coinalyze", "current_oi", THRESH)
    assert stale is True
    assert state == "STALE"
    cell = _make_cell(
        "open_interest", "CAPITULATION", val, state, "coinalyze", as_of, stale,
        signal="FIRING",
    )
    assert cell["signal"] == "UNKNOWN"


def test_snapshot_cache_is_sixty_seconds():
    assert perps.SNAPSHOT_CACHE_SECONDS == 60


@pytest.mark.asyncio
async def test_singleflight_shares_one_funding_and_one_oi(monkeypatch):
    hits = []

    async def _req(endpoint, params=None):
        hits.append(endpoint)
        await asyncio.sleep(0.02)
        if endpoint == "/funding-rate":
            return [{"symbol": "BTCUSD_PERP.A", "value": 0.01}]
        hist = [{"t": i, "o": 10 + i, "c": 100} for i in range(6)]
        return [{"symbol": "BTCUSD_PERP.A", "history": hist}]

    monkeypatch.setattr(cz, "_make_request", _req)
    monkeypatch.setattr(cz, "_make_okx_request", AsyncMock(side_effect=AssertionError("no OKX")))
    monkeypatch.setattr(cz, "record_observation", AsyncMock(return_value="LIVE"))

    a, b = await asyncio.gather(cz.get_funding_rate("BTC"), cz.get_funding_rate("BTC"))
    assert a.get("funding_rate") == b.get("funding_rate")
    assert hits.count("/funding-rate") == 1

    cz.reset_for_tests()
    hits.clear()
    c, d = await asyncio.gather(cz.get_open_interest("ETH"), cz.get_open_interest("ETH"))
    assert c.get("current_oi") == d.get("current_oi")
    assert hits.count("/open-interest-history") == 1
