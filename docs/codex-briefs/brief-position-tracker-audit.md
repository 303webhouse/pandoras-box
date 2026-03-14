# Brief: Position Tracker Audit & Cash Reconciliation

## Problem Statement

The RH portfolio total is "wildly off." Position close operations sometimes succeed without updating the portfolio balance. New position entries intermittently fail with 502s during deploys but even when they succeed, the running cash balance drifts over time. This brief systematically identifies and fixes every failure mode in the position lifecycle.

## Priority: HIGH — This is Nick's primary execution interface. Bugs here erode trust.

---

## Step 0: Diagnosis (DO THIS FIRST)

Before fixing anything, dump the current state so we know what's actually broken. Run these queries against Supabase/PostgreSQL and include results in the PR description.

### 0A. Check account_balances table
```sql
SELECT account_name, cash, balance, updated_at, updated_by
FROM account_balances
ORDER BY account_name;
```
Document the exact `account_name` values. The code matches positions stored as `account = 'ROBINHOOD'` against `account_balances.account_name` using `_match_account_balance()`. If these don't match (e.g. "Robinhood - Individual" vs "Robinhood"), every cash adjustment silently fails.

### 0B. Check for cash drift
```sql
-- Sum what cash SHOULD be: starting balance - all open position costs + all closed position proceeds
-- vs what it actually is
SELECT
    ab.account_name,
    ab.cash AS current_cash,
    (SELECT COUNT(*) FROM unified_positions WHERE status = 'OPEN' AND account = 'ROBINHOOD') AS open_count,
    (SELECT COUNT(*) FROM unified_positions WHERE status = 'CLOSED' AND account = 'ROBINHOOD') AS closed_count,
    (SELECT COALESCE(SUM(cost_basis), 0) FROM unified_positions WHERE status = 'OPEN' AND account = 'ROBINHOOD') AS open_cost_basis_total,
    (SELECT COALESCE(SUM(realized_pnl), 0) FROM unified_positions WHERE status = 'CLOSED' AND account = 'ROBINHOOD') AS total_realized_pnl
FROM account_balances ab
WHERE ab.account_name ILIKE '%robinhood%';
```

### 0C. Check entry_date column existence
```sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'unified_positions'
ORDER BY ordinal_position;
```
The close flow references `pos.get("entry_date")` — confirm this column actually exists. If it doesn't, `opened_at` in the trades table gets `now` instead of when the position was actually opened.

### 0D. Check for orphaned cash adjustments
```sql
-- Positions that were deleted (not closed) — their cash deductions were never reversed
-- This requires checking if there are any missing position_ids that appear in trades but not in unified_positions
SELECT t.signal_id, t.ticker, t.pnl_dollars, t.closed_at
FROM trades t
LEFT JOIN unified_positions up ON t.signal_id = up.signal_id
WHERE up.signal_id IS NULL AND t.closed_at > NOW() - INTERVAL '30 days';
```

---

## Bug List (Prioritized)

### BUG 1: Silent cash adjustment failures (ROOT CAUSE of drift)
**File:** `backend/api/unified_positions.py`
**Impact:** Cash balance becomes permanently wrong. Every subsequent portfolio total is wrong.

Every call to `_adjust_account_cash()` is wrapped in a bare try/except that swallows the error:

```python
try:
    await _adjust_account_cash(pool, account, cash_delta)
except Exception as e:
    logger.warning("Cash adjustment failed on close: %s", e)
```

And `_adjust_account_cash` itself silently does nothing if no matching row is found:
```python
logger.warning("No matching account_balance row for account=%s", account)
```

**Fix:** Make `_adjust_account_cash` return a bool. Log ERROR not WARNING. Add the cash adjustment result to the API response so the frontend can warn Nick.

```python
async def _adjust_account_cash(pool, account: str, delta: float) -> bool:
    """Atomically adjust cash balance. Returns True if adjustment was applied."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT account_name, cash FROM account_balances")
        for row in rows:
            if _match_account_balance(account, row["account_name"]):
                await conn.execute(
                    "UPDATE account_balances SET cash = cash + $1, updated_at = NOW(), updated_by = 'auto' WHERE account_name = $2",
                    round(delta, 2), row["account_name"],
                )
                logger.info("Cash adjusted for %s: %+.2f", row["account_name"], delta)
                return True
    logger.error("CASH ADJUSTMENT FAILED: No matching account_balance row for account=%s (delta=%+.2f)", account, delta)
    return False
```

Then in all callers, surface the failure:
```python
cash_ok = await _adjust_account_cash(pool, account, cash_delta)
# Include in response
return {"status": "created", "position": result, "cash_adjusted": cash_ok}
```

