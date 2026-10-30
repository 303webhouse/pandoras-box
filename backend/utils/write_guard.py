"""R-IV.1446(d): one app-wide guard on every write request.

Every request whose method is not GET, HEAD or OPTIONS must carry the same credential
`require_api_key` accepts -- the PIVOT key (X-API-Key or Bearer) or a signed session cookie with
the CSRF header -- unless its path is on ALLOWLIST below. Until now each route carried its own
check, and a route that forgot one had none; this puts one check in front of all of them.

TWO MODES, chosen per request by the `WRITE_GUARD_MODE` variable:
  * anything but "enforce" (the default, and unset) -> LOG ONLY: the request goes through, and
    what the guard WOULD have refused is recorded in `write_guard_events`.
  * "enforce" -> refused with 401 before any handler runs. Setting it is a deploy.

What a record holds: when, method, path (query string dropped -- a query can carry a secret),
the source address as Railway passes it (X-Forwarded-For), the proxy's own address, the user
agent, the Origin, and WHICH credential was missing or wrong. Never a credential's value.

The alert hooks are on the allowlist because their senders cannot carry a session or the key;
each checks its own secret, switched separately (WEBHOOK_*_ENFORCE). Their requests are
recorded as `hook_seen`, sources only, a bounded sample per day, so a hook's real sender can be
shown by address before its own switch is turned on.

R-IV.1456(e)3, THE SOURCE CHECK: every hook TradingView sends to is also checked by where the
request came from. A request whose real source address (X-Real-IP, which Railway overwrites --
a client-supplied value does not survive, measured 2026-10-30 18:07 UTC) is not one of
TradingView's four published webhook addresses is recorded as `source_unlisted`. It refuses
nothing until `WEBHOOK_SOURCE_CHECK` is "enforce" (a deploy, on SPINE's go).

R-IV.1456(c)2, THE CONSENT FORM: /mcp/v1/consent is NOT on the allowlist. It needs Nick's signed-in
session, and a session cookie alone is enough there: the form is a plain HTML POST that cannot
add the CSRF header, it carries FastMCP's own double-submit CSRF token, and the session cookie
is SameSite=Lax, so a cross-site POST never carries it.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

#: Methods that never write. OPTIONS is the CORS preflight: browsers send it without
#: credentials by specification, and no route in this app handles OPTIONS itself (the
#: route-table test proves that), so refusing it would break CORS and protect nothing.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: path -> (group, why it is public). Exact paths: a trailing-slash variant is NOT covered
#: unless it is listed itself.
ALLOWLIST: Dict[str, Tuple[str, str]] = {
    # ── sign-in ──────────────────────────────────────────────────────────────────────────
    "/api/auth/login": ("signin", "issues the session: the caller has none yet; the handler "
                                  "checks the dashboard password"),
    "/api/auth/logout": ("signin", "clears the caller's own session cookie; changes nothing else"),
    # ── MCP sign-in (OAuth). Clients call these BEFORE they hold any credential. ────────
    "/register": ("mcp_signin", "MCP client registration (OAuth DCR) at the host root, which "
                                "Claude.ai calls before it has a token"),
    "/mcp/v1/register": ("mcp_signin", "the same registration under the MCP mount"),
    "/mcp/v1/token": ("mcp_signin", "OAuth token exchange: trades a one-time GitHub-approved "
                                    "code for a token, so it cannot require one"),
    "/mcp/v1/authorize": ("mcp_signin", "OAuth authorize step (FastMCP accepts POST here); "
                                        "starts the GitHub sign-in"),
    # ── the MCP protocol itself: FastMCP's OAuthProxy refuses a missing or invalid bearer
    #    with 401 on every call (measured: unauthenticated POSTs to /mcp/v1 get 401). ─────
    "/mcp/v1": ("mcp_own_auth", "MCP tool calls; FastMCP checks its own GitHub-OAuth bearer "
                                "and answers 401 without one"),
    "/mcp/v1/": ("mcp_own_auth", "the same endpoint with the trailing slash (the mount root)"),
    # ── alert hooks: TradingView cannot send a session or the key; each checks its own
    #    shared secret, enforced by its own switch. ──────────────────────────────────────
    "/webhook/tradingview": ("hook", "TradingView strategy alerts; own secret, WEBHOOK_TV_ENFORCE"),
    "/webhook/breadth": ("hook", "TradingView breadth feed; own secret, WEBHOOK_BREADTH_ENFORCE"),
    "/webhook/tick": ("hook", "TradingView TICK feed; own secret, WEBHOOK_TICK_ENFORCE"),
    "/webhook/circuit_breaker": ("hook", "TradingView circuit-breaker alerts; own secret, "
                                         "WEBHOOK_CB_ENFORCE"),
    "/webhook/whale": ("hook", "TradingView whale alerts; own secret, WEBHOOK_WHALE_ENFORCE"),
    "/webhook/footprint": ("hook", "TradingView footprint alerts; own secret, "
                                   "WEBHOOK_FOOTPRINT_ENFORCE"),
    "/api/webhook/hermes": ("hook", "HERMES alerts; own secret, WEBHOOK_HERMES_ENFORCE"),
    "/api/webhook/pythia": ("hook", "PYTHIA market-profile alerts; own secret, "
                                    "WEBHOOK_PYTHIA_ENFORCE"),
    "/webhook/mp_levels": ("hook", "PYTHIA level sheet; own secret, ALREADY refused when wrong "
                                   "(no observe mode)"),
}

#: path -> why. Writes here need Nick's session, but the session cookie ALONE is enough (no CSRF
#: header): see the module docstring.
SESSION_FORM_PATHS: Dict[str, str] = {
    "/mcp/v1/consent": "the OAuth consent form Nick approves in his browser when Claude.ai "
                       "connects; a plain HTML form with its own double-submit CSRF token",
}

_CONSENT_REFUSAL_BODY = json.dumps({
    "detail": "Sign in to the hub in this browser first, then approve the connection again."
}).encode()

#: R-IV.1456(e)3: TradingView's published webhook source addresses (support article
#: 43000529348, "How to configure webhook alerts").
TRADINGVIEW_ADDRESSES = frozenset({
    "52.89.214.238", "34.212.75.30", "54.218.53.128", "52.32.178.7",
})
SOURCE_CHECK_ENV = "WEBHOOK_SOURCE_CHECK"

MODE_ENV = "WRITE_GUARD_MODE"

#: Per process, per UTC day. Past these, events are only counted (a flood must not become a
#: flood of database writes).
MAX_RECORDS_PER_DAY = 3000
MAX_HOOK_SAMPLES_PER_PATH_PER_DAY = 50

_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS write_guard_events ("
    "  id BIGSERIAL PRIMARY KEY,"
    "  at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
    "  kind TEXT NOT NULL,"
    "  mode TEXT NOT NULL,"
    "  method TEXT NOT NULL,"
    "  path TEXT NOT NULL,"
    "  credential TEXT,"
    "  forwarded_for TEXT,"
    "  real_ip TEXT,"
    "  proxy_addr TEXT,"
    "  user_agent TEXT,"
    "  origin TEXT,"
    "  build TEXT)"
)


def mode() -> str:
    return "enforce" if (os.getenv(MODE_ENV) or "").strip().lower() == "enforce" else "log"


def allowlisted(path: str) -> Optional[Tuple[str, str]]:
    return ALLOWLIST.get(path)


def source_mode() -> str:
    """The hook source check: "enforce" only on that exact value; anything else logs."""
    return ("enforce" if (os.getenv(SOURCE_CHECK_ENV) or "").strip().lower() == "enforce"
            else "log")


def source_address(headers) -> str:
    """The request's real source: X-Real-IP (Railway sets it and overwrites a client's), else
    the first X-Forwarded-For hop. Empty when neither is present."""
    real = (headers.get("x-real-ip") or "").strip()
    if real:
        return real
    return (headers.get("x-forwarded-for") or "").split(",")[0].strip()


def source_is_tradingview(headers) -> bool:
    return source_address(headers) in TRADINGVIEW_ADDRESSES


def classify_credential(method: str, headers, cookies) -> str:
    """The credential `require_api_key` would accept, or why it would not.

    Returns "key" or "session" when accepted; otherwise one of "none", "key_wrong",
    "bearer_wrong", "session_invalid", "session_without_csrf_header". Mirrors
    utils.pivot_auth.require_api_key exactly (a test holds the two together).
    """
    from utils import pivot_auth
    from utils.session import COOKIE_NAME, verify_session

    key = pivot_auth.PIVOT_API_KEY
    x_api_key = headers.get("x-api-key")
    authorization = headers.get("authorization") or ""
    tried = []
    if key:
        if x_api_key:
            if hmac.compare_digest(x_api_key, key):
                return "key"
            tried.append("key_wrong")
        if authorization.startswith("Bearer "):
            if hmac.compare_digest(authorization.split(" ", 1)[1].strip(), key):
                return "key"
            tried.append("bearer_wrong")
    elif x_api_key or authorization.startswith("Bearer "):
        tried.append("key_wrong")
    raw_cookie = cookies.get(COOKIE_NAME)
    if verify_session(raw_cookie):
        if method in pivot_auth._MUTATING and headers.get("x-requested-with") != "XMLHttpRequest":
            return "session_without_csrf_header"
        return "session"
    if raw_cookie:
        tried.append("session_invalid")
    return tried[0] if tried else "none"


# ── recording ─────────────────────────────────────────────────────────────────────────────

_day: Optional[str] = None
_recorded = 0
_dropped = 0
_hook_samples: Dict[str, int] = {}
_table_ready = False
counts: Dict[str, int] = {}


def _roll_day() -> None:
    global _day, _recorded, _dropped, _hook_samples
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _day:
        _day, _recorded, _dropped, _hook_samples = today, 0, 0, {}


def _clip(v: Optional[str], n: int) -> Optional[str]:
    if v is None:
        return None
    return str(v)[:n]


def build_event(kind: str, scope, headers, credential: Optional[str]) -> dict:
    client = scope.get("client") or ("", 0)
    return {
        "kind": kind,
        "mode": mode(),
        "method": scope.get("method", ""),
        "path": _clip(scope.get("path", ""), 200),
        "credential": credential,
        "forwarded_for": _clip(headers.get("x-forwarded-for"), 300),
        "real_ip": _clip(headers.get("x-real-ip"), 64),
        "proxy_addr": _clip(client[0] if client else "", 64),
        "user_agent": _clip(headers.get("user-agent"), 200),
        "origin": _clip(headers.get("origin"), 200),
        "build": _clip(os.getenv("RAILWAY_GIT_COMMIT_SHA") or "", 12),
    }


async def _insert(event: dict) -> None:
    """Never raises: a supervision write must never break the request it supervises."""
    global _table_ready
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            if not _table_ready:
                await conn.execute(_TABLE_SQL)
                _table_ready = True
            await conn.execute(
                "INSERT INTO write_guard_events (kind, mode, method, path, credential, "
                "forwarded_for, real_ip, proxy_addr, user_agent, origin, build) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                event["kind"], event["mode"], event["method"], event["path"],
                event["credential"], event["forwarded_for"], event["real_ip"],
                event["proxy_addr"], event["user_agent"], event["origin"], event["build"])
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[write_guard] event not recorded: %s", type(exc).__name__)


def record(event: dict) -> None:
    """Count always; write a row while under the day's caps. Never raises."""
    global _recorded, _dropped
    try:
        _roll_day()
        counts[event["kind"]] = counts.get(event["kind"], 0) + 1
        if event["kind"] == "hook_seen":
            n = _hook_samples.get(event["path"], 0)
            if n >= MAX_HOOK_SAMPLES_PER_PATH_PER_DAY:
                return
            _hook_samples[event["path"]] = n + 1
        else:
            logger.warning("[write_guard] %s %s %s credential=%s ua=%s",
                           event["kind"].upper(),
                           event["method"], event["path"], event["credential"],
                           (event["user_agent"] or "")[:60])
        if _recorded >= MAX_RECORDS_PER_DAY:
            _dropped += 1
            if _dropped % 100 == 1:
                logger.warning("[write_guard] daily record cap reached; %d events counted only",
                               _dropped)
            return
        _recorded += 1
        # Off only in the test suite (tests/conftest.py), whose mocked pools must not see
        # extra writes; production never sets it.
        if (os.getenv("WRITE_GUARD_RECORD") or "").strip().lower() == "off":
            return
        asyncio.ensure_future(_insert(event))
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("[write_guard] record failed: %s", type(exc).__name__)


