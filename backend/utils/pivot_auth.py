"""
Pivot API key authentication.
Accepts either X-API-Key or Authorization: Bearer <key>.
Used as a FastAPI dependency on all mutation routes.
"""

from __future__ import annotations

import os
from fastapi import Header, HTTPException

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY") or ""


def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    """Validate API key from either X-API-Key or Authorization: Bearer header."""
    if not PIVOT_API_KEY:
        raise HTTPException(status_code=503, detail="PIVOT_API_KEY not configured")

    # Check X-API-Key first (frontend, some VPS callers)
    if x_api_key and x_api_key == PIVOT_API_KEY:
        return x_api_key

    # Check Authorization: Bearer (VPS committee bridge, Pivot bot)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token == PIVOT_API_KEY:
            return token

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# Keep old names as aliases so existing imports don't break
verify_pivot_key = require_api_key
verify_api_key = require_api_key
