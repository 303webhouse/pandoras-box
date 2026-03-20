# Brief — MTM Clock Alignment + Sector Heatmap Fix

**Priority:** HIGH — MTM affects position accuracy, heatmap is a visible break
**Touches:** `backend/main.py`, possibly `frontend/app.js` (if heatmap has a JS error)
**Estimated time:** 30 minutes

---

## Part 1 — MTM Clock Alignment

### Problem

The mark-to-market loop uses `await asyncio.sleep(900)` — a flat 15-minute sleep after each run. This means MTM fires at whatever random offset from when Railway last deployed (e.g., :03, :18, :33, :48). Polygon's Stocks Starter tier updates options snapshots roughly on the quarter-hour (:00, :15, :30, :45), with a short lag before data is available.

Result: MTM often runs just *before* Polygon updates, fetching stale prices. Positions like near-ATM spreads (IGV 83p with underlying at 82.54) show significantly wrong PnL because the option snapshot hasn't refreshed yet.

### Fix

Replace the flat sleep with a "sleep until next quarter-hour + 2 minute offset" calculation. This gives Polygon time to publish fresh snapshots before we fetch.

### File: `backend/main.py` — `mark_to_market_loop()` function

**Find (~line 169):**
```python
            await asyncio.sleep(900)  # 15 minutes
```

**Replace with:**
```python
            # Sleep until next quarter-hour + 2 min offset (Polygon publishes ~on the quarter-hour)
            # e.g., if it's 9:37, next run at 9:47 (9:45 + 2 min)
            import math
            now_ts = dt_cls.now(pytz.timezone("America/New_York"))
            current_minute = now_ts.minute
            # Next quarter-hour: ceil to next 15-min mark
            next_quarter = (math.ceil((current_minute + 1) / 15) * 15) % 60
            if next_quarter <= current_minute:
                # Wrapped past :60, means next hour
                minutes_until = (60 - current_minute) + next_quarter
            else:
                minutes_until = next_quarter - current_minute
            # Add 2 minutes offset for Polygon lag
            sleep_seconds = (minutes_until * 60) + 120 - now_ts.second
            # Clamp: minimum 60s (don't spin if we're right at the boundary), max 17 min
            sleep_seconds = max(60, min(sleep_seconds, 1020))
            logger.debug("MTM next run in %d seconds (target :%02d:02)", sleep_seconds, next_quarter)
            await asyncio.sleep(sleep_seconds)
```

This ensures MTM runs at :02, :17, :32, :47 past each hour — 2 minutes after Polygon's quarter-hour refresh.

---

## Part 2 — Sector Heatmap Diagnosis

### Likely Cause

The backend endpoint `GET /api/sectors/heatmap` returns valid data (11 sectors, all fields populated). The issue is frontend-only.

Four deploys hit `app.js` today (v115→v118). If any deploy introduced a JS syntax error, the entire script fails and nothing renders — including the sector heatmap.

### Investigation Steps for CC

1. **Check browser console** — open the deployed Trading Hub and look for red JS errors in the console (F12 → Console). Any syntax error will point to the exact line.

2. **If no console error visible**, check if the `.sector-heatmap` container has zero dimensions:
   ```javascript
   const el = document.getElementById('sectorHeatmap');
   console.log('heatmap dims:', el?.clientWidth, el?.clientHeight);
   ```
   If both are 0, the container is collapsing due to a CSS layout issue.

3. **If dimensions are fine but no cells render**, the `loadSectorHeatmap()` function isn't being called or is silently erroring. Add a temporary console.log:
   ```javascript
   async function loadSectorHeatmap() {
       console.log('loadSectorHeatmap called');
       // ... existing code
   }
   ```

### Most Likely Fix

If a JS syntax error is found in recent changes (flow badges, portfolio PnL, etc.), fix that error. The heatmap code itself (`renderSectorHeatmap` at ~line 7092) was verified to be syntactically correct.

If the issue is CSS-related (container height collapse), add a fallback min-height to `.headlines-tab-content`:
```css
.headlines-tab-content {
    flex: 1;
    overflow-y: auto;
    min-height: 300px;   /* ADD: prevent collapse when parent height is ambiguous */
    scrollbar-width: thin;
    scrollbar-color: rgba(20, 184, 166, 0.3) transparent;
}
```

**CC: Diagnose first, then fix. Don't guess — check the console.**

---

## Build Order

| Step | File | What |
|------|------|------|
| 1 | `main.py` | Replace `asyncio.sleep(900)` with clock-aligned sleep |
| 2 | Diagnose | Check browser console for JS errors on deployed site |
| 3 | Fix | Apply whatever the console reveals for the heatmap |

---

## Verification

- [ ] After deploy, check Railway logs for MTM timing: should show runs at ~:02, :17, :32, :47
- [ ] Trigger MTM manually, compare position prices to Robinhood — gap should be smaller
- [ ] Sector heatmap renders correctly with colored cells
- [ ] No red errors in browser console

---

## Commit

```
fix: align MTM to quarter-hour clock + diagnose sector heatmap
```
