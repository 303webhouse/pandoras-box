"""Tests for CORS handling on the MCP ASGI app.

Regression guard: the OPTIONS preflight on the protocol root MUST return
200/204 (not 405) or Claude.ai's browser-mediated connector flow fails
with a 405 forwarded through their /v1/toolbox/shttp/mcp/<uuid> proxy.
"""

import os

import httpx
import pytest


@pytest.fixture(scope="module", autouse=True)
def _oauth_env():
    """Provide dummy OAuth env so the provider builds at import time."""
    os.environ.setdefault("GITHUB_OAUTH_CLIENT_ID", "dummy-id")
    os.environ.setdefault("GITHUB_OAUTH_CLIENT_SECRET", "dummy-secret")
    os.environ.setdefault("MCP_ALLOWED_GITHUB_USERS", "test-user")
    os.environ.setdefault("MCP_PUBLIC_BASE_URL", "http://localhost/mcp/v1")


@pytest.mark.asyncio
async def test_options_preflight_returns_2xx_not_405():
    """The exact failure mode that broke Claude.ai connector: OPTIONS preflight
    on the protocol root must NOT return 405 (FastMCP's default for OPTIONS).
    CORSMiddleware should intercept and answer with 200/204."""
    from hub_mcp.router import mcp_app, mcp_lifespan

    async with mcp_lifespan(None):
        transport = httpx.ASGITransport(app=mcp_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
            r = await c.request(
                "OPTIONS",
                "/",
                headers={
                    "Origin": "https://claude.ai",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Authorization, Content-Type",
                },
            )
    assert r.status_code in (200, 204), f"OPTIONS preflight returned {r.status_code}"
    # Must echo CORS headers
    assert "access-control-allow-origin" in {k.lower() for k in r.headers}
    assert "access-control-allow-methods" in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_cors_origin_not_in_allowlist_rejected():
    """Origins outside the Anthropic/Claude.ai allowlist must NOT receive
    a permissive Access-Control-Allow-Origin echo."""
    from hub_mcp.router import mcp_app, mcp_lifespan

    async with mcp_lifespan(None):
        transport = httpx.ASGITransport(app=mcp_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
            r = await c.request(
                "OPTIONS",
                "/",
                headers={
                    "Origin": "https://evil.example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )
    # CORSMiddleware rejects the preflight (no allow-origin header echoed).
    aco = r.headers.get("access-control-allow-origin") or r.headers.get(
        "Access-Control-Allow-Origin"
    )
    assert aco != "https://evil.example.com"


@pytest.mark.asyncio
async def test_anthropic_subdomain_origin_allowed():
    """anthropic.com subdomains (api., console., etc.) must pass via the regex."""
    from hub_mcp.router import mcp_app, mcp_lifespan

    async with mcp_lifespan(None):
        transport = httpx.ASGITransport(app=mcp_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
            r = await c.request(
                "OPTIONS",
                "/",
                headers={
                    "Origin": "https://api.anthropic.com",
                    "Access-Control-Request-Method": "POST",
                },
            )
    assert r.status_code in (200, 204)
    aco = r.headers.get("access-control-allow-origin") or r.headers.get(
        "Access-Control-Allow-Origin"
    )
    assert aco == "https://api.anthropic.com"
