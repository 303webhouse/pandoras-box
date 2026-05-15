"""MCP FastAPI sub-app mounted at /mcp/v1/.

Implemented as an isolated `FastAPI()` instance so CORS middleware applied
here scopes to /mcp/v1/* routes only — the parent app's CORS is untouched
(AEGIS requirement: do not loosen CORS on existing hub endpoints).

Middleware order:
  1. CORS              (claude.ai + *.anthropic.com only)
  2. Bearer auth       (via Depends on every route)
  3. Rate limit        (per-token, mcp_ping exempt)
  4. Audit log         (record every call regardless of outcome)
  5. Tool dispatch     (invoke the registered handler)
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .audit import CallTimer, log_call
from .auth import verify_bearer
from .decorators import REGISTERED_TOOL_NAMES, get_registry
from .envelope import make_response
from .rate_limit import limiter

# Side-effect: importing tools registers every handler with the decorator
# registry. Must happen before the router serves a request.
from . import tools  # noqa: F401  pylint: disable=unused-import

logger = logging.getLogger(__name__)

# Anthropic MCP connector origins as of 2026-05. If Anthropic publishes
# additional origins, append to ALLOWED_ORIGINS (or extend the regex).
ALLOWED_ORIGINS = (
    "https://claude.ai",
    "https://www.claude.ai",
)
ALLOWED_ORIGIN_REGEX = r"https://([a-z0-9-]+\.)*anthropic\.com"


def _require_https(request: Request) -> None:
    """Reject plain HTTP. Railway's proxy sets X-Forwarded-Proto=https."""
    scheme = (
        request.headers.get("X-Forwarded-Proto")
        or request.headers.get("x-forwarded-proto")
        or request.url.scheme
    )
    if scheme.lower() != "https":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTTPS required for MCP requests",
        )


def build_mcp_app() -> FastAPI:
    """Construct the /mcp/v1 sub-application."""
    app = FastAPI(
        title="Pandora's Box Hub MCP",
        version="v1.0",
        docs_url=None,  # disable OpenAPI UI on the auth-gated app
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_origin_regex=ALLOWED_ORIGIN_REGEX,
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
        max_age=600,
    )

    @app.get("/health")
    async def mcp_health() -> dict:
        """Public health probe. Railway can hit this without auth."""
        return {"status": "ok", "service": "mcp/v1"}

    @app.post("/tools/{tool_name}")
    async def dispatch_tool(
        tool_name: str,
        request: Request,
        token: str = Depends(verify_bearer),
    ) -> JSONResponse:
        _require_https(request)

        if tool_name not in REGISTERED_TOOL_NAMES:
            return JSONResponse(
                status_code=404,
                content=make_response(
                    status="unavailable",
                    error=f"Unknown tool '{tool_name}'",
                    summary=f"Unknown tool '{tool_name}'.",
                ),
            )

        rate_error = limiter.check(token, tool_name)
        if rate_error is not None:
            envelope = make_response(
                status="unavailable",
                error=rate_error,
                summary="MCP: rate limit exceeded.",
            )
            log_call(
                request=request,
                tool_name=tool_name,
                parameters=None,
                response_status="unavailable",
                latency_ms=0.0,
                token=token,
            )
            return JSONResponse(status_code=429, content=envelope)

        registry = get_registry()
        registration = registry.get(tool_name)
        if registration is None:
            return JSONResponse(
                status_code=500,
                content=make_response(
                    status="unavailable",
                    error=f"Tool '{tool_name}' whitelisted but not registered",
                    summary="MCP: tool not loaded.",
                ),
            )

        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}

        # Pass only kwargs the handler accepts.
        handler = registration.handler
        sig = inspect.signature(handler)
        accepted = set(sig.parameters)
        kwargs = {k: v for k, v in body.items() if k in accepted}

        with CallTimer() as timer:
            try:
                result: Any = await handler(**kwargs)
            except TypeError as exc:
                log_call(
                    request=request,
                    tool_name=tool_name,
                    parameters=body,
                    response_status="unavailable",
                    latency_ms=timer.elapsed_ms,
                    token=token,
                )
                return JSONResponse(
                    status_code=400,
                    content=make_response(
                        status="unavailable",
                        error=f"Invalid parameters: {exc}",
                        summary="Invalid parameters.",
                    ),
                )
            except Exception:
                logger.exception("MCP tool '%s' raised", tool_name)
                log_call(
                    request=request,
                    tool_name=tool_name,
                    parameters=body,
                    response_status="unavailable",
                    latency_ms=timer.elapsed_ms,
                    token=token,
                )
                return JSONResponse(
                    status_code=500,
                    content=make_response(
                        status="unavailable",
                        error="Internal error executing tool",
                        summary="MCP: internal error.",
                    ),
                )

        response_status = (result or {}).get("status", "unavailable")
        log_call(
            request=request,
            tool_name=tool_name,
            parameters=body,
            response_status=response_status,
            latency_ms=timer.elapsed_ms,
            token=token,
        )
        return JSONResponse(status_code=200, content=result)

    return app


mcp_app = build_mcp_app()
