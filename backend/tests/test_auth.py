"""
Auth enforcement tests — verify all mutation routes require PIVOT_API_KEY.

Phase 0H — auto-discovery test ensures new mutation routes cannot be added
without auth. Parametrized tests cover all known protected routes.
"""
import inspect
import pytest


# Routes that are intentionally public (with justification)
AUTH_EXEMPT_MUTATIONS = {
    # TradingView webhooks — can't send headers, data-write only
    ("POST", "/webhook/tradingview"),
    ("POST", "/webhook/signal"),
    ("POST", "/webhook/circuit_breaker"),
    ("POST", "/webhook/whale"),
    # Breadth/tick/mcclellan webhooks from TradingView
    ("POST", "/webhook/breadth"),
    ("POST", "/webhook/tick"),
    ("POST", "/webhook/mcclellan"),
    # Alert ingestion
    ("POST", "/webhook/alerts/pivot"),
}

# Pre-existing routes that need auth but weren't in Phase 0H scope.
# TODO: Lock these down in a future phase.
AUTH_TODO_LOCKDOWN = {
    # Bias engine management
    ("DELETE", "/api/bias/override"),
    ("POST", "/api/bias-auto/savita/update"),
    ("POST", "/api/bias/factor-update"),
    ("POST", "/api/bias/override"),
    ("POST", "/api/bias/savita/check"),
    ("POST", "/api/bias/savita/enable"),
    ("POST", "/api/bias/weekly-audit"),
    ("PUT", "/api/bias/savita"),
    # UW flow ingestion
    ("POST", "/api/bias/uw/economic_calendar"),
    ("POST", "/api/bias/uw/flow_alerts"),
    ("POST", "/api/bias/uw/generic"),
    ("POST", "/api/bias/uw/highest_volume"),
    ("POST", "/api/bias/uw/market_tide"),
    ("POST", "/api/bias/uw/sectorflow"),
    # Signal management
    ("DELETE", "/api/signals/clear-all"),
    ("POST", "/api/signal/action"),
    ("POST", "/api/signals/archive"),
    ("POST", "/api/signals/{signal_id}/accept"),
    ("POST", "/api/signals/{signal_id}/accept-options"),
    ("POST", "/api/signals/{signal_id}/dismiss"),
    # Trade acceptance
    ("POST", "/api/accept/{pending_id}/fill-options"),
    ("POST", "/api/accept/{pending_id}/fill-stocks"),
    ("POST", "/api/accept/{signal_id}/options"),
    ("POST", "/api/accept/{signal_id}/stocks"),
    ("POST", "/api/pending-trades/expire"),
    # Scanner / strategies / confluence
    ("POST", "/api/confluence/scan"),
    ("POST", "/api/cta/config/enable"),
    ("POST", "/api/cta/scan/custom"),
    ("POST", "/api/cta/scan/push"),
    ("POST", "/api/scanner/enable"),
    ("POST", "/api/scanner/run"),
    ("PUT", "/api/scanner/filters"),
    ("POST", "/api/strategies/disable-all"),
    ("POST", "/api/strategies/enable-all"),
    ("POST", "/api/strategies/reset"),
    ("POST", "/api/strategies/{strategy_id}/toggle"),
    ("PUT", "/api/strategies/{strategy_id}/settings"),
    # Market indicators / sector
    ("POST", "/api/market-indicators/credit-spreads/refresh"),
    ("POST", "/api/market-indicators/market-breadth/refresh"),
    ("POST", "/api/market-indicators/refresh-all"),
    ("POST", "/api/market-indicators/vix-term/refresh"),
    ("POST", "/api/sector-rotation/momentum/refresh"),
    ("POST", "/api/sector-rotation/refresh"),
    # Misc
    ("POST", "/api/dollar-smile/manual"),
    ("POST", "/api/dollar-smile/webhook"),
    ("POST", "/api/flow/configure"),
    ("POST", "/api/flow/manual"),
    ("POST", "/api/flow/webhook"),
    ("POST", "/api/hybrid/refresh"),
    ("POST", "/api/knowledgebase/reload"),
    ("POST", "/webhook/test"),
}

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class TestAuthEnforcement:
    """Mutation routes must require authentication."""

    PROTECTED_ROUTES = [
        # v2 positions (existing)
        ("POST", "/api/v2/positions", {"ticker": "TEST", "entry_price": 100, "quantity": 1}),
        ("PATCH", "/api/v2/positions/POS_TEST_123", {"notes": "test"}),
        ("POST", "/api/v2/positions/POS_TEST_123/close", {"exit_price": 105}),
        ("DELETE", "/api/v2/positions/POS_TEST_123", None),
        ("POST", "/api/v2/positions/bulk", {"positions": []}),
        ("POST", "/api/v2/positions/reconcile", {"positions": []}),
        ("POST", "/api/v2/positions/mark-to-market", None),
        ("PATCH", "/api/v2/positions/account-balance", {"cash": 1000}),
        # Committee results (existing)
        ("POST", "/api/committee/results", {
            "signal_id": "test", "committee_run_id": "test",
            "action": "PASS", "conviction": "LOW",
        }),
        # Watchlist (Phase 0H)
        ("PUT", "/api/watchlist", {"tickers": ["SPY"]}),
        ("POST", "/api/watchlist/add", {"ticker": "AAPL"}),
        ("POST", "/api/watchlist/remove", {"ticker": "AAPL"}),
        ("DELETE", "/api/watchlist/clear", None),
        ("POST", "/api/watchlist/reset", None),
        ("POST", "/api/watchlist/sector-strength", {"sector_strength": {}}),
        ("PATCH", "/api/watchlist/tickers/SPY/mute", {"muted": True}),
        ("PATCH", "/api/watchlist/tickers/bulk-mute", {"symbols": ["SPY"], "muted": True}),
        ("DELETE", "/api/watchlist/tickers/SPY", None),
        ("POST", "/api/watchlist/tickers/add", {"symbol": "AAPL"}),
        # Circuit breaker management (Phase 0H)
        ("POST", "/webhook/circuit_breaker/reset", None),
        ("POST", "/webhook/circuit_breaker/accept_reset", None),
        ("POST", "/webhook/circuit_breaker/reject_reset", None),
        ("POST", "/webhook/circuit_breaker/test/spy_down_1pct", None),
        # BTC signals (Phase 2A)
        ("POST", "/api/btc/bottom-signals/refresh", None),
        ("POST", "/api/btc/bottom-signals/test_signal", {"status": "FIRING"}),
        ("POST", "/api/btc/bottom-signals/reset", None),
        ("POST", "/api/btc/bottom-signals/test_signal/clear-override", None),
        # Portfolio (Phase 0H)
        ("POST", "/api/portfolio/cash-flows", {"amount": 100}),
        # Portfolio (existing, verify still protected)
        ("POST", "/api/portfolio/balances/update", {"account_name": "Robinhood", "balance": 1000}),
        ("POST", "/api/portfolio/positions/sync", {"positions": []}),
        ("POST", "/api/portfolio/positions", {
            "ticker": "SPY", "position_type": "option", "direction": "BULLISH", "quantity": 1,
        }),
        ("POST", "/api/portfolio/positions/close", {"ticker": "SPY"}),
        ("PATCH", "/api/portfolio/positions/closed/1", {"notes": "test"}),
        # Analytics mutations (Brief 3A)
        ("POST", "/api/analytics/resolve-counterfactuals", None),
        # Weekly reports (Brief 3D)
        ("POST", "/api/analytics/weekly-reports", {
            "week_of": "2026-03-07", "report_json": {}, "narrative": "test",
        }),
        # Analytics mutations (Brief 3E — locked down)
        ("POST", "/api/analytics/backtest", {
            "start_date": "2026-01-01", "end_date": "2026-03-01",
        }),
        ("POST", "/api/analytics/log-trade", {"ticker": "SPY"}),
        ("POST", "/api/analytics/log-trade-leg", {
            "trade_id": 1, "ticker": "SPY", "direction": "LONG",
        }),
        ("POST", "/api/analytics/outcomes/manual", {
            "ticker": "SPY", "direction": "LONG", "outcome": "WIN",
        }),
        ("POST", "/api/analytics/log-signal", {
            "signal_id": "test", "ticker": "SPY", "direction": "BULLISH",
            "source": "test",
        }),
        ("POST", "/api/analytics/log-uw-snapshot", {
            "dashboard_type": "flow", "data": {},
        }),
        ("POST", "/api/analytics/import-trades", {"trades": []}),
        ("DELETE", "/api/analytics/trades", None),
        ("DELETE", "/api/analytics/trades/99999", None),
        ("PUT", "/api/analytics/health-alert/1/dismiss", None),
        ("PUT", "/api/analytics/trade/99999/close", {
            "exit_price": 100, "close_reason": "test",
        }),
    ]

    PUBLIC_ROUTES = [
        ("GET", "/health"),
        ("GET", "/live"),
        ("GET", "/api/v2/positions?status=OPEN"),
        ("GET", "/api/v2/positions/summary"),
        ("GET", "/api/bias/composite"),
        ("GET", "/api/committee/queue"),
        ("GET", "/api/monitoring/factor-staleness"),
        ("GET", "/api/monitoring/polygon-health"),
    ]

    def _send(self, client, method, path, body=None, headers=None):
        """Send a request with the given method."""
        kw = {}
        if headers:
            kw["headers"] = headers
        if method == "POST":
            return client.post(path, json=body, **kw) if body is not None else client.post(path, **kw)
        elif method == "PUT":
            return client.put(path, json=body, **kw) if body is not None else client.put(path, **kw)
        elif method == "PATCH":
            return client.patch(path, json=body, **kw) if body is not None else client.patch(path, **kw)
        elif method == "DELETE":
            return client.delete(path, **kw)
        elif method == "GET":
            return client.get(path, **kw)
        else:
            pytest.fail(f"Unknown method: {method}")

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_no_auth_returns_401(self, client, method, path, body):
        response = self._send(client, method, path, body)
        assert response.status_code == 401, (
            f"{method} {path} returned {response.status_code} without auth"
        )

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_valid_x_api_key_accepted(self, client, test_api_key, method, path, body):
        headers = {"X-API-Key": test_api_key}
        response = self._send(client, method, path, body, headers)
        assert response.status_code != 401, (
            f"{method} {path} returned 401 WITH valid API key"
        )

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_valid_bearer_accepted(self, client, test_api_key, method, path, body):
        headers = {"Authorization": f"Bearer {test_api_key}"}
        response = self._send(client, method, path, body, headers)
        assert response.status_code != 401, (
            f"{method} {path} returned 401 WITH valid Bearer token"
        )

    def test_wrong_key_returns_401(self, client):
        response = client.post(
            "/api/v2/positions",
            json={"ticker": "TEST", "entry_price": 100, "quantity": 1},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    @pytest.mark.parametrize("method,path", PUBLIC_ROUTES)
    def test_public_routes_no_auth_needed(self, client, method, path):
        response = self._send(client, method, path)
        assert response.status_code not in (401, 403), (
            f"{method} {path} returned {response.status_code} — should not require auth"
        )


class TestAuthCompleteness:
    """Auto-discovery: every mutation route must either require auth or be explicitly exempted."""

    def test_no_unprotected_mutations(self, client):
        """Fail if any mutation route lacks auth and isn't in the exempt list."""
        from main import app

        all_mutations = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method in MUTATION_METHODS:
                        all_mutations.append((method, route.path, route))

        unprotected = []
        for method, path, route in all_mutations:
            if (method, path) in AUTH_EXEMPT_MUTATIONS or (method, path) in AUTH_TODO_LOCKDOWN:
                continue

            endpoint = getattr(route, "endpoint", None)
            if not endpoint:
                unprotected.append(f"{method} {path}")
                continue

            has_auth = False
            try:
                sig = inspect.signature(endpoint)
                for param in sig.parameters.values():
                    default = param.default
                    if default is inspect.Parameter.empty:
                        continue
                    # FastAPI Depends objects have a .dependency attribute
                    dep_func = getattr(default, "dependency", None)
                    if dep_func is not None and getattr(dep_func, "__name__", "") in (
                        "require_api_key", "verify_pivot_key", "verify_api_key",
                    ):
                        has_auth = True
                        break
            except (ValueError, TypeError):
                pass

            if not has_auth:
                unprotected.append(f"{method} {path}")

        assert not unprotected, (
            f"Found {len(unprotected)} unprotected mutation route(s):\n"
            + "\n".join(f"  - {r}" for r in sorted(unprotected))
            + "\n\nEither add Depends(require_api_key) or add to AUTH_EXEMPT_MUTATIONS with justification."
        )
