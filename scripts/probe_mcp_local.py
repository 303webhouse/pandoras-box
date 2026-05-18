#!/usr/bin/env python3
"""Local end-to-end MCP protocol probe.

Boots the hub_mcp ASGI app in-process (no live Railway), then drives the
JSON-RPC handshake exactly as Claude.ai's connector would:

  1. POST initialize     -> server returns InitializeResult + Mcp-Session-Id
  2. POST notifications/initialized
  3. POST tools/list     -> must list all 9 tools
  4. POST tools/call mcp_ping -> must return our envelope

Verifies the protocol layer is correct end-to-end without needing the live
deploy. Each step asserts on the response shape; failure prints the offending
response and exits non-zero.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure backend/ is on sys.path (Procfile cd's there at runtime).
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import os

os.environ.setdefault("MCP_BEARER_TOKEN", "probe-token-xyz")

# Importing the router builds the FastMCP app and registers all 9 tools.
from hub_mcp.router import mcp_app, mcp_lifespan  # noqa: E402

import httpx  # noqa: E402


async def probe() -> int:
    # FastMCP's session manager needs its lifespan active for the duration
    # of the probe. In production this runs inside the parent FastAPI app's
    # lifespan; here we drive it directly.
    async with mcp_lifespan(None):
        return await _drive(mcp_app)


async def _drive(mcp_app) -> int:
    transport = httpx.ASGITransport(app=mcp_app)
    headers_base = {
        "Authorization": f"Bearer {os.environ['MCP_BEARER_TOKEN']}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # 1) initialize
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "1.0"},
            },
        }
        r = await c.post("/", json=init_req, headers=headers_base)
        print(f"[1/4] initialize       -> HTTP {r.status_code}")
        if r.status_code != 200:
            print("  body:", r.text[:300])
            return 1
        session_id = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
        if not session_id:
            print("  WARNING: no Mcp-Session-Id header on InitializeResult")
        else:
            print(f"  Mcp-Session-Id: {session_id[:16]}...")
        # The response may be JSON or SSE; parse either.
        init_payload = _parse_response(r)
        if not init_payload or "result" not in init_payload:
            print("  unexpected initialize response:", init_payload)
            return 1
        result = init_payload["result"]
        print(f"  serverInfo: {result.get('serverInfo')}")
        print(f"  capabilities.tools: {result.get('capabilities', {}).get('tools') is not None}")

        sess_headers = dict(headers_base)
        if session_id:
            sess_headers["Mcp-Session-Id"] = session_id

        # 2) notifications/initialized
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        r = await c.post("/", json=notif, headers=sess_headers)
        print(f"[2/4] notifications/initialized -> HTTP {r.status_code}")
        if r.status_code not in (200, 202):
            print("  body:", r.text[:300])
            return 1

        # 3) tools/list
        list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        r = await c.post("/", json=list_req, headers=sess_headers)
        print(f"[3/4] tools/list       -> HTTP {r.status_code}")
        if r.status_code != 200:
            print("  body:", r.text[:300])
            return 1
        list_payload = _parse_response(r)
        tools = (list_payload or {}).get("result", {}).get("tools", [])
        names = sorted(t.get("name") for t in tools)
        print(f"  {len(names)} tools: {names}")
        expected = {
            "hub_get_bias_composite",
            "hub_get_flow_radar",
            "hub_get_sector_strength",
            "hub_get_hermes_alerts",
            "hub_get_hydra_scores",
            "hub_get_positions",
            "hub_get_portfolio_balances",
            "mcp_ping",
            "mcp_describe_tools",
        }
        if set(names) != expected:
            print(f"  MISMATCH; expected {sorted(expected)}")
            return 1

        # 4) tools/call mcp_ping
        call_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "mcp_ping", "arguments": {}},
        }
        r = await c.post("/", json=call_req, headers=sess_headers)
        print(f"[4/4] tools/call ping  -> HTTP {r.status_code}")
        if r.status_code != 200:
            print("  body:", r.text[:300])
            return 1
        call_payload = _parse_response(r)
        result = (call_payload or {}).get("result", {})
        content = result.get("content", [])
        # FastMCP wraps dict returns as structured content; envelope may be in
        # structuredContent or in content[0].text as JSON.
        envelope = result.get("structuredContent")
        if envelope is None and content:
            first = content[0]
            if first.get("type") == "text":
                try:
                    envelope = json.loads(first["text"])
                except (json.JSONDecodeError, KeyError):
                    envelope = None
        print(f"  envelope.status: {(envelope or {}).get('status')}")
        print(f"  envelope.schema_version: {(envelope or {}).get('schema_version')}")
        print(f"  envelope.summary: {(envelope or {}).get('summary', '')[:80]}")
        if not envelope or envelope.get("schema_version") != "v1.0":
            print("  envelope shape wrong")
            return 1

        print()
        print("OK: All 4 protocol steps passed.")
        return 0


def _parse_response(r: "httpx.Response") -> dict | None:
    """Parse a JSON or SSE-framed response body."""
    ct = r.headers.get("content-type", "")
    body = r.text
    if "application/json" in ct:
        try:
            return r.json()
        except json.JSONDecodeError:
            return None
    if "text/event-stream" in ct or body.startswith("event:") or "data:" in body:
        # Pull the first data: line.
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
    # Last resort: try JSON anyway.
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


if __name__ == "__main__":
    sys.exit(asyncio.run(probe()))
