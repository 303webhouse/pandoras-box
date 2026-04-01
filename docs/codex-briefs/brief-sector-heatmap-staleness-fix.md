# BRIEF: Sector Heatmap Fix — Snapshot Staleness, Logging, Cache TTL
## Priority: P0 | System: Backend
## Date: 2026-04-01
## File: `backend/api/sectors.py`

---

## CONTEXT FOR CLAUDE CODE

The main sector heatmap treemap shows yesterday's data during market hours, but the sector drill-down popup (same Polygon snapshot function) shows current prices. Root cause: the heatmap's `change_1d` value is stale because:

1. The Polygon snapshot may return `0.0` for `day_change_pct` on ETFs (snapshot hasn't rolled to today's session), but the code only falls back to historical bars **outside** market hours — during market hours, it keeps the `0.0`
2. The historical bars cache is 30 minutes, but now that we include today's partial bar (Fix 4), it needs to refresh much more frequently during market hours
3. Insufficient logging to see what Polygon is actually returning vs what gets displayed

The popup works because it has NO outer Redis cache and displays raw price data, not computed daily changes.

**4 changes, all in `backend/api/sectors.py`:**

---

## CHANGE 1: Add `_hist_cache_ttl()` function — reduce historical bars cache during market hours

The historical bars now include today's partial bar (Fix 4 change), so they need to refresh faster during market hours — not every 30 minutes.

**Find:**
```python
HEATMAP_HIST_TTL = 1800  # 30 min — daily bars don't change intraday
```

**Replace with:**
```python
HEATMAP_HIST_TTL = 1800  # 30 min — daily bars don't change intraday

def _hist_cache_ttl() -> int:
    """Shorter hist cache during market hours since we now include today's partial bar."""
    if _is_market_hours():
        return 120  # 2 min during market hours — today's bar changes
    return HEATMAP_HIST_TTL
```

Then update the cache SET call to use the new function:

**Find:**
```python
                await redis.set(HEATMAP_HIST_KEY, json.dumps(all_closes), ex=HEATMAP_HIST_TTL)
```

**Replace with:**
```python
                await redis.set(HEATMAP_HIST_KEY, json.dumps(all_closes), ex=_hist_cache_ttl())
```

---

## CHANGE 2: Add cache-miss + snapshot diagnostic logging

**Find:**
```python
    # Check cache first
    if redis:
        try:
            cached = await redis.get(HEATMAP_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
```

**Replace with:**
```python
    # Check cache first
    if redis:
        try:
            cached = await redis.get(HEATMAP_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    logger.info("Sector heatmap: cache MISS (is_market_hours=%s, cache_ttl=%ds, hist_ttl=%ds)",
                _is_market_hours(), _heatmap_cache_ttl(), _hist_cache_ttl())
```

Then update the snapshot logging to show actual values:

**Find:**
```python
    # --- Live data from Polygon snapshot (primary) ---
    polygon_snapshot = await _fetch_sector_snapshot(ALL_TICKERS)
    if not polygon_snapshot:
        logger.warning("Sector heatmap: Polygon snapshot returned empty — falling back to historical bars only")
    else:
        logger.debug("Sector heatmap: Polygon snapshot returned %d tickers", len(polygon_snapshot))
```

**Replace with:**
```python
    # --- Live data from Polygon snapshot (primary) ---
    polygon_snapshot = await _fetch_sector_snapshot(ALL_TICKERS)
    if not polygon_snapshot:
        logger.warning("Sector heatmap: Polygon snapshot returned empty — falling back to historical bars only")
    else:
        logger.info("Sector heatmap: Polygon snapshot returned %d tickers. SPY snap: %s, XLK snap: %s",
                     len(polygon_snapshot),
                     polygon_snapshot.get("SPY", "MISSING"),
                     polygon_snapshot.get("XLK", "MISSING"))
```

---

## CHANGE 3: Fix SPY change fallback — allow during market hours

The SPY `change_1d` fallback to historical bars previously only triggered outside market hours. If the snapshot returns 0.0 during market hours (stale data), SPY change stays at 0.0, making all RS calculations wrong.

