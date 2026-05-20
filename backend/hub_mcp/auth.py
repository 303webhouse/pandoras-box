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

# Public base URL of the MCP server. MUST include the /mcp/v1 mount prefix
# AND a trailing slash. The trailing slash is critical: without it, FastMCP
# advertises `issuer: ".../mcp/v1"` (no slash), Claude.ai's connector uses
# the issuer as the MCP endpoint URL and POSTs there, hits FastAPI's
# mount-redirect (307 -> ".../mcp/v1/"), and aborts because most clients
# don't follow 307 redirects on POST. With the trailing slash, FastMCP
# advertises `issuer: ".../mcp/v1/"` directly and the 307 hop is avoided.
PUBLIC_BASE_URL_ENV = "MCP_PUBLIC_BASE_URL"
DEFAULT_PUBLIC_BASE_URL = "https://pandoras-box-production.up.railway.app/mcp/v1/"


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
    proxy = OAuthProxy(
        upstream_authorization_endpoint="https://github.com/login/oauth/authorize",
        upstream_token_endpoint="https://github.com/login/oauth/access_token",
        upstream_client_id=client_id,
        upstream_client_secret=client_secret,
        token_verifier=verifier,
        base_url=base_url,
        # redirect_path defaults to /auth/callback, which is what the GitHub
        # OAuth App is configured for (verified empirically 2026-05-15).
    )
    logger.info(
        "OAuth enabled: GitHub upstream, %d allowed user(s), base=%s",
        len(allowed_users),
        base_url,
    )
    return proxy
