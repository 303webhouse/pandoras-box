"""
Pivot API key authentication helper.
"""

from __future__ import annotations

import os
from fastapi import Header, HTTPException


def verify_pivot_key(authorization: str | None = Header(default=None)) -> str:
    """Validate Pivot's Bearer token header."""
    expected = os.getenv("PIVOT_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="PIVOT_API_KEY not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return token
