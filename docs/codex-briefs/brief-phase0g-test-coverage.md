# Brief: Phase 0G — Test Coverage (Sharp Edges Only)

**Priority:** MEDIUM — The codebase has 20 scorer tests and nothing else. After today's massive cleanup (1,500+ lines removed, auth added, positions migrated), we need regression protection on the sharp edges before the next round of feature work.
**Target:** Railway backend (`backend/tests/`)
**Estimated time:** 60–90 minutes
**Prerequisites:** All Phase 0A–0F complete. `httpx` already in requirements. Add `pytest`, `pytest-asyncio` to requirements if missing.

---

## Context

Today we shipped 6 phases of code hygiene. The codebase is dramatically cleaner, but we have zero automated tests on:
- Auth enforcement (the biggest regression risk — accidentally dropping a `Depends(require_api_key)` reopens the mutation surface)
- Webhook validation (the new `secret` field)
- Position CRUD (the rewritten accept_signal path + v2 endpoints)
- Frontend route existence (catching dead endpoint references before they ship)

These tests should be **fast, focused, and mockable** — no live database connections required. Use FastAPI's `TestClient` with dependency overrides to mock Postgres and Redis.

---

## Setup: Test infrastructure

### Add test dependencies

**File: `backend/requirements.txt`** — add if not already present:
```
pytest>=7.0
pytest-asyncio>=0.23.0
httpx>=0.26.0
```

(`httpx` is already there. `pytest` may be installed but not in requirements.)

### Create test config

**File: `backend/tests/conftest.py`**

```python
"""
Shared test fixtures for Pandora's Box backend tests.

All tests use FastAPI's TestClient with dependency overrides —
no live Postgres or Redis connections required.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set a test API key BEFORE any app imports read PIVOT_API_KEY
os.environ["PIVOT_API_KEY"] = "test-api-key-12345"
os.environ["TRADINGVIEW_WEBHOOK_SECRET"] = "test-webhook-secret"

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def test_api_key():
    return "test-api-key-12345"


@pytest.fixture(scope="module")
def webhook_secret():
    return "test-webhook-secret"


@pytest.fixture(scope="module")
def client():
    """
    Create a TestClient with mocked database dependencies.
    The app boots without real Postgres/Redis connections.
    """
    # Mock database modules before importing the app
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()
    mock_redis.scan_iter = MagicMock(return_value=AsyncIterator([]))

    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=0)
    mock_conn.execute = AsyncMock(return_value="UPDATE 0")
    mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))

    with patch("database.redis_client.get_redis_client", return_value=mock_redis), \
         patch("database.redis_client.get_redis_status", return_value={"status": "ok"}), \
         patch("database.postgres_client.get_postgres_client", return_value=mock_pool), \
         patch("database.postgres_client.init_database", new_callable=AsyncMock), \
         patch("api.watchlist.init_watchlist_table", new_callable=AsyncMock), \
         patch("bias_engine.factor_utils.purge_suspicious_cache_entries", new_callable=AsyncMock, return_value={"scanned": 0, "purged": 0}), \
         patch("webhooks.circuit_breaker.restore_circuit_breaker_state", new_callable=AsyncMock, return_value=False), \
         patch("scheduler.bias_scheduler.start_scheduler", new_callable=AsyncMock), \
         patch("websocket.broadcaster.manager"):

        from main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class AsyncIterator:
    """Helper to mock async iterators (scan_iter)."""
    def __init__(self, items):
        self.items = iter(items)
    def __aiter__(self):
        return self
    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration:
            raise StopAsyncIteration


class AsyncContextManager:
    """Helper to mock async context managers (pool.acquire)."""
    def __init__(self, value):
        self.value = value
    async def __aenter__(self):
        return self.value
    async def __aexit__(self, *args):
        pass
    def __call__(self):
        return self
```

**IMPORTANT:** The conftest mocking is tricky. If `TestClient` can't boot the app with these mocks, CC should adjust the patch targets. The goal is a client that can hit routes without live databases. If some mocks don't work perfectly, skip those tests and move on — partial coverage beats no coverage.

---

## Task 1: Auth enforcement tests

**File: `backend/tests/test_auth.py`**

These tests verify that all mutation routes return 401 without a valid API key and accept requests with a valid key.

