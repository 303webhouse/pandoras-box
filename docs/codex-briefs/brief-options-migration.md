# Brief: Options In-Memory Ledger Migration to Unified Positions

## Summary

Kill `backend/api/options_positions.py` (in-memory dict) and reroute the frontend's options UI to use `unified_positions` endpoints. Nick's options positions are ALREADY in the `unified_positions` PostgreSQL table — the old module is dead weight showing an empty list.

## Current State

- `unified_positions` has 3 open options (XLE call spread, IGV put spread, XLF put spread) with structure, strikes, expiry, DTE, P&L — fully DB-backed
- `options_positions.py` uses `_options_positions: Dict = {}` in memory — empty after every Railway deploy
- Frontend "Options" section calls `/options/positions` → gets empty list
- Frontend "Positions" section calls `/v2/positions` → shows the same options correctly
- The `options_legs` JSONB column exists in `unified_positions` but is null (not populated on create)
- The `options_positions` DB table exists separately but is not the source of truth

## Backend Changes

### 1. Ensure `options_legs` gets stored on create

In `backend/api/unified_positions.py`, the `PositionCreate` model already accepts `legs: Optional[List[Dict]]`. Verify that the INSERT query stores `legs` into the `options_legs` column. Check the `create_position` function (~line 200+).

If legs are passed in the request but not stored, add:
```python
# In the INSERT query, add options_legs
"options_legs": json.dumps(params.get("legs")) if params.get("legs") else None,
```

### 2. Ensure legs are returned in GET responses

In the `_row_to_dict` helper function, verify that `options_legs` is parsed from JSON back to a Python list/dict when returned. The frontend needs `pos.legs` as an array.

If not already handled:
```python
if row.get("options_legs"):
    result["legs"] = json.loads(row["options_legs"]) if isinstance(row["options_legs"], str) else row["options_legs"]
```

### 3. Remove options_positions.py from main.py

In `backend/main.py` (line ~518):
```python
# DELETE THIS:
from api.options_positions import router as options_router
# AND the corresponding app.include_router line
```

### 4. Do NOT delete the options_positions.py file yet

Keep the file in the repo but unmounted. Some scripts may reference the DB functions in `postgres_client.py` (`log_options_position`, etc.). Those can be cleaned up in a later pass.

## Frontend Changes

### 5. Reroute API calls in `frontend/app.js`

Four calls need updating:

| Old Call | New Call |
|----------|----------|
| `POST /options/positions` (line 9469) | `POST /v2/positions` |
| `GET /options/positions?status=OPEN` (line 9492) | `GET /v2/positions?status=OPEN&asset_type=OPTION` (see note) |
| `GET /options/positions/{id}` (line 9603) | `GET /v2/positions/{id}` |
| `POST /options/positions/{id}/close` (line 9620) | `POST /v2/positions/{id}/close` |

**Note on filtering:** The unified positions GET endpoint doesn't currently have an `asset_type` filter parameter. Two options:
- **Option A (recommended):** Add `asset_type` query param to the `list_positions` function in `unified_positions.py`. Simple: `if asset_type: conditions.append(f"asset_type = ${idx}")`.
- **Option B:** Filter client-side: fetch all positions, filter to `asset_type === 'OPTION'` in JS.

Use Option A — it's a 3-line backend change and avoids fetching unnecessary data.

### 6. Map field names in frontend

The `renderOptionsPositions` function (line 9504) and `loadOptionsPositions` (line 9491) expect the old response shape. Map to unified fields:

| Old Field | Unified Field | Notes |
|-----------|--------------|-------|
| `pos.underlying` | `pos.ticker` | Direct rename |
| `pos.strategy_type` | `pos.structure` | Direct rename |
| `pos.strategy_display` | Compute from `pos.structure` | Map structure strings to display names |
| `pos.direction` | `pos.direction` | Same field |
| `pos.legs` | `pos.options_legs` or `pos.legs` | Depends on _row_to_dict output |
| `pos.net_premium` | `pos.options_net_premium` or `pos.entry_price` | Map to whichever is populated |
| `pos.thesis` | `pos.notes` | Direct rename |
| `pos.metrics.days_to_expiry` | `pos.dte` | Already computed by unified |
| `pos.metrics.unrealized_pnl` | `pos.unrealized_pnl` | Already computed by unified |
| `pos.metrics.net_delta` | Not inline (future) | Show '--' for now |
| `pos.metrics.net_theta` | Not inline (future) | Show '--' for now |

**Strategy display name mapping** — add to the JS or compute from `structure`:
```javascript
const STRUCTURE_DISPLAY = {
    'call_debit_spread': 'Bull Call Spread',
    'put_debit_spread': 'Bear Put Spread',
    'call_credit_spread': 'Bear Call Spread',
    'put_credit_spread': 'Bull Put Spread',
    'long_call': 'Long Call',
    'long_put': 'Long Put',
    'stock': 'Stock',
    'iron_condor': 'Iron Condor',
    // etc
};
```

### 7. Map the create payload

The "Add Options Position" modal submits to `POST /options/positions`. Remap to `POST /v2/positions`:

```javascript
// Old payload shape
{
    underlying: "SPY",
    strategy_type: "BULL_PUT_SPREAD",
    direction: "BULLISH",
    legs: [...],
    net_premium: -150,
    max_loss: 350,
    thesis: "..."
}

// New payload shape for /v2/positions
{
    ticker: "SPY",
    asset_type: "OPTION",
    structure: "put_credit_spread",  // Map from old strategy_type
    direction: "LONG",  // Map: BULLISH->LONG, BEARISH->SHORT
    legs: [...],  // Same format - stored as options_legs JSONB
    entry_price: 1.50,  // Per-contract premium
    quantity: 1,
    options_net_premium: -150,
    max_loss: 350,
    notes: "...",  // Was "thesis"
    expiry: "2026-04-17",  // Extract from leg expirations
    long_strike: 50,  // Extract from legs
    short_strike: 45,  // Extract from legs
    account: "ROBINHOOD"  // Default or let user pick
}
```

### 8. Map the close payload

Remap close from `POST /options/positions/{id}/close` to `POST /v2/positions/{id}/close`:

```javascript
// Old
{ exit_premium: 50, exit_notes: "...", outcome: "WIN" }

// New (check what /v2/positions/{id}/close expects)
{ exit_price: 0.50, notes: "...", outcome: "WIN" }
```

## Out of Scope

- **Inline per-position Greeks:** Currently only available via `/v2/positions/greeks` (portfolio-level). Adding per-position Greeks inline is an enhancement, not a migration requirement. Show '--' in the UI for now.
- **Dropping the `options_positions` DB table:** Leave it. Clean up later.
- **Deleting `options_positions.py`:** Leave the file unmounted in the repo. Remove in a future cleanup.

## Testing

1. Open unified positions list - verify options positions show with correct structure, strikes, expiry
2. Options tab - verify it loads positions from `/v2/positions?asset_type=OPTION`
3. Add a test options position - verify legs stored in `options_legs` JSONB
4. Close an options position - verify status changes to CLOSED
5. Verify existing 169 tests still pass (may need to remove/update tests that hit `/options/positions`)

## Definition of Done

- [ ] `options_positions.py` unmounted from `main.py` (router not included)
- [ ] `asset_type` query param added to unified positions list endpoint
- [ ] `options_legs` JSONB stored on create and returned on read
- [ ] Frontend options UI loads from `/v2/positions?asset_type=OPTION`
- [ ] Frontend create/close flows use `/v2/positions` endpoints
- [ ] Field names mapped (underlying->ticker, strategy_type->structure, etc.)
- [ ] Strategy display names computed from structure strings
- [ ] Greeks show '--' (not broken, just not inline yet)
- [ ] 169+ tests pass
