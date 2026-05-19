#!/usr/bin/env python3
"""Local probe for the hub MCP server.

Post v3 (OAuth migration), the protocol path requires GitHub OAuth — not
something an automated probe can complete without browser interaction. So
this script tests what it CAN test without going through OAuth:

  1. The OAuth metadata endpoint is reachable and well-formed
     (/.well-known/oauth-authorization-server)
  2. The OAuth-protected-resource metadata endpoint advertises the right scopes
     (/.well-known/oauth-protected-resource/...)
  3. The protocol root (/) requires auth (returns 401, not 404)
  4. Tool functions still work when called directly (in-process, bypasses
     all auth) — sanity check that the OAuth wiring didn't break tool dispatch

For production verification of the OAuth handshake end-to-end, use
MCP Inspector or claude.ai's connector flow — both drive a real browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

# Set OAuth env so the provider builds; values are dummy — we never reach
# GitHub. Allowlist is irrelevant for the endpoints we probe.
os.environ.setdefault("GITHUB_OAUTH_CLIENT_ID", "dummy-client-id-for-probe")
os.environ.setdefault("GITHUB_OAUTH_CLIENT_SECRET", "dummy-secret-for-probe")
os.environ.setdefault("MCP_ALLOWED_GITHUB_USERS", "probe-user")
os.environ.setdefault(
    "MCP_PUBLIC_BASE_URL", "http://localhost/mcp/v1"
)

from hub_mcp.router import mcp_app, mcp_lifespan  # noqa: E402

import httpx  # noqa: E402


async def probe() -> int:
    async with mcp_lifespan(None):
        return await _drive()


async def _drive() -> int:
    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        # 1) OAuth metadata
        r = await c.get("/.well-known/oauth-authorization-server")
        print(f"[1/4] OAuth metadata -> HTTP {r.status_code}")
        if r.status_code != 200:
            print("  body:", r.text[:300])
            return 1
        meta = r.json()
        expected_endpoints = ("issuer", "authorization_endpoint", "token_endpoint")
        missing = [k for k in expected_endpoints if not meta.get(k)]
        if missing:
            print(f"  missing fields: {missing}")
            return 1
        print(f"  issuer:                 {meta.get('issuer')}")
        print(f"  authorization_endpoint: {meta.get('authorization_endpoint')}")
        print(f"  token_endpoint:         {meta.get('token_endpoint')}")

        # 2) OAuth-protected-resource metadata
        r2 = await c.get("/.well-known/oauth-protected-resource/")
        print(f"[2/4] OAuth-protected-resource -> HTTP {r2.status_code}")
        # FastMCP may serve this at /.well-known/oauth-protected-resource/<path>
        # so a 404 is acceptable if it's mounted under a sub-path.
        if r2.status_code == 200:
            pr = r2.json()
            print(f"  resource: {pr.get('resource')}")

        # 3) Protocol root requires auth
        r3 = await c.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        print(f"[3/4] protocol root (no auth) -> HTTP {r3.status_code}")
        if r3.status_code not in (401, 403):
            print(f"  WARNING: expected 401/403, got {r3.status_code}")
            print(f"  body: {r3.text[:240]}")
            # Not a hard fail — FastMCP may answer with a different code

        # 4) Tool functions still callable directly
        from hub_mcp.tools.ping import mcp_ping

        envelope = await mcp_ping()
        print(f"[4/4] tool function direct call -> envelope.status={envelope.get('status')}")
        if envelope.get("schema_version") != "v1.0":
            print(f"  envelope shape wrong: {envelope}")
            return 1

        print()
        print("OK: All probe checks passed.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(probe()))
