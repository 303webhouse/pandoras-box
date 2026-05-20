"""MCP ASGI app mounted at /mcp/v1/ on the parent FastAPI.

Architecture (v3 — OAuth migration):

    Parent FastAPI app
      └── mount("/mcp/v1", asgi_app)
            └── RateLimitMiddleware (429 on per-token quota; mcp_ping bypasses;
                key = Authorization header value, which after OAuth is
                FastMCP's own access token, before-OAuth would be the bearer)
                  └── AuditMiddleware (every request → audit logger)
                        └── FastMCP Streamable HTTP ASGI app
                              (auth = OAuthProxy(GitHub) + allowlisted
                              verifier; FastMCP owns the auth surface)

The bearer-auth middleware from v1/v2 is gone — Claude.ai's connector UI
only accepts OAuth, and FastMCP's OAuthProxy is now the authoritative auth
gate. Rate-limit + audit middleware stay because they're auth-scheme
agnostic (they hash whatever's in the Authorization header).

Tool registration: side-effect import of `hub_mcp.tools` triggers each
tool module to call `@mcp_tool(...)` which delegates to FastMCP. After
import, FastMCP knows all 9 tools.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from starlette.middleware.cors import CORSMiddleware

from .audit import CallTimer, log_call
from .rate_limit import EXEMPT_TOOLS, limiter
from .server import mcp

# Side-effect import: each tool module's @mcp_tool decorator runs at
# import time and registers with FastMCP. Must come after `mcp` is defined.
from . import tools  # noqa: F401  pylint: disable=unused-import

logger = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────

def _get_header(scope: dict, name: str) -> Optional[str]:
    """Extract a header value (case-insensitive) from an ASGI scope."""
    target = name.lower().encode("ascii")
    for k, v in scope.get("headers", []):
        if k.lower() == target:
            try:
                return v.decode("utf-8")
            except UnicodeDecodeError:
                return None
    return None


async def _send_json(send, status_code: int, body: dict) -> None:
    """Emit a complete ASGI HTTP response with JSON body."""
    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload, "more_body": False})


def _extract_bearer_from_scope(scope: dict) -> Optional[str]:
    """Extract the Authorization header value (post-'Bearer ' prefix).

    Used only as a rate-limit/audit key — actual auth is owned by FastMCP's
    OAuthProxy and happens inside the wrapped app.
    """
    header = _get_header(scope, "authorization")
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


# ─── Middleware: rate limit ─────────────────────────────────────────────

class RateLimitMiddleware:
    """Per-token rate-limit middleware.

    Keys off whatever's in the Authorization header (FastMCP-issued OAuth
    access token after the OAuth flow; pre-OAuth the upstream GitHub token
    during the handshake). Anonymous requests (no auth header — e.g. the
    OAuth metadata endpoint or OAuth callback) get keyed off the caller IP.

    Buffers the request body, peeks at the JSON-RPC method name to detect
    tools/call → tool name, then replays the body downstream. Skips the
    limit for tools in EXEMPT_TOOLS (currently just mcp_ping).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _extract_bearer_from_scope(scope)
        if not token:
            # Anonymous endpoints (OAuth metadata, callback, /.well-known/*).
            # Key off the caller IP so a misbehaving client still gets capped.
            client = scope.get("client") or ("unknown", 0)
            token = f"ip:{client[0]}"

        # Buffer request body so we can peek + replay.
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            msg = await receive()
            if msg["type"] == "http.request":
                chunk = msg.get("body", b"")
                if chunk:
                    body_chunks.append(chunk)
                more_body = msg.get("more_body", False)
            elif msg["type"] == "http.disconnect":
                return
        body = b"".join(body_chunks)

        tool_name = "<unknown>"
        try:
            parsed = json.loads(body) if body else {}
            if isinstance(parsed, dict):
                if parsed.get("method") == "tools/call":
                    tool_name = ((parsed.get("params") or {}).get("name")) or tool_name
                elif parsed.get("method"):
                    tool_name = parsed.get("method")
        except (ValueError, TypeError):
            pass

        if tool_name not in EXEMPT_TOOLS:
            err = limiter.check(token, tool_name)
            if err is not None:
                await _send_json(send, 429, {"error": err})
                return

        # Replay buffered body to downstream. After the body chunk is
        # delivered, the receive callable MUST block (not return disconnect)
        # — returning disconnect would make FastMCP abort the response cycle.
        import asyncio

        sent = False
        wait_event = asyncio.Event()

        async def receive_replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await wait_event.wait()
            return {"type": "http.disconnect"}

        scope["state"] = scope.get("state") or {}
        scope["state"]["mcp_token"] = token
        scope["state"]["rate_limited_tool"] = tool_name
        try:
            await self.app(scope, receive_replay, send)
        finally:
            wait_event.set()


