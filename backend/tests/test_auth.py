"""
Auth enforcement tests — verify all mutation routes require PIVOT_API_KEY.

Phase 0G — tests that protected endpoints return 401 without a key,
and accept requests with a valid X-API-Key or Bearer token.
"""
import pytest


class TestAuthEnforcement:
    """Mutation routes must require authentication."""

    PROTECTED_ROUTES = [
        ("POST", "/api/v2/positions", {"ticker": "TEST", "entry_price": 100, "quantity": 1}),
        ("PATCH", "/api/v2/positions/POS_TEST_123", {"notes": "test"}),
        ("POST", "/api/v2/positions/POS_TEST_123/close", {"exit_price": 105}),
        ("DELETE", "/api/v2/positions/POS_TEST_123", None),
        ("POST", "/api/v2/positions/bulk", {"positions": []}),
        ("POST", "/api/v2/positions/reconcile", {"positions": []}),
        ("POST", "/api/v2/positions/mark-to-market", None),
        ("PATCH", "/api/v2/positions/account-balance", {"cash": 1000}),
        ("POST", "/api/committee/results", {
            "signal_id": "test", "committee_run_id": "test",
            "action": "PASS", "conviction": "LOW",
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
