# Brief: Sync v2 Position Changes to Portfolio Positions Table

**Priority:** CRITICAL — Every partial close, full close, or position update through the v2 path leaves the portfolio positions table stale. Pivot Chat reads from portfolio positions, so it shows wrong quantities, wrong values, and ghost positions.
**Target:** Railway backend (`backend/api/unified_positions.py`)
**Estimated time:** 1-2 hours
**Source:** March 9 — Nick closed 1-of-2 on AMZN and XLF via the hub UI. The v2 system updated correctly (qty 2→1), but the portfolio positions table stayed at qty:2. This caused a $287 discrepancy and Pivot Chat reporting wrong positions.

---

## Problem

There are two position tracking systems that don't talk to each other:

1. **`unified_positions` table (v2)** — What the frontend reads and writes. Handles partial closes, quantity changes, and all UI operations correctly.
2. **`positions` table (portfolio)** — What Pivot Chat reads via `GET /api/portfolio/positions`. Also used by the committee context builder on VPS. Never updated by v2 operations.

When Nick closes 1-of-2 contracts through the UI:
- v2: AMZN qty goes from 2 → 1 ✅
- portfolio: AMZN qty stays at 2 ❌
- Pivot Chat reports 2 AMZN contracts instead of 1
- Account total is inflated because phantom contracts are counted

The previous fix (close position P&L brief) added a `closed_positions` INSERT on full close. But it did NOT handle:
- Partial closes (quantity reduction)
- Position value updates
- Full closes updating the portfolio `is_active` flag

## Fix: Add Portfolio Sync to All v2 Position Mutations

Every time the v2 path changes a position, it should also update the corresponding portfolio positions row. The portfolio table has a `position_id` column that may or may not map to the v2 ID. Look at the data to determine the linking strategy.

### Strategy: Match by ticker + strike + short_strike + expiry + direction + account

Since the two tables may not share IDs, match portfolio positions to v2 positions using the composite key of: `ticker`, `strike`, `short_strike`, `expiry`, `direction`, and `account`.

### Change 1: After partial close in `close_position()` (unified_positions.py)

After the v2 `unified_positions` UPDATE that reduces quantity, also update the portfolio positions table:

```python
# After partial close in v2, sync to portfolio positions table
try:
    await pool.execute("""
        UPDATE positions 
        SET quantity = $1,
            current_value = $2,
            last_updated = NOW(),
            updated_by = 'v2_partial_close'
        WHERE ticker = $3 
          AND direction = $4
          AND strike = $5
          AND short_strike = $6
          AND expiry = $7
          AND is_active = true
    """, new_qty, new_current_value, ticker, direction, strike, short_strike, expiry)
except Exception as e:
    logger.warning(f"Portfolio sync failed on partial close: {e}")
```

For the `cost_basis` on partial close: if the original cost was $96 for 2 contracts, after closing 1, the remaining cost_basis should be $48 (proportional). Calculate as: `original_cost_basis * (remaining_qty / original_qty)`.

### Change 2: After full close in `close_position()` (unified_positions.py)

After the v2 `unified_positions` UPDATE that sets status='CLOSED', also deactivate in portfolio:

```python
# After full close in v2, deactivate in portfolio positions table
try:
    await pool.execute("""
        UPDATE positions 
        SET is_active = false,
            last_updated = NOW(),
            updated_by = 'v2_full_close'
        WHERE ticker = $1 
          AND direction = $2
          AND strike = $3
          AND short_strike = $4
          AND expiry = $5
          AND is_active = true
    """, ticker, direction, strike, short_strike, expiry)
except Exception as e:
    logger.warning(f"Portfolio sync failed on full close: {e}")
```

This is in ADDITION to the `closed_positions` INSERT from the previous fix.

### Change 3: After position value update (if v2 has a value sync endpoint)

If the v2 system updates `current_value` on positions (e.g., from price refreshes or manual updates), also sync to portfolio:

```python
# After v2 value update, sync to portfolio
try:
    await pool.execute("""
        UPDATE positions 
        SET current_value = $1,
            last_updated = NOW(),
            updated_by = 'v2_sync'
        WHERE ticker = $2 
          AND direction = $3
          AND strike = $4
          AND short_strike = $5
          AND is_active = true
    """, new_value, ticker, direction, strike, short_strike)
except Exception as e:
    logger.warning(f"Portfolio value sync failed: {e}")
```

### Change 4: After new position creation in v2

If a new position is created through the v2 path (not the portfolio path), also INSERT into portfolio positions so Pivot Chat can see it:

```python
# After v2 position creation, also create in portfolio
try:
    await pool.execute("""
        INSERT INTO positions 
            (ticker, position_type, direction, quantity, option_type, 
             strike, short_strike, expiry, spread_type, cost_basis, 
             current_value, account, is_active, updated_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, true, 'v2_create')
        ON CONFLICT DO NOTHING
    """, ...)
except Exception as e:
    logger.warning(f"Portfolio create sync failed: {e}")
```

Use `ON CONFLICT DO NOTHING` to avoid duplicates if the position was already created through the portfolio path.

---

## Alternative Approach: Deprecate Portfolio Table

Instead of keeping two tables in sync, modify `GET /api/portfolio/positions` to read from `unified_positions` instead of `positions`. This would eliminate the sync problem entirely.

**Pros:** No more sync bugs, single source of truth
**Cons:** Requires verifying that all consumers of `/api/portfolio/positions` (Pivot Chat, VPS committee context builder, frontend portfolio display) can handle the v2 data format

CC should evaluate which approach is cleaner. If the unified_positions table has all the fields that portfolio consumers need (ticker, direction, strike, short_strike, expiry, quantity, cost_basis, current_value, account, is_active), then deprecation is the better long-term fix.

---

## Files Changed

- `backend/api/unified_positions.py` — Add portfolio sync to close_position(), value updates, and position creation
- OR `backend/api/portfolio.py` — Redirect GET /api/portfolio/positions to read from unified_positions

## Deployment

Push to `main` → Railway auto-deploy.

## Verification

1. Open hub UI, do a partial close (1-of-2) on any position
2. Check `GET /api/portfolio/positions` — quantity should be 1, not 2
3. Do a full close — position should show `is_active: false` in portfolio table
4. Ask Pivot: "What are my positions?" — should match the UI exactly
5. Create a new position through the UI — should appear in both v2 and portfolio tables
