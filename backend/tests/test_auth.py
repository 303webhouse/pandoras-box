"""
Auth enforcement tests — verify all mutation routes require PIVOT_API_KEY.

Phase 0H — auto-discovery test ensures new mutation routes cannot be added
without auth. Parametrized tests cover all known protected routes.
"""
import inspect
import pytest


# Routes exempt from HEADER/API-key auth by design.
# NOTE (Phase 1 webhook hardening): the TradingView webhooks below are NOT plain-public —
# they are gated by a shared body `secret` field via validate_webhook_secret() (TV can't send
# headers). They run in OBSERVE mode and flip fail-closed per the flip-day runbook. They remain
# in this set because the auto-discovery test only recognizes Depends(require_api_key)-style
# header auth, not the body-secret gate. Post-flip a secretless POST returns 401.
AUTH_EXEMPT_MUTATIONS = {
    # TradingView webhooks — header-less; body-secret gated (Phase 1, observe→flip)
    ("POST", "/webhook/tradingview"),
    ("POST", "/webhook/signal"),
    ("POST", "/webhook/circuit_breaker"),
    ("POST", "/webhook/whale"),
    # Breadth/tick/mcclellan webhooks from TradingView — body-secret gated (Phase 1)
    ("POST", "/webhook/breadth"),
    ("POST", "/webhook/tick"),
    ("POST", "/webhook/mcclellan"),
    # Alert ingestion
    ("POST", "/webhook/alerts/pivot"),
    # Dashboard auth — intentionally public (login can't require a session; logout clears it)
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    # R-IV.419(a) — routes with their OWN auth, confirmed by reading the handler, NEVER by a
    # live request. Each is re-checked by TestExemptionsStillHold, so an
    # entry here cannot quietly outlive the mechanism that justified it.
    #   TradingView-style webhooks: header-less, body-secret gated.
    ("POST", "/api/webhook/pythia"),       # fail-closed, constant-time (PYTHIA_WEBHOOK_SECRET)
    ("POST", "/webhook/mp_levels"),        # fail-closed, constant-time (PYTHIA_WEBHOOK_SECRET)
    ("POST", "/api/webhook/hermes"),       # validate_webhook_secret (switch: WEBHOOK_HERMES_ENFORCE)
    ("POST", "/webhook/footprint"),        # validate_webhook_secret (switch: WEBHOOK_FOOTPRINT_ENFORCE)
    #   Own header/session checks that require_api_key cannot express:
    ("POST", "/api/chronos/refresh"),      # PIVOT_API_KEY via header OR ?api_key= query param
    ("POST", "/api/layout"),               # verify_session; its v2 caller sends no CSRF header
    #   The MCP app: GitHub OAuth (OAuthProxy) + username allowlist, hub_mcp/auth.py
    ("POST", "/mcp/v1"),
    ("DELETE", "/mcp/v1"),
    ("POST", "/register"),                 # OAuth dynamic client registration for that connector
}

