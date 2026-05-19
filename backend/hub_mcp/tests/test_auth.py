"""Tests for hub_mcp/auth.py — OAuth allowlist verifier + provider build."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hub_mcp.auth import (
    ALLOWED_USERS_ENV,
    AllowlistedGitHubTokenVerifier,
    GITHUB_CLIENT_ID_ENV,
    GITHUB_CLIENT_SECRET_ENV,
    _parse_allowlist,
    build_oauth_provider,
)


# ─── _parse_allowlist ────────────────────────────────────────────────────

def test_parse_allowlist_single_user():
    assert _parse_allowlist("303webhouse") == frozenset({"303webhouse"})


def test_parse_allowlist_multiple_with_spaces():
    assert _parse_allowlist("alice, bob ,charlie") == frozenset(
        {"alice", "bob", "charlie"}
    )


def test_parse_allowlist_empty_string():
    assert _parse_allowlist("") == frozenset()


def test_parse_allowlist_none():
    assert _parse_allowlist(None) == frozenset()


# ─── AllowlistedGitHubTokenVerifier ──────────────────────────────────────

def _access_token(login):
    """Build a stub AccessToken with a `claims` dict containing `login`."""
    tok = MagicMock()
    tok.claims = {"login": login} if login is not None else {}
    return tok


@pytest.mark.asyncio
async def test_verifier_admits_allowed_user(monkeypatch):
    verifier = AllowlistedGitHubTokenVerifier(allowed_users=["303webhouse"])
    allowed = _access_token("303webhouse")
    monkeypatch.setattr(
        "fastmcp.server.auth.providers.github.GitHubTokenVerifier.verify_token",
        AsyncMock(return_value=allowed),
    )
    result = await verifier.verify_token("any-token")
    assert result is allowed


@pytest.mark.asyncio
async def test_verifier_rejects_non_allowed_user(monkeypatch):
    verifier = AllowlistedGitHubTokenVerifier(allowed_users=["303webhouse"])
    stranger = _access_token("rando")
    monkeypatch.setattr(
        "fastmcp.server.auth.providers.github.GitHubTokenVerifier.verify_token",
        AsyncMock(return_value=stranger),
    )
    result = await verifier.verify_token("any-token")
    assert result is None


@pytest.mark.asyncio
async def test_verifier_rejects_missing_login(monkeypatch):
    verifier = AllowlistedGitHubTokenVerifier(allowed_users=["303webhouse"])
    no_login = _access_token(None)
    monkeypatch.setattr(
        "fastmcp.server.auth.providers.github.GitHubTokenVerifier.verify_token",
        AsyncMock(return_value=no_login),
    )
    result = await verifier.verify_token("any-token")
    assert result is None


@pytest.mark.asyncio
async def test_verifier_passes_through_parent_failure(monkeypatch):
    """If the parent verifier itself fails (returns None), we propagate."""
    verifier = AllowlistedGitHubTokenVerifier(allowed_users=["303webhouse"])
    monkeypatch.setattr(
        "fastmcp.server.auth.providers.github.GitHubTokenVerifier.verify_token",
        AsyncMock(return_value=None),
    )
    result = await verifier.verify_token("bad-token")
    assert result is None


# ─── build_oauth_provider ────────────────────────────────────────────────

def test_build_provider_returns_none_when_oauth_env_missing(monkeypatch):
    monkeypatch.delenv(GITHUB_CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(GITHUB_CLIENT_SECRET_ENV, raising=False)
    monkeypatch.setenv(ALLOWED_USERS_ENV, "303webhouse")
    assert build_oauth_provider() is None


def test_build_provider_returns_none_when_allowlist_missing(monkeypatch):
    monkeypatch.setenv(GITHUB_CLIENT_ID_ENV, "abc")
    monkeypatch.setenv(GITHUB_CLIENT_SECRET_ENV, "def")
    monkeypatch.delenv(ALLOWED_USERS_ENV, raising=False)
    assert build_oauth_provider() is None


def test_build_provider_returns_oauthproxy_when_env_complete(monkeypatch):
    from fastmcp.server.auth.oauth_proxy import OAuthProxy

    monkeypatch.setenv(GITHUB_CLIENT_ID_ENV, "abc-id")
    monkeypatch.setenv(GITHUB_CLIENT_SECRET_ENV, "def-secret")
    monkeypatch.setenv(ALLOWED_USERS_ENV, "303webhouse")
    provider = build_oauth_provider()
    assert isinstance(provider, OAuthProxy)
