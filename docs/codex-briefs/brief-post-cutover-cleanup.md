# CC Brief — Post-Cutover Cleanup

**Date:** 2026-04-27
**Author:** Opus (via Nick)
**Status:** routine — no urgency, no live trading impact
**Scope:** ~6 deletions across 4 files + 1 main.py edit

---

## Background — why this brief exists

Today's UW migration cutover (commit landed via separate brief) successfully swapped the production data path from Polygon to UW. The Polygon plan is canceled. With the cutover verified green (4/5 PASS — see verification results in `brief-uw-migration-final-cutover.md`), several Polygon-related code paths are now dead weight:

- `polygon_options.py` and `polygon_equities.py` exist but no live code calls them
- `mtm_compare.py` was migration scaffolding to compare Polygon vs UW prices side-by-side; with Polygon dead and UW now in production, this endpoint has zero remaining value (and currently returns 401 anyway due to a separate auth wiring bug)
- `monitoring/polygon_health.py` provided Polygon API health checks; no longer relevant
- `sector_snapshot.py` has a Polygon-calling function (`fetch_sector_prices_polygon`) and a Polygon-calling block inside `refresh_sma_cache` that became unreachable when the cutover bypassed them
- A comment in `main.py::mark_to_market_loop` still references "Polygon's 15-min data refresh"

Leaving this code in place creates a foot-gun: any future build that imports from these files re-introduces today's incident.

---

## Scope — 6 deletions, 1 edit

| # | File | Action |
|---|---|---|
| 1 | `backend/integrations/polygon_options.py` | DELETE entire file |
| 2 | `backend/integrations/polygon_equities.py` | DELETE entire file |
| 3 | `backend/api/mtm_compare.py` | DELETE entire file |
| 4 | `backend/monitoring/polygon_health.py` | DELETE entire file (verify it exists first) |
| 5 | `backend/integrations/sector_snapshot.py` | DELETE `fetch_sector_prices_polygon` function and dead Polygon block in `refresh_sma_cache` |
| 6 | `backend/main.py` | Remove `mtm_compare_router` import + mount; remove `polygon_health` endpoint + import; update Polygon-referencing comment |

---

## File 1: DELETE `backend/integrations/polygon_options.py`

```bash
rm backend/integrations/polygon_options.py
```

---

## File 2: DELETE `backend/integrations/polygon_equities.py`

```bash
rm backend/integrations/polygon_equities.py
```

---

## File 3: DELETE `backend/api/mtm_compare.py`

```bash
rm backend/api/mtm_compare.py
```

---

## File 4: DELETE `backend/monitoring/polygon_health.py`

```bash
# Verify file exists first; if not, skip this step and note in commit message
ls backend/monitoring/polygon_health.py
rm backend/monitoring/polygon_health.py
```

---

## File 5: `backend/integrations/sector_snapshot.py` — remove dead Polygon code

### Edit 5.1 — Delete `fetch_sector_prices_polygon` function

**FIND** the entire function (starts around line 47):
```python
async def fetch_sector_prices_polygon() -> Dict[str, float]:
    """
    Fetch current prices for all sector ETFs + SPY in ONE Polygon API call.
    Uses the multi-ticker snapshot endpoint.
    Returns: {"SPY": 542.30, "XLK": 198.50, ...}
    """
    if not POLYGON_API_KEY:
        logger.warning("POLYGON_API_KEY not set — cannot fetch sector prices")
        return {}

    try:
        url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={
                "apiKey": POLYGON_API_KEY,
                "tickers": TICKER_LIST_STR,
            })
            resp.raise_for_status()
            data = resp.json()

        prices = {}
        for t in data.get("tickers", []):
            ticker = t.get("ticker")
            # Use day close if available, else last trade, else prevDay close
            day = t.get("day", {})
            last_trade = t.get("lastTrade", {})
            prev_day = t.get("prevDay", {})
            price = (
                day.get("c")
                or last_trade.get("p")
                or prev_day.get("c")
            )
            if ticker and price:
                prices[ticker] = float(price)

        if prices:
            logger.debug(f"Polygon sector snapshot: {len(prices)} tickers")
        return prices

    except Exception as e:
        logger.warning(f"Polygon sector snapshot failed: {e}")
        return {}


```

**REPLACE WITH:** *(nothing — delete the function and the blank line after it)*

### Edit 5.2 — Delete dead Polygon block in `refresh_sma_cache`

