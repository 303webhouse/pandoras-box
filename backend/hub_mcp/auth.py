"""OAuth authentication for the hub MCP server (GitHub via FastMCP OAuthProxy).

The previous bearer-token middleware is gone — Claude.ai's custom connector
UI only accepts OAuth, so we delegate the user-facing auth surface to
FastMCP's OAuthProxy with GitHub as the upstream IdP.

Two-layer guard:
  1. FastMCP / OAuthProxy handles the OAuth 2.1 flow + token issuance/verification
  2. AllowlistedGitHubTokenVerifier subclasses the default GitHub verifier and
     rejects any GitHub user whose `login` is not in MCP_ALLOWED_GITHUB_USERS
     (comma-separated; current value is just `303webhouse`). Per-request check
     uses the parent's cache so we don't hammer the GitHub API.

The `MCP_BEARER_TOKEN` env var is no longer read by any live code path. It can
be left set in Railway during the transition; removing it is a follow-up cleanup.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, Optional

from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.github import GitHubTokenVerifier
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)


GITHUB_CLIENT_ID_ENV = "GITHUB_OAUTH_CLIENT_ID"
GITHUB_CLIENT_SECRET_ENV = "GITHUB_OAUTH_CLIENT_SECRET"
ALLOWED_USERS_ENV = "MCP_ALLOWED_GITHUB_USERS"
REDIS_URL_ENV = "REDIS_URL"

# Public base URL of the MCP server. Must include the /mcp/v1 mount prefix
# so OAuthProxy advertises the correct authorize / token / callback URLs.
# (No trailing slash. The 307-redirect-on-POST issue that affected Claude.ai
# is fixed at the parent-app level via FastAPI redirect_slashes=False in
# backend/main.py — both `/mcp/v1` and `/mcp/v1/` reach the FastMCP app
# without a redirect hop.)
PUBLIC_BASE_URL_ENV = "MCP_PUBLIC_BASE_URL"
DEFAULT_PUBLIC_BASE_URL = "https://pandoras-box-production.up.railway.app/mcp/v1"


def _parse_allowlist(raw: Optional[str]) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(u.strip() for u in raw.split(",") if u.strip())


class AllowlistedGitHubTokenVerifier(GitHubTokenVerifier):
    """GitHub token verifier that additionally enforces a username allowlist.

    The parent's `verify_token` hits the GitHub `/user` endpoint, populates
    `AccessToken.claims["login"]`, and caches the result. We chain on top:
    if `login` is not in the allowlist, return None (auth fails). The cache
    layer ensures we don't re-hit GitHub on every MCP request from the
    same user.
    """

    def __init__(self, *, allowed_users: Iterable[str], **kwargs):
        super().__init__(**kwargs)
        self._allowed_users = frozenset(u for u in allowed_users if u)
        if not self._allowed_users:
            logger.critical(
                "%s is empty — refusing to start would lock everyone out; "
                "configure at least one allowed GitHub username.",
                ALLOWED_USERS_ENV,
            )

    async def verify_token(self, token: str) -> AccessToken | None:
        access = await super().verify_token(token)
        if access is None:
            return None
        login = (access.claims or {}).get("login")
        if not login or login not in self._allowed_users:
            logger.warning(
                "GitHub user '%s' not in %s allowlist; rejecting token",
                login,
                ALLOWED_USERS_ENV,
            )
            return None
        return access


def _build_client_storage(client_secret: str):
    """Build a Redis-backed encrypted state store for FastMCP's OAuthProxy.

    Phase C.1-rev2 fix (2026-05-24): replaces FastMCP 3.3.1 OAuthProxy's
    default file-backed `client_storage`, which Railway wipes on every
    redeploy (ephemeral container filesystem). Persisting via Redis lets all
    six OAuthProxy state collections (JTI mappings, DCR clients, refresh
    tokens, transactions, auth codes, upstream tokens) survive restarts.

    rev1 → rev2 delta (idle-drop resilience):
        rev1 used `RedisStore(url=...)`, which constructs an internal
        redis-py client without retry / keepalive / health-check config.
        Empirically, Upstash's idle timeout (~5 min) closed the underlying
        socket within minutes of startup; the next OAuth registration hit a
        dead fd and bubbled `ConnectionError: Connection closed by server`
        all the way to a 500. See:
        docs/strategy-reviews/phase-c.1-rev1-closure-note-2026-05-24.md.

        rev2 pre-builds the async redis-py client with:
        - `health_check_interval=30` — proactive PING every 30s of idle so
          the connection is detected dead before the user hits it; ALSO
          keeps the connection from idling out on Upstash's side.
        - `retry_on_timeout=True` — transparent retry on `TimeoutError`.
        - `socket_keepalive=True` — TCP keep-alive defense in depth.

    Encryption-at-rest preserved via Fernet (parity with FastMCP's default).
    The Fernet key derives from GITHUB_OAUTH_CLIENT_SECRET via HKDF-SHA256
    with a versioned salt. FastMCP treats decryption errors as cache misses
    (proxy.py:482-485), so secret rotation degrades gracefully.

    Returns None if REDIS_URL is unset or imports fail — caller falls back
    to FastMCP's default file store with a WARNING log.
    """
    redis_url = os.environ.get(REDIS_URL_ENV)
    if not redis_url:
        return None

    try:
        from cryptography.fernet import Fernet
        from fastmcp.server.auth.jwt_issuer import derive_jwt_key
        from key_value.aio.stores.redis import RedisStore
        from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
        import redis.asyncio as redis_async
    except ImportError as exc:
        logger.warning(
            "OAuth Redis-backed storage unavailable (import failed: %s). "
            "Falling back to FastMCP's default file-backed store — state "
            "will NOT survive Railway redeploys.",
            exc,
        )
        return None

    redis_client = redis_async.Redis.from_url(
        redis_url,
        health_check_interval=30,
        retry_on_timeout=True,
        socket_keepalive=True,
        decode_responses=False,
    )

    storage_key = derive_jwt_key(
        high_entropy_material=client_secret,
        salt="hub-mcp-oauth-storage-key-v1",
    )

    redis_store = RedisStore(client=redis_client, default_collection="fastmcp-oauth")
    return FernetEncryptionWrapper(
        key_value=redis_store,
        fernet=Fernet(key=storage_key),
        raise_on_decryption_error=False,
    )


def build_oauth_provider() -> Optional[OAuthProxy]:
    """Build the OAuthProxy for GitHub, or return None if env vars are unset.

    Returning None lets the FastMCP instance start in unauthenticated mode,
    which is what unit tests want. In production, missing env vars are a
    misconfiguration and we log a critical error.
    """
    client_id = os.environ.get(GITHUB_CLIENT_ID_ENV)
    client_secret = os.environ.get(GITHUB_CLIENT_SECRET_ENV)
    allowed_users = _parse_allowlist(os.environ.get(ALLOWED_USERS_ENV))
    base_url = os.environ.get(PUBLIC_BASE_URL_ENV) or DEFAULT_PUBLIC_BASE_URL

    if not client_id or not client_secret:
        logger.warning(
            "OAuth disabled: %s and/or %s not set. MCP will accept "
            "unauthenticated requests — only acceptable for local tests.",
            GITHUB_CLIENT_ID_ENV,
            GITHUB_CLIENT_SECRET_ENV,
        )
        return None

    if not allowed_users:
        logger.critical(
            "%s is empty or missing — refusing to build OAuth provider "
            "(would either lock everyone out or admit anyone).",
            ALLOWED_USERS_ENV,
        )
        return None

    verifier = AllowlistedGitHubTokenVerifier(
        allowed_users=allowed_users,
        required_scopes=["user"],
        cache_ttl_seconds=300,
    )

    client_storage = _build_client_storage(client_secret)
    if client_storage is None:
        logger.warning(
            "%s not set — OAuthProxy will use FastMCP's default file-backed "
            "store. OAuth state (DCR registrations, JTI mappings, refresh "
            "tokens) will NOT survive Railway redeploys; clients will need "
            "to manually reconnect after each deploy. Set %s to fix.",
            REDIS_URL_ENV, REDIS_URL_ENV,
        )

    proxy = OAuthProxy(
        upstream_authorization_endpoint="https://github.com/login/oauth/authorize",
        upstream_token_endpoint="https://github.com/login/oauth/access_token",
        upstream_client_id=client_id,
        upstream_client_secret=client_secret,
        token_verifier=verifier,
        base_url=base_url,
        client_storage=client_storage,
        # redirect_path defaults to /auth/callback, which is what the GitHub
        # OAuth App is configured for (verified empirically 2026-05-15).
    )
    logger.info(
        "OAuth enabled: GitHub upstream, %d allowed user(s), base=%s, "
        "client_storage=%s",
        len(allowed_users),
        base_url,
        "redis (persistent, health-check=30s)" if client_storage is not None else "file (ephemeral)",
    )
    return proxy