**Find:**
```python
    # SPY daily change: prefer Polygon (live), fall back to yfinance
    spy_change_1d = spy_snap.get("day_change_pct") if spy_snap else None
    # If Polygon returns 0.0 outside market hours, use yfinance's last close-to-close
    if spy_change_1d == 0.0 and not is_live:
        spy_change_1d = _pct_change(spy_closes, 1) or 0.0
    if spy_change_1d is None:
        spy_change_1d = _pct_change(spy_closes, 1) or 0.0
```

**Replace with:**
```python
    # SPY daily change: prefer Polygon (live), fall back to historical bars
    spy_change_1d = spy_snap.get("day_change_pct") if spy_snap else None
    # If Polygon returns 0.0, use historical bars (snapshot may not have today's data)
    if spy_change_1d == 0.0 and spy_closes:
        hist_spy = _pct_change(spy_closes, 1)
        if hist_spy is not None and hist_spy != 0.0:
            spy_change_1d = hist_spy
    if spy_change_1d is None:
        spy_change_1d = _pct_change(spy_closes, 1) or 0.0
```

---

## CHANGE 4: Fix per-sector change fallback + add per-ticker diagnostic logging

Same issue as SPY — sector ETF `change_1d` fallback only triggered outside market hours.

**Find:**
```python
        # Price + daily change: prefer Polygon (live), fall back to yfinance
        if snap and snap.get("price"):
            price = snap["price"]
            change_1d = snap.get("day_change_pct", 0.0)
            # If Polygon returns 0.0 outside market hours, use yfinance
            if change_1d == 0.0 and not is_live:
                change_1d = _pct_change(closes, 1) or 0.0
        else:
            price = closes[-1] if closes else None
            change_1d = _pct_change(closes, 1)
```

**Replace with:**
```python
        # Price + daily change: prefer Polygon (live), fall back to historical bars
        if snap and snap.get("price"):
            price = snap["price"]
            change_1d = snap.get("day_change_pct", 0.0)
            # If Polygon returns 0.0, use historical bars as fallback
            # (snapshot may not have rolled over to today's trading session)
            if change_1d == 0.0 and closes:
                hist_change = _pct_change(closes, 1)
                if hist_change is not None and hist_change != 0.0:
                    change_1d = hist_change
            if etf in ("XLK", "SPY"):
                logger.info("Heatmap %s: SNAPSHOT path — price=%.2f change_1d=%.2f (snap_raw=%s, closes[-2:]=%s)",
                           etf, price, change_1d, snap, closes[-2:] if len(closes) >= 2 else closes)
        else:
            price = closes[-1] if closes else None
            change_1d = _pct_change(closes, 1)
            if etf in ("XLK", "SPY"):
                logger.info("Heatmap %s: FALLBACK path — price=%s change_1d=%s (closes[-2:]=%s)",
                           etf, price, change_1d, closes[-2:] if len(closes) >= 2 else closes)
```

---

## VERIFICATION

After deploying (wait 60-90s for Railway restart):

1. Hard-refresh Agora (Ctrl+Shift+R) and check if sector heatmap shows today's changes
2. Check Railway logs for these diagnostic messages:
   - `"Sector heatmap: cache MISS"` — confirms cache TTLs are correct
   - `"Sector heatmap: Polygon snapshot returned X tickers. SPY snap: ..."` — shows actual snapshot data
   - `"Heatmap SPY: SNAPSHOT path"` or `"Heatmap SPY: FALLBACK path"` — shows which code path each ETF takes and the actual values

**If logs show SPY/XLK are hitting SNAPSHOT path with real `change_1d` values:** the fix worked, snapshot data was being overridden by cache.
**If logs show SNAPSHOT path but `change_1d=0.0`:** the Polygon Starter plan snapshot doesn't include intraday changes for ETFs — the historical bars fallback will now cover this.
**If logs show FALLBACK path:** the snapshot is returning empty for ETFs — the historical bars fallback (now with 2-min cache and today's bar) should provide reasonably fresh data.

---

## ORDER OF OPERATIONS

All 4 changes are in one file (`backend/api/sectors.py`). Apply them top-to-bottom, then commit and push.
