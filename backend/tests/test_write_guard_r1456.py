"""R-IV.1456(c) and (e)3: the consent form, the hook source check, and the own checks.

  * /mcp/v1/consent is off the allowlist: a signed-in approval passes (session cookie alone,
    because the form cannot add the CSRF header), an anonymous one is refused in enforce.
  * Every hook TradingView sends to is checked by source address: log-only by default
    (`source_unlisted`), refused only when WEBHOOK_SOURCE_CHECK is exactly "enforce".
  * (c)4: every path on the allowlist BECAUSE it has its own check gets proof here that the
    check refuses an anonymous request -- the nine hooks with their own switch on, the MCP
    protocol endpoint, and the OAuth token exchange.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils import write_guard
from utils.write_guard import (ALLOWLIST, SESSION_FORM_PATHS, TRADINGVIEW_ADDRESSES,
                               WriteGuardMiddleware)

TV = "52.89.214.238"
ELSEWHERE = "203.0.113.9"


@pytest.fixture
def captured(monkeypatch):
    seen = []
    monkeypatch.setattr(write_guard, "record", lambda ev: seen.append(ev))
    return seen


def _tiny():
    a = FastAPI()

    @a.post("/mcp/v1/consent")
    async def consent():
        return {"ran": True}

    for p in [p for p, (g, _) in ALLOWLIST.items() if g == "hook"]:
        a.add_api_route(p, (lambda: {"ran": True}), methods=["POST"])
    a.add_middleware(WriteGuardMiddleware)
    return a


# ── the consent form ──────────────────────────────────────────────────────────────────────

def test_consent_is_off_the_allowlist_and_needs_a_session():
    assert "/mcp/v1/consent" not in ALLOWLIST
    assert set(SESSION_FORM_PATHS) == {"/mcp/v1/consent"}


def test_a_SIGNED_IN_consent_approval_passes_without_the_csrf_header(monkeypatch, captured):
    from utils.session import COOKIE_NAME, issue_session
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    c = TestClient(_tiny())
    c.cookies.set(COOKIE_NAME, issue_session())
    # A plain HTML form post: form-encoded, no X-Requested-With.
    resp = c.post("/mcp/v1/consent", data={"txn_id": "t", "action": "approve", "csrf_token": "x"})
    assert resp.status_code == 200 and resp.json() == {"ran": True}
    assert captured == []


def test_an_ANONYMOUS_consent_approval_is_refused_in_enforce(monkeypatch, captured):
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    resp = TestClient(_tiny()).post("/mcp/v1/consent", data={"action": "approve"})
    assert resp.status_code == 401
    assert "Sign in to the hub" in resp.json()["detail"]
    assert captured[0]["kind"] == "refused" and captured[0]["credential"] == "none"


def test_a_FORGED_session_cannot_approve_consent(monkeypatch, captured):
    from utils.session import COOKIE_NAME
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    c = TestClient(_tiny())
    c.cookies.set(COOKIE_NAME, "e30.forged-signature")
    assert c.post("/mcp/v1/consent", data={"action": "approve"}).status_code == 401
    assert captured[0]["credential"] == "session_invalid"


def test_the_session_alone_exemption_is_ONLY_for_the_consent_form(monkeypatch, captured):
    """Everywhere else a session without the CSRF header is still refused."""
    from utils.session import COOKIE_NAME, issue_session
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    a = FastAPI()

    @a.post("/api/some-write")
    async def w():
        return {"ran": True}
    a.add_middleware(WriteGuardMiddleware)
    c = TestClient(a)
    c.cookies.set(COOKIE_NAME, issue_session())
    assert c.post("/api/some-write").status_code == 401
    assert captured[0]["credential"] == "session_without_csrf_header"


def test_the_real_app_refuses_an_anonymous_consent_post(client, monkeypatch):
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    c = TestClient(client.app, raise_server_exceptions=False)
    assert c.post("/mcp/v1/consent", data={"action": "approve"}).status_code == 401


# ── the source check ──────────────────────────────────────────────────────────────────────

HOOKS = sorted(p for p, (g, _) in ALLOWLIST.items() if g == "hook")


def test_the_addresses_are_tradingviews_four():
    assert TRADINGVIEW_ADDRESSES == {"52.89.214.238", "34.212.75.30", "54.218.53.128",
                                     "52.32.178.7"}
    assert len(HOOKS) == 9


@pytest.mark.parametrize("path", HOOKS)
def test_LOG_mode_records_an_unlisted_source_and_refuses_nothing(monkeypatch, captured, path):
    monkeypatch.delenv("WEBHOOK_SOURCE_CHECK", raising=False)
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")   # the write guard's own mode is separate
    resp = TestClient(_tiny()).post(path, headers={"X-Real-IP": ELSEWHERE})
    assert resp.status_code == 200
    assert captured[0]["kind"] == "source_unlisted" and captured[0]["path"] == path
    assert captured[0]["real_ip"] == ELSEWHERE


@pytest.mark.parametrize("path", HOOKS)
def test_a_tradingview_source_is_a_plain_sample(monkeypatch, captured, path):
    monkeypatch.setenv("WEBHOOK_SOURCE_CHECK", "enforce")
    for addr in sorted(TRADINGVIEW_ADDRESSES):
        assert TestClient(_tiny()).post(path, headers={"X-Real-IP": addr}).status_code == 200
    assert {e["kind"] for e in captured} == {"hook_seen"}


@pytest.mark.parametrize("path", HOOKS)
def test_ENFORCE_refuses_an_unlisted_source(monkeypatch, captured, path):
    monkeypatch.setenv("WEBHOOK_SOURCE_CHECK", "enforce")
    resp = TestClient(_tiny()).post(path, headers={"X-Real-IP": ELSEWHERE})
    assert resp.status_code == 401
    assert captured[0]["kind"] == "source_refused"


def test_X_REAL_IP_wins_over_a_forwarded_for_that_names_tradingview(monkeypatch, captured):
    """Railway overwrites X-Real-IP; a sender cannot borrow TradingView's address via XFF."""
    monkeypatch.setenv("WEBHOOK_SOURCE_CHECK", "enforce")
    resp = TestClient(_tiny()).post("/webhook/tradingview",
                                    headers={"X-Real-IP": ELSEWHERE, "X-Forwarded-For": TV})
    assert resp.status_code == 401


