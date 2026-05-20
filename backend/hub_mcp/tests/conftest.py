"""Test fixtures for the MCP module.

The MCP module reads MCP_BEARER_TOKEN at request time, never at import,
so tests can set/unset it freely. Tool tests mock the read_only namespace
directly — no live Redis or Postgres needed.
"""

import os
import sys
from pathlib import Path

import pytest

# Add backend/ to sys.path so the MCP package imports resolve the same way
# they do under uvicorn (Procfile cd's into backend/ before launch).
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# OAuth env MUST be set before any test imports hub_mcp.server, because
# the FastMCP instance + OAuthProxy routes are built at import time. If
# OAuth env is missing, build_oauth_provider() returns None and the
# .well-known OAuth metadata routes are never registered, which makes
# tests that hit those endpoints fail with 404.
os.environ.setdefault("GITHUB_OAUTH_CLIENT_ID", "dummy-id-for-tests")
os.environ.setdefault("GITHUB_OAUTH_CLIENT_SECRET", "dummy-secret-for-tests")
os.environ.setdefault("MCP_ALLOWED_GITHUB_USERS", "test-user")
os.environ.setdefault("MCP_PUBLIC_BASE_URL", "http://localhost/mcp/v1/")


@pytest.fixture(autouse=True)
def _set_mcp_token(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "test-token-abc123")
