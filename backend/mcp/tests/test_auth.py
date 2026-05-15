"""Tests for backend/mcp/auth.py."""

import pytest
from fastapi import HTTPException, Request

from mcp.auth import verify_bearer


def _make_request(headers: dict) -> Request:
    """Build a minimal Starlette request with the given headers."""
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in headers.items()
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/v1/tools/mcp_ping",
        "headers": raw_headers,
        "query_string": b"",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_correct_token_passes(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "good-token")
    req = _make_request({"Authorization": "Bearer good-token"})
    token = await verify_bearer(req)
    assert token == "good-token"


@pytest.mark.asyncio
async def test_missing_header_returns_401(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "good-token")
    req = _make_request({})
    with pytest.raises(HTTPException) as exc:
        await verify_bearer(req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_malformed_header_returns_401(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "good-token")
    req = _make_request({"Authorization": "NotBearer good-token"})
    with pytest.raises(HTTPException) as exc:
        await verify_bearer(req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_returns_401(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "good-token")
    req = _make_request({"Authorization": "Bearer wrong-token"})
    with pytest.raises(HTTPException) as exc:
        await verify_bearer(req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_env_var_returns_500(monkeypatch):
    monkeypatch.delenv("MCP_BEARER_TOKEN", raising=False)
    req = _make_request({"Authorization": "Bearer anything"})
    with pytest.raises(HTTPException) as exc:
        await verify_bearer(req)
    assert exc.value.status_code == 500