```python
"""
Auth enforcement tests — verify all mutation routes require API key.
Regression protection for Phase 0B auth lockdown.
"""
import pytest


class TestAuthEnforcement:
    """Every POST/PATCH/DELETE mutation route must require auth."""

    # Routes that MUST return 401 without auth
    PROTECTED_ROUTES = [
        # Unified positions (Phase 0B)
        ("POST", "/api/v2/positions", {"ticker": "TEST", "entry_price": 100, "quantity": 1}),
        ("PATCH", "/api/v2/positions/POS_TEST_123", {"notes": "test"}),
        ("POST", "/api/v2/positions/POS_TEST_123/close", {"exit_price": 105}),
        ("DELETE", "/api/v2/positions/POS_TEST_123", None),
        ("POST", "/api/v2/positions/bulk", {"positions": []}),
        ("POST", "/api/v2/positions/reconcile", {"positions": []}),
        ("POST", "/api/v2/positions/mark-to-market", None),
        ("PATCH", "/api/v2/positions/account-balance", {"cash": 1000}),
        # Committee bridge (Phase 0B)
        ("POST", "/api/committee/results", {
            "signal_id": "test", "committee_run_id": "test",
            "action": "PASS", "conviction": "LOW"
        }),
    ]

    # Routes that MUST remain open (no auth)
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

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_no_auth_returns_401(self, client, method, path, body):
        """Mutation routes without API key must return 401."""
        if method == "POST":
            response = client.post(path, json=body) if body else client.post(path)
        elif method == "PATCH":
            response = client.patch(path, json=body) if body else client.patch(path)
        elif method == "DELETE":
            response = client.delete(path)
        else:
            pytest.fail(f"Unknown method: {method}")

        assert response.status_code == 401, (
            f"{method} {path} returned {response.status_code} without auth — "
            f"expected 401. Response: {response.text[:200]}"
        )

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_valid_x_api_key_accepted(self, client, test_api_key, method, path, body):
        """Mutation routes with valid X-API-Key should NOT return 401."""
        headers = {"X-API-Key": test_api_key}
        if method == "POST":
            response = client.post(path, json=body, headers=headers) if body else client.post(path, headers=headers)
        elif method == "PATCH":
            response = client.patch(path, json=body, headers=headers) if body else client.patch(path, headers=headers)
        elif method == "DELETE":
            response = client.delete(path, headers=headers)
        else:
            pytest.fail(f"Unknown method: {method}")

        # Should NOT be 401. May be 404/422/500 due to mocked DB, but not auth failure.
        assert response.status_code != 401, (
            f"{method} {path} returned 401 WITH valid API key — auth dependency may be broken"
        )

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_valid_bearer_accepted(self, client, test_api_key, method, path, body):
        """Mutation routes with valid Bearer token should NOT return 401."""
        headers = {"Authorization": f"Bearer {test_api_key}"}
        if method == "POST":
            response = client.post(path, json=body, headers=headers) if body else client.post(path, headers=headers)
        elif method == "PATCH":
            response = client.patch(path, json=body, headers=headers) if body else client.patch(path, headers=headers)
        elif method == "DELETE":
            response = client.delete(path, headers=headers)
        else:
            pytest.fail(f"Unknown method: {method}")

        assert response.status_code != 401, (
            f"{method} {path} returned 401 WITH valid Bearer token — auth dependency may be broken"
        )

    def test_wrong_key_returns_401(self, client):
        """Invalid API key should return 401."""
        response = client.post(
            "/api/v2/positions",
            json={"ticker": "TEST", "entry_price": 100, "quantity": 1},
            headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401

    @pytest.mark.parametrize("method,path", PUBLIC_ROUTES)
    def test_public_routes_no_auth_needed(self, client, method, path):
        """Read-only routes should work without auth."""
        response = client.get(path)
        # Should not be 401 or 403
        assert response.status_code not in (401, 403), (
            f"GET {path} returned {response.status_code} — public route should not require auth"
        )
```

## Task 2: Webhook validation tests

**File: `backend/tests/test_webhooks.py`**