# Pre-existing routes that need auth but weren't in Phase 0H scope.
# TODO: Lock these down in a future phase.
AUTH_TODO_LOCKDOWN = {
    # Bias engine management
    ("DELETE", "/api/bias/override"),
    ("POST", "/api/bias-auto/savita/update"),
    ("POST", "/api/bias/factor-update"),
    ("POST", "/api/bias/override"),
    ("POST", "/api/bias/savita/check"),
    ("POST", "/api/bias/savita/enable"),
    ("POST", "/api/bias/weekly-audit"),
    ("PUT", "/api/bias/savita"),
    # UW flow ingestion
    ("POST", "/api/bias/uw/economic_calendar"),
    ("POST", "/api/bias/uw/flow_alerts"),
    ("POST", "/api/bias/uw/generic"),
    ("POST", "/api/bias/uw/highest_volume"),
    ("POST", "/api/bias/uw/market_tide"),
    ("POST", "/api/bias/uw/sectorflow"),
    # Signal management
    ("DELETE", "/api/signals/clear-all"),
    ("POST", "/api/signal/action"),
    ("POST", "/api/signals/archive"),
    ("POST", "/api/signals/{signal_id}/accept"),
    ("POST", "/api/signals/{signal_id}/accept-options"),
    ("POST", "/api/signals/{signal_id}/dismiss"),
    # Trade acceptance
    ("POST", "/api/accept/{pending_id}/fill-options"),
    ("POST", "/api/accept/{pending_id}/fill-stocks"),
    ("POST", "/api/accept/{signal_id}/options"),
    ("POST", "/api/accept/{signal_id}/stocks"),
    ("POST", "/api/pending-trades/expire"),
    # Scanner / strategies / confluence
    ("POST", "/api/confluence/scan"),
    ("POST", "/api/cta/config/enable"),
    ("POST", "/api/cta/scan/custom"),
    ("POST", "/api/cta/scan/push"),
    ("POST", "/api/strategies/disable-all"),
    ("POST", "/api/strategies/enable-all"),
    ("POST", "/api/strategies/reset"),
    ("POST", "/api/strategies/{strategy_id}/toggle"),
    ("PUT", "/api/strategies/{strategy_id}/settings"),
    # Market indicators / sector
    ("POST", "/api/market-indicators/credit-spreads/refresh"),
    ("POST", "/api/market-indicators/market-breadth/refresh"),
    ("POST", "/api/market-indicators/refresh-all"),
    ("POST", "/api/market-indicators/vix-term/refresh"),
    ("POST", "/api/sector-rotation/momentum/refresh"),
    ("POST", "/api/sector-rotation/refresh"),
    # Misc
    ("POST", "/api/dollar-smile/manual"),
    ("POST", "/api/dollar-smile/webhook"),
    ("POST", "/api/flow/configure"),
    ("POST", "/api/flow/manual"),
    ("POST", "/api/flow/webhook"),
    ("POST", "/api/hybrid/refresh"),
    ("POST", "/api/knowledgebase/reload"),
    # ("POST", "/webhook/test") — locked down in Chunk G; now in PROTECTED_ROUTES
}

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class TestAuthEnforcement:
    """Mutation routes must require authentication."""

    PROTECTED_ROUTES = [
        # v2 positions (existing)
        ("POST", "/api/v2/positions", {"ticker": "TEST", "entry_price": 100, "quantity": 1}),
        ("PATCH", "/api/v2/positions/POS_TEST_123", {"notes": "test"}),
        ("POST", "/api/v2/positions/POS_TEST_123/close", {"exit_price": 105}),
        ("DELETE", "/api/v2/positions/POS_TEST_123", None),
        ("POST", "/api/v2/positions/bulk", {"positions": []}),
        ("POST", "/api/v2/positions/reconcile", {"positions": []}),
        ("POST", "/api/v2/positions/mark-to-market", None),
        ("PATCH", "/api/v2/positions/account-balance", {"cash": 1000}),
        # Committee results (existing)
        ("POST", "/api/committee/results", {
            "signal_id": "test", "committee_run_id": "test",
            "action": "PASS", "conviction": "LOW",
        }),
        # Watchlist (Phase 0H)
        ("PUT", "/api/watchlist", {"tickers": ["SPY"]}),
        ("POST", "/api/watchlist/add", {"ticker": "AAPL"}),
        ("POST", "/api/watchlist/remove", {"ticker": "AAPL"}),
        ("DELETE", "/api/watchlist/clear", None),
        ("POST", "/api/watchlist/reset", None),
        ("POST", "/api/watchlist/sector-strength", {"sector_strength": {}}),
        ("PATCH", "/api/watchlist/tickers/SPY/mute", {"muted": True}),
        ("PATCH", "/api/watchlist/tickers/bulk-mute", {"symbols": ["SPY"], "muted": True}),
        ("DELETE", "/api/watchlist/tickers/SPY", None),
        ("POST", "/api/watchlist/tickers/add", {"symbol": "AAPL"}),
        # Circuit breaker management (Phase 0H)
        ("POST", "/webhook/circuit_breaker/reset", None),
        ("POST", "/webhook/circuit_breaker/accept_reset", None),
        ("POST", "/webhook/circuit_breaker/reject_reset", None),
        ("POST", "/webhook/circuit_breaker/test/spy_down_1pct", None),
        # BTC signals (Phase 2A)
        ("POST", "/api/btc/bottom-signals/refresh", None),
        ("POST", "/api/btc/bottom-signals/test_signal", {"status": "FIRING"}),
        ("POST", "/api/btc/bottom-signals/reset", None),
        ("POST", "/api/btc/bottom-signals/test_signal/clear-override", None),
        # Portfolio (Phase 0H)
        ("POST", "/api/portfolio/cash-flows", {"amount": 100}),
        # Portfolio (existing, verify still protected)
        ("POST", "/api/portfolio/balances/update", {"account_name": "Robinhood", "balance": 1000}),
        # legacy /positions/sync, /positions, /positions/close removed 2026-06-17 (open_positions deprecated)
        ("PATCH", "/api/portfolio/positions/closed/1", {"notes": "test"}),
        # Analytics mutations (Brief 3A)
        ("POST", "/api/analytics/resolve-counterfactuals", None),
        # Weekly reports (Brief 3D)
        ("POST", "/api/analytics/weekly-reports", {
            "week_of": "2026-03-07", "report_json": {}, "narrative": "test",
        }),
        # Analytics mutations (Brief 3E — locked down)
        ("POST", "/api/analytics/backtest", {
            "start_date": "2026-01-01", "end_date": "2026-03-01",
        }),
        ("POST", "/api/analytics/log-trade", {"ticker": "SPY"}),
        ("POST", "/api/analytics/log-trade-leg", {
            "trade_id": 1, "ticker": "SPY", "direction": "LONG",
        }),
        ("POST", "/api/analytics/outcomes/manual", {
            "ticker": "SPY", "direction": "LONG", "outcome": "WIN",
        }),
        # /api/analytics/log-signal removed 2026-07-21 (DEF-SIGNAL-METADATA):
        # it bypassed process_signal_unified()'s chokepoint and had zero
        # callers/zero invocations. Its auth-behavior case is dropped with it.
        ("POST", "/api/analytics/log-uw-snapshot", {
            "dashboard_type": "flow", "data": {},
        }),
        ("POST", "/api/analytics/import-trades", {"trades": []}),
        ("DELETE", "/api/analytics/trades", None),
        ("DELETE", "/api/analytics/trades/99999", None),
        ("PUT", "/api/analytics/health-alert/1/dismiss", None),
        ("PUT", "/api/analytics/trade/99999/close", {
            "exit_price": 100, "close_reason": "test",
        }),
        # Olympus analysis (Agora — auth required)
        ("POST", "/api/analyze/SPY/olympus", None),
        # Test webhook (Chunk G — gated with require_api_key)
        ("POST", "/webhook/test", {"ping": "test"}),
    ]

    # Book reads require auth (R-IV.417); they are covered by TestBookReadsGated below.
    PUBLIC_ROUTES = [
        ("GET", "/health"),
        ("GET", "/live"),
        ("GET", "/api/bias/composite"),
        ("GET", "/api/committee/queue"),
        ("GET", "/api/monitoring/factor-staleness"),
        ("GET", "/api/monitoring/polygon-health"),
    ]

    def _send(self, client, method, path, body=None, headers=None):
        """Send a request with the given method."""
        kw = {}
        if headers:
            kw["headers"] = headers
        if method == "POST":
            return client.post(path, json=body, **kw) if body is not None else client.post(path, **kw)
        elif method == "PUT":
            return client.put(path, json=body, **kw) if body is not None else client.put(path, **kw)
        elif method == "PATCH":
            return client.patch(path, json=body, **kw) if body is not None else client.patch(path, **kw)
        elif method == "DELETE":
            return client.delete(path, **kw)
        elif method == "GET":
            return client.get(path, **kw)
        else:
            pytest.fail(f"Unknown method: {method}")

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_no_auth_returns_401(self, client, method, path, body):
        response = self._send(client, method, path, body)
        assert response.status_code == 401, (
            f"{method} {path} returned {response.status_code} without auth"
        )

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_valid_x_api_key_accepted(self, client, test_api_key, method, path, body):
        headers = {"X-API-Key": test_api_key}
        response = self._send(client, method, path, body, headers)
        assert response.status_code != 401, (
            f"{method} {path} returned 401 WITH valid API key"
        )

    @pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
    def test_valid_bearer_accepted(self, client, test_api_key, method, path, body):
        headers = {"Authorization": f"Bearer {test_api_key}"}
        response = self._send(client, method, path, body, headers)
        assert response.status_code != 401, (
            f"{method} {path} returned 401 WITH valid Bearer token"
        )

    def test_wrong_key_returns_401(self, client):
        response = client.post(
            "/api/v2/positions",
            json={"ticker": "TEST", "entry_price": 100, "quantity": 1},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    @pytest.mark.parametrize("method,path", PUBLIC_ROUTES)
    def test_public_routes_no_auth_needed(self, client, method, path):
        response = self._send(client, method, path)
        assert response.status_code not in (401, 403), (
            f"{method} {path} returned {response.status_code} — should not require auth"
        )


class TestAuthCompleteness:
    """Auto-discovery: every mutation route must either require auth or be explicitly exempted."""

    def test_no_unprotected_mutations(self, client):
        """Fail if any mutation route lacks auth and isn't in the exempt list."""
        from main import app

        all_mutations = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method in MUTATION_METHODS:
                        all_mutations.append((method, route.path, route))

        unprotected = []
        for method, path, route in all_mutations:
            if (method, path) in AUTH_EXEMPT_MUTATIONS or (method, path) in AUTH_TODO_LOCKDOWN:
                continue

            endpoint = getattr(route, "endpoint", None)
            if not endpoint:
                unprotected.append(f"{method} {path}")
                continue

            # The RESOLVED dependant tree — what FastAPI actually runs. A signature check
            # cannot see `@router.post(..., dependencies=[Depends(require_api_key)])`.
            has_auth = _has_auth(route.dependant) if hasattr(route, "dependant") else False

            if not has_auth:
                unprotected.append(f"{method} {path}")

        assert not unprotected, (
            f"Found {len(unprotected)} unprotected mutation route(s):\n"
            + "\n".join(f"  - {r}" for r in sorted(unprotected))
            + "\n\nEither add Depends(require_api_key) or add to AUTH_EXEMPT_MUTATIONS with justification."
        )


class TestSessionAuth:
    """Browser session cookie is accepted alongside the machine X-API-Key/Bearer path."""

    def test_session_cookie_accepted_on_mutation(self, client):
        from utils.session import issue_session, COOKIE_NAME
        token = issue_session()
        assert token, "issue_session() returned None — DASHBOARD_SESSION_SECRET not set"
        r = client.post(
            "/api/portfolio/cash-flows", json={"amount": 1},
            headers={"X-Requested-With": "XMLHttpRequest"}, cookies={COOKIE_NAME: token},
        )
        assert r.status_code != 401, r.text

    def test_session_mutation_without_csrf_header_is_403(self, client):
        from utils.session import issue_session, COOKIE_NAME
        token = issue_session()
        r = client.post("/api/portfolio/cash-flows", json={"amount": 1}, cookies={COOKIE_NAME: token})
        assert r.status_code == 403, r.text

    def test_invalid_session_cookie_rejected(self, client):
        from utils.session import COOKIE_NAME
        r = client.post(
            "/api/portfolio/cash-flows", json={"amount": 1},
            headers={"X-Requested-With": "XMLHttpRequest"}, cookies={COOKIE_NAME: "garbage.notasig"},
        )
        assert r.status_code == 401, r.text

    def test_machine_key_still_works(self, client, test_api_key):
        # dual-accept must NOT regress the VPS/server header path (CSRF-exempt)
        r = client.post("/api/portfolio/cash-flows", json={"amount": 1}, headers={"X-API-Key": test_api_key})
        assert r.status_code != 401, r.text

    def test_login_wrong_password_401(self, client):
        assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401

    def test_login_correct_password_then_logout(self, client):
        r = client.post("/api/auth/login", json={"password": "test-dashboard-password"})
        assert r.status_code == 200, r.text
        assert "pivot_session" in r.headers.get("set-cookie", "")
        assert client.post("/api/auth/logout").status_code == 200


# ── R-IV.417 — book-reading GETs are gated ──────────────────────────────────────────────

BOOK_PREFIXES = ("/api/analytics", "/api/portfolio", "/api/v2/positions", "/api/options/positions")
_AUTH_DEP_NAMES = {"require_api_key", "verify_pivot_key", "verify_api_key"}


def _has_auth(dependant) -> bool:
    """Walk FastAPI's RESOLVED dependency tree — what actually runs on a request.

    Deliberately not inspect.signature(): a gate declared as
    `@router.get(..., dependencies=[Depends(require_api_key)])` is invisible to a
    signature check, so that check would report a gated route as open (or, written the
    other way round, an open one as gated). The dependant is the ground truth.
    """
    for dep in dependant.dependencies:
        if getattr(dep.call, "__name__", "") in _AUTH_DEP_NAMES or _has_auth(dep):
            return True
    return False


def _ungated_book_gets(app) -> list:
    out = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if "GET" in methods and path.startswith(BOOK_PREFIXES):
            if not _has_auth(route.dependant):
                out.append(path)
    return sorted(out)


class TestBookReadsGated:
    """Every book-reading GET answers 401 without credentials and accepts all three
    credential forms. One or more samples per router that serves them."""

    SAMPLES = [
        "/api/analytics/trade-stats",                 # analytics router
        "/api/analytics/export/trades",               # named in R-IV.417(a)
        "/api/analytics/cash-flows",                  # analytics router
        "/api/portfolio/balances",                    # portfolio router
        "/api/portfolio/positions",                   # portfolio router
        "/api/portfolio/cash-flows",                  # portfolio router
        "/api/v2/positions?status=OPEN",              # unified_positions — formerly PUBLIC
        "/api/v2/positions/summary",                  # unified_positions — formerly PUBLIC
        "/api/v2/positions/greeks",                   # unified_positions
        "/api/analytics/footprint-correlation",       # footprint_correlation router
        "/api/analytics/confluence-validation",       # app-level route in main.py
    ]

    @pytest.mark.parametrize("path", SAMPLES)
    def test_no_credentials_is_401(self, client, path):
        r = client.get(path)
        assert r.status_code == 401, f"GET {path} returned {r.status_code} without credentials"

    @pytest.mark.parametrize("path", SAMPLES)
    def test_wrong_key_is_401(self, client, path):
        r = client.get(path, headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 401, f"GET {path} accepted a wrong key ({r.status_code})"

    @pytest.mark.parametrize("path", SAMPLES)
    def test_machine_key_accepted(self, client, test_api_key, path):
        r = client.get(path, headers={"X-API-Key": test_api_key})
        assert r.status_code not in (401, 403), f"GET {path} rejected a valid key ({r.status_code})"

    @pytest.mark.parametrize("path", SAMPLES)
    def test_bearer_accepted(self, client, test_api_key, path):
        r = client.get(path, headers={"Authorization": f"Bearer {test_api_key}"})
        assert r.status_code not in (401, 403), f"GET {path} rejected a valid Bearer ({r.status_code})"

    @pytest.mark.parametrize("path", SAMPLES)
    def test_session_cookie_accepted_without_csrf_header(self, client, path):
        """The browser path. A GET is not a mutation, so no X-Requested-With is needed —
        requiring it would blank every dashboard read."""
        from utils.session import issue_session, COOKIE_NAME
        token = issue_session()
        assert token, "issue_session() returned None — DASHBOARD_SESSION_SECRET not set"
        r = client.get(path, cookies={COOKIE_NAME: token})
        assert r.status_code not in (401, 403), f"GET {path} rejected a valid session ({r.status_code})"


class TestBookReadCompleteness:
    """A new book route cannot quietly ship open."""

    def test_no_ungated_get_under_book_prefixes(self, client):
        from main import app
        open_routes = _ungated_book_gets(app)
        assert not open_routes, (
            f"{len(open_routes)} book-reading GET route(s) have no auth:\n"
            + "\n".join(f"  - GET {p}" for p in open_routes)
            + "\n\nAdd dependencies=[Depends(require_api_key)] to the decorator. There is no "
              "exemption list for these prefixes, by design (R-IV.417(c))."
        )

    def test_there_is_something_to_check(self, client):
        """Guards against the completeness test passing because the prefix matched nothing."""
        from main import app
        n = sum(1 for r in app.routes
                if "GET" in (getattr(r, "methods", None) or set())
                and getattr(r, "path", "").startswith(BOOK_PREFIXES))
        assert n >= 30, f"only {n} GET routes under the book prefixes — the scan is not seeing the routers"

    def test_detector_reports_an_ungated_route(self):
        """Law 3 (Addendum 3): prove the detector CAN say "open" before trusting its silence.
        One gated and one ungated route under a book prefix; it must flag exactly one."""
        from fastapi import Depends, FastAPI
        from utils.pivot_auth import require_api_key

        probe = FastAPI()

        @probe.get("/api/portfolio/__probe_gated", dependencies=[Depends(require_api_key)])
        async def _gated():
            return {}

        @probe.get("/api/portfolio/__probe_param_gated")
        async def _param_gated(_=Depends(require_api_key)):
            return {}

        @probe.get("/api/portfolio/__probe_open")
        async def _open():
            return {}

        @probe.get("/elsewhere/__probe_open")
        async def _out_of_scope():
            return {}

        assert _ungated_book_gets(probe) == ["/api/portfolio/__probe_open"]


# ── R-IV.419(a) — write routes that had no auth of their own are gated ──────────────────

# Machine-only: the handler ALSO requires X-API-Key after the gate, so a browser session is
# rightly refused there (defence in depth for a VPS endpoint, not a defect). Module scope,
# because a comprehension inside a class body cannot see class-level names.
_MACHINE_ONLY_WRITES = frozenset({"/api/hermes/analysis"})


class TestWriteRoutesGated:
    """No credentials -> 401 (before the handler runs, so nothing is written); a machine key
    is accepted; a browser session is accepted only WITH the CSRF header."""

    ROUTES = [
        ("POST", "/api/committee/quick-review", {"ticker": "SPY"}),
        ("PATCH", "/api/hermes/alerts/1/dismiss", None),
        ("POST", "/api/hermes/analysis", {"event_id": "1"}),
        ("PATCH", "/api/hydra/lightning/1/status", {"status": "dismissed"}),
        ("POST", "/api/hydra/refresh", None),
        ("POST", "/api/sectors/seed-constituents", None),
        ("POST", "/api/trade-watchlist", {"ticker": "SPY"}),
        ("PATCH", "/api/trade-watchlist/1", {"notes": "x"}),
        ("DELETE", "/api/trade-watchlist/1", None),
        ("POST", "/api/trade-watchlist/1/reactivate", None),
        ("POST", "/api/trip-wires/ceasefire/off", None),
    ]

    @staticmethod
    def _send(client, method, path, body, headers=None, cookies=None):
        kw = {}
        if headers:
            kw["headers"] = headers
        if cookies:
            kw["cookies"] = cookies
        if body is not None and method != "DELETE":
            kw["json"] = body
        return client.request(method, path, **kw)

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_no_credentials_is_401(self, client, method, path, body):
        r = self._send(client, method, path, body)
        assert r.status_code == 401, f"{method} {path} -> {r.status_code} without credentials"

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_machine_key_accepted(self, client, test_api_key, method, path, body):
        r = self._send(client, method, path, body, headers={"X-API-Key": test_api_key})
        assert r.status_code not in (401, 403), f"{method} {path} rejected a valid key ({r.status_code})"

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_session_without_csrf_header_is_403(self, client, method, path, body):
        from utils.session import issue_session, COOKIE_NAME
        r = self._send(client, method, path, body, cookies={COOKIE_NAME: issue_session()})
        assert r.status_code == 403, f"{method} {path} -> {r.status_code}; a session write needs the CSRF header"

    @pytest.mark.parametrize("method,path,body",
                             [r for r in ROUTES if r[1] not in _MACHINE_ONLY_WRITES])
    def test_session_with_csrf_header_accepted(self, client, method, path, body):
        from utils.session import issue_session, COOKIE_NAME
        r = self._send(client, method, path, body,
                       headers={"X-Requested-With": "XMLHttpRequest"},
                       cookies={COOKIE_NAME: issue_session()})
        assert r.status_code not in (401, 403), f"{method} {path} rejected a valid session ({r.status_code})"


class TestExemptionsStillHold:
    """An exemption is a claim that the route authenticates some OTHER way. Each claim is
    checked here, so the exemption list cannot outlive the mechanism that justified it."""

    @pytest.mark.parametrize("path,body", [
        ("/api/chronos/refresh", None),
        ("/api/layout", {"layout": {}}),
    ])
    def test_own_check_rejects_without_credentials(self, client, path, body):
        r = client.post(path, json=body) if body is not None else client.post(path)
        assert r.status_code == 401, f"POST {path} -> {r.status_code}; its own auth check is gone"

    @pytest.mark.parametrize("path", ["/api/webhook/pythia", "/webhook/mp_levels"])
    def test_fail_closed_webhook_rejects_without_secret(self, client, path):
        r = client.post(path, json={"ticker": "SPY"})
        assert r.status_code in (401, 503), (
            f"POST {path} -> {r.status_code}; a fail-closed webhook must reject a secretless body")

    @pytest.mark.parametrize("path,body,enforce_env,secret_env", [
        ("/api/webhook/hermes", {"ticker": "SPY"}, "WEBHOOK_HERMES_ENFORCE", "HERMES_WEBHOOK_SECRET"),
        ("/webhook/footprint", {"ticker": "SPY"}, "WEBHOOK_FOOTPRINT_ENFORCE", "TRADINGVIEW_WEBHOOK_SECRET"),
    ])
    def test_observe_webhook_rejects_once_enforce_is_on(self, client, monkeypatch,
                                                        path, body, enforce_env, secret_env):
        """These two gate on validate_webhook_secret behind an enforce switch. The exemption
        is only honest if that switch actually closes them — proven here."""
        monkeypatch.setenv(enforce_env, "true")
        monkeypatch.setenv(secret_env, "test-webhook-secret-for-enforce")
        r = client.post(path, json=body)
        assert r.status_code == 401, (
            f"POST {path} -> {r.status_code} with {enforce_env}=true and no secret; "
            f"the flip-day switch does not close this route")

    def test_mcp_app_is_built_with_an_auth_provider(self):
        import inspect as _inspect
        from hub_mcp import server
        src = _inspect.getsource(server)
        assert "auth=build_oauth_provider()" in src, "the MCP app no longer wires its OAuth provider"

    def test_mcp_oauth_provider_is_built_when_configured(self, monkeypatch):
        """The MCP exemption holds only while the provider is actually built."""
        from hub_mcp import auth as mcp_auth
        monkeypatch.setenv(mcp_auth.GITHUB_CLIENT_ID_ENV, "id")
        monkeypatch.setenv(mcp_auth.GITHUB_CLIENT_SECRET_ENV, "secret")
        monkeypatch.setenv(mcp_auth.ALLOWED_USERS_ENV, "someone")
        assert mcp_auth.build_oauth_provider() is not None


# ─────────────────────────────────────────────────────────────────────────────
# R-IV.503(b) — ROUTE-DISCOVERED book-read coverage.
#
# BOOK_PREFIXES above is an ASSUMPTION, and it is the assumption that hid six
# routes serving the principal's holdings on a public repo: /api/hydra/exposure,
# /api/alerts/earnings/check-positions, /api/flow/radar, /api/chronos/book-impact,
# /api/pending-trades and /api/signals/statistics. Not one of them starts with a
# book prefix, so the prefix test passed while all six answered without
# credentials.
#
# This check asks what the handler TOUCHES, not where it is mounted. A GET whose
# handler reads a book table must require auth, wherever it lives.
# ─────────────────────────────────────────────────────────────────────────────

BOOK_TABLES = {
    "unified_positions", "position_lots", "position_legs", "closed_positions",
    "options_positions", "pending_trades", "account_balances", "cash_flows",
    "trades", "trade_executions", "signal_outcomes", "portfolio_snapshots",
}

# Handlers that name a book table but do NOT serve its rows. Each is justified by
# reading the handler, and each is re-checked below, so an entry cannot outlive
# the reason for it.
BOOK_READ_EXEMPT_GETS: set = set()

_SRC_CACHE: dict = {}


def _fn_source(fn, depth=0, seen=None):
    """Source of `fn` plus the same-project functions it calls, to `depth`.

    A handler usually delegates its SQL to a helper, so reading only the handler
    would miss the table and call the route clean. Depth-limited and cycle-safe;
    the limit is stated rather than assumed complete.
    """
    import inspect as _i
    seen = seen if seen is not None else set()
    key = getattr(fn, "__qualname__", None) or repr(fn)
    if key in seen or depth > 2:
        return ""
    seen.add(key)
    try:
        src = _i.getsource(_i.unwrap(fn))
    except (OSError, TypeError):
        return ""
    out = [src]
    if depth < 2:
        g = getattr(_i.unwrap(fn), "__globals__", {}) or {}
        import ast
        try:
            tree = ast.parse(_i.cleandoc(src)) if src.strip().startswith(("def ", "async def ")) else ast.parse(src)
        except SyntaxError:
            try:
                import textwrap
                tree = ast.parse(textwrap.dedent(src))
            except SyntaxError:
                return "".join(out)
        # R-IV.511(a): follow REFERENCE edges, not only call edges.
        #
        # QUERY's first walk missed /api/signals/active for exactly this reason. Its
        # handler never calls the thing that reads the book — it hands it over:
        #
        #     swr.get_or_refresh(key, compute_fn=_compute_signals_active)
        #
        # A walker that reads `ast.Call.func` sees `get_or_refresh` and stops. The
        # name that matters is an ARGUMENT, and the book read happens a hop later
        # inside it. Every bare Name in the body is therefore resolved, whether it
        # is called here, passed as a positional, passed as a keyword, or stored.
        # It over-collects — a name that is merely mentioned gets resolved too —
        # and that is the right direction to be wrong in for a security check.
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name):
                    names.add(f.id)
                elif isinstance(f, ast.Attribute):
                    names.add(f.attr)
            elif isinstance(n, ast.Name):
                names.add(n.id)
            elif isinstance(n, ast.Attribute):
                names.add(n.attr)
        for nm in names:
            tgt = g.get(nm)
            if callable(tgt) and getattr(tgt, "__module__", "") and not getattr(tgt, "__module__", "").startswith(
                ("fastapi", "pydantic", "starlette", "builtins", "typing", "asyncio", "datetime", "json", "os", "re")
            ):
                out.append(_fn_source(tgt, depth + 1, seen))
    return "".join(out)


import re as _re

_SQL_CTX = ("from", "join", "into", "update", "table")


def _reads_table(src: str, table: str) -> bool:
    """True only where `table` appears in SQL position, not in prose.

    A bare substring test flagged four routes that merely contain the WORD:
    /api/congress/recent-trades (its own path string), /api/cta/signals/{ticker}
    ("unusual trades" in a sentence), and the two crypto routes (Binance/OKX
    `/trades` endpoints). A detector that cries wolf gets switched off, so it
    matches FROM/JOIN/INTO/UPDATE/TABLE <name> and nothing else.
    """
    # Built from character classes only: a SQL keyword, then non-word characters,
    # then the table name as a whole word. No backslash escapes, so the pattern
    # cannot be mangled by whatever writes this file.
    pat = _re.compile(
        "(?:^|[^A-Za-z0-9_])(?:" + "|".join(_SQL_CTX) + ")[^A-Za-z0-9_]+"
        + _re.escape(table) + "(?![A-Za-z0-9_])",
        _re.I,
    )
    return bool(pat.search(src))


def _book_reading_gets(app) -> list:
    """(path, tables) for every GET whose handler reaches a book table."""
    found = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        ep = getattr(route, "endpoint", None)
        if "GET" not in methods or not ep:
            continue
        key = f"{path}:{getattr(ep, '__qualname__', '')}"
        if key not in _SRC_CACHE:
            _SRC_CACHE[key] = _fn_source(ep)
        src = _SRC_CACHE[key]
        hit = sorted(t for t in BOOK_TABLES if _reads_table(src, t))
        if hit:
            found.append((path, hit))
    return sorted(found)


class TestBookReadsDiscoveredByHandler:
    """R-IV.503(b): discovery by what the handler touches, not by where it is mounted."""

    def test_the_six_named_routes_are_gated(self, client):
        """The routes AEGIS found open. Named explicitly so a regression is unmistakable."""
        from main import app
        six = {
            "/api/hydra/exposure",
            "/api/alerts/earnings/check-positions",
            "/api/flow/radar",
            "/api/chronos/book-impact",
            "/api/pending-trades",
            "/api/signals/statistics",
        }
        by_path = {getattr(r, "path", ""): r for r in app.routes
                   if "GET" in (getattr(r, "methods", None) or set())}
        missing = sorted(p for p in six if p not in by_path)
        assert not missing, f"route(s) vanished from the app: {missing}"
        ungated = sorted(p for p in six if not _has_auth(by_path[p].dependant))
        assert not ungated, (
            "R-IV.503(b) routes are open again:\n" + "\n".join(f"  - GET {p}" for p in ungated))

    @pytest.mark.parametrize("path", sorted([
        "/api/hydra/exposure",
        "/api/alerts/earnings/check-positions",
        "/api/flow/radar",
        "/api/chronos/book-impact",
        "/api/pending-trades",
        "/api/signals/statistics",
    ]))
    def test_six_answer_401_without_credentials(self, client, path):
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", sorted([
        "/api/hydra/exposure", "/api/flow/radar", "/api/pending-trades",
        "/api/chronos/book-impact", "/api/signals/statistics",
        "/api/alerts/earnings/check-positions",
    ]))
    def test_six_accept_a_session_cookie(self, client, path):
        """The dashboard path — a GET needs no X-Requested-With, or every read blanks."""
        from utils.session import issue_session, COOKIE_NAME
        token = issue_session()
        assert token, "issue_session() returned None — DASHBOARD_SESSION_SECRET not set"
        r = client.get(path, cookies={COOKIE_NAME: token})
        assert r.status_code not in (401, 403), f"GET {path} rejected a valid session ({r.status_code})"

    def test_no_ungated_get_touches_a_book_table(self, client):
        """The general rule. No prefix list — the prefix list is what hid the six."""
        from main import app
        offenders = [(p, t) for p, t in _book_reading_gets(app)
                     if p not in BOOK_READ_EXEMPT_GETS
                     and not _has_auth({r.path: r for r in app.routes
                                        if getattr(r, "path", "") == p
                                        and "GET" in (getattr(r, "methods", None) or set())}[p].dependant)]
        assert not offenders, (
            f"{len(offenders)} GET route(s) read a book table without auth:\n"
            + "\n".join(f"  - GET {p}  (touches: {', '.join(t)})" for p, t in offenders)
            + "\n\nGate with Depends(require_api_key), or justify in BOOK_READ_EXEMPT_GETS "
              "after reading the handler.")

    def test_the_discovery_itself_works(self, client):
        """A test that can't find anything passes for the wrong reason."""
        from main import app
        found = _book_reading_gets(app)
        assert len(found) >= 6, (
            f"handler discovery found only {len(found)} book-reading GETs — the scan is broken, "
            "not the app")

    def test_every_exemption_still_lacks_book_rows(self, client):
        """An exemption cannot outlive the reading that justified it."""
        from main import app
        paths = {p for p, _ in _book_reading_gets(app)}
        stale = sorted(p for p in BOOK_READ_EXEMPT_GETS if p not in paths)
        assert not stale, f"exemption(s) no longer touch a book table — delete them: {stale}"