**FIND** (the unreachable code after the `return` statement, approximately lines 116-160):
```python
async def refresh_sma_cache() -> Dict[str, Dict[str, float]]:
    """
    Compute 20-day and 50-day SMAs via yfinance (Polygon is deprecated).
    Called once daily after close. Cached in Redis with 24h TTL.
    Returns: {"SPY": {"sma20": 540.5, "sma50": 535.2, "pct_1mo": 2.3}, ...}
    """
    return await _refresh_sma_yfinance()

    sma_data = {}
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=80)  # ~55 trading days for 50-day SMA

    async with httpx.AsyncClient(timeout=10.0) as client:
        for ticker in ALL_TICKERS:
            try:
                url = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"
                resp = await client.get(url, params={
                    "apiKey": POLYGON_API_KEY,
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": 100,
                })
                resp.raise_for_status()
                results = resp.json().get("results", [])

                if not results:
                    continue

                closes = [r["c"] for r in results]

                sma20 = sum(closes[-20:]) / min(20, len(closes)) if len(closes) >= 20 else None
                sma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 50 else None

                # 1-month performance (21 trading days)
                pct_1mo = None
                if len(closes) >= 22:
                    pct_1mo = ((closes[-1] - closes[-22]) / closes[-22]) * 100

                sma_data[ticker] = {
                    "sma20": round(sma20, 2) if sma20 else None,
                    "sma50": round(sma50, 2) if sma50 else None,
                    "pct_1mo": round(pct_1mo, 2) if pct_1mo else None,
                }

            except Exception as e:
                logger.warning(f"Polygon SMA fetch failed for {ticker}: {e}")

    # Cache in Redis
    if sma_data:
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis:
                payload = json.dumps(sma_data)
                await redis.set(SECTOR_SMA_KEY, payload, ex=86400)  # 24h TTL
                logger.info(f"Sector SMA cache refreshed: {len(sma_data)} tickers")
        except Exception as e:
            logger.warning(f"Redis SMA cache write failed: {e}")

    return sma_data
```

**REPLACE WITH:**
```python
async def refresh_sma_cache() -> Dict[str, Dict[str, float]]:
    """
    Compute 20-day and 50-day SMAs via yfinance.
    Called once daily after close. Cached in Redis with 24h TTL.
    Returns: {"SPY": {"sma20": 540.5, "sma50": 535.2, "pct_1mo": 2.3}, ...}
    """
    sma_data = await _refresh_sma_yfinance()

    # Cache in Redis
    if sma_data:
        try:
            from database.redis_client import get_redis_client
            redis = await get_redis_client()
            if redis:
                payload = json.dumps(sma_data)
                await redis.set(SECTOR_SMA_KEY, payload, ex=86400)  # 24h TTL
                logger.info(f"Sector SMA cache refreshed: {len(sma_data)} tickers")
        except Exception as e:
            logger.warning(f"Redis SMA cache write failed: {e}")

    return sma_data
```

### Edit 5.3 — Remove unused Polygon constants at top of file

**FIND** (near top of file, around lines 18-19):
```python
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
POLYGON_BASE = "https://api.polygon.io"
```

**REPLACE WITH:** *(nothing — delete both lines and the blank line after them)*

### Edit 5.4 — Remove unused imports

**FIND** at top of file:
```python
from datetime import datetime, timedelta, timezone
```

**REPLACE WITH:**
```python
# datetime imports removed — no longer needed after Polygon block deletion
```

*(If `datetime`/`timedelta`/`timezone` are still referenced elsewhere in the file after the deletions, leave the import. CC: verify with a grep before deleting.)*

### Edit 5.5 — Remove `httpx` import if no longer used

**Verify with grep:**
```bash
grep -n "httpx" backend/integrations/sector_snapshot.py
```

If no remaining references after Edits 5.1 and 5.2, remove `import httpx` from the top of the file.

### Edit 5.6 — Update module docstring

**FIND** (top of file):
```python
"""
Sector Strength Snapshot — Polygon.io

Real-time sector ETF prices via Polygon bulk snapshot (1 API call).
SMA data cached separately (refreshed once daily).

Data source: Polygon.io (primary), yfinance (fallback).
"""
```

**REPLACE WITH:**
```python
"""
Sector Strength Snapshot

Real-time sector ETF prices via yfinance.
SMA data cached separately (refreshed once daily).

Data source: yfinance (UW API migration in progress — see POST-CUTOVER-TODO.md P3).
"""
```

---

## File 6: `backend/main.py` — remove dead route mounts

### Edit 6.1 — Remove `mtm_compare_router` import

**FIND:**
```python
from api.mtm_compare import router as mtm_compare_router
```

**REPLACE WITH:** *(nothing — delete the line)*

### Edit 6.2 — Remove `mtm_compare_router` mount

**FIND:**
```python
app.include_router(mtm_compare_router, prefix="/api", tags=["mtm-validation"])
```

**REPLACE WITH:** *(nothing — delete the line)*

### Edit 6.3 — Remove `polygon-health` endpoint

**FIND:**
```python
@app.get("/api/monitoring/polygon-health")
async def polygon_health_endpoint():
    """Check Polygon.io API health from rolling call window."""
    from monitoring.polygon_health import get_polygon_health
    return get_polygon_health()


```

**REPLACE WITH:** *(nothing — delete the entire endpoint and trailing blank line)*

### Edit 6.4 — Update Polygon-referencing comment in `mark_to_market_loop`

**FIND:**
```python
    # Mark-to-market: refresh position prices at :02, :17, :32, :47 past each hour
    # (2 minutes after Polygon's 15-min data refresh) during market hours
    async def mark_to_market_loop():
        """Fetch live Polygon prices for open positions during market hours.
        Clock-aware: fires at :02, :17, :32, :47 past each hour (9 AM - 5 PM ET weekdays).
        Forces a closing bell run at 4:17 PM ET to capture near-close prices.
        """
        import pytz
        from datetime import datetime as dt_cls

        MTM_MINUTES = [2, 17, 32, 47]  # 2 min after Polygon refresh at :00/:15/:30/:45
```

