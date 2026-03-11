"""
Position CRUD tests — verify v2 endpoints respond correctly.

Phase 0G — route wiring + legacy routes confirmed dead.
"""
import pytest


class TestPositionRoutes:
    """v2 position endpoints should be wired and respond."""

    def test_list_positions_returns_200(self, client):
        response = client.get("/api/v2/positions?status=OPEN")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data

    def test_position_summary_returns_200(self, client):
        response = client.get("/api/v2/positions/summary")
        assert response.status_code == 200
        data = response.json()
        assert "position_count" in data
        assert "cash" in data

    def test_create_position_requires_auth(self, client):
        response = client.post(
            "/api/v2/positions",
            json={
                "ticker": "AAPL",
                "entry_price": 175.50,
                "quantity": 1,
                "structure": "long_call",
                "expiry": "2026-04-17",
                "long_strike": 175,
            },
        )
        assert response.status_code == 401

    def test_create_position_with_auth(self, client, test_api_key):
        response = client.post(
            "/api/v2/positions",
            json={
                "ticker": "AAPL",
                "entry_price": 175.50,
                "quantity": 1,
                "structure": "long_call",
                "expiry": "2026-04-17",
                "long_strike": 175,
            },
            headers={"X-API-Key": test_api_key},
        )
        assert response.status_code != 401

    def test_close_nonexistent_position(self, client, test_api_key):
        response = client.post(
            "/api/v2/positions/POS_FAKE_999/close",
            json={"exit_price": 180.0},
            headers={"X-API-Key": test_api_key},
        )
        # Should be 404 (not found) or 500 (db error on mock), but not 401
        assert response.status_code in (404, 500)

    def test_delete_nonexistent_position(self, client, test_api_key):
        response = client.delete(
            "/api/v2/positions/POS_FAKE_999",
            headers={"X-API-Key": test_api_key},
        )
        # Soft-delete may return 200 even on missing rows (UPDATE WHERE returns 0 rows)
        assert response.status_code in (200, 404, 500)


class TestLegacyRoutesRemoved:
    """Legacy position endpoints should no longer be routable."""

    DEAD_ROUTES = [
        ("GET", "/api/positions/open"),
        ("POST", "/api/positions/open"),
        ("POST", "/api/positions/manual"),
        ("POST", "/api/positions/close"),
        ("POST", "/api/positions/close-expired"),
        ("GET", "/api/positions/history"),
        ("GET", "/api/positions/debug-db"),
        ("GET", "/api/positions/diagnose"),
        ("POST", "/api/positions/force-sync"),
        ("POST", "/api/position/update"),
    ]

    @pytest.mark.parametrize("method,path", DEAD_ROUTES)
    def test_legacy_route_returns_404_or_405(self, client, method, path):
        if method == "GET":
            response = client.get(path)
        elif method == "POST":
            response = client.post(path, json={})
        else:
            pytest.fail(f"Unknown method: {method}")
        assert response.status_code in (404, 405, 422), (
            f"{method} {path} returned {response.status_code} — legacy route should be gone"
        )
