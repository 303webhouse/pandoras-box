# Brief: Phase 0B — Auth Lockdown

**Priority:** HIGH — Public Railway URL means anyone who discovers it can create/close positions, inject fake signals, and submit bogus committee results.
**Target:** Railway backend (`backend/`)
**Estimated time:** 60–90 minutes
**Prerequisites:** None — all work is in the repo, auto-deploys on push

---

## Context

The Railway backend is publicly accessible at `pandoras-box-production.up.railway.app`. An external audit (GPT-5.4, March 9) found that most state-changing endpoints have no authentication. The existing auth is also inconsistent — some routes check `X-API-Key` header, others check `Authorization: Bearer`, both against the same `PIVOT_API_KEY` env var.

This brief standardizes auth and applies it to every mutation surface.

---

## Task 1: Create unified auth dependency

Replace the two inconsistent auth functions with one that accepts EITHER header format.

**File: `backend/utils/pivot_auth.py`**

Replace the entire file contents with:

```python
"""
Pivot API key authentication.
Accepts either X-API-Key or Authorization: Bearer <key>.
Used as a FastAPI dependency on all mutation routes.
"""

from __future__ import annotations

import os
from fastapi import Header, HTTPException

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY") or ""


def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    """Validate API key from either X-API-Key or Authorization: Bearer header."""
    if not PIVOT_API_KEY:
        raise HTTPException(status_code=503, detail="PIVOT_API_KEY not configured")

    # Check X-API-Key first (frontend, some VPS callers)
    if x_api_key and x_api_key == PIVOT_API_KEY:
        return x_api_key

    # Check Authorization: Bearer (VPS committee bridge, Pivot bot)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token == PIVOT_API_KEY:
            return token

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# Keep old name as alias so existing imports don't break
verify_pivot_key = require_api_key
verify_api_key = require_api_key
```

This preserves backward compatibility — existing `Depends(verify_pivot_key)` and `Depends(verify_api_key)` calls will still work.

## Task 2: Add auth to unified_positions.py

This is the most critical file — it controls all position CRUD.

**File: `backend/api/unified_positions.py`**

Add import at the top (near the other imports):

```python
from fastapi import APIRouter, HTTPException, Header, Query, Request, Depends
from utils.pivot_auth import require_api_key
```

Note: `Depends` may already be imported. If not, add it to the existing `from fastapi import ...` line.

Then add `_=Depends(require_api_key)` to every mutation route signature:

### POST /v2/positions (create)
Find:
```python
async def create_position(req: CreatePositionRequest):
```
Replace with:
```python
async def create_position(req: CreatePositionRequest, _=Depends(require_api_key)):
```

### PATCH /v2/positions/account-balance
Find:
```python
async def update_account_balance(request: Request):
```
Replace with:
```python
async def update_account_balance(request: Request, _=Depends(require_api_key)):
```

### PATCH /v2/positions/{position_id} (update)
Find:
```python
async def update_position(position_id: str, req: UpdatePositionRequest):
```
Replace with:
```python
async def update_position(position_id: str, req: UpdatePositionRequest, _=Depends(require_api_key)):
```

### POST /v2/positions/{position_id}/close
Find:
```python
async def close_position(position_id: str, req: ClosePositionRequest):
```
Replace with:
```python
async def close_position(position_id: str, req: ClosePositionRequest, _=Depends(require_api_key)):
```

### DELETE /v2/positions/{position_id}
Find:
```python
async def delete_position(position_id: str):
```
Replace with:
```python
async def delete_position(position_id: str, _=Depends(require_api_key)):
```

### POST /v2/positions/bulk
Find:
```python
async def bulk_create_positions(req: BulkRequest):
```
Replace with:
```python
async def bulk_create_positions(req: BulkRequest, _=Depends(require_api_key)):
```

### POST /v2/positions/reconcile
Find:
```python
async def reconcile_positions(req: ReconcileRequest):
```
Replace with:
```python
async def reconcile_positions(req: ReconcileRequest, _=Depends(require_api_key)):
```