```python
"""
Webhook validation tests — verify secret field enforcement.
Regression protection for Phase 0B webhook security.
"""
import pytest


class TestTradingViewWebhookSecret:
    """TradingView webhook endpoints must validate secret when configured."""

    WEBHOOK_ENDPOINTS = [
        ("/webhook/tradingview", {
            "ticker": "SPY",
            "strategy": "test",
            "direction": "LONG",
            "interval": "15",
            "price": "590.50",
        }),
    ]

    @pytest.mark.parametrize("path,payload", WEBHOOK_ENDPOINTS)
    def test_wrong_secret_rejected(self, client, path, payload):
        """Webhook with wrong secret should be rejected."""
        payload_with_bad_secret = {**payload, "secret": "wrong-secret"}
        response = client.post(path, json=payload_with_bad_secret)
        assert response.status_code == 401, (
            f"POST {path} with wrong secret returned {response.status_code} — expected 401"
        )

    @pytest.mark.parametrize("path,payload", WEBHOOK_ENDPOINTS)
    def test_correct_secret_accepted(self, client, webhook_secret, path, payload):
        """Webhook with correct secret should not return 401."""
        payload_with_secret = {**payload, "secret": webhook_secret}
        response = client.post(path, json=payload_with_secret)
        # May fail for other reasons (mocked DB) but NOT 401
        assert response.status_code != 401, (
            f"POST {path} with correct secret returned 401 — secret validation broken"
        )

    @pytest.mark.parametrize("path,payload", WEBHOOK_ENDPOINTS)
    def test_missing_secret_rejected(self, client, path, payload):
        """Webhook without secret field should be rejected when secret is configured."""
        response = client.post(path, json=payload)
        assert response.status_code == 401, (
            f"POST {path} without secret returned {response.status_code} — expected 401"
        )
```

## Task 3: Position CRUD tests

**File: `backend/tests/test_positions.py`**

```python
"""
Position CRUD tests — verify v2 endpoints respond correctly.
Regression protection for Phase 0C positions migration.

NOTE: These test route wiring and auth, not database behavior
(DB is mocked). For full integration tests, use a test database.
"""
import pytest


class TestPositionRoutes:
    """Verify v2 position endpoints are wired and respond."""

    def test_list_positions_returns_200(self, client):
        """GET /v2/positions should return 200 with positions array."""
        response = client.get("/api/v2/positions?status=OPEN")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        assert isinstance(data["positions"], list)

    def test_position_summary_returns_200(self, client):
        """GET /v2/positions/summary should return 200 with summary fields."""
        response = client.get("/api/v2/positions/summary")
        assert response.status_code == 200
        data = response.json()
        assert "position_count" in data
        assert "cash" in data

    def test_create_position_requires_auth(self, client):
        """POST /v2/positions without auth should return 401."""
        response = client.post("/api/v2/positions", json={
            "ticker": "AAPL",
            "entry_price": 175.50,
            "quantity": 1,
            "structure": "long_call",
            "expiry": "2026-04-17",
            "long_strike": 175,
        })
        assert response.status_code == 401

    def test_create_position_with_auth(self, client, test_api_key):
        """POST /v2/positions with auth should not return 401."""
        response = client.post("/api/v2/positions", json={
            "ticker": "AAPL",
            "entry_price": 175.50,
            "quantity": 1,
            "structure": "long_call",
            "expiry": "2026-04-17",
            "long_strike": 175,
        }, headers={"X-API-Key": test_api_key})
        # Won't be 401. Likely 500 (mocked DB) but that's fine — auth passed.
        assert response.status_code != 401

    def test_close_nonexistent_position(self, client, test_api_key):
        """POST /v2/positions/{id}/close for missing ID should return 404."""
        response = client.post(
            "/api/v2/positions/POS_FAKE_999/close",
            json={"exit_price": 180.0},
            headers={"X-API-Key": test_api_key}
        )
        # With mocked DB returning None, should be 404
        assert response.status_code in (404, 500)  # 404 preferred, 500 acceptable with mocks

    def test_delete_nonexistent_position(self, client, test_api_key):
        """DELETE /v2/positions/{id} for missing ID should return 404."""
        response = client.delete(
            "/api/v2/positions/POS_FAKE_999",
            headers={"X-API-Key": test_api_key}
        )
        assert response.status_code in (404, 500)


class TestLegacyRoutesRemoved:
    """Verify legacy position endpoints no longer exist (Phase 0C)."""

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
        """Legacy position routes should no longer exist."""
        if method == "GET":
            response = client.get(path)
        elif method == "POST":
            response = client.post(path, json={})
        else:
            pytest.fail(f"Unknown method: {method}")

        assert response.status_code in (404, 405, 422), (
            f"{method} {path} returned {response.status_code} — "
            f"legacy route should be gone (expected 404/405). Response: {response.text[:200]}"
        )
```

