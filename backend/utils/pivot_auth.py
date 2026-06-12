"""
Pivot auth — accepts EITHER a browser session cookie OR the machine X-API-Key/Bearer header.

Injected on all ~95 mutation routes via Depends(require_api_key), so this one function
covers the whole protected surface. The browser dashboard uses the session cookie (so the
powerful PIVOT_API_KEY no longer ships to the client); VPS / server-to-server callers keep
using X-API-Key / Authorization: Bearer unchanged.
"""

from __future__ import annotations

import hmac
import os
from fastapi import Header, HTTPException, Request

from utils.session import COOKIE_NAME, verify_session

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY") or ""
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    """
    Accept either of:
      1. Machine header auth — X-API-Key or `Authorization: Bearer` == PIVOT_API_KEY.
         CSRF-exempt (server-to-server callers, not browsers). Constant-time compared.
      2. Browser session — a valid signed `pivot_session` cookie. Session-authed *mutations*
         must ALSO carry `X-Requested-With: XMLHttpRequest` (CSRF defense; layered on
         same-origin + SameSite=Lax).
    Fail-closed: anything else → 401.
    """
    # 1) Machine header auth (unchanged behavior for VPS callers)
    if PIVOT_API_KEY:
        if x_api_key and hmac.compare_digest(x_api_key, PIVOT_API_KEY):
            return x_api_key
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1].strip()
            if hmac.compare_digest(token, PIVOT_API_KEY):
                return token

    # 2) Browser session cookie
    if verify_session(request.cookies.get(COOKIE_NAME)):
        if request.method in _MUTATING and request.headers.get("x-requested-with") != "XMLHttpRequest":
            raise HTTPException(status_code=403, detail="Missing CSRF header")
        return "session"

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# Keep old names as aliases so existing imports don't break
verify_pivot_key = require_api_key
verify_api_key = require_api_key
