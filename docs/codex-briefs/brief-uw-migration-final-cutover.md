# CC Brief — UW Migration Final Cutover

**Date:** 2026-04-27
**Author:** Opus (via Nick)
**Status:** URGENT — markets open, MTM dead
**Scope:** ~5 surgical edits across 4 files

---

## Background — why this brief exists

The April UW migration (Sprints 1-4) was incomplete. Sprint 4 built UW-equivalents of the Polygon MTM functions in `backend/integrations/uw_api.py` (`get_spread_value`, `get_single_option_value`, `get_multi_leg_value`, `get_ticker_greeks_summary`) and a comparison endpoint at `/api/positions/mtm-compare`. The plan was to validate those for 3-5 trading days, then cut over the production code paths from Polygon to UW.

**The cutover never happened.** The Polygon Stocks Starter plan has now been disabled or downgraded — every Polygon call is returning HTTP 403 `NOT_AUTHORIZED`. As a result:

- **Background MTM scheduler is dead** (`backend/api/unified_positions.py::run_mark_to_market`). All option positions in `unified_positions` show `current_price=null`, `unrealized_pnl=0`, `price_updated_at` frozen at Friday's deploy.
- **Sector heatmap is dead** (`backend/api/sectors.py` and `backend/integrations/sector_snapshot.py`). Polygon snapshot returns empty, falls back to historical yfinance bars, only 4 of 11 ETFs survive.
- **Trade idea enrichment Polygon snapshot is dead** (`backend/enrichment/context_modifier.py`). Same root cause.
- **Bonus bugs found in logs:**
  - `_portfolio_greeks_inner` in `unified_positions.py` calls `get_redis_client()` without a module-level import → `NameError`.
  - `enrich_trade_idea` in `context_modifier.py:382` uses `%d` format for `signal_id` which is a VARCHAR string → `TypeError` on every Holy Grail signal.

Verified live: `/api/positions/mtm-compare` already returns valid UW MTM values for 7/12 spreads right now during market hours, proving the UW path works on demand. The bug is that the background scheduler doesn't use the UW path.

---

## Scope of this fix

Five surgical edits across four files. **No new functions, no architecture changes.** Just swap Polygon imports for the UW equivalents that already exist with identical signatures, fix two unrelated bugs that surfaced in the same investigation.

| # | File | Change |
|---|---|---|
| 1 | `backend/api/unified_positions.py` | Add `get_redis_client` module-level import; swap MTM scheduler imports from `polygon_options` to `uw_api`; swap Greeks endpoint imports |
| 2 | `backend/api/sectors.py` | Replace `_fetch_sector_snapshot` Polygon body with yfinance via `uw_api.get_snapshot`; replace `_fetch_all_bars` Polygon body with `uw_api.get_bars` |
| 3 | `backend/integrations/sector_snapshot.py` | Make `fetch_sector_prices` skip the dead Polygon path and use yfinance only |
| 4 | `backend/enrichment/context_modifier.py` | Replace `_get_snapshot` Polygon body with `uw_api.get_snapshot` calls; fix two `%d` → `%s` log format bugs |

---

## File 1: `backend/api/unified_positions.py`

### Edit 1.1 — Add module-level Redis import

**FIND** (around line 17, after the postgres_client import):
```python
from database.postgres_client import get_postgres_client
from websocket.broadcaster import manager
from models.position_risk import calculate_position_risk, infer_direction
```

**REPLACE WITH:**
```python
from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client
from websocket.broadcaster import manager
from models.position_risk import calculate_position_risk, infer_direction
```

### Edit 1.2 — Greeks endpoint: swap to UW

**FIND** (in `_portfolio_greeks_inner`, the import block):
```python
    # Try UW API first, fall back to Polygon
    get_ticker_greeks_summary = None
    try:
        from integrations.uw_api import get_options_snapshot as _uw_opts
        from integrations.polygon_options import get_ticker_greeks_summary
    except ImportError:
        pass
    if not get_ticker_greeks_summary:
        try:
            from integrations.polygon_options import get_ticker_greeks_summary, POLYGON_API_KEY
            if not POLYGON_API_KEY:
                return {"status": "no_api_key", "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}
        except ImportError:
            return {"status": "unavailable", "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}
```

**REPLACE WITH:**
```python
    # UW API only — Polygon is deprecated
    try:
        from integrations.uw_api import get_ticker_greeks_summary, UW_API_KEY
        if not UW_API_KEY:
            return {"status": "no_api_key", "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}
    except ImportError:
        return {"status": "unavailable", "tickers": {}, "totals": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}}
```

