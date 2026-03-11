"""
Shared test fixtures for Pandora's Box backend tests.
All tests use FastAPI's TestClient with dependency overrides —
no live Postgres or Redis connections required.

Phase 0G — test infrastructure.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set env vars BEFORE any app code is imported
os.environ["PIVOT_API_KEY"] = "test-api-key-12345"
os.environ["TRADINGVIEW_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["POLYGON_API_KEY"] = "test-polygon-key"
os.environ["FRED_API_KEY"] = "test-fred-key"

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

class AsyncIterator:
    """Async iterator wrapper for mocking redis scan_iter etc."""
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
    """Async context manager wrapper for mocking pool.acquire()."""
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        pass

    def __call__(self):
        return self


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_api_key():
    return "test-api-key-12345"


@pytest.fixture(scope="module")
def webhook_secret():
    return "test-webhook-secret"


@pytest.fixture(scope="module")
def client():
    # --- Mock Redis ---
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.scan_iter = MagicMock(return_value=AsyncIterator([]))
    mock_redis.ping = AsyncMock(return_value=True)

    # --- Mock Postgres pool ---
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=0)
    mock_conn.execute = AsyncMock(return_value="UPDATE 0")
    mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
    mock_pool.close = AsyncMock()

    patches = [
        patch("database.redis_client.get_redis_client", new_callable=AsyncMock, return_value=mock_redis),
        patch("database.redis_client.get_redis_status", return_value={"status": "ok", "consecutive_errors": 0}),
        patch("database.postgres_client.get_postgres_client", new_callable=AsyncMock, return_value=mock_pool),
        patch("database.postgres_client.init_database", new_callable=AsyncMock),
        patch("api.watchlist.init_watchlist_table", new_callable=AsyncMock),
        patch("bias_engine.factor_utils.purge_suspicious_cache_entries", new_callable=AsyncMock, return_value={"scanned": 0, "purged": 0}),
        patch("webhooks.circuit_breaker.restore_circuit_breaker_state", new_callable=AsyncMock, return_value=False),
        patch("scheduler.bias_scheduler.start_scheduler", new_callable=AsyncMock),
        patch("websocket.broadcaster.manager", MagicMock(active_connections=set())),
    ]

    for p in patches:
        p.start()

    from main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    for p in patches:
        p.stop()
