"""R-IV.1446(d): the app-wide write guard and its route table.

The route-table rule: every write route either carries `require_api_key`, or is refused by the
guard without a credential (enforce mode), or is on the guard's ALLOWLIST with a reason. The
enforce-mode sweep sends a real anonymous request to EVERY write route in the live route table,
mounts included, so a route added tomorrow is covered without anyone editing this file -- and
an allowlist entry added tomorrow fails here until it is written into EXPECTED_ALLOWLIST.
"""

import re

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from utils import write_guard
from utils.write_guard import ALLOWLIST, WriteGuardMiddleware

KEY = "test-api-key-12345"   # conftest's placeholder

#: The allowlist as ruled (R-IV.1446(d)1, R-IV.1456(c)). /mcp/v1/consent is NOT on it: it needs
#: Nick's session (test_write_guard_r1456). Changing the allowlist means changing this.
EXPECTED_ALLOWLIST = {
    "/api/auth/login", "/api/auth/logout",
    "/register", "/mcp/v1/register", "/mcp/v1/token", "/mcp/v1/authorize",
    "/mcp/v1", "/mcp/v1/",
    "/webhook/tradingview", "/webhook/breadth", "/webhook/tick", "/webhook/circuit_breaker",
    "/webhook/whale", "/webhook/footprint", "/api/webhook/hermes", "/api/webhook/pythia",
    "/webhook/mp_levels",
}
WRITE = {"POST", "PUT", "PATCH", "DELETE"}


@pytest.fixture(scope="module")
def app(client):
    """conftest's app: imported only after its database and Redis mocks are in place."""
    return client.app


def _write_routes(routes, prefix=""):
    """(method, path template, route) for every write route, descending into mounts."""
    out = []
    for r in routes:
        path = prefix + getattr(r, "path", "")
        if isinstance(r, Mount):
            sub = getattr(r.app, "routes", None)
            out.append(("MOUNT", path, r))
            if sub:
                out.extend(_write_routes(sub, path))
            continue
        for m in sorted((getattr(r, "methods", None) or set()) & WRITE):
            out.append((m, path, r))
    return out


def _concrete(path):
    return re.sub(r"\{[^}]+\}", "1", path)


def _has_api_key_dep(route):
    seen = set()

    def walk(dep):
        for d in dep.dependencies:
            if d.call is not None:
                seen.add(getattr(d.call, "__name__", ""))
            walk(d)
    if getattr(route, "dependant", None) is not None:
        walk(route.dependant)
    return "require_api_key" in seen


# ── the allowlist ─────────────────────────────────────────────────────────────────────────

def test_allowlist_is_exactly_the_ruled_set():
    assert set(ALLOWLIST) == EXPECTED_ALLOWLIST


def test_every_allowlist_entry_says_why_it_is_public():
    for path, (group, why) in ALLOWLIST.items():
        assert group in {"signin", "mcp_signin", "mcp_own_auth", "hook"}, path
        assert len(why.split()) >= 5, "allowlist entry %s needs a real reason" % path


def test_every_allowlist_entry_names_a_real_route(app):
    """No stale entries: each is a write route in the table, or sits under the MCP mount
    (whose OAuth routes exist only when the OAuth variables are set, as in production)."""
    table = {p for m, p, _ in _write_routes(app.routes) if m != "MOUNT"}
    mounts = {p for m, p, _ in _write_routes(app.routes) if m == "MOUNT"}
    for path in ALLOWLIST:
        under_mount = any(path == mp or path.startswith(mp + "/") for mp in mounts)
        assert path in table or under_mount, "allowlist entry %s matches no route" % path


def test_the_hooks_are_the_ones_that_check_their_own_secret(app):
    import inspect
    from webhooks import (circuit_breaker, footprint, hermes, mp_levels, pythia_events,
                          tradingview, whale)
    for mod in (circuit_breaker, footprint, hermes, pythia_events, tradingview, whale):
        assert "validate_webhook_secret(" in inspect.getsource(mod), mod.__name__
    assert "compare_digest" in inspect.getsource(mp_levels)
    hooks = {p for p, (g, _) in ALLOWLIST.items() if g == "hook"}
    assert len(hooks) == 9
    # McClellan has NO secret check, so it is deliberately NOT on the allowlist.
    assert "/webhook/mcclellan" not in ALLOWLIST


# ── the route table ───────────────────────────────────────────────────────────────────────

