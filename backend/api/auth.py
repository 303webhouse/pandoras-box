"""
Dashboard login/logout — issues / clears the HttpOnly session cookie.

These endpoints are intentionally UNAUTHENTICATED (login can't require a session —
that's circular). They're allowlisted in tests/test_auth.py::AUTH_EXEMPT_MUTATIONS.
Browser sessions replace the embedded PIVOT_API_KEY; machine callers are unaffected.
"""
from __future__ import annotations

import hmac
import logging
import os

from fastapi import APIRouter, Body, HTTPException, Request, Response

from utils.session import COOKIE_NAME, SESSION_TTL_SECONDS, issue_session, verify_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD") or ""


@router.post("/auth/login")
async def login(response: Response, payload: dict = Body(default=None)):
    """Verify the shared dashboard password → set an HttpOnly session cookie."""
    if not DASHBOARD_PASSWORD:
        raise HTTPException(status_code=503, detail="Dashboard auth not configured")
    supplied = str((payload or {}).get("password") or "")
    if not supplied or not hmac.compare_digest(supplied, DASHBOARD_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = issue_session()
    if not token:
        raise HTTPException(status_code=503, detail="Session secret not configured")
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    logger.info("Dashboard session issued")
    return {"status": "ok"}


@router.post("/auth/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/auth/session")
async def session_status(request: Request):
    """Lightweight check the frontend calls on load to decide whether to show login."""
    return {"authenticated": verify_session(request.cookies.get(COOKIE_NAME))}