# ── the middleware ────────────────────────────────────────────────────────────────────────

_REFUSAL_BODY = json.dumps({"detail": "Invalid or missing API key"}).encode()


class WriteGuardMiddleware:
    """Pure ASGI, so streamed responses (the MCP's) pass through untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method", "GET") in SAFE_METHODS:
            return await self.app(scope, receive, send)

        from starlette.requests import Request
        req = Request(scope)
        headers = req.headers
        path = scope.get("path", "")
        listed = allowlisted(path)
        if listed is not None:
            if listed[0] == "hook":
                # R-IV.1456(e)3: by source first. Its own secret check still runs after this.
                if source_is_tradingview(headers):
                    record(build_event("hook_seen", scope, headers, None))
                elif source_mode() == "enforce":
                    record(build_event("source_refused", scope, headers, "source"))
                    return await _refuse(send, _REFUSAL_BODY)
                else:
                    record(build_event("source_unlisted", scope, headers, "source"))
            return await self.app(scope, receive, send)

        session_form = path in SESSION_FORM_PATHS
        try:
            cred = classify_credential(scope.get("method", ""), headers, req.cookies)
        except Exception as exc:                                    # noqa: BLE001
            # Fail closed in enforce, open in log: an unreadable credential is not a credential.
            logger.warning("[write_guard] credential check failed: %s", type(exc).__name__)
            cred = "check_failed"
        if cred in ("key", "session"):
            return await self.app(scope, receive, send)
        if session_form and cred == "session_without_csrf_header":
            return await self.app(scope, receive, send)

        if mode() == "enforce":
            record(build_event("refused", scope, headers, cred))
            return await _refuse(send, _CONSENT_REFUSAL_BODY if session_form else _REFUSAL_BODY)
        record(build_event("would_refuse", scope, headers, cred))
        return await self.app(scope, receive, send)


async def _refuse(send, body: bytes) -> None:
    await send({"type": "http.response.start", "status": 401,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
