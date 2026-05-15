"""Audit logging for the MCP server.

Every tool call is logged through `pandoras_box.mcp.audit` with the fields
specified in the implementation brief. Full tokens and raw parameter values
are NEVER logged — both are SHA-256 truncated to 8 hex chars.

The logger uses the existing Railway logging setup; no new infrastructure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from fastapi import Request

logger = logging.getLogger("pandoras_box.mcp.audit")


def _hash_short(value: str) -> str:
    """SHA-256 of value, truncated to 8 hex chars."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def hash_parameters(parameters: Mapping[str, Any]) -> str:
    """Stable hash of a parameters dict (JSON, sorted keys)."""
    if not parameters:
        return _hash_short("{}")
    try:
        canonical = json.dumps(parameters, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = repr(parameters)
    return _hash_short(canonical)


def hash_token(token: str) -> str:
    """SHA-256 of bearer token, truncated to 8 hex chars."""
    return _hash_short(token)


def _caller_ip(request: Request) -> str:
    """Resolve the caller's IP, preferring X-Forwarded-For (Railway proxy)."""
    xff = request.headers.get("X-Forwarded-For") or request.headers.get(
        "x-forwarded-for"
    )
    if xff:
        return xff.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def log_call(
    *,
    request: Request,
    tool_name: str,
    parameters: Optional[Mapping[str, Any]],
    response_status: str,
    latency_ms: float,
    token: Optional[str] = None,
) -> None:
    """Emit a single structured-ish line to the audit logger."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "parameters_hash": hash_parameters(parameters or {}),
        "response_status": response_status,
        "latency_ms": round(latency_ms, 2),
        "caller_ip": _caller_ip(request),
        "token_hash": hash_token(token) if token else "anonymous",
    }
    # Single-line so log aggregation parses cleanly.
    logger.info("mcp_call %s", json.dumps(payload))


class CallTimer:
    """Context manager: measure elapsed ms for log_call()."""

    __slots__ = ("_t0", "elapsed_ms")

    def __enter__(self) -> "CallTimer":
        self._t0 = time.perf_counter()
        self.elapsed_ms = 0.0
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.elapsed_ms = (time.perf_counter() - self._t0) * 1000.0