## Task 4: Frontend route smoke test

**File: `backend/tests/test_frontend_routes.py`**

```python
"""
Frontend route smoke test — verify every endpoint the UI calls actually exists.
Prevents dead endpoint references from shipping.

These are based on a grep of frontend/app.js for all fetch() calls.
"""
import pytest


class TestFrontendEndpointsExist:
    """Every endpoint the frontend calls should return a real response (not 404)."""

    # GET endpoints the frontend calls (from app.js grep)
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
    ]

    @pytest.mark.parametrize("path", FRONTEND_GET_ENDPOINTS)
    def test_endpoint_exists(self, client, path):
        """Frontend GET endpoint should return something other than 404."""
        response = client.get(path)
        assert response.status_code != 404, (
            f"GET {path} returned 404 — frontend calls this endpoint but it doesn't exist. "
            f"Either add the route or remove the frontend fetch() call."
        )


class TestFrontendDeadEndpointsGone:
    """Endpoints that were removed in Phase 0D should stay dead."""

    REMOVED_ENDPOINTS = [
        "/api/bias-auto/status",
        "/api/bias-auto/shift-status",
        "/api/bias-auto/CYCLICAL",
    ]

    @pytest.mark.parametrize("path", REMOVED_ENDPOINTS)
    def test_dead_endpoint_is_dead(self, client, path):
        """Removed endpoints should return 404 (not silently resurface)."""
        response = client.get(path)
        assert response.status_code == 404, (
            f"GET {path} returned {response.status_code} — this endpoint was removed in Phase 0D "
            f"and should not exist. Did someone accidentally re-add it?"
        )
```

---

## Task 5: Verify tests pass

After creating all test files, run:

```bash
cd backend && python -m pytest tests/ -v --tb=short
```

Expected outcome:
- All `test_scorer.py` tests still pass (existing 20 tests)
- Auth tests: protected routes return 401 without key, accept with key
- Webhook tests: wrong/missing secret rejected, correct secret accepted
- Position tests: v2 routes respond, legacy routes are gone
- Frontend routes: all endpoints the UI calls actually exist

**If some tests fail due to mocking issues**, that's expected — the conftest mocking is complex. CC should:
1. Fix simple mock issues (wrong patch target, missing mock method)
2. Skip tests that require deep database mocking with `@pytest.mark.skip(reason="needs DB mock fix")`
3. Do NOT spend more than 15 minutes debugging any single mock issue — partial coverage is fine

---

## Definition of Done

1. `backend/tests/conftest.py` exists with shared fixtures and mocked dependencies
2. `backend/tests/test_auth.py` — auth enforcement tests (401 without key, accepts with key, wrong key rejected)
3. `backend/tests/test_webhooks.py` — webhook secret validation tests
4. `backend/tests/test_positions.py` — v2 route wiring + legacy routes confirmed dead
5. `backend/tests/test_frontend_routes.py` — every frontend GET endpoint returns non-404
6. `pytest` and `pytest-asyncio` in requirements
7. `python -m pytest tests/ -v` passes (or has clear skip markers on known mock limitations)
8. Original 20 scorer tests still pass

---

## What this brief does NOT do

- Does NOT add full integration tests with a real database (that's a bigger effort)
- Does NOT test every endpoint in the app (just the sharp edges from Phase 0)
- Does NOT add CI/CD pipeline (future improvement — run tests on push)
- Does NOT test VPS scripts (no test framework for those yet)
- Does NOT test the bias engine computation (already has 20 scorer tests)

---

## Test philosophy

These tests are **regression guards**, not comprehensive coverage. They protect against the most likely regressions:
- Someone accidentally removes `Depends(require_api_key)` from a route
- Someone adds a new mutation route without auth
- Someone re-adds a legacy endpoint that was removed
- Someone adds a frontend fetch to an endpoint that doesn't exist
- Someone breaks the webhook secret validation

The pattern for each test is: **call the route, check the status code**. No complex assertion chains, no database state verification. Simple, fast, hard to break.

---

## Post-build checklist

1. All existing tests still pass: `cd backend && python -m pytest tests/test_scorer.py -v`
2. New tests pass: `cd backend && python -m pytest tests/ -v --tb=short`
3. Total test count should be 60+ (20 existing + ~40 new)
4. Push to main
5. Consider running tests locally before each future push (add to workflow)
