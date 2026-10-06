"""
Frontend route smoke tests — verify every endpoint the UI calls actually exists.

Phase 0G — the frontend JS calls these GET endpoints; if any returns 404
it means a route was removed or renamed without updating the UI.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_live_venues(monkeypatch):
    """No unit test waits on a live exchange — R-IV.644(g)1.

    This file asks whether each route EXISTS, and it answered by really calling them. For
    `/api/crypto/market` that meant real HTTP to Binance, Coinbase, OKX and Bybit from inside
    the suite. Two things followed, and Cursor found both:

      * the file HANGS when it runs after the crypto tests — a unit test's duration became a
        function of someone else's network;
      * it left module state behind. `test_cvd_trend_state_is_per_symbol` expects BTC's
        `ema_ratio` to be None and got -0.93, because this file had driven a real computation
        through it first (fixed from the other side in a3e088c; this is the cause).

    The venues are stubbed to fail fast. A route that returns 200 with honest nulls and a
    route that returns 200 with real prices both answer the only question this file asks,
    and the endpoint is built to degrade rather than raise when a venue is down.
    """
    import httpx

    class _DeadVenue:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("venue stubbed out: no live network in a unit test")

        async def post(self, *a, **k):
            raise httpx.ConnectError("venue stubbed out: no live network in a unit test")

    monkeypatch.setattr(httpx, "AsyncClient", _DeadVenue)
    yield


class TestFrontendEndpointsExist:
    """Every GET endpoint called by app.js must exist."""

    FRONTEND_GET_ENDPOINTS = [
        "/health",
        "/api/v2/positions?status=OPEN",
        "/api/v2/positions/summary",
        "/api/bias/composite",
        "/api/bias/composite/timeframes",
        "/api/bias/factor-health",
        "/api/bias/tick",
        "/api/signals/active",
        "/api/committee/queue",
        "/api/committee/history",
        "/api/portfolio/positions",
        "/api/portfolio/balances",
        "/api/monitoring/factor-staleness",
        "/api/monitoring/polygon-health",
        "/api/trade-ideas/grouped",
        # Crypto / Stater Swap endpoints
        "/api/crypto/market",
        "/api/btc/bottom-signals",
        # Analytics / Ariadne's Thread
        "/api/analytics/risk-budget",
        # Analytics / The Oracle
        "/api/analytics/oracle",
        # Analytics / Hermes Dispatch
        "/api/analytics/weekly-reports",
        # Agora / Sector Heatmap
        "/api/sectors/heatmap",
        # Agora / Flow Summary
        "/api/flow/summary",
        # Agora / Analyzer signals
        "/api/analyze/SPY/signals?days=14",
    ]

    @pytest.mark.parametrize("path", FRONTEND_GET_ENDPOINTS)
    def test_endpoint_exists(self, client, path):
        response = client.get(path)
        assert response.status_code != 404, (
            f"GET {path} returned 404 — frontend calls this endpoint but it doesn't exist"
        )


class TestFrontendDeadEndpointsGone:
    """Removed endpoints should return 404."""

    REMOVED_ENDPOINTS = [
        "/api/bias-auto/status",
        "/api/bias-auto/shift-status",
        "/api/bias-auto/CYCLICAL",
    ]

    @pytest.mark.parametrize("path", REMOVED_ENDPOINTS)
    def test_dead_endpoint_is_dead(self, client, path):
        response = client.get(path)
        assert response.status_code == 404, (
            f"GET {path} returned {response.status_code} — this endpoint was removed"
        )