### Edit 1.3 — MTM scheduler: swap to UW

**FIND** (top of `run_mark_to_market`):
```python
    # Import options valuation functions — UW API provides Polygon-compatible schemas
    try:
        from integrations.polygon_options import (
            get_spread_value, get_single_option_value, get_multi_leg_value, POLYGON_API_KEY
        )
    except ImportError:
        POLYGON_API_KEY = ""
        get_spread_value = None
        get_single_option_value = None
        get_multi_leg_value = None
```

**REPLACE WITH:**
```python
    # UW API only — Polygon is deprecated
    try:
        from integrations.uw_api import (
            get_spread_value, get_single_option_value, get_multi_leg_value, UW_API_KEY
        )
    except ImportError:
        UW_API_KEY = ""
        get_spread_value = None
        get_single_option_value = None
        get_multi_leg_value = None
```

### Edit 1.4 — MTM scheduler: rename use_polygon flag

**FIND:**
```python
    use_polygon = bool(POLYGON_API_KEY) and get_spread_value is not None
```

**REPLACE WITH:**
```python
    use_options_pricing = bool(UW_API_KEY) and get_spread_value is not None
```

### Edit 1.5 — MTM scheduler: update flag references and log strings

**FIND** (4 occurrences of `use_polygon` in the function body):
```python
        if use_polygon and expiry and legs_data:
```
**REPLACE WITH:**
```python
        if use_options_pricing and expiry and legs_data:
```

**FIND:**
```python
        if current_price is None and use_polygon and expiry and long_strike:
```
**REPLACE WITH:**
```python
        if current_price is None and use_options_pricing and expiry and long_strike:
```

**FIND:**
```python
                logger.warning("Multi-leg mark-to-market failed for %s: %s", row["position_id"], e)
```
**REPLACE WITH:** *(no change — just confirming this stays)*

**FIND:**
```python
                logger.warning("Polygon mark-to-market failed for %s: %s", row["position_id"], e)
```
**REPLACE WITH:**
```python
                logger.warning("UW mark-to-market failed for %s: %s", row["position_id"], e)
```

**FIND:**
```python
    result = {"status": "updated", "updated": updated, "source": "polygon" if use_polygon else "yfinance"}
```
**REPLACE WITH:**
```python
    result = {"status": "updated", "updated": updated, "source": "uw" if use_options_pricing else "yfinance"}
```

---

## File 2: `backend/api/sectors.py`

### Edit 2.1 — Replace `_fetch_all_bars` Polygon body with UW bars

**FIND** the entire function:
```python
async def _fetch_all_bars(tickers: List[str] = None, days: int = 45) -> Dict[str, List[float]]:
    """Fetch daily close bars from Polygon for SPY + sector ETFs.

    Primary data source: Polygon.io (Stocks Starter plan).
    No yfinance dependency.
    """
    if not POLYGON_API_KEY:
        logger.warning("POLYGON_API_KEY not set — cannot fetch historical bars")
        return {}

    from datetime import date as date_cls, timedelta as td
    today = date_cls.today()
    from_date = (today - td(days=days)).isoformat()
    to_date = today.isoformat()  # Include today's partial bar for intraday fallback

    target_tickers = tickers or ALL_TICKERS
    results: Dict[str, List[float]] = {}

    async with aiohttp.ClientSession() as session:
        for ticker in target_tickers:
            try:
                url = (
                    f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day"
                    f"/{from_date}/{to_date}?adjusted=true&sort=asc&apiKey={POLYGON_API_KEY}"
                )
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bars = data.get("results", [])
                        if bars:
                            results[ticker] = [b["c"] for b in bars if "c" in b]
                    else:
                        logger.debug("Polygon bars HTTP %d for %s", resp.status, ticker)
            except asyncio.TimeoutError:
                logger.debug("Polygon bars timeout for %s", ticker)
            except Exception as e:
                logger.debug("Polygon bars failed for %s: %s", ticker, e)

    if len(results) < 6:
        logger.warning("Polygon returned bars for only %d/%d tickers", len(results), len(target_tickers))

    return results
```

