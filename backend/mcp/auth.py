"""Bearer-token authentication middleware for the MCP server.

Verifies `Authorization: Bearer <token>` against MCP_BEARER_TOKEN env var
using constant-time comparison (secrets.compare_digest) — AEGIS Pass 1
requirement.

Behavior:
  - Missing/malformed header                  -> 401
  - Bearer token mismatch                     -> 401
  - MCP_BEARER_TOKEN env var unset            -> 500 (server misconfigured)
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

ENV_VAR = "MCP_BEARER_TOKEN"


def _extract_bearer(request: Request) -> Optional[str]:
    """Return the bearer token from the Authorization header, or None."""
    header = request.headers.get("Authorization") or request.headers.get(
        "authorization"
    )
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


async def verify_bearer(request: Request) -> str:
    """FastAPI dependency. Raises HTTPException on auth failure.

    Returns the verified token (so downstream handlers can hash it for
    audit logs / rate limit keys).
    """
    expected = os.environ.get(ENV_VAR)
    if not expected:
        logger.critical(
            "MCP server misconfigured: %s env var is not set", ENV_VAR
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MCP server misconfigured",
        )

    presented = _extract_bearer(request)
    if not presented:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )

    # Constant-time comparison; reject quickly without leaking token length.
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )

    return presented