def test_NO_source_at_all_is_unlisted(monkeypatch, captured):
    monkeypatch.setenv("WEBHOOK_SOURCE_CHECK", "enforce")
    assert TestClient(_tiny()).post("/webhook/tick").status_code == 401


def test_only_the_exact_value_enforce_enforces_the_source_check(monkeypatch, captured):
    for v in ("", "1", "true", "on", "log", " Enforce "):
        monkeypatch.setenv("WEBHOOK_SOURCE_CHECK", v)
        expected = 401 if v.strip().lower() == "enforce" else 200
        resp = TestClient(_tiny()).post("/webhook/breadth", headers={"X-Real-IP": ELSEWHERE})
        assert resp.status_code == expected, repr(v)


# ── (c)4: each own check refuses an anonymous request ─────────────────────────────────────

SECRET = "own-check-test-secret"

#: path -> (its own switch, a payload valid in shape but carrying no secret)
OWN_CHECKS = {
    "/webhook/tradingview": ("WEBHOOK_TV_ENFORCE",
                             {"ticker": "SPY", "strategy": "artemis", "direction": "LONG"}),
    "/webhook/breadth": ("WEBHOOK_BREADTH_ENFORCE", {"uvol": 1.0, "dvol": 1.0}),
    "/webhook/tick": ("WEBHOOK_TICK_ENFORCE", {"tick_high": 800.0, "tick_low": -800.0}),
    "/webhook/circuit_breaker": ("WEBHOOK_CB_ENFORCE", {"trigger": "spy_down_1pct"}),
    "/webhook/whale": ("WEBHOOK_WHALE_ENFORCE", {"ticker": "SPY"}),
    "/webhook/footprint": ("WEBHOOK_FOOTPRINT_ENFORCE", {"ticker": "SPY"}),
    "/api/webhook/hermes": ("WEBHOOK_HERMES_ENFORCE", {"ticker": "SPY"}),
    "/api/webhook/pythia": ("WEBHOOK_PYTHIA_ENFORCE", {"ticker": "SPY", "alert_type": "x"}),
    "/webhook/mp_levels": (None, {"ticker": "SPY", "poc": 1.0}),   # always enforced
}


def test_every_hook_has_an_own_check_case():
    assert set(OWN_CHECKS) == set(HOOKS)