**REPLACE WITH:**
```python
async def _fetch_all_bars(tickers: List[str] = None, days: int = 45) -> Dict[str, List[float]]:
    """Fetch daily close bars via uw_api.get_bars (yfinance under the hood).

    Polygon is deprecated. UW API wraps yfinance for OHLCV bars.
    """
    from integrations.uw_api import get_bars

    from datetime import date as date_cls, timedelta as td
    today = date_cls.today()
    from_date = (today - td(days=days)).isoformat()
    to_date = today.isoformat()  # Include today's partial bar for intraday fallback

    target_tickers = tickers or ALL_TICKERS
    results: Dict[str, List[float]] = {}

    for ticker in target_tickers:
        try:
            bars = await get_bars(ticker, 1, "day", from_date, to_date)
            if bars:
                results[ticker] = [b["c"] for b in bars if "c" in b and b["c"] is not None]
        except Exception as e:
            logger.debug("uw_api bars failed for %s: %s", ticker, e)

    if len(results) < 6:
        logger.warning("uw_api returned bars for only %d/%d tickers", len(results), len(target_tickers))

    return results
```

### Edit 2.2 — Replace `_fetch_sector_snapshot` Polygon body with UW snapshot

**FIND** the entire function:
```python
async def _fetch_sector_snapshot(tickers: List[str]) -> Dict[str, Dict]:
    """Fetch Polygon snapshot for a list of tickers. Returns {ticker: snapshot_data}."""
    if not POLYGON_API_KEY:
        return {}

    # Build a stable cache key from first 5 sorted tickers (per-sector)
    cache_key = "sector:snapshot:" + ",".join(sorted(tickers[:5]))
    redis = await get_redis_client()

    # Check per-request cache (5s TTL)
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    result: Dict[str, Dict] = {}
    try:
        ticker_str = ",".join(tickers)
        url = f"{SNAPSHOT_URL}?tickers={ticker_str}&apiKey={POLYGON_API_KEY}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    body_preview = await resp.text()
                    logger.warning("Polygon sector snapshot HTTP %d — body: %.200s", resp.status, body_preview)
                    return result
                data = await resp.json()
                for t in data.get("tickers", []):
                    sym = t.get("ticker", "")
                    day = t.get("day", {})
                    prev = t.get("prevDay", {})
                    price = day.get("c") or prev.get("c") or 0
                    prev_close = prev.get("c") or 0
                    day_change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
                    result[sym] = {
                        "price": round(price, 2),
                        "day_change_pct": day_change_pct,
                        "volume": day.get("v", 0),
                        "prev_volume": prev.get("v", 0),
                    }
    except Exception as e:
        logger.error("Polygon sector snapshot error: %s", e)

    # Cache for 5 seconds
    if redis and result:
        try:
            await redis.set(cache_key, json.dumps(result), ex=5)
        except Exception:
            pass

    return result
```

**REPLACE WITH:**
```python
async def _fetch_sector_snapshot(tickers: List[str]) -> Dict[str, Dict]:
    """Fetch live snapshot via uw_api.get_snapshot (yfinance under the hood).

    Polygon is deprecated. UW API wraps yfinance for real-time quotes.
    """
    from integrations.uw_api import get_snapshot

    # Build a stable cache key from first 5 sorted tickers (per-sector)
    cache_key = "sector:snapshot:" + ",".join(sorted(tickers[:5]))
    redis = await get_redis_client()

    # Check per-request cache (5s TTL)
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    result: Dict[str, Dict] = {}
    for ticker in tickers:
        try:
            snap = await get_snapshot(ticker)
            if not snap:
                continue
            day = snap.get("day", {}) or {}
            prev = snap.get("prevDay", {}) or {}
            price = day.get("c") or snap.get("lastTrade", {}).get("p") or prev.get("c") or 0
            prev_close = prev.get("c") or 0
            day_change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
            result[ticker] = {
                "price": round(float(price), 2) if price else 0,
                "day_change_pct": day_change_pct,
                "volume": day.get("v", 0) or 0,
                "prev_volume": prev.get("v", 0) or 0,
            }
        except Exception as e:
            logger.debug("uw_api snapshot failed for %s: %s", ticker, e)

    # Cache for 5 seconds
    if redis and result:
        try:
            await redis.set(cache_key, json.dumps(result), ex=5)
        except Exception:
            pass

    return result
```

---

## File 3: `backend/integrations/sector_snapshot.py`

### Edit 3.1 — Skip dead Polygon path in `fetch_sector_prices`

**FIND:**
```python
async def fetch_sector_prices() -> Dict[str, float]:
    """Polygon first, yfinance fallback."""
    prices = await fetch_sector_prices_polygon()
    if len(prices) >= 6:  # At least half the tickers
        return prices
    logger.warning(f"Polygon returned only {len(prices)} tickers — trying yfinance fallback")
    return await fetch_sector_prices_yfinance()
```