### BUG 2: Delete position never reverses cash
**File:** `backend/api/unified_positions.py`, function `delete_position`

When a position is deleted, its cost_basis was deducted from cash at creation — but delete never adds it back. This permanently reduces the cash balance.

**Fix:** Before deleting, fetch the position, compute the original cash impact, and reverse it:

```python
@router.delete("/v2/positions/{position_id}")
async def delete_position(position_id: str, _=Depends(require_api_key)):
    """Delete a position (for errors/test data). Reverses the cash adjustment from creation."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM unified_positions WHERE position_id = $1", position_id
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")

    pos = _row_to_dict(row)

    # Only reverse cash for OPEN positions (closed positions already had cash reversed on close)
    if pos.get("status") == "OPEN" and pos.get("cost_basis"):
        s = (pos.get("structure") or "").lower()
        cost = float(pos["cost_basis"])
        # Reverse: if it was a credit (cash went up at open), now cash goes down. And vice versa.
        cash_delta = -cost if s in CREDIT_STRUCTURES else cost
        try:
            await _adjust_account_cash(pool, pos.get("account", "ROBINHOOD"), cash_delta)
        except Exception as e:
            logger.error("Cash reversal failed on delete: %s", e)

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM unified_positions WHERE position_id = $1", position_id
        )
    # ... rest of existing broadcast code
```

### BUG 3: PATCH updates to entry_price/quantity don't adjust cash
**File:** `backend/api/unified_positions.py`, function `update_position`

If Nick edits entry_price or quantity via the PATCH endpoint, cost_basis changes but cash is not re-adjusted to match.

**Fix:** When entry_price or quantity change, compute the delta between old and new cost_basis, and adjust cash:

In `update_position`, after the UPDATE RETURNING, add:
```python
# If entry_price or quantity changed, recalculate cost_basis and adjust cash for the delta
if (req.entry_price is not None or req.quantity is not None) and result.get("status") == "OPEN":
    old_cost = float(row["cost_basis"] or 0)  # Need to fetch old row first
    s = (result.get("structure") or "").lower()
    is_stock = s in ("stock", "stock_long", "long_stock", "stock_short", "short_stock")
    new_entry = result.get("entry_price") or 0
    new_qty = result.get("quantity") or 0
    new_cost = abs(new_entry) * new_qty * (1 if is_stock else 100)

    if new_cost != old_cost:
        cost_delta = new_cost - old_cost
        cash_delta = cost_delta if s in CREDIT_STRUCTURES else -cost_delta
        await _adjust_account_cash(pool, result.get("account", "ROBINHOOD"), cash_delta)

        # Update cost_basis in DB
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE unified_positions SET cost_basis = $1 WHERE position_id = $2",
                round(new_cost, 2), position_id
            )
```

**Note:** This requires fetching the old row BEFORE the update. Change the update_position function to fetch the existing row first (like close_position does), then do the update.

### BUG 4: No cash reconciliation mechanism
**File:** `backend/api/unified_positions.py` (new endpoint)

Once cash drifts, there's no way to fix it without manually doing math. Add a reconciliation endpoint:

```
POST /v2/positions/reconcile-cash
```

Logic:
1. Accept a `known_cash` parameter — what Nick's broker actually shows as cash
2. Set `account_balances.cash = known_cash` directly
3. Log the old vs new values
4. Return the delta (how far off it was)

This is the nuclear option — just set it to what the broker says. No math, no guessing.

```python
@router.post("/v2/positions/reconcile-cash")
async def reconcile_cash(request: Request, _=Depends(require_api_key)):
    """Set cash to a known value from the broker. Fixes all accumulated drift."""
    body = await request.json()
    known_cash = body.get("cash")
    account = body.get("account", "ROBINHOOD")
    if known_cash is None:
        raise HTTPException(status_code=400, detail="cash field required")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT account_name, cash FROM account_balances")
        for row in rows:
            if _match_account_balance(account, row["account_name"]):
                old_cash = float(row["cash"] or 0)
                drift = round(known_cash - old_cash, 2)
                await conn.execute(
                    "UPDATE account_balances SET cash = $1, updated_at = NOW(), updated_by = 'cash_reconcile' WHERE account_name = $2",
                    round(float(known_cash), 2), row["account_name"],
                )
                logger.info("Cash reconciled for %s: was $%.2f, now $%.2f (drift: $%+.2f)",
                           row["account_name"], old_cash, known_cash, drift)
                return {"status": "reconciled", "account": row["account_name"],
                        "old_cash": old_cash, "new_cash": known_cash, "drift": drift}

    raise HTTPException(status_code=404, detail=f"No account_balance row matching '{account}'")
```