# ─── Middleware: audit log ──────────────────────────────────────────────

class AuditMiddleware:
    """Audit-log every MCP HTTP request through pandoras_box.mcp.audit."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.get("state") or {}
        token = state.get("mcp_token")
        tool_name = state.get("rate_limited_tool") or "<unknown>"
        status_holder = {"status": "ok"}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                code = message.get("status", 200)
                if code >= 500 or code == 429:
                    status_holder["status"] = "unavailable"
                elif code >= 400:
                    status_holder["status"] = "degraded"
            await send(message)

        with CallTimer() as timer:
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                status_holder["status"] = "unavailable"
                raise
            finally:
                try:
                    from starlette.requests import Request

                    log_call(
                        request=Request(scope),
                        tool_name=tool_name,
                        parameters=None,
                        response_status=status_holder["status"],
                        latency_ms=timer.elapsed_ms,
                        token=token,
                    )
                except Exception:
                    logger.exception("Audit logging failed; continuing")


# ─── Public: build the mounted ASGI app ─────────────────────────────────

# FastMCP's StreamableHTTPSessionManager needs its lifespan run on the
# parent ASGI app. Construct the raw FastMCP starlette app here and
# expose its `.lifespan` for main.py to chain into the parent FastAPI
# lifespan. The middleware-wrapped variant is what we mount.
# stateless_http=False enables GET on the MCP endpoint (for server-initiated
# SSE streams per the Streamable HTTP spec). With stateless_http=True FastMCP
# rejects GET with 405 — Claude.ai's connector treats that as "unreachable"
# and aborts the handshake. The session manager's task group lifespan is
# chained into the parent FastAPI app via mcp_lifespan in backend/main.py,
# so stateful mode is safe.
fastmcp_app = mcp.http_app(path="/", transport="http", stateless_http=False)


def build_mcp_asgi_app():
    """Wrap the FastMCP app with our middleware chain.

    Outermost → innermost: CORS → RateLimit → Audit → FastMCP.

    CORS is the OUTERMOST layer so OPTIONS preflight requests get answered
    immediately by CORSMiddleware (200 OK with the right Access-Control-*
    headers) — they never reach FastMCP, which would return 405 for OPTIONS
    on the protocol root and break Claude.ai's browser-mediated handshake.

    Auth is owned by FastMCP's OAuthProxy (configured in hub_mcp/server.py).
    Our middleware only adds CORS, rate-limiting, and audit-logging.
    """
    app = AuditMiddleware(fastmcp_app)
    app = RateLimitMiddleware(app)
    # Anthropic / Claude.ai origins. allow_origin_regex catches anthropic.com
    # subdomains (api.anthropic.com, console.anthropic.com, etc.) without
    # listing each one. allow_credentials=False because we're bearer-auth
    # only — no cookies.
    app = CORSMiddleware(
        app,
        allow_origins=["https://claude.ai", "https://www.claude.ai"],
        allow_origin_regex=r"https://([a-z0-9-]+\.)*anthropic\.com",
        allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "MCP-Protocol-Version",
            "MCP-Session-Id",
            "Last-Event-ID",
        ],
        expose_headers=["MCP-Session-Id"],
        allow_credentials=False,
        max_age=600,
    )
    return app


mcp_app = build_mcp_asgi_app()
mcp_lifespan = fastmcp_app.router.lifespan_context
