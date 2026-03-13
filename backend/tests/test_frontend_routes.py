"""
Frontend route smoke tests — verify every endpoint the UI calls actually exists.

Phase 0G — the frontend JS calls these GET endpoints; if any returns 404
it means a route was removed or renamed without updating the UI.
"""
import pytest


class TestFrontendEndpointsExist:
    """Every GET endpoint called by app.js / analytics.js must exist."""

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