@pytest.mark.parametrize("path", sorted(OWN_CHECKS))
def test_each_hooks_OWN_check_refuses_an_anonymous_request(client, monkeypatch, path):
    from webhooks import mp_levels, pythia_events
    flag, payload = OWN_CHECKS[path]
    if flag:
        monkeypatch.setenv(flag, "1")
    for name in ("TRADINGVIEW_WEBHOOK_SECRET", "HERMES_WEBHOOK_SECRET"):
        monkeypatch.setenv(name, SECRET)
    monkeypatch.setattr(pythia_events, "PYTHIA_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(mp_levels, "PYTHIA_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("WRITE_GUARD_MODE", raising=False)
    monkeypatch.delenv("WEBHOOK_SOURCE_CHECK", raising=False)
    c = TestClient(client.app, raise_server_exceptions=False)
    for body in (payload, dict(payload, secret="wrong-value")):
        resp = c.post(path, json=body, headers={"X-Real-IP": TV})
        assert resp.status_code == 401, (path, body.get("secret"), resp.status_code, resp.text)
        assert "secret" in resp.text.lower(), resp.text


def test_mp_levels_refuses_a_MISSING_secret_with_no_switch_at_all(client, monkeypatch):
    """R-IV.1456(c)3: mp_levels has no observe mode; a missing secret is refused today."""
    from webhooks import mp_levels
    monkeypatch.setattr(mp_levels, "PYTHIA_WEBHOOK_SECRET", SECRET)
    c = TestClient(client.app, raise_server_exceptions=False)
    resp = c.post("/webhook/mp_levels", json={"ticker": "SPY"})
    assert resp.status_code == 401


def _mcp_app(monkeypatch):
    """The production provider (GitHub OAuthProxy + login allowlist) around a FastMCP app,
    mounted at /mcp/v1 as backend/main.py mounts it."""
    from fastmcp import FastMCP
    from starlette.applications import Starlette
    from starlette.routing import Mount

    from hub_mcp.auth import (ALLOWED_USERS_ENV, GITHUB_CLIENT_ID_ENV, GITHUB_CLIENT_SECRET_ENV,
                              build_oauth_provider)
    monkeypatch.setenv(GITHUB_CLIENT_ID_ENV, "test-id")
    monkeypatch.setenv(GITHUB_CLIENT_SECRET_ENV, "test-secret")
    monkeypatch.setenv(ALLOWED_USERS_ENV, "only-this-login")
    m = FastMCP(name="t", auth=build_oauth_provider())

    @m.tool()
    def ping() -> str:
        return "pong"
    inner = m.http_app(path="/")
    return Starlette(routes=[Mount("/mcp/v1", app=inner)], lifespan=inner.lifespan)


def test_the_MCP_endpoint_refuses_a_call_without_its_own_token(monkeypatch):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    accept = {"Accept": "application/json, text/event-stream"}
    with TestClient(_mcp_app(monkeypatch)) as c:
        for path in ("/mcp/v1/", "/mcp/v1"):
            assert c.post(path, json=body, headers=accept).status_code == 401, path
            assert c.post(path, json=body, headers=dict(
                accept, Authorization="Bearer forged")).status_code == 401, path


def test_the_TOKEN_exchange_refuses_without_a_code_and_grants_no_client_credentials(monkeypatch):
    """R-IV.1456(c)2: /token grants only authorization-code and refresh exchanges."""
    with TestClient(_mcp_app(monkeypatch)) as c:
        meta = c.get("/mcp/v1/.well-known/oauth-authorization-server").json()
        assert sorted(meta["grant_types_supported"]) == ["authorization_code", "refresh_token"]
        # Anonymous: no registered client at all.
        for g in ("authorization_code", "refresh_token", "client_credentials"):
            r = c.post("/mcp/v1/token", data={"grant_type": g, "client_id": "nobody",
                                              "code": "x", "refresh_token": "x"})
            assert r.status_code == 401, (g, r.text)
        # A registered client still gets nothing without a code consent + GitHub produced.
        reg = c.post("/mcp/v1/register", json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token", "client_credentials"]})
        assert reg.status_code in (200, 201), reg.text
        # The registration may ECHO a requested client_credentials grant back; what matters is
        # that the token endpoint has no such exchange, which is what this proves.
        cid = reg.json()["client_id"]
        r = c.post("/mcp/v1/token", data={"grant_type": "client_credentials", "client_id": cid})
        assert r.status_code in (400, 401) and "access_token" not in r.text, r.text
        assert "unsupported_grant_type" in r.text or "invalid_request" in r.text, r.text
        r = c.post("/mcp/v1/token", data={
            "grant_type": "authorization_code", "client_id": cid, "code": "made-up",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback", "code_verifier": "v" * 43})
        assert r.status_code == 401 and "access_token" not in r.text, r.text


def test_CONSENT_issues_nothing_without_a_live_transaction(monkeypatch):
    """Even before the guard, FastMCP's consent POST needs the transaction /authorize made."""
    with TestClient(_mcp_app(monkeypatch)) as c:
        r = c.post("/mcp/v1/consent", data={"txn_id": "nope", "action": "approve",
                                            "csrf_token": "x"})
        assert r.status_code == 400 and "location" not in {k.lower() for k in r.headers}