### POST /v2/positions/mark-to-market
Find:
```python
async def mark_to_market():
```
Replace with:
```python
async def mark_to_market(_=Depends(require_api_key)):
```

**Leave GET routes (list, summary, greeks, single) unauthenticated** — read-only data is not a mutation risk, and the dashboard needs to fetch without friction.

## Task 3: Add auth to committee_bridge.py

**File: `backend/api/committee_bridge.py`**

Add import:
```python
from fastapi import APIRouter, HTTPException, Query, Depends
from utils.pivot_auth import require_api_key
```

Add auth to POST endpoint:

Find:
```python
async def submit_committee_results(body: CommitteeResult):
```
Replace with:
```python
async def submit_committee_results(body: CommitteeResult, _=Depends(require_api_key)):
```

**Leave GET /committee/queue and /committee/history unauthenticated** — read-only.

## Task 4: Add auth to trade_ideas.py

**File: `backend/api/trade_ideas.py`**

Find the file and add auth import, then add `_=Depends(require_api_key)` to:
- PATCH endpoint that changes signal status
- POST endpoint that expires signals

Same pattern as above. Leave GET/read endpoints unauthenticated.

## Task 5: Add webhook secret to TradingView endpoints

TradingView allows you to include a custom field in webhook payloads. We'll use a `secret` field.

**File: `backend/webhooks/tradingview.py`**

Add near the top of the file:
```python
import os

WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET") or ""
```

Then at the START of `receive_tradingview_alert()`, before any processing:

Find the beginning of the function body (right after the function signature). Add:
```python
    # Webhook secret validation
    if WEBHOOK_SECRET:
        payload_secret = getattr(alert, 'secret', None) or ""
        if payload_secret != WEBHOOK_SECRET:
            logger.warning("Rejected TradingView webhook — invalid secret from %s", alert.ticker if hasattr(alert, 'ticker') else 'unknown')
            raise HTTPException(status_code=401, detail="Invalid webhook secret")
```

Also add `secret` as an optional field to the `TradingViewAlert` Pydantic model:
```python
    secret: Optional[str] = None
```

Do the same for `receive_breadth_data`, `receive_tick_data`, and `receive_mcclellan_data` — add secret field to their payload models and validate at the top of each handler.

**IMPORTANT:** After deploy, you'll need to:
1. Set `TRADINGVIEW_WEBHOOK_SECRET` env var in Railway
2. Add the secret field to all TradingView alert messages in PineScript (add `"secret": "YOUR_SECRET"` to the JSON payload)
3. Until the secret is set in Railway, the `if WEBHOOK_SECRET:` guard means existing webhooks will continue to work (no secret = no check)

## Task 6: Restrict CORS

**File: `backend/main.py`**