def test_the_guard_is_installed_outermost(app):
    assert app.user_middleware, "no middleware at all"
    assert app.user_middleware[0].cls is WriteGuardMiddleware, (
        "the guard must be added last (outermost) so it sees every request first")


def test_no_route_handles_options_itself(app):
    """OPTIONS is exempt because it is only ever the CORS preflight here."""
    for r in app.routes:
        assert "OPTIONS" not in (getattr(r, "methods", None) or set()), getattr(r, "path", r)


def test_every_write_route_is_authed_guarded_or_allowlisted(app, monkeypatch):
    """THE ROUTE-TABLE TEST. A real anonymous request to every write route, enforce mode."""
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    client = TestClient(app, raise_server_exceptions=False)
    routes = [(m, p, r) for m, p, r in _write_routes(app.routes) if m != "MOUNT"]
    assert len(routes) > 150, "the route table looks wrong: %d write routes" % len(routes)
    unprotected, checked = [], 0
    for method, path, route in routes:
        if path in ALLOWLIST:
            continue
        checked += 1
        resp = client.request(method, _concrete(path))
        if resp.status_code != 401 and not _has_api_key_dep(route):
            unprotected.append((method, path, resp.status_code))
        else:
            assert resp.status_code == 401, (method, path, resp.status_code)
    assert not unprotected, "write routes with no auth, not allowlisted: %s" % unprotected
    assert checked >= 140


def test_mounted_write_paths_are_refused_too(app, monkeypatch):
    """A mount's routes are invisible to a route census; the guard must still see them."""
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    client = TestClient(app, raise_server_exceptions=False)
    for path in ("/mcp/v1/not-a-listed-path", "/assets/x.js"):
        assert client.post(path).status_code == 401, path


def test_a_new_unauthenticated_route_is_caught():
    """Proof the sweep can fail: an open route added to an app with the guard is refused in
    enforce, and WITHOUT the guard the same sweep reports it unprotected."""
    def make(with_guard):
        a = FastAPI()
        r = APIRouter()

        @r.post("/api/brand-new-open-write")
        async def open_write():
            return {"ok": True}
        a.include_router(r)
        if with_guard:
            a.add_middleware(WriteGuardMiddleware)
        return a

    import os
    old = os.environ.get("WRITE_GUARD_MODE")
    os.environ["WRITE_GUARD_MODE"] = "enforce"
    try:
        assert TestClient(make(True)).post("/api/brand-new-open-write").status_code == 401
        assert TestClient(make(False)).post("/api/brand-new-open-write").status_code == 200
    finally:
        if old is None:
            os.environ.pop("WRITE_GUARD_MODE", None)
        else:
            os.environ["WRITE_GUARD_MODE"] = old


# ── the modes ─────────────────────────────────────────────────────────────────────────────

def _tiny():
    a = FastAPI()

    @a.post("/w")
    async def w():
        return {"ran": True}

    @a.get("/r")
    async def r():
        return {"ran": True}

    @a.post("/webhook/tradingview")
    async def hook():
        return {"ran": True}
    a.add_middleware(WriteGuardMiddleware)
    return a


@pytest.fixture
def captured(monkeypatch):
    seen = []
    monkeypatch.setattr(write_guard, "record", lambda ev: seen.append(ev))
    return seen


def test_log_mode_refuses_nothing_and_records_what_it_would_refuse(monkeypatch, captured):
    monkeypatch.delenv("WRITE_GUARD_MODE", raising=False)
    c = TestClient(_tiny())
    resp = c.post("/w?secret=SHOULD-NOT-APPEAR", headers={
        "X-API-Key": "WRONG-KEY-VALUE", "User-Agent": "probe/1",
        "X-Forwarded-For": "203.0.113.9, 10.0.0.1", "Origin": "https://example.test"})
    assert resp.status_code == 200 and resp.json() == {"ran": True}
    assert len(captured) == 1
    ev = captured[0]
    assert ev["kind"] == "would_refuse" and ev["mode"] == "log"
    assert ev["method"] == "POST" and ev["path"] == "/w"
    assert ev["credential"] == "key_wrong"
    assert ev["forwarded_for"] == "203.0.113.9, 10.0.0.1"
    assert ev["user_agent"] == "probe/1" and ev["origin"] == "https://example.test"
    flat = repr(ev)
    assert "SHOULD-NOT-APPEAR" not in flat and "WRONG-KEY-VALUE" not in flat and KEY not in flat