**REPLACE WITH:**
```python
async def fetch_sector_prices() -> Dict[str, float]:
    """yfinance only — Polygon is deprecated."""
    return await fetch_sector_prices_yfinance()
```

### Edit 3.2 — Skip dead Polygon path in `refresh_sma_cache`

**FIND:**
```python
async def refresh_sma_cache() -> Dict[str, Dict[str, float]]:
    """
    Fetch historical daily bars from Polygon and compute 20-day and 50-day SMAs.
    Called once daily after close. Cached in Redis with 24h TTL.
    Returns: {"SPY": {"sma20": 540.5, "sma50": 535.2, "pct_1mo": 2.3}, ...}
    """
    if not POLYGON_API_KEY:
        return await _refresh_sma_yfinance()
```

**REPLACE WITH:**
```python
async def refresh_sma_cache() -> Dict[str, Dict[str, float]]:
    """
    Compute 20-day and 50-day SMAs via yfinance (Polygon is deprecated).
    Called once daily after close. Cached in Redis with 24h TTL.
    Returns: {"SPY": {"sma20": 540.5, "sma50": 535.2, "pct_1mo": 2.3}, ...}
    """
    return await _refresh_sma_yfinance()
```

*(The remainder of the original `refresh_sma_cache` body — the Polygon-calling block — becomes unreachable but should be left in place for now. Don't delete.)*

---

## File 4: `backend/enrichment/context_modifier.py`

### Edit 4.1 — Replace `_get_snapshot` Polygon body with UW

**FIND:**
```python
async def _get_snapshot(tickers: list) -> Dict[str, Dict]:
    """Fetch Polygon snapshot for tickers."""
    if not POLYGON_API_KEY:
        return {}
    try:
        ticker_str = ",".join(tickers)
        url = f"{SNAPSHOT_URL}?tickers={ticker_str}&apiKey={POLYGON_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                result = {}
                for t in data.get("tickers", []):
                    sym = t.get("ticker", "")
                    day = t.get("day", {})
                    prev = t.get("prevDay", {})
                    price = day.get("c") or prev.get("c") or 0
                    prev_close = prev.get("c") or 0
                    day_change = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
                    result[sym] = {
                        "price": round(price, 2),
                        "day_change_pct": day_change,
                        "volume": day.get("v", 0),
                        "prev_volume": prev.get("v", 0),
                    }
                return result
    except Exception as e:
        logger.warning("Context modifier snapshot error: %s", e)
        return {}
```

**REPLACE WITH:**
```python
async def _get_snapshot(tickers: list) -> Dict[str, Dict]:
    """Fetch snapshot via uw_api.get_snapshot (yfinance under the hood)."""
    from integrations.uw_api import get_snapshot
    result = {}
    for ticker in tickers:
        try:
            snap = await get_snapshot(ticker)
            if not snap:
                continue
            day = snap.get("day", {}) or {}
            prev = snap.get("prevDay", {}) or {}
            price = day.get("c") or snap.get("lastTrade", {}).get("p") or prev.get("c") or 0
            prev_close = prev.get("c") or 0
            day_change = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
            result[ticker] = {
                "price": round(float(price), 2) if price else 0,
                "day_change_pct": day_change,
                "volume": day.get("v", 0) or 0,
                "prev_volume": prev.get("v", 0) or 0,
            }
        except Exception as e:
            logger.debug("Context modifier snapshot failed for %s: %s", ticker, e)
    return result
```

### Edit 4.2 — Fix info log format bug

**FIND:**
```python
        logger.info(
            "Context modifier for %s (id=%d): %+d (adjusted %d -> %d, contrarian=%s)",
            ticker, signal_id, context_modifier, base_score, adjusted_score, is_contrarian,
        )
```

**REPLACE WITH:**
```python
        logger.info(
            "Context modifier for %s (id=%s): %+d (adjusted %d -> %d, contrarian=%s)",
            ticker, signal_id, context_modifier, base_score, adjusted_score, is_contrarian,
        )
```

### Edit 4.3 — Fix error log format bug

**FIND:**
```python
    except Exception as e:
        logger.error("Context modifier enrichment failed for %s (id=%d): %s", ticker, signal_id, e)
```

**REPLACE WITH:**
```python
    except Exception as e:
        logger.error("Context modifier enrichment failed for %s (id=%s): %s", ticker, signal_id, e)
```

---

## Verification (CC must run after deploy)

After Railway redeploys, wait 60 seconds for the MTM background loop to run, then verify:

### 1. MTM scheduler is writing prices

```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/v2/positions" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
options = [p for p in d['positions'] if p.get('asset_type') in ('OPTION', 'SPREAD')]
priced = [p for p in options if p.get('current_price') is not None]
print(f'Options positions: {len(options)} | with current_price: {len(priced)}')
print(f'PASS' if len(priced) >= len(options) * 0.7 else 'FAIL — fewer than 70% priced')
"
```
**Expected:** ≥70% of option positions show non-null `current_price`. (Some illiquid contracts may legitimately fail.)

### 2. Sector heatmap returns live prices for all 11 sectors

```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/sectors/heatmap" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
priced = [s for s in d['sectors'] if s.get('price') is not None]
print(f'Sectors with price: {len(priced)}/11')
print(f'PASS' if len(priced) == 11 else 'FAIL')
"
```
**Expected:** 11/11 sectors with non-null price.

### 3. Greeks endpoint no longer NameErrors

```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/v2/positions/greeks" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'status: {d.get(\"status\")}')
print(f'PASS' if d.get('status') == 'ok' else 'FAIL')
"
```
**Expected:** `status: ok`

### 4. Railway logs are clean of `get_redis_client is not defined` and `%d format` errors

After deploy, tail logs for 60 seconds and confirm neither error appears. Any other warnings are pre-existing.

### 5. `mtm-compare` still works

```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/positions/mtm-compare" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
uw_priced = [p for p in d['positions'] if p.get('uw_mtm') is not None]
print(f'UW priced: {len(uw_priced)}/{len(d[\"positions\"])}')
"
```
**Expected:** Same number of UW-priced positions as before (this was working before, should still work).

---

## Rollback plan

If verification fails badly:
```bash
cd C:\trading-hub
git revert HEAD
git push origin main
```
Railway redeploys to pre-fix state. **Note:** rollback restores Polygon-calling code which is broken anyway — rollback only makes sense if the new code is *worse* than the broken-but-stable pre-fix state. Forward-fix preferred.

---

## Out of scope (do NOT touch)

- `backend/integrations/polygon_options.py` — leave the file in place. After this brief lands and verifies, it becomes deletable dead code. Do not delete in this brief.
- `backend/integrations/polygon_equities.py` — same.
- `backend/integrations/sector_snapshot.py::fetch_sector_prices_polygon` and `refresh_sma_cache` Polygon block — leave the function bodies. Just bypass them per Edit 3.1 / 3.2.
- The unreachable Polygon block inside `refresh_sma_cache` — leave it. Cleanup is a separate brief.
- Any other Polygon references in the codebase that don't match the find anchors above — flag and report, don't change.

---

## Commit message

```
fix(mtm,sectors): finish UW migration cutover — drop dead Polygon paths

Polygon plan was disabled, returning HTTP 403 NOT_AUTHORIZED. The April UW
migration (Sprints 1-4) built UW equivalents but the cutover was never
finalized. This commit completes the swap:

- run_mark_to_market: Polygon → uw_api MTM functions
- portfolio_greeks: Polygon → uw_api MTM functions + add module-level redis import
- _fetch_sector_snapshot: Polygon → uw_api.get_snapshot
- _fetch_all_bars: Polygon → uw_api.get_bars
- sector_snapshot.fetch_sector_prices: skip dead Polygon, yfinance only
- sector_snapshot.refresh_sma_cache: skip dead Polygon, yfinance only
- context_modifier._get_snapshot: Polygon → uw_api.get_snapshot

Bonus bugfixes surfaced in the same diagnostic run:
- unified_positions._portfolio_greeks_inner: NameError on get_redis_client
  (added module-level import)
- context_modifier.enrich_trade_idea: TypeError on %d format with VARCHAR
  signal_id (changed to %s in two places)

polygon_options.py and polygon_equities.py remain in place as dead code.
Cleanup follows in a separate commit after verification.
```

---

## Session checklist for CC

1. Pull latest: `cd C:\trading-hub && git pull origin main`
2. Read this brief in full.
3. Apply Edits 1.1 → 4.3 in order.
4. Run any local syntax check: `python -m py_compile backend/api/unified_positions.py backend/api/sectors.py backend/integrations/sector_snapshot.py backend/enrichment/context_modifier.py`
5. Commit with the message above.
6. `git push origin main`
7. Wait ~90s for Railway to deploy (transient 502s expected).
8. Run all 5 verification curls.
9. If anything FAILs, do NOT attempt fixes — report the failure to Nick.
10. If all PASS, post a summary message: "UW migration cutover complete. MTM, heatmap, greeks all green. polygon_options.py and polygon_equities.py are now deletable dead code (separate brief)."
