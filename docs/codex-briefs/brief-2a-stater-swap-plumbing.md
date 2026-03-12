# Brief 2A: Stater Swap Plumbing, Auth & Cleanup

## Summary

Fix the broken foundation under Stater Swap so BTC perp signals route correctly, auth gaps are closed, legacy coupling is removed, and dead code is cleaned up. No new features — just make the existing surface trustworthy.

## 1. Ticker Suffix Normalization

### Problem
TradingView sends Bybit perp tickers as `BTCUSDT.P`. The `is_crypto_ticker()` function in `backend/webhooks/tradingview.py` does a direct lookup against `CRYPTO_TICKERS` set, which doesn't include `.P` variants. BTC perp alerts silently classify as `EQUITY`.

### Fix
In `backend/webhooks/tradingview.py`, update `is_crypto_ticker()` to normalize before lookup:

```python
def is_crypto_ticker(ticker: str) -> bool:
    """Check if a ticker is a cryptocurrency. Handles exchange suffixes like .P (perp)"""
    t = ticker.upper()
    # Strip common exchange suffixes
    for suffix in ('.P', 'PERP', '.PERP', '-PERP'):
        if t.endswith(suffix):
            t = t[:-len(suffix)]
            break
    return t in CRYPTO_TICKERS
```

Also add `BTCUSDT.P` and `ETHUSDT.P` explicitly to `CRYPTO_TICKERS` as a belt-and-suspenders fallback.

### Verify
After this change, a TradingView alert with `ticker: "BTCUSDT.P"` should produce `asset_class: "CRYPTO"` in the signals table.

## 2. Auth Lockdown on BTC Signal Routes

### Problem
BTC bottom-signal mutation routes in `backend/api/btc_signals.py` have no `require_api_key` dependency. Anyone who discovers the Railway URL can flip signal states.

### Fix
Add `_=Depends(require_api_key)` to every mutation route in `btc_signals.py`:

```
Line ~65:  POST /bottom-signals/refresh
Line ~96:  POST /bottom-signals/{signal_id}  (update_signal)
Line ~121: POST /bottom-signals/reset
Line ~132: POST /bottom-signals/{signal_id}/clear-override
```

Add import at top if not present:
```python
from fastapi import Depends
from utils.pivot_auth import require_api_key
```

Leave GET routes public (read-only data).

### Also check
The legacy dismiss route GPT flagged — search for `/signals/{id}/dismiss` or similar in `positions.py` or any route file without auth. If found, add auth.

## 3. Kill Legacy Crypto Signal Coupling

### Problem
Stater Swap loads signals from BOTH `/signals/active` (legacy) AND `/trade-ideas/grouped` (new). The legacy dismiss route is also still used.

### Fix in `frontend/app.js`

Search for crypto signal loading functions. They should ONLY use the trade-ideas endpoints:

- Initial crypto signal load: should use `/trade-ideas/grouped` with crypto filter, NOT `/signals/active`
- Signal dismiss: should use `/trade-ideas/{signal_id}/status` PATCH (same as Agora), NOT `/signals/{id}/dismiss`
- Signal accept: should use `/trade-ideas/{signal_id}/status` PATCH, NOT legacy routes

Specifically look at:
- `renderCryptoSignals()` (~line 3429) — what data source does it read from?
- `dismissCryptoSignal()` (~line 1501) — what endpoint does it call?
- `handleCryptoSignalAction()` (~line 1430) — what routes does it hit?

Reroute all to the trade-ideas API. The equity side already uses these correctly.

## 4. Symbol Propagation

### Problem
Coin selector changes the TradingView chart widget but doesn't propagate to API calls. Market data always fetches BTCUSDT regardless of selection.

### Fix

The backend endpoint `GET /api/crypto/market` already accepts a `symbol` query param (defaults to `BTCUSDT`). The frontend just doesn't pass it.

In `app.js`, find `loadCryptoMarketData()` (~line 4095):
- Read the currently selected coin from the coin chip UI state
- Pass it as `?symbol={selectedCoin}USDT` to the market endpoint

For key levels (`loadCryptoKeyLevels()` ~line 4055):
- If levels are hardcoded to BTC, make them symbol-aware or hide them when non-BTC is selected
- For Phase 2A, it's acceptable to show BTC levels with a "BTC only" label and hide for other coins

For bottom signals panel:
- This is inherently BTC-only (the 9 derivative indicators are BTC-specific)
- Add a visible label: "BTC Confluence" and keep it visible regardless of coin selection
- Do NOT try to make it multi-coin — that's a Phase 2E task

## 5. Ticker Whitelist Consistency

### Problem
UI coin chips include HYPE and ASTR but they're missing from the crypto classification logic.

### Fix
Either:
- **Option A (recommended for now):** Remove HYPE and ASTR chips from `frontend/index.html` since we're BTC-focused for Phase 2. Keep BTC, ETH, SOL as the coin options.
- **Option B:** Add HYPE, ASTR, and their USDT pairs to `CRYPTO_TICKERS` in `tradingview.py` AND to the frontend whitelist functions.

Use Option A — BTC-first, expand later.

## 6. Dead Code Cleanup

### Frontend (`app.js`)
Remove or mark as deprecated:
- References to `cryptoChartTabs`, `cryptoFilterLong`, `cryptoScoreThreshold` if the DOM elements don't exist in `index.html`
- Stale comment at ~line 6565: `// MOVED TO CRYPTO-SCALPER: BTC session functions relocated to dedicated crypto-scalper application` — the standalone scalper is dead, this comment is misleading
- Any functions that reference the standalone scalper's localhost:8001

### Fix accept modal
Find the crypto accept modal — it labels position size as "Contracts" (equity term). For crypto perps, this should say "Contracts" too actually (perp futures ARE contracts), but verify the sizing logic is calculating BTC perp contract size, not equity shares.

## 7. Test Coverage

Add route smoke tests to `backend/tests/test_frontend_routes.py` (or appropriate test file):

```python
# Crypto endpoint smoke tests
("GET", "/api/crypto/market"),
("GET", "/api/btc/bottom-signals"),
("GET", "/api/btc/sessions"),
("GET", "/api/btc/sessions/current"),
```

Also add the BTC mutation routes to the auth test's `PROTECTED_ROUTES` list (or verify the auto-discovery test catches them).

## 8. Update AUTH_TODO_LOCKDOWN

If the auto-discovery auth test from Phase 0H has an `AUTH_TODO_LOCKDOWN` set, remove the BTC signal mutation routes from it (they're now protected).

## Definition of Done

- [ ] `BTCUSDT.P` correctly classifies as `asset_class=CRYPTO`
- [ ] BTC signal mutation routes require API key (4 routes)
- [ ] Stater Swap uses trade-ideas endpoints only (no legacy /signals/ routes)
- [ ] Market data endpoint receives selected symbol from frontend
- [ ] HYPE/ASTR chips removed (BTC-first)
- [ ] Dead DOM references cleaned up
- [ ] Smoke tests added for crypto endpoints
- [ ] All existing tests pass
