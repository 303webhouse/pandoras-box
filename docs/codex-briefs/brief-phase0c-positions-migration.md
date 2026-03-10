# Brief: Phase 0C — Finish Positions Migration

**Priority:** HIGH — Two parallel position systems are running simultaneously. The legacy one uses in-memory state that evaporates on Railway redeploy. This creates phantom positions, stale UI, and restart mismatches.
**Target:** Railway backend (`backend/`) + frontend (`frontend/`)
**Estimated time:** 90–120 minutes
**Prerequisites:** Phase 0B (auth lockdown) complete

---

## Context

The position ledger was migrated to `unified_positions` (v2) but the old system was never fully removed. Right now:

- `backend/api/positions.py` has `_open_positions = []`, `_closed_trades = []`, `_position_counter = 1` as in-memory state
- `main.py` calls `sync_positions_from_database()` on startup to populate that in-memory state from the OLD `positions` table
- The frontend has TWO position globals: `_open_positions_cache` (legacy) and `openPositions` (v2)
- The frontend has TWO render paths: `renderPositions()` (legacy) and `renderPositionsEnhanced()` (v2)
- The frontend calls `GET /positions/open` (returns in-memory list) AND `GET /v2/positions?status=OPEN` (returns from DB)
- Close position has a fallback chain: tries v2 first, falls back to legacy
- Manual position creation has TWO paths: `POST /v2/positions` and `POST /positions/manual`
- Signal acceptance (`accept_signal`) still writes to the old `positions` table AND pushes to `_open_positions`

**Goal:** One position system. One truth. Everything reads and writes through v2.

---

## IMPORTANT: What to KEEP in positions.py

`positions.py` contains BOTH position CRUD routes AND signal management routes. **The signal routes are still actively used by the frontend and must NOT be removed.** Here's the split:

### KEEP these routes (signal management — still in use):
- `POST /signals/{signal_id}/accept` — but UPDATE it (see Task 2)
- `POST /signals/{signal_id}/accept-options` — already writes to unified_positions, keep as-is
- `POST /signals/{signal_id}/dismiss` — keep as-is
- `POST /signal/action` — legacy adapter, keep as-is
- `GET /signals/active` — main trade ideas feed, keep as-is
- `GET /signals/active/paged` — pagination, keep as-is
- `GET /signals/queue` — auto-refill, keep as-is
- `POST /signals/archive` — backtesting, keep as-is
- `GET /signals/debug` — diagnostic, keep as-is
- `DELETE /signals/clear-all` — admin tool, keep as-is
- `GET /signals/statistics` — backtesting stats, keep as-is

### REMOVE these routes (legacy position CRUD — replaced by v2):
- `POST /positions/open` — replaced by `POST /v2/positions`
- `POST /positions/manual` — replaced by `POST /v2/positions`
- `POST /positions/close` — replaced by `POST /v2/positions/{id}/close`
- `POST /positions/close-expired` — replaced by v2 close with exit_price=0
- `PATCH /positions/{position_id}` — replaced by `PATCH /v2/positions/{id}`
- `POST /position/update` — placeholder, never implemented
- `GET /positions/open` — replaced by `GET /v2/positions?status=OPEN`
- `GET /positions/history` — returns in-memory `_closed_trades`, useless
- `GET /positions/debug-db` — diagnostic for old system
- `GET /positions/diagnose` — diagnostic for old system
- `POST /positions/force-sync` — syncs old system
- `DELETE /positions/{position_id}` — replaced by `DELETE /v2/positions/{id}`

---

## Task 1: Kill in-memory position state

**File: `backend/api/positions.py`**

Remove or comment out these module-level variables:

```python
# In-memory position store (synced with database on startup)
_open_positions = []
_closed_trades = []
_position_counter = 1
```

Replace with a comment:
```python
# Legacy in-memory position state REMOVED (Phase 0C).
# All position data lives in unified_positions table.
# Position CRUD routes are in api/unified_positions.py.
```

