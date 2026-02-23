# Brief 07-B — Portfolio API Endpoints

**Phase:** 2 (PARALLEL — can run after 07-P1 completes)
**Touches:** `backend/api/portfolio.py` (new), `backend/main.py` (add router)
**Depends on:** 07-P1 (tables must exist)
**Estimated time:** 1.5-2 hours

---

## Task

Create REST API endpoints for account balances, open positions, and trade history. These power the frontend dashboard and are called by Pivot (the Discord bot) when it parses screenshots.

**IMPORTANT:** Do NOT modify existing `backend/api/positions.py` or `backend/api/options_positions.py`. Create a NEW file `backend/api/portfolio.py`.

## File: `backend/api/portfolio.py`

Use FastAPI `APIRouter()`, following the same pattern as every other file in `backend/api/`.

### Auth pattern

```python
import os
from fastapi import Header, HTTPException

PIVOT_API_KEY = os.getenv("PIVOT_API_KEY", "")

def verify_api_key(x_api_key: str = Header(None)):
    if PIVOT_API_KEY and x_api_key != PIVOT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

Use `Depends(verify_api_key)` on POST endpoints. GET endpoints are open (read-only).

### DB access pattern

```python
from database.postgres_client import get_postgres_client

async def some_endpoint():
    pool = await get_postgres_client()
    rows = await pool.fetch("SELECT ...")
```

## Endpoints (7 total)

### 1. GET `/balances`

Returns all account balances ordered with Robinhood first.

```sql
SELECT account_name, broker, balance, cash, buying_power, margin_total, updated_at, updated_by
FROM account_balances
ORDER BY CASE broker WHEN 'robinhood' THEN 0 ELSE 1 END, account_name
```

Return as JSON array of row dicts.

### 2. POST `/balances/update` (auth required)

Body: `{account_name, balance, cash?, buying_power?, margin_total?}`

```sql
UPDATE account_balances
SET balance = $1, cash = $2, buying_power = $3, margin_total = $4,
    updated_at = NOW(), updated_by = 'pivot_screenshot'
WHERE account_name = $5
```

404 if no row updated. Return updated row.

### 3. GET `/positions`

All active positions.

```sql
SELECT * FROM open_positions
WHERE is_active = TRUE
ORDER BY expiry ASC NULLS LAST, ticker ASC
```

### 4. POST `/positions/sync` (auth required)

**The core sync endpoint.** Body: `{positions: [PositionData, ...]}`

1. Fetch all active positions from DB
2. For each incoming position, match by `(ticker, strike, expiry, short_strike, direction)`:
   - Match → UPDATE current_value, current_price, unrealized_pnl, unrealized_pnl_pct, last_updated
   - No match → INSERT new position
3. Any DB positions NOT in incoming list → set `is_active = FALSE`, add to `closed` array
4. Return: `{added: [...], updated: [...], closed: [...]}`

### 5. POST `/positions/close` (auth required)

Body: `{ticker, strike?, expiry?, short_strike?, exit_price, exit_date?, realized_pnl?, notes?}`

Find matching active position. Set `is_active = FALSE`, update notes with exit info.

### 6. GET `/trade-history`

Query params: `ticker?`, `start_date?`, `end_date?`, `is_option?`, `limit=50`, `offset=0`

```sql
SELECT * FROM rh_trade_history
WHERE ($1::text IS NULL OR ticker = $1)
  AND ($2::date IS NULL OR activity_date >= $2)
  AND ($3::date IS NULL OR activity_date <= $3)
  AND ($4::boolean IS NULL OR is_option = $4)
ORDER BY activity_date DESC, id DESC
LIMIT $5 OFFSET $6
```

### 7. GET `/trade-history/stats`

Return aggregate stats:
```json
{
    "total_trades": 370,
    "total_option_trades": 259,
    "total_stock_trades": 111,
    "unique_tickers": 47,
    "date_range": {"start": "2026-01-02", "end": "2026-02-18"},
    "total_cash_flows": -2301.00
}
```

## Register in main.py

Add these two lines:

```python
# In imports section:
from api.portfolio import router as portfolio_router

# In include_router section:
app.include_router(portfolio_router, prefix="/api/portfolio", tags=["portfolio"])
```

**Note:** Prefix is `/api/portfolio` so endpoint decorators use `/balances`, `/positions`, etc.

## Verification

```bash
curl https://pandoras-box-production.up.railway.app/api/portfolio/balances
# → 4 account rows

curl https://pandoras-box-production.up.railway.app/api/portfolio/positions
# → []

curl https://pandoras-box-production.up.railway.app/api/portfolio/trade-history/stats
# → zeroed stats
```

## Commit

```
feat: add portfolio API endpoints for balances, positions, trade history (brief 07-B)
```

## Definition of Done

- [ ] `backend/api/portfolio.py` created with all 7 endpoints
- [ ] Router registered in `backend/main.py`
- [ ] GET /balances returns seeded data
- [ ] POST /positions/sync handles add/update/close detection
- [ ] POST /balances/update requires API key
- [ ] GET /trade-history supports all filter params