Find:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Replace with:
```python
# CORS — restrict to known frontend origins
_cors_origins = os.getenv("ALLOWED_ORIGINS") or "*"
if _cors_origins == "*":
    _allowed_origins = ["*"]
else:
    _allowed_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This reads from `ALLOWED_ORIGINS` env var. Set it in Railway to the actual dashboard URL(s). Until it's set, defaults to `*` (no breakage).

## Task 7: Add API key to frontend

**File: `frontend/app.js`**

The frontend needs to send `X-API-Key` header on all POST/PATCH/DELETE requests.

Search for every `fetch(` call in `app.js` that uses `method: 'POST'` or `method: 'PATCH'` or `method: 'DELETE'`. Each one needs the API key header added.

First, add a config constant near the top of the file:
```javascript
// API authentication — key is embedded for single-user system
// This is visible in source but combined with CORS restrictions provides adequate protection
const API_KEY = 'PIVOT_KEY_PLACEHOLDER';
```

Then create a helper function:
```javascript
function authHeaders(extraHeaders = {}) {
    return {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
        ...extraHeaders
    };
}
```

Then find every `fetch()` call with a mutation method and replace its `headers` with `authHeaders()`. For example:

Find patterns like:
```javascript
fetch(`${API_BASE}/v2/positions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
```

Replace headers with:
```javascript
fetch(`${API_BASE}/v2/positions`, {
    method: 'POST',
    headers: authHeaders(),
```

**AFTER DEPLOY:** Replace `PIVOT_KEY_PLACEHOLDER` with the actual `PIVOT_API_KEY` value. Since the frontend is served from the same Railway app (not a separate domain), the key is no more exposed than it already is in the browser network tab.

Alternatively, the backend could serve the key to the frontend via a config endpoint — but for a single-user system, the hardcoded approach is simpler.

## Task 8: Remove duplicate auth functions

After Task 1 creates the unified `require_api_key`, the old per-file auth functions are redundant.

**File: `backend/api/portfolio.py`**
Find and remove the local `verify_api_key` function definition (around line 24). Replace its import/usage with:
```python
from utils.pivot_auth import require_api_key
```
Change all `Depends(verify_api_key)` to `Depends(require_api_key)` in this file.

**File: `backend/api/macro.py`**
Same — remove local `verify_api_key`, import from `utils.pivot_auth`.

---

## DST Cron Note (informational, no action needed yet)

Phase 0B originally included DST cron fixes. However, IBKR is not yet funded, so the IBKR pollers (`ibkr_poller.py`, `ibkr_quotes.py`) aren't connecting to anything. The DST cron fix is deferred until IBKR account is funded. When that happens, update `openclaw/cron/jobs.json` to use `13-20 UTC` for EDT (March-November) or convert to IANA timezone-aware scheduling.

---

## Definition of Done

1. `backend/utils/pivot_auth.py` has ONE auth function (`require_api_key`) that accepts both `X-API-Key` and `Authorization: Bearer`
2. All POST/PATCH/DELETE routes in `unified_positions.py` require auth
3. `POST /committee/results` requires auth
4. Trade ideas mutation routes require auth
5. TradingView webhook handler checks `secret` field (gracefully skips if env var not set)
6. CORS reads from `ALLOWED_ORIGINS` env var (defaults to `*` until set)
7. Frontend `app.js` sends `X-API-Key` header on all mutation requests
8. No duplicate `verify_api_key` / `verify_api_key` functions in individual route files
9. All GET/read-only routes remain unauthenticated (no friction for dashboard reads)
10. `curl -X POST .../v2/positions` without auth returns 401

---

## What this brief does NOT do

- Does NOT add user accounts or session management (single-user system doesn't need it)
- Does NOT add auth to GET/read endpoints (read-only data, no mutation risk)
- Does NOT set the actual TradingView webhook secret in PineScript alerts (Nick does that manually)
- Does NOT set ALLOWED_ORIGINS in Railway env vars (Nick does that after deploy)
- Does NOT fix DST cron timing (deferred — IBKR not funded)
- Does NOT touch VPS scripts (they already send `Authorization: Bearer` via `verify_pivot_key`)

---

## Post-build checklist

1. Verify Railway auto-deploy: `curl https://pandoras-box-production.up.railway.app/health`
2. Verify auth works: `curl -X POST https://pandoras-box-production.up.railway.app/api/v2/positions -H 'Content-Type: application/json' -d '{"ticker":"TEST"}' ` → should return 401
3. Verify auth passes: same curl but add `-H 'X-API-Key: <actual key>'` → should return 400 (missing fields) not 401
4. Verify dashboard still works (frontend sends key correctly)
5. Nick: Set `TRADINGVIEW_WEBHOOK_SECRET` in Railway env vars, then add `"secret": "<value>"` to all PineScript alert JSON payloads
6. Nick: Set `ALLOWED_ORIGINS` in Railway env vars (e.g., `https://pandoras-box-production.up.railway.app`)
7. Nick: Replace `PIVOT_KEY_PLACEHOLDER` in `frontend/app.js` with actual key, push
