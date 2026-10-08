"""R-IV.741 — our Coinalyze budget refuse is not the vendor's silence."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bias_filters import coinalyze_client as cz  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    cz.reset_for_tests()
    yield
    cz.reset_for_tests()


@pytest.mark.asyncio
async def test_budget_refusal_surfaces_as_reason_not_missing_data(monkeypatch):
    now = time.monotonic()
    cz._call_times[:] = [now] * cz.COINALYZE_LIMIT_PER_MINUTE
    monkeypatch.setattr(cz, "_get_api_key", lambda: "test-key")
    monkeypatch.setattr(cz, "record_observation", AsyncMock(return_value="DEAD"))

    class _Boom:
        def __init__(self, *a, **k):
            raise AssertionError("budget refuse must not HTTP")

    monkeypatch.setattr(cz.httpx, "AsyncClient", _Boom)

    miss = await cz._make_request("/long-short-ratio-history", {"symbols": "BTCUSD_PERP.A"})
    assert isinstance(miss, cz.CoinalyzeMiss)
    assert miss.reason == cz.COINALYZE_BUDGET_REFUSED
    assert miss.reason != cz.COINALYZE_VENDOR_FAILED

    got = await cz.get_long_short_ratio("BTC")
    assert got.get("ratio") is None
    assert got.get("reason") == "COINALYZE_BUDGET_REFUSED"
    assert got.get("state") == "NA"
    assert "no long/short ratio" not in str(got.get("error") or "")


@pytest.mark.asyncio
async def test_vendor_empty_is_not_a_budget_refuse(monkeypatch):
    monkeypatch.setattr(cz, "_get_api_key", lambda: "test-key")
    monkeypatch.setattr(cz, "record_observation", AsyncMock(return_value="DEAD"))

    async def _empty(endpoint, params=None):
        return []

    monkeypatch.setattr(cz, "_make_request", _empty)
    got = await cz.get_long_short_ratio("BTC")
    assert got.get("ratio") is None
    assert got.get("reason") == "COINALYZE_VENDOR_FAILED"
    assert got.get("reason") != "COINALYZE_BUDGET_REFUSED"
    assert "no long/short ratio" in str(got.get("error") or "")
