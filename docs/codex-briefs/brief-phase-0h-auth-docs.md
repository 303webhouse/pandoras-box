# Brief: Phase 0H — Auth Lockdown Completion + Doc Fixes

## Summary

GPT-5.4 post-audit found 21 mutation routes still exposed without authentication, plus stale docs. This brief locks down every remaining public mutation endpoint using the same `Depends(require_api_key)` pattern already in place, adds an auto-discovery auth test to prevent future drift, and fixes doc inaccuracies.

**Out of scope:** Options in-memory ledger migration (separate brief — architectural decision needed).

## Auth Lockdown

Every mutation route below needs `_=Depends(require_api_key)` added to its function signature. Import `from utils.pivot_auth import require_api_key` and `from fastapi import Depends` if not already present.

### `backend/api/watchlist.py` — 10 routes, 0 currently protected

```
Line 525:  PUT    /watchlist
Line 550:  POST   /watchlist/add
Line 588:  POST   /watchlist/remove
Line 624:  DELETE /watchlist/clear
Line 639:  POST   /watchlist/reset
Line 656:  POST   /watchlist/sector-strength
Line 830:  PATCH  /watchlist/tickers/{symbol}/mute
Line 862:  PATCH  /watchlist/tickers/bulk-mute
Line 904:  DELETE /watchlist/tickers/{symbol}
Line 939:  POST   /watchlist/tickers/add
```

Pattern — add `_=Depends(require_api_key)` as the LAST parameter of each async function:
```python
# BEFORE
async def update_watchlist(body: WatchlistUpdate):

# AFTER
async def update_watchlist(body: WatchlistUpdate, _=Depends(require_api_key)):
```

### `backend/webhooks/circuit_breaker.py` — 5 routes, 0 currently protected

```
Line 589:  POST /circuit_breaker           (webhook — see note below)
Line 634:  POST /circuit_breaker/reset
Line 668:  POST /circuit_breaker/accept_reset
Line 674:  POST /circuit_breaker/reject_reset
Line 680:  POST /circuit_breaker/test/{trigger}
```

**Note on POST /circuit_breaker (line 589):** This is the TradingView webhook receiver. TradingView cannot send API key headers. Two options:
- **Option A (recommended):** Leave the webhook endpoint public but protect the 4 management routes (reset, accept_reset, reject_reset, test). The webhook only writes data — the management routes are what's dangerous.
- **Option B:** Add a query-param token check for the webhook (e.g., `?token=XXX`). More secure but requires updating TradingView alerts.

**Use Option A** — protect lines 634, 668, 674, 680 only. Leave line 589 as-is with a comment explaining why.

### `backend/api/options_positions.py` — 5 routes, 0 currently protected

```
Line 212:  POST   /options/positions
Line 339:  PUT    /options/positions/{position_id}
Line 381:  POST   /options/positions/{position_id}/close
Line 441:  DELETE /options/positions/{position_id}
Line 475:  POST   /options/positions/sync-from-db
```

### `backend/api/portfolio.py` — 1 route missing auth

```
Line 657:  POST /cash-flows
```

The other 5 mutation routes in this file already have `require_api_key`. Only `/cash-flows` was missed.

## Auto-Discovery Auth Test

Replace the hardcoded `PROTECTED_ROUTES` list in `backend/tests/test_auth.py` with a test that introspects the actual mounted FastAPI app.

```python
import pytest
from main import app

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Routes that are intentionally public (with justification)
AUTH_EXEMPT_MUTATIONS = {
    # TradingView webhook — can't send headers, data-write only
    ("POST", "/webhook/circuit_breaker"),
    # Alert ingestion webhooks from TradingView
    ("POST", "/webhook/tradingview"),
    ("POST", "/webhook/signal"),
    # Health/status endpoints
    ("POST", "/webhook/alerts/pivot"),
}

def get_all_mutation_routes():
    """Introspect FastAPI app for all mutation routes."""
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method in MUTATION_METHODS:
                    routes.append((method, route.path))
    return routes

class TestAuthCompleteness:
    """Every mutation route must either require auth or be explicitly exempted."""

    def test_no_unprotected_mutations(self):
        """Fail if any mutation route lacks auth and isn't in the exempt list."""
        all_mutations = get_all_mutation_routes()
        unprotected = []

        for method, path in all_mutations:
            if (method, path) in AUTH_EXEMPT_MUTATIONS:
                continue
            # Check if route has require_api_key dependency
            for route in app.routes:
                if hasattr(route, "path") and route.path == path:
                    deps = getattr(route, "dependencies", []) or []
                    endpoint = getattr(route, "endpoint", None)
                    # Check function signature for Depends(require_api_key)
                    has_auth = False
                    if endpoint:
                        import inspect
                        sig = inspect.signature(endpoint)
                        for param in sig.parameters.values():
                            if param.default and hasattr(param.default, "dependency"):
                                dep_func = param.default.dependency
                                if dep_func.__name__ == "require_api_key":
                                    has_auth = True
                                    break
                    if not has_auth:
                        unprotected.append(f"{method} {path}")

        assert not unprotected, (
            f"Found {len(unprotected)} unprotected mutation route(s):\n"
            + "\n".join(f"  - {r}" for r in unprotected)
            + "\n\nEither add Depends(require_api_key) or add to AUTH_EXEMPT_MUTATIONS with justification."
        )
```

**Important:** The above is a reference implementation. The actual introspection may need adjustment depending on how FastAPI exposes dependencies. The key requirement is: if a new mutation route is added without auth, this test MUST fail. Claude Code should verify the introspection approach works and adjust as needed.

Keep the existing parametrized tests (`test_protected_returns_401_without_key`, etc.) but update `PROTECTED_ROUTES` to include ALL now-protected routes (the 21 added by this brief + the existing ones).

## Doc Fixes

### `CLAUDE.md`

1. **Line 41:** Change "Served from VPS" to "Served from Railway (static files)" — the frontend is served by the Railway FastAPI app, not VPS.

2. **Lines 95, 214, 235:** Replace all references to `backend/api/v2_positions.py` with `backend/api/unified_positions.py`. That file was renamed during Phase 0C and the old name no longer exists.

### `docs/TRADING_TEAM_LOG.md`

**Line 98:** Remove the merge artifact `>>>>>>> Stashed changes`. Check surrounding lines for any other stash/merge markers and clean them up.

### `DEVELOPMENT_STATUS.md`

Search for any references to `open_positions` as "canonical" or "source of truth" and update to reflect that `unified_positions` is the single position system. The old `open_positions` and `positions` tables are deprecated.

## Frontend Note

The frontend (`app.js`) already sends the API key header via `authHeaders()` on all fetch calls. Locking down these backend routes should not break the frontend — it's already sending auth, the backend just wasn't checking it.

**Exception:** Any direct browser navigation to these endpoints (unlikely for POST/PUT/PATCH/DELETE) would fail. Verify no GET routes were accidentally caught.

## Definition of Done

- [ ] 20 mutation routes locked down with `Depends(require_api_key)` (21 minus the CB webhook)
- [ ] CB webhook (POST /circuit_breaker) left public with explanatory comment
- [ ] POST /cash-flows locked down
- [ ] Auto-discovery auth test passes
- [ ] Existing 93 tests still pass
- [ ] CLAUDE.md: "Served from VPS" fixed, v2_positions.py references updated
- [ ] TRADING_TEAM_LOG.md: merge artifact removed
- [ ] DEVELOPMENT_STATUS.md: open_positions references corrected