def test_enforce_mode_refuses_before_the_handler(monkeypatch, captured):
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    resp = TestClient(_tiny()).post("/w")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or missing API key"}
    assert captured[0]["kind"] == "refused" and captured[0]["credential"] == "none"


@pytest.mark.parametrize("mode", ["log", "enforce"])
def test_reads_and_valid_credentials_pass_untouched(monkeypatch, captured, mode):
    monkeypatch.setenv("WRITE_GUARD_MODE", mode)
    c = TestClient(_tiny())
    assert c.get("/r").status_code == 200
    assert c.post("/w", headers={"X-API-Key": KEY}).status_code == 200
    assert c.post("/w", headers={"Authorization": "Bearer " + KEY}).status_code == 200
    from utils.session import COOKIE_NAME, issue_session
    c.cookies.set(COOKIE_NAME, issue_session())
    assert c.post("/w", headers={"X-Requested-With": "XMLHttpRequest"}).status_code == 200
    assert captured == []


def test_a_hook_passes_in_enforce_and_leaves_a_source_sample(monkeypatch, captured):
    monkeypatch.setenv("WRITE_GUARD_MODE", "enforce")
    resp = TestClient(_tiny()).post("/webhook/tradingview",
                                    headers={"X-Forwarded-For": "52.89.214.238"})
    assert resp.status_code == 200
    assert captured[0]["kind"] == "hook_seen" and captured[0]["credential"] is None


def test_only_the_exact_value_enforce_enforces(monkeypatch, captured):
    for v in ("", "1", "true", "ENFORCE ", "on"):
        monkeypatch.setenv("WRITE_GUARD_MODE", v)
        expected = 401 if v.strip().lower() == "enforce" else 200
        assert TestClient(_tiny()).post("/w").status_code == expected, repr(v)


# ── the guard and require_api_key agree ───────────────────────────────────────────────────

@pytest.mark.parametrize("hdrs,cookie,expect", [
    ({}, False, "none"),
    ({"X-API-Key": KEY}, False, "key"),
    ({"X-API-Key": "nope"}, False, "key_wrong"),
    ({"Authorization": "Bearer " + KEY}, False, "key"),
    ({"Authorization": "Bearer nope"}, False, "bearer_wrong"),
    ({"X-API-Key": "nope", "Authorization": "Bearer " + KEY}, False, "key"),
    ({}, True, "session_without_csrf_header"),
    ({"X-Requested-With": "XMLHttpRequest"}, True, "session"),
    ({"X-Requested-With": "XMLHttpRequest"}, "forged", "session_invalid"),
])
def test_classify_matches_require_api_key(hdrs, cookie, expect):
    from fastapi import Depends
    from utils.pivot_auth import require_api_key
    from utils.session import COOKIE_NAME, issue_session

    a = FastAPI()

    @a.post("/dep")
    async def dep(_=Depends(require_api_key)):
        return {"ok": True}

    @a.post("/cls")
    async def cls(request: __import__("fastapi").Request):
        return {"c": write_guard.classify_credential("POST", request.headers, request.cookies)}

    c = TestClient(a)
    if cookie is True:
        c.cookies.set(COOKIE_NAME, issue_session())
    elif cookie == "forged":
        c.cookies.set(COOKIE_NAME, "e30.forged-signature")
    got = c.post("/cls", headers=hdrs).json()["c"]
    accepted_by_dep = c.post("/dep", headers=hdrs).status_code == 200
    assert got == expect
    assert (got in ("key", "session")) == accepted_by_dep


def test_the_daily_caps_hold(monkeypatch):
    monkeypatch.setattr(write_guard, "MAX_RECORDS_PER_DAY", 3)
    monkeypatch.setattr(write_guard, "MAX_HOOK_SAMPLES_PER_PATH_PER_DAY", 2)
    monkeypatch.setattr(write_guard, "_day", None)
    inserted = []
    monkeypatch.delenv("WRITE_GUARD_RECORD", raising=False)
    monkeypatch.setattr(write_guard.asyncio, "ensure_future", lambda coro: (inserted.append(1),
                                                                            coro.close()))
    ev = {"kind": "would_refuse", "method": "POST", "path": "/w", "credential": "none",
          "user_agent": None}
    hk = dict(ev, kind="hook_seen", path="/webhook/tick", credential=None)
    for _ in range(5):
        write_guard.record(dict(hk))
    assert len(inserted) == 2
    for _ in range(5):
        write_guard.record(dict(ev))
    assert len(inserted) == 3   # 2 hook samples + 1 more before the day's cap of 3
