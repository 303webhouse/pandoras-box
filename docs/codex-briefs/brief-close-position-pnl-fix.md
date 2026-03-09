# Brief: Fix Close Position P&L Tracking

**Priority:** HIGH — Every closed trade loses its P&L data. Nick entered exit prices in the UI and none were saved.
**Target:** Frontend (`frontend/app.js`) + Railway backend (`backend/api/portfolio.py`)
**Estimated time:** 2-3 hours
**Source:** March 9 — Nick closed PLTR, TSLA, IWM, TOST via the hub UI with exit prices entered. All `closed_positions` rows have NULL for `exit_value`, `exit_price`, `pnl_dollars`, `pnl_percent`.

---

## Bug 1 (CRITICAL): Frontend Close Flow Doesn't Send Exit Values

### Problem

When Nick closes a position from the trading hub UI, the frontend calls `POST /api/portfolio/positions/close` but does NOT include `exit_value` or `exit_price` in the request body, even though the UI may have fields where Nick enters that data.

The API accepts these fields — the backend `PositionClose` model in `backend/api/portfolio.py` (line ~250) defines:
```python
class PositionClose(BaseModel):
    ticker: str
    strike: Optional[float] = None
    expiry: Optional[str] = None
    short_strike: Optional[float] = None
    direction: Optional[str] = None
    exit_value: Optional[float] = None      # <-- exists in API
    exit_price: Optional[float] = None      # <-- exists in API
    close_reason: Optional[str] = "manual"
    closed_at: Optional[str] = None
    account: Optional[str] = None
    notes: Optional[str] = None
```

The backend correctly computes P&L when `exit_value` is provided:
```python
if body.exit_value is not None and cost_basis is not None:
    pnl_dollars = round(body.exit_value - cost_basis, 2)
    if cost_basis != 0:
        pnl_percent = round((pnl_dollars / abs(cost_basis)) * 100, 2)
```

So the backend is ready — the frontend just isn't passing the data through.

### Fix

Find the close position flow in `frontend/app.js`. It's a 9,366-line file. Look for:
- Any modal/dialog for closing positions
- Any fetch/POST call that includes the word "close"
- Functions named something like `closePosition`, `handleClose`, `confirmClose`

The fix is to ensure the request body includes `exit_value` (total spread value at close × 100) when calling the close endpoint. If the UI has an exit price input field, wire it into the POST body.

If the UI does NOT have an exit price input field:
1. Add an input field to the close position modal/dialog: "Exit Price (per contract)" 
2. Calculate `exit_value = exit_price × 100 × quantity`
3. Include both `exit_price` and `exit_value` in the POST request body

Also include `close_reason` — default to "manual" but allow the user to select from: "profit", "loss", "expired", "manual".

### Important: The close flow might use a DIFFERENT endpoint

The frontend might be using one of these instead:
- `POST /api/positions/close` (different from `/api/portfolio/positions/close`)
- `POST /api/v2/positions/{id}/close`
- `POST /api/options/positions/{id}/close`

Check which endpoint the frontend actually calls. All of them should accept exit values — verify and fix whichever one is being used.

---

## Bug 2: No Endpoint to Update Closed Positions After Creation

Once a position is in the `closed_positions` table with NULL P&L, there's no way to backfill it through the API. This matters because:
- Manual trades closed outside the hub need P&L backfilled
- If Bug 1 happens again, there's no recovery path
- The weekly review needs accurate P&L data

### Fix

Add a PATCH endpoint to update closed positions:

**In `backend/api/portfolio.py`, add:**

```python
class ClosedPositionUpdate(BaseModel):
    exit_value: Optional[float] = None
    exit_price: Optional[float] = None
    pnl_dollars: Optional[float] = None
    pnl_percent: Optional[float] = None
    close_reason: Optional[str] = None
    notes: Optional[str] = None

@router.patch("/positions/closed/{closed_id}")
async def update_closed_position(closed_id: int, body: ClosedPositionUpdate, _=Depends(verify_api_key)):
    pool = await get_postgres_client()
    
    # Get existing record
    existing = await pool.fetchrow(
        "SELECT * FROM closed_positions WHERE id = $1", closed_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Closed position {closed_id} not found")
    
    # Auto-calculate P&L if exit_value provided but pnl not
    exit_val = body.exit_value
    pnl_d = body.pnl_dollars
    pnl_p = body.pnl_percent
    
    if exit_val is not None and pnl_d is None:
        cost_basis = float(existing["cost_basis"]) if existing.get("cost_basis") else None
        if cost_basis is not None:
            pnl_d = round(exit_val - cost_basis, 2)
            if cost_basis != 0:
                pnl_p = round((pnl_d / abs(cost_basis)) * 100, 2)
    
    await pool.execute("""
        UPDATE closed_positions
        SET exit_value = COALESCE($1, exit_value),
            exit_price = COALESCE($2, exit_price),
            pnl_dollars = COALESCE($3, pnl_dollars),
            pnl_percent = COALESCE($4, pnl_percent),
            close_reason = COALESCE($5, close_reason),
            notes = COALESCE($6, notes)
        WHERE id = $7
    """, exit_val, body.exit_price, pnl_d, pnl_p,
        body.close_reason, body.notes, closed_id)
    
    row = await pool.fetchrow("SELECT * FROM closed_positions WHERE id = $1", closed_id)
    return _row_to_dict(row)
```

This allows backfilling P&L on any closed position by ID.

---

## Bug 3: Trade Logging Pipeline Should Also Handle Closes

The trade logging pipeline (just deployed) detects trade ENTRIES ("took the trade", "I'm in"). It should also detect trade EXITS and call the close endpoint with P&L data.

### Fix

In `committee_interaction_handler.py`, extend the `on_message` trade detection to also match close patterns:

```python
TRADE_EXIT_PATTERNS = [
    re.compile(r"\bclosed\b", re.I),
    re.compile(r"\btook profits?\b", re.I),
    re.compile(r"\bexited\b", re.I),
    re.compile(r"\bsold\b.*\b(position|spread|calls?|puts?)\b", re.I),
    re.compile(r"\bclosed out\b", re.I),
    re.compile(r"\bcut\b.*\b(loss|position)\b", re.I),
    re.compile(r"\bstopped out\b", re.I),
]
```

When a close pattern matches, prompt Nick to confirm the exit details (ticker, exit price) and call `POST /api/portfolio/positions/close` with the exit value.

---

## Verification

After deploying:
1. Open the hub UI, close a test position with an exit price entered
2. Check `closed_positions` table — `exit_value` and `pnl_dollars` should be populated
3. Test the PATCH endpoint: `curl -X PATCH .../api/portfolio/positions/closed/2 -d '{"exit_value": 168}'` — should auto-calculate P&L
4. In Discord, say "closed AMZN for $1.50" — Pivot should prompt to log the close with P&L

## Files Changed

- `frontend/app.js` — Wire exit price into close position API call
- `backend/api/portfolio.py` — Add PATCH endpoint for closed positions
- `backend/discord_bridge/bot.py` or VPS interaction handler — Add trade exit detection (can be deferred)

## Deployment

- Frontend + backend: push to `main` → Railway auto-deploy
- VPS interaction handler: SCP + restart (if exit detection added)
