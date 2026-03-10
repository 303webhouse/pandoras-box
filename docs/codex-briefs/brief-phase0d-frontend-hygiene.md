# Brief: Phase 0D — Frontend Hygiene

**Priority:** MEDIUM — Dead endpoint calls cause silent 404s, wasted network requests, and console noise. Redundant polling adds unnecessary backend load.
**Target:** Frontend (`frontend/app.js`)
**Estimated time:** 45–60 minutes
**Prerequisites:** Phase 0C complete (positions unified)

---

## Context

The frontend calls several backend endpoints that no longer exist. These always return 404 but fail silently, adding latency to page load and polluting the browser console. Additionally, multiple polling loops refresh the same data at different intervals.

The external audit (GPT-5.4) flagged the hybrid scanner as potentially dead code. **It is NOT dead** — the frontend still actively uses `hybrid/price/{ticker}` for position price updates and `hybrid/combined/{ticker}` for analyzer context. The hybrid scanner backend and routes should be KEPT.

---

## Task 1: Remove dead `loadBiasData()` function

**File: `frontend/app.js`**

`loadBiasData()` (around line 1315) calls `bias-auto/status` which does not exist. It always fails and falls back to `loadBiasDataFallback()`. The actual working bias functions are `fetchCompositeBias()` and `fetchTimeframeBias()` which call `/bias/composite` and `/bias/composite/timeframes`.

Find the `loadBiasData()` function (starts around line 1315, `async function loadBiasData()`).

Replace the entire function body so it just calls the fallback directly:

```javascript
async function loadBiasData() {
    // bias-auto/status endpoint removed. Use composite endpoints directly.
    await loadBiasDataFallback();
}
```