Also remove the `sync_positions_from_database()` function entirely (it's the one that populates `_open_positions` from the old `positions` table on startup).

## Task 2: Fix accept_signal to write to unified_positions

**File: `backend/api/positions.py`**

The `accept_signal()` function (route `POST /signals/{signal_id}/accept`) currently:
1. Calls `create_position()` which writes to the OLD `positions` table
2. Pushes to `_open_positions` in-memory list

It needs to write to `unified_positions` instead. The `accept_signal_as_options()` function already does this correctly — use it as the pattern.

In `accept_signal()`, replace the position creation block. Instead of calling `create_position(signal_id, position_data)` and appending to `_open_positions`, create the position directly in `unified_positions`:

```python
# Create position in unified_positions (v2)
from database.postgres_client import get_postgres_client
pool = await get_postgres_client()
now = datetime.now(timezone.utc)
position_id = f"POS_{signal_data.get('ticker', 'UNK').upper()}_{now.strftime('%Y%m%d_%H%M%S')}"

async with pool.acquire() as conn:
    row = await conn.fetchrow("""
        INSERT INTO unified_positions (
            position_id, ticker, asset_type, structure, direction,
            entry_price, quantity, cost_basis,
            stop_loss, target_1, target_2,
            source, signal_id, account, notes
        ) VALUES (
            $1, $2, 'EQUITY', 'stock', $3,
            $4, $5, $6,
            $7, $8, $9,
            'SIGNAL', $10, $11, $12
        )
        RETURNING *
    """,
        position_id, signal_data.get('ticker', '').upper(),
        signal_data.get('direction', 'LONG'),
        request.actual_entry_price, request.quantity,
        round(request.actual_entry_price * request.quantity, 2),
        request.stop_loss or signal_data.get('stop_loss'),
        request.target_1 or signal_data.get('target_1'),
        request.target_2 or signal_data.get('target_2'),
        signal_id, (request.account or 'ROBINHOOD').upper(),
        request.notes
    )
```

Remove the `_open_positions.append(position)` line and the `_position_counter` increment.

Keep the rest of the function (signal update, committee override check, WebSocket broadcast, watchlist upsert).

## Task 3: Remove legacy position routes

**File: `backend/api/positions.py`**

Delete all the route functions listed in the REMOVE section above. That's roughly lines covering:
- `open_position()` — `POST /positions/open`
- `create_manual_position()` — `POST /positions/manual`
- `close_position()` — `POST /positions/close`
- `close_expired_position()` — `POST /positions/close-expired`
- `update_position()` (the PATCH one) — `PATCH /positions/{position_id}`
- `update_position()` (the POST one) — `POST /position/update`
- `get_open_positions_api()` — `GET /positions/open`
- `remove_position()` — `DELETE /positions/{position_id}`
- `get_trade_history()` — `GET /positions/history`
- `debug_positions_db()` — `GET /positions/debug-db`
- `diagnose_positions()` — `GET /positions/diagnose`
- `force_sync_positions()` — `POST /positions/force-sync`
- `sync_positions_from_database()` — startup function

Also clean up any imports that become unused after removing these functions.

## Task 4: Remove startup sync from main.py

**File: `backend/main.py`**

Find and remove:
```python
    # Sync open positions from database
    try:
        from api.positions import sync_positions_from_database
        await sync_positions_from_database()
        logger.info("✅ Positions synced from database")
    except Exception as e:
        logger.warning(f"⚠️ Could not sync positions: {e}")
```

This was the startup call that populated the in-memory `_open_positions` from the old `positions` table.

## Task 5: Remove sync_v2_to_legacy and sync_legacy_to_v2

**File: `backend/api/unified_positions.py`**

Delete the two sync functions:
- `sync_v2_to_legacy()` — ~80 lines, syncs v2 → old `open_positions` table
- `sync_legacy_to_v2()` — ~80 lines, syncs old → v2

These exist only to bridge the two systems. With legacy removed, they're dead code.

Also check if anything imports them (grep for `sync_v2_to_legacy` and `sync_legacy_to_v2` across the codebase). If nothing does, safe to delete.

## Task 6: Frontend — kill legacy position paths

**File: `frontend/app.js`**

### 6a: Remove `_open_positions_cache`

Find:
```javascript
let _open_positions_cache = [];
```
Delete it.

Find every reference to `_open_positions_cache` in the file. There should be ~3-4:
- Assignment from `GET /positions/open` response
- Used in crypto position filtering
- Maybe used in some render path

Replace each usage with `openPositions` (the v2 variable that already exists at line ~6617).

### 6b: Remove the legacy positions fetch

Find the function or block that calls `GET /positions/open` (around line 3317):
```javascript
const response = await fetch(`${API_URL}/positions/open`);
```

Delete the entire fetch block and the `renderPositions()` call that follows it. The v2 fetch at line ~7155 (`GET /v2/positions?status=OPEN`) is the canonical path.

### 6c: Remove `renderPositions()` function

Find `function renderPositions(positions)` (around line 4484). Delete the entire function. Everything should use `renderPositionsEnhanced()` only.

### 6d: Remove legacy close fallback

Around line 7955 there's a fallback that calls the legacy `POST /positions/close` endpoint when v2 close fails or for old-format positions. Remove this fallback — all closes should go through v2.

Find the pattern:
```javascript
response = await fetch(`${API_URL}/positions/close`, {
```

Delete the entire fallback block. If the v2 close fails, it should show an error, not silently try the old endpoint.

### 6e: Remove legacy manual position creation

Around line 8608 there's a call to `POST /positions/manual`. Delete this code path. Manual position creation should use `POST /v2/positions` only (which already exists around line 8202).

### 6f: Remove the `openPositions` duplicate declaration if any

Verify there's only ONE `let openPositions = [];` declaration. If there are two, keep the one near the v2 code and remove the other.

## Task 7: Verify no other callers

Run these greps to make sure nothing else depends on the removed code:

```bash
# Check for any remaining references to legacy position endpoints
grep -rn "positions/open\|positions/manual\|positions/close\b\|positions/force-sync\|positions/debug-db\|positions/diagnose\|positions/history" --include="*.py" --include="*.js" backend/ frontend/ scripts/ pivot/

# Check for references to in-memory position state
grep -rn "_open_positions\|_closed_trades\|_position_counter\|sync_positions_from_database" --include="*.py" backend/

# Check for legacy sync functions
grep -rn "sync_v2_to_legacy\|sync_legacy_to_v2" --include="*.py" backend/

# Check for _open_positions_cache in frontend
grep -n "_open_positions_cache\|renderPositions[^E]" frontend/app.js
```

If any of these return hits outside the files being modified, investigate before deleting.

---

## Definition of Done

1. `_open_positions`, `_closed_trades`, `_position_counter` no longer exist in `positions.py`
2. `sync_positions_from_database()` no longer exists and is not called on startup
3. `accept_signal()` writes to `unified_positions` table, not old `positions` table
4. All legacy position CRUD routes removed from `positions.py`
5. Signal routes (`/signals/*`) still work as before
6. `sync_v2_to_legacy()` and `sync_legacy_to_v2()` removed from `unified_positions.py`
7. Frontend has ONE position global (`openPositions`), ONE render function (`renderPositionsEnhanced`), ONE fetch path (`GET /v2/positions`)
8. `_open_positions_cache` removed from frontend
9. No calls to `GET /positions/open`, `POST /positions/manual`, `POST /positions/close` in frontend
10. Dashboard loads correctly with positions from v2 only
11. Signal accept → creates position in unified_positions → appears in dashboard

---

## What this brief does NOT do

- Does NOT drop the old `positions` or `open_positions` database tables (do that later after confirming zero callers)
- Does NOT remove `positions.py` entirely (signal routes still live there)
- Does NOT move signal routes to a separate file (good future cleanup but not in scope)
- Does NOT touch the VPS scripts (they already read from v2 via Railway API)

---

## Risk notes

- **Signal acceptance is the riskiest change.** The `accept_signal()` rewrite (Task 2) changes where new positions land. Test by accepting a signal and verifying it appears in the dashboard.
- **Frontend has ~8,700 lines.** The grep patterns above should catch everything, but test the dashboard manually after deploy: load positions, create one, close one, check crypto tab.
- **The old `positions` table may still have FK references** from the `signals` table (`positions.signal_id`). Don't drop the table yet — just stop writing to it.

---

## Post-build checklist

1. Verify Railway auto-deploy: `curl https://pandoras-box-production.up.railway.app/health`
2. Open dashboard → verify positions load (from v2)
3. Test: create a manual position via dashboard → verify it appears
4. Test: close a position via dashboard → verify it moves to closed
5. Test: if any active trade ideas exist, accept one → verify position created in v2
6. Check browser console for zero 404 errors on position endpoints
7. Verify VPS committee context still gets position data: check next committee run or trigger manually
