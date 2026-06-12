"""
Dashboard session — stateless HMAC-signed cookie (no server-side store).

Lets the browser dashboard authenticate without ever shipping the powerful
PIVOT_API_KEY to the client. Machine callers (VPS) keep using X-API-Key/Bearer
(see utils/pivot_auth.py) — this module is browser-only.

Design (locked 2026-06-11, security session; full review deferred to Fable):
  - Stateless: token = base64url(json{sub,iat}) + "." + base64url(HMAC-SHA256).
    No Redis dependency (Upstash flapped repeatedly this week).
  - Revoke-all lever: rotate DASHBOARD_SESSION_SECRET → every issued cookie invalid.
  - Fixed TTL (default 14 days); re-login after expiry.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

SESSION_SECRET = os.getenv("DASHBOARD_SESSION_SECRET") or ""
SESSION_TTL_SECONDS = int(os.getenv("DASHBOARD_SESSION_TTL_SECONDS") or 14 * 24 * 3600)
COOKIE_NAME = "pivot_session"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(body: str) -> str:
    return _b64e(hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).digest())


def issue_session(subject: str = "dashboard") -> Optional[str]:
    """Signed session token, or None if no signing secret is configured (fail-closed)."""
    if not SESSION_SECRET:
        return None
    body = _b64e(
        json.dumps({"sub": subject, "iat": int(time.time())}, separators=(",", ":")).encode()
    )
    return f"{body}.{_sign(body)}"


def verify_session(token: Optional[str]) -> bool:
    """True only for a well-formed, correctly-signed, non-expired token. Fail-closed."""
    if not token or not SESSION_SECRET:
        return False
    try:
        body, sig = token.split(".", 1)
    except (ValueError, AttributeError):
        return False
    if not hmac.compare_digest(sig, _sign(body)):
        return False
    try:
        payload = json.loads(_b64d(body))
        iat = float(payload.get("iat", 0))
    except Exception:
        return False
    return iat > 0 and (time.time() - iat) <= SESSION_TTL_SECONDS