### BUG 5: Portfolio summary shows stale position values
**File:** `backend/api/unified_positions.py`, function `portfolio_summary`

The portfolio total = cash + position_value. Position_value = sum(cost_basis + unrealized_pnl). If unrealized_pnl is null (MTM hasn't run or failed), the position counts at cost_basis — which could be wildly wrong for positions that have moved.

**Fix:** In `portfolio_summary`, flag positions with stale pricing:

```python
# After building summaries list:
stale_count = sum(1 for p in positions if not p.get("price_updated_at") or
    (datetime.fromisoformat(str(p["price_updated_at"])).replace(tzinfo=timezone.utc) <
     datetime.now(timezone.utc) - timedelta(hours=2)))
```

Include `"stale_positions": stale_count` in the response so the frontend can show a warning like "⚠️ 3 positions have stale pricing."

### BUG 6: Frontend doesn't show cash adjustment failures
**File:** `frontend/app.js`, function `executePositionClose` (~line 8386)

After closing, the frontend checks `data.status === 'closed'` but ignores whether cash was adjusted. Add a check:

```javascript
if (data.cash_adjusted === false) {
    console.warn('Cash adjustment failed for position close');
    // Optionally show subtle warning
}
```

### BUG 7: entry_date might not exist as a column
**File:** `backend/api/unified_positions.py`, function `close_position`

The close flow does:
```python
opened_at = datetime.fromisoformat(pos["entry_date"]) if isinstance(pos.get("entry_date"), str) else pos.get("entry_date", now)
```

If the column is actually `created_at` and `entry_date` doesn't exist, `opened_at` always equals `now`, making `hold_days` always 0. This corrupts the `closed_positions` analytics table.

**Fix (after checking Step 0C):** If `entry_date` doesn't exist, use `created_at`:
```python
# Use entry_date if it exists, otherwise fall back to created_at
raw_opened = pos.get("entry_date") or pos.get("created_at")
opened_at = datetime.fromisoformat(str(raw_opened)) if isinstance(raw_opened, str) else (raw_opened or now)
```

### BUG 8: Add Position modal entry_price field accepts values without leading zero
**Observed:** Nick entered `.38` for the AAPL put debit spread. The backend likely parses this fine, but verify that `entry_price` is stored as `0.38` not `None` or some mangled value. This is cosmetic but worth confirming.

---

## Frontend Enhancement: Cash Reconcile Button

Add a small "Sync Cash" button to the portfolio summary widget. When clicked:
1. Prompt: "Enter your actual Robinhood cash balance:"
2. POST to `/v2/positions/reconcile-cash` with the entered value
3. Reload portfolio summary
4. Show the drift amount: "Cash corrected by +$142.50"

This lets Nick fix cash drift in 5 seconds any time it happens.

---

## Test Plan

Add tests to `tests/test_unified_positions.py`:

1. **test_close_position_adjusts_cash** — create position (cash goes down), close it (cash goes back up), verify cash matches starting value
2. **test_delete_position_reverses_cash** — create position, delete it, verify cash restored
3. **test_patch_entry_price_adjusts_cash** — create position, PATCH entry_price, verify cash delta applied
4. **test_cash_adjustment_no_matching_account** — call `_adjust_account_cash` with a bogus account name, verify it returns False
5. **test_reconcile_cash** — set known_cash, verify account_balances updated and drift returned
6. **test_portfolio_summary_stale_flag** — create position without running MTM, verify stale_positions count in summary
7. **test_close_creates_trade_record** — close position, verify trades table has correct opened_at (not NOW)

---

## Verification Checklist

After deploy:
- [ ] `GET /v2/positions/summary?account=ROBINHOOD` returns `cash_adjusted` info
- [ ] Close a position → portfolio total updates correctly
- [ ] Delete a position → cash is reversed
- [ ] PATCH entry_price on open position → cash adjusts for delta
- [ ] `POST /v2/positions/reconcile-cash` with `{"cash": 3000, "account": "ROBINHOOD"}` → sets cash and returns drift
- [ ] Portfolio summary includes `stale_positions` count
- [ ] Frontend "Sync Cash" button works end-to-end

---

## Scope Exclusions

- Mark-to-market reliability (separate concern — Polygon API failures are expected during off-hours)
- Multi-leg iron condor pricing (working correctly when legs JSONB is populated)
- Frontend position entry modal UX improvements (separate brief)