**REPLACE WITH:**
```python
    # Mark-to-market: refresh position prices at :02, :17, :32, :47 past each hour
    # during market hours (offset 2 min from quarter-hour boundaries to allow data settle)
    async def mark_to_market_loop():
        """Fetch live UW API prices for open positions during market hours.
        Clock-aware: fires at :02, :17, :32, :47 past each hour (9 AM - 5 PM ET weekdays).
        Forces a closing bell run at 4:17 PM ET to capture near-close prices.
        """
        import pytz
        from datetime import datetime as dt_cls

        MTM_MINUTES = [2, 17, 32, 47]  # 2 min offset from :00/:15/:30/:45 quarter-hours
```

---

## Verification

After deploy, verify the following remain green (per the cutover brief's verification 1-4):

1. **MTM scheduler still writing prices**
```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/v2/positions" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
options = [p for p in d['positions'] if p.get('asset_type') in ('OPTION', 'SPREAD')]
priced = [p for p in options if p.get('current_price') is not None]
print(f'Options priced: {len(priced)}/{len(options)}')
print('PASS' if len(priced) >= len(options) * 0.7 else 'FAIL')
"
```

2. **Sector heatmap still 11/11**
```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/sectors/heatmap" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
priced = [s for s in d['sectors'] if s.get('price') is not None]
print(f'{len(priced)}/11')
print('PASS' if len(priced) == 11 else 'FAIL')
"
```

3. **Greeks still status: ok**
```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/v2/positions/greeks" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
print('PASS' if d.get('status') == 'ok' else 'FAIL')
"
```

4. **`mtm-compare` and `polygon-health` now return 404 (not 401, not 500)**
```bash
curl -s -o /dev/null -w "%{http_code}" \
  "https://pandoras-box-production.up.railway.app/api/positions/mtm-compare"
# Expected: 404 (route deleted)

curl -s -o /dev/null -w "%{http_code}" \
  "https://pandoras-box-production.up.railway.app/api/monitoring/polygon-health"
# Expected: 404 (route deleted)
```

5. **Logs clean of import errors after deploy**
After Railway redeploy completes, tail logs and confirm no `ModuleNotFoundError` or `ImportError` references to `polygon_options`, `polygon_equities`, `mtm_compare`, or `polygon_health`.

---

## Rollback plan

If anything breaks:
```bash
cd C:\trading-hub
git revert HEAD
git push origin main
```

The deletions are non-destructive in a normal sense (UW path was working before), but if any test code or doc-search depended on the deleted files, revert and investigate.

---

## Out of scope

- **PROJECT_RULES.md cleanup** — already updated in commit 805e7747 (April 27)
- **PineScript files in `docs/pinescript/`** — none of those reference Polygon
- **Documentation updates beyond this brief** — handled in `docs/POST-CUTOVER-TODO.md`

---

## Commit message

```
chore: post-cutover cleanup — delete dead Polygon code

Polygon plan canceled 2026-04-27. Today's UW cutover migrated all live
production paths off Polygon. This commit removes the remaining dead code:

- DELETE backend/integrations/polygon_options.py
- DELETE backend/integrations/polygon_equities.py
- DELETE backend/api/mtm_compare.py (migration scaffolding, role complete)
- DELETE backend/monitoring/polygon_health.py
- sector_snapshot.py: remove fetch_sector_prices_polygon function
- sector_snapshot.py: remove dead Polygon block in refresh_sma_cache
- sector_snapshot.py: remove unused POLYGON_API_KEY/POLYGON_BASE constants
- main.py: remove mtm_compare_router import + mount
- main.py: remove /api/monitoring/polygon-health endpoint
- main.py: update Polygon-referencing comment in mark_to_market_loop

Net effect:
- /api/positions/mtm-compare → 404 (was 401, scaffolding endpoint)
- /api/monitoring/polygon-health → 404
- All MTM, heatmap, Greeks endpoints unaffected (verified post-deploy)

No production functionality removed — only dead code paths.
```

---

## Session checklist for CC

1. `cd C:\trading-hub && git pull origin main`
2. Read this brief in full.
3. Verify `backend/monitoring/polygon_health.py` exists before attempting File 4 deletion (skip with note if not).
4. Apply Edits 1 → 6.4 in order.
5. Run syntax check: `python -m py_compile backend/integrations/sector_snapshot.py backend/main.py`
6. Run grep verification: `grep -r "polygon_options\|polygon_equities\|mtm_compare\|polygon_health" backend/ --include="*.py"` — should return zero results
7. Commit with the message above.
8. `git push origin main`
9. Wait ~90s for Railway deploy.
10. Run all 5 verification curls.
11. If all PASS, post: "Cleanup complete. All Polygon dead code removed. mtm-compare and polygon-health now 404 as expected."
