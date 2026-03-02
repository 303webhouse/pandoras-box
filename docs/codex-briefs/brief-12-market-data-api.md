# Brief 12 — Market Data API (Polygon Passthrough)

## Goal

Expose Railway's existing Polygon.io integration as read-only API endpoints so Pivot (and any future client) can query live market data through the Trading Hub instead of needing direct Polygon credentials.

## Why

Pivot (Discord bot on VPS) needs live market data — stock quotes, options chains, greeks, price history — but doesn't have a Polygon API key. Railway already has full Polygon integration (`backend/integrations/polygon_options.py` and `polygon_equities.py`) used by the mark-to-market job. We just need thin GET routes wrapping those existing functions.

## Scope

**One new file:** `backend/api/market_data.py`
**One edit:** `backend/main.py` (register the router)

No database changes. No new dependencies. No new env vars.

---

## File 1: CREATE `backend/api/market_data.py`

Create this file with a FastAPI router containing 5 GET endpoints. All endpoints are **read-only, no auth required** (matching existing GET patterns like `/api/bias/composite`).

### Endpoints

#### 1. `GET /market/quote/{ticker}`
**Purpose:** Current stock/ETF snapshot (price, volume, change %).
**Implementation:** Call `polygon_equities.get_snapshot(ticker)`. Return the result directly. Return 404 if `None` or if `POLYGON_API_KEY` is not set.

#### 2. `GET /market/previous-close/{ticker}`
**Purpose:** Previous trading day OHLCV.
**Implementation:** Call `polygon_equities.get_previous_close(ticker)`. Return result. 404 if None.

#### 3. `GET /market/bars/{ticker}`
**Purpose:** OHLCV price history bars.
**Query params:**
- `days` (int, default 30) — how many trading days of history
- `timespan` (str, default "day") — bar size: "day", "hour", "minute"
- `multiplier` (int, default 1) — bar multiplier

**Implementation:** Calculate `from_date` as `(today - timedelta(days=int(days * 1.6) + 5)).isoformat()` and `to_date` as `date.today().isoformat()`. Call `polygon_equities.get_bars(ticker, multiplier, timespan, from_date, to_date)`. Return the list. 404 if None/empty.

#### 4. `GET /market/options-chain/{ticker}`
**Purpose:** Options chain snapshot with greeks, bid/ask, IV.
**Query params:**
- `expiration` (str, optional) — filter by expiry date YYYY-MM-DD
- `strike_gte` (float, optional) — min strike price
- `strike_lte` (float, optional) — max strike price
- `contract_type` (str, optional) — "call" or "put"

**Implementation:** Call `polygon_options.get_options_snapshot(ticker, expiration_date=expiration, strike_gte=strike_gte, strike_lte=strike_lte, contract_type=contract_type)`. Return the list. 404 if None.

#### 5. `GET /market/option-value`
**Purpose:** Get current value + greeks for a single option or spread.
**Query params (all required):**
- `underlying` (str) — ticker e.g. "SPY"
- `long_strike` (float) — long leg strike
- `expiry` (str) — expiration date YYYY-MM-DD
- `option_type` (str) — "call" or "put"
- `short_strike` (float, optional) — short leg strike (omit for single leg)
- `structure` (str, optional) — e.g. "put_debit_spread", "call_credit_spread" (required if short_strike provided)

**Implementation:**
- If `short_strike` is provided: call `polygon_options.get_spread_value(underlying, long_strike, short_strike, expiry, structure)`.
- If `short_strike` is NOT provided: call `polygon_options.get_single_option_value(underlying, long_strike, expiry, option_type)`.
- Return result. 404 if None.

### Error handling pattern

All endpoints should follow this pattern:
```python
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

router = APIRouter()

@router.get("/market/quote/{ticker}")
async def get_quote(ticker: str):
    from integrations.polygon_equities import get_snapshot
    result = await get_snapshot(ticker.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    return result
```

Keep imports inside the function body (lazy imports), matching the project's existing pattern in `main.py`.

---

## File 2: EDIT `backend/main.py`

### Edit 1 — Add import

**Find this line:**
```python
from api.committee_bridge import router as committee_bridge_router
```

**Replace with:**
```python
from api.committee_bridge import router as committee_bridge_router
from api.market_data import router as market_data_router
```

### Edit 2 — Register router

**Find this line:**
```python
app.include_router(committee_bridge_router, prefix="/api", tags=["committee"])
```

**Replace with:**
```python
app.include_router(committee_bridge_router, prefix="/api", tags=["committee"])
app.include_router(market_data_router, prefix="/api", tags=["market-data"])
```

---

## Verification

After deploying (push to `main` → Railway auto-deploys), test with:

```bash
# Stock quote
curl -s https://pandoras-box-production.up.railway.app/api/market/quote/SPY | python3 -m json.tool | head -20

# Previous close
curl -s https://pandoras-box-production.up.railway.app/api/market/previous-close/AAPL | python3 -m json.tool

# Price bars (30 days daily)
curl -s "https://pandoras-box-production.up.railway.app/api/market/bars/SPY?days=30" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} bars')"

# Options chain (SPY puts, specific expiry, near 580 strike)
curl -s "https://pandoras-box-production.up.railway.app/api/market/options-chain/SPY?expiration=2026-03-20&strike_gte=575&strike_lte=585&contract_type=put" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} contracts')"

# Single option value
curl -s "https://pandoras-box-production.up.railway.app/api/market/option-value?underlying=SPY&long_strike=580&expiry=2026-03-20&option_type=put" | python3 -m json.tool
```

**All 5 should return JSON (not 404/500).** The options endpoints return 15-min delayed data (Polygon Starter plan).

---

## What NOT to do

- Do NOT add authentication to these endpoints — they're read-only market data, not user data.
- Do NOT create new Polygon client code — use the existing functions in `backend/integrations/polygon_equities.py` and `polygon_options.py` as-is.
- Do NOT modify any existing files other than `main.py`.
- Do NOT add new dependencies to `requirements.txt` — everything needed is already installed.
- Do NOT add caching — the Polygon integration files already have 5-minute in-memory caches built in.

---

## Post-Deploy: Update Pivot's API Reference

After the endpoints are live, append these to `/opt/openclaw/workspace/TRADING_HUB_API.md` on the VPS:

```markdown
## Live Market Data (Polygon — 15-min delayed)

```bash
# Current stock/ETF quote (price, volume, change)
curl -s "$PANDORA_API_URL/market/quote/{ticker}"

# Previous day's OHLCV
curl -s "$PANDORA_API_URL/market/previous-close/{ticker}"

# Price history bars (default 30 days daily)
curl -s "$PANDORA_API_URL/market/bars/{ticker}?days=30&timespan=day"

# Options chain snapshot (with greeks, IV, bid/ask)
curl -s "$PANDORA_API_URL/market/options-chain/{ticker}?expiration=YYYY-MM-DD&strike_gte=575&strike_lte=585&contract_type=put"

# Single option or spread value + greeks
curl -s "$PANDORA_API_URL/market/option-value?underlying=SPY&long_strike=580&expiry=2026-03-20&option_type=put"
curl -s "$PANDORA_API_URL/market/option-value?underlying=SPY&long_strike=580&short_strike=570&expiry=2026-03-20&option_type=put&structure=put_debit_spread"
```
```

---

## Definition of Done

All 5 endpoints return valid JSON responses from the Railway deployment. The OpenAPI docs at `/docs` show the new `market-data` tag with all 5 routes.