This preserves the function name (since it's called from the init sequence) while eliminating the dead fetch.

## Task 2: Remove dead `fetchBiasShiftStatus()` call

`fetchBiasShiftStatus()` (around line 3137) calls `bias-auto/shift-status` which does not exist. It's polled every 5 minutes (line ~990).

Find the polling interval:
```javascript
    setInterval(() => {
        fetchBiasShiftStatus();
    }, 5 * 60 * 1000); // 5 minutes
```
Delete this `setInterval` block entirely.

Then find the `fetchBiasShiftStatus()` function definition and either:
- Delete it entirely, OR
- Replace the body with a no-op if other code calls it:
```javascript
async function fetchBiasShiftStatus() {
    // bias-auto/shift-status endpoint removed. Shift data now comes from composite.
    return;
}
```

Also find and delete `updateBiasShiftDisplay()` if it's only called from `fetchBiasShiftStatus()`. Grep for `updateBiasShiftDisplay` to confirm no other callers.

## Task 3: Remove dead `loadCyclicalBiasFallback()`

`loadCyclicalBiasFallback()` (around line 3260) calls `bias-auto/CYCLICAL` which does not exist.

Find `async function loadCyclicalBiasFallback()` and replace with:
```javascript
async function loadCyclicalBiasFallback() {
    // bias-auto/CYCLICAL endpoint removed. Cyclical data comes from timeframe cards.
    return;
}
```

## Task 4: Remove dead `signals/ticker/{ticker}` call from analyzer

The analyzer context fetch (around line 5784) fires 6 parallel requests. One of them is dead:

```javascript
const [ctaResponse, sectorResponse, biasResponse, flowResponse, signalsResponse, priceResponse] = await Promise.all([
    fetch(`${API_URL}/cta/analyze/${ticker}`),
    fetch(`${API_URL}/hybrid/combined/${ticker}`),
    fetch(`${API_URL}/bias-auto/status`),          // ← DEAD
    fetch(`${API_URL}/flow/ticker/${ticker}`),
    fetch(`${API_URL}/signals/ticker/${ticker}`),   // ← DEAD
    fetch(`${API_URL}/hybrid/price/${ticker}`)       // ← KEEP
]);
```

Replace with:
```javascript
const [ctaResponse, sectorResponse, biasResponse, flowResponse, priceResponse] = await Promise.all([
    fetch(`${API_URL}/cta/analyze/${ticker}`),
    fetch(`${API_URL}/hybrid/combined/${ticker}`),
    fetch(`${API_URL}/bias/composite`),
    fetch(`${API_URL}/flow/ticker/${ticker}`),
    fetch(`${API_URL}/hybrid/price/${ticker}`)
]);
```

Note: removed `signals/ticker/{ticker}` entirely (no replacement needed — signal data for that ticker isn't available per-ticker) and replaced `bias-auto/status` with `bias/composite` (which actually works).

Also update the destructuring on the lines that follow to remove `signalsResponse` and update variable names. The code below that tries to parse `signalsData` will need to be removed or stubbed:

```javascript
const ctaData = await ctaResponse.json();
const sectorData = await sectorResponse.json();
const biasData = await biasResponse.json();
const flowData = await flowResponse.json();
const priceData = await priceResponse.json();
```

Then find where `signalsData` is used to populate a UI card. Either remove that card section or stub it with a "no data" message.

## Task 5: Consolidate polling intervals

Current polling is scattered and partially redundant:

| What | Interval | Function | Status |
|------|----------|----------|--------|
| Positions (v2) | 10s | `loadOpenPositionsEnhanced()` | Too aggressive |
| Portfolio positions | 60s | `loadPortfolioPositions()` | Partially redundant |
| Portfolio balances | 60s | `loadPortfolioBalances()` | OK |
| Price updates | 30s | `updateCurrentPrices()` | Per-ticker loop |
| Bias shift | 5m | `fetchBiasShiftStatus()` | Dead endpoint (removed in Task 2) |
| Timeframe bias | 2m | `fetchTimeframeBias()` | OK |
| Pivot health | 5m | `checkPivotHealth()` | OK |
| Redis health | 2m | `checkRedisHealth()` | OK |

Changes:

### 5a: Slow down position refresh from 10s to 30s

Find (around line 1006):
```javascript
    setInterval(() => {
        if (document.visibilityState === 'visible') {
            loadOpenPositionsEnhanced();
        }
    }, 10 * 1000);
```

Change to:
```javascript
    setInterval(() => {
        if (document.visibilityState === 'visible') {
            loadOpenPositionsEnhanced();
        }
    }, 30 * 1000);
```

30 seconds is still fast enough for a single user. The WebSocket broadcast already pushes position updates in real-time when changes happen.

### 5b: Remove redundant portfolio positions polling

Find (around line 2186):
```javascript
setInterval(loadPortfolioPositions, 60000);
```

`loadPortfolioPositions()` calls `GET /api/portfolio/positions` which now reads from the same `unified_positions` table as `loadOpenPositionsEnhanced()`. They're fetching the same data with different renderers.

Remove the `setInterval` line. Let the 30s position refresh handle it. If the portfolio summary table still needs a separate render, call `loadPortfolioPositions()` from inside `loadOpenPositionsEnhanced()` after the v2 data loads (so one fetch drives both renders).

### 5c: Merge price updates into position refresh

The price updater (`updateCurrentPrices()`) runs every 30s and loops over each open ticker, hitting `hybrid/price/{ticker}` individually. This is N+1 fetching.

Option A (simple): Keep it separate but increase to 60s since mark-to-market already updates via Polygon every 15 minutes on the backend. The hybrid price fetch is for interim display.

Option B (better): Remove `updateCurrentPrices()` entirely and rely on the `current_price` field from `unified_positions` that gets set by mark-to-market. The v2 positions endpoint already returns `current_price` and `unrealized_pnl`.

**Recommend Option A for now** (less risk). Change:
```javascript
priceUpdateInterval = setInterval(updateCurrentPrices, 30000);
```
To:
```javascript
priceUpdateInterval = setInterval(updateCurrentPrices, 60000);
```

---

## Task 6: Document hybrid scanner as ACTIVE

The GPT audit flagged hybrid scanner as potentially dead. It is NOT.

**File: `backend/api/hybrid_scanner.py`**

Add a comment at the top of the file:
```python
# NOTE: Despite UI for hybrid scanner being killed in Brief 09,
# the following endpoints are still actively used by the frontend:
#   - GET /hybrid/price/{ticker}  — position card price updates (updateCurrentPrices)
#   - GET /hybrid/combined/{ticker} — analyzer per-ticker context
# DO NOT remove this router without updating frontend/app.js.
```

---

## Definition of Done

1. `loadBiasData()` no longer calls `bias-auto/status`
2. `fetchBiasShiftStatus()` polling removed — no more 5-minute calls to dead endpoint
3. `loadCyclicalBiasFallback()` no longer calls `bias-auto/CYCLICAL`
4. Analyzer context no longer calls `signals/ticker/{ticker}` or `bias-auto/status`
5. Position polling changed from 10s to 30s
6. Portfolio positions 60s polling removed (redundant)
7. Price update interval changed from 30s to 60s
8. Zero 404 errors in browser console on page load and during normal operation
9. Hybrid scanner documented as active dependency

---

## What this brief does NOT do

- Does NOT remove the hybrid scanner backend (it's still in use)
- Does NOT rewrite the analyzer to use different endpoints (just removes dead ones)
- Does NOT add WebSocket-based position updates (future improvement)
- Does NOT touch backend code beyond the one comment in hybrid_scanner.py

---

## Verification

After deploy:
1. Open dashboard in browser
2. Open browser DevTools → Network tab
3. Look for any red/failed requests (should be zero)
4. Check Console for error messages (should be clean)
5. Verify bias cards still load correctly
6. Verify position cards still show prices
7. Click into the analyzer on any ticker — verify CTA, sector, flow, price data loads
8. Monitor Network tab for 30 seconds — verify polling intervals are correct (no 10s position spam)
