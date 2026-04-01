# BUG FIX: Chronos FMP Stable API Field Mapping + ETF Holdings Fallback
## Priority: P0 (blocks Chronos data population)
## Date: 2026-04-01

---

## THE PROBLEM

The FMP API client (`backend/integrations/fmp_client.py`) was pointing at the **legacy** v3 endpoint which returns 403 for new accounts. The base URL has been fixed to use the Stable API (`https://financialmodelingprep.com/stable`), but the Stable API returns **different response fields** than what the ingestion code expects.

**Stable API earnings response (confirmed working):**
```json
{
  "symbol": "BAC",
  "date": "2026-04-15",
  "epsActual": null,
  "epsEstimated": 0.99,
  "revenueActual": null,
  "revenueEstimated": 29793700000,
  "lastUpdated": "2026-04-01"
}
```

**Fields the ingestion code expects but Stable API does NOT return:**
- `name` / `company_name` — NOT present (no company name in response)
- `fiscalDateEnding` — NOT present
- `fiscal_year` — NOT present
- `time` — NOT present (no BMO/AMC timing info)
- `marketCap` — NOT present

**Additionally:** The ETF holdings endpoint (`/stable/etf/holdings`) returns 402 (paid only). The `refresh_etf_components()` function in `position_overlap.py` will fail on free tier.

---

## FIX 1: Update `fmp_client.py` — Timing Detection

The `_timing` field logic in `fetch_earnings_calendar()` currently checks `entry.get("time")`, which the Stable API does not return. The timing info needs to come from a different source.

**Option A (recommended):** Remove the timing normalization from `fmp_client.py` entirely. Set `_timing` to `None` for all entries. Then use a separate Polygon snapshot call to get BMO/AMC timing for the ~20-30 tickers that overlap with positions/watchlist (not all 500+ entries). This avoids wasting the free API budget.

**Option B (simpler):** Just default everything to `None` and accept we don't have BMO/AMC info from FMP free tier. The earnings DATE is the critical info — timing is nice-to-have.

Implement Option B for now (simplest, unblocks the pipeline):

In `backend/integrations/fmp_client.py`, replace the timing normalization loop:

```python
    # Stable API does not include 'time' field (BMO/AMC)
    # Default to None — timing can be enriched later from other sources
    for entry in data:
        entry["_timing"] = None
```

---

## FIX 2: Update `chronos_ingest.py` — Handle Missing Fields Gracefully

The SQL INSERT passes 12 values. Several source fields don't exist in Stable API responses. Update the parameter mapping to handle None gracefully for missing fields:

In `backend/jobs/chronos_ingest.py`, in the upsert loop, change the parameter block to:

```python
                ticker,
                None,  # company_name — not available from FMP Stable free tier
                report_date,
                None,  # fiscal_period — not available from FMP Stable free tier
                None,  # fiscal_year — not available from FMP Stable free tier
                entry.get("_timing"),  # Will be None (see fmp_client fix)
                _to_float(entry.get("epsEstimated")),
                _to_int(entry.get("revenueEstimated")),
                None,  # market_cap — not available from FMP Stable free tier
                in_book,
                in_wl,
                overlap_details
```

This replaces the previous lines that tried to read `entry.get("name")`, `entry.get("fiscalDateEnding")`, `entry.get("fiscal_year")`, and `entry.get("marketCap")`.

---

## FIX 3: Guard `refresh_etf_components()` in `position_overlap.py`

The ETF holdings endpoint is paid-only (returns 402). The weekly refresh call will crash. Add a guard:

In `backend/utils/position_overlap.py`, in `refresh_etf_components()`, wrap the fetch call so that a 402/403 response logs a warning and keeps the hardcoded defaults:

```python
async def refresh_etf_components():
    """
    Refresh ETF_COMPONENTS dict from FMP ETF holdings API.
    Falls back to hardcoded values if FMP fails or endpoint is paid-only.
    """
    from integrations.fmp_client import fetch_etf_holdings

    etf_tickers = ["XLF", "SMH", "IYR"]

    for etf in etf_tickers:
        try:
            holdings = await fetch_etf_holdings(etf, limit=10)
            if holdings:
                new_components = [h.get("asset", "").upper() for h in holdings if h.get("asset")]
                if new_components:  # Only update if we got real data
                    ETF_COMPONENTS[etf] = new_components
                    logger.info("Refreshed %s components: %s", etf, ETF_COMPONENTS[etf])
                else:
                    logger.info("FMP returned empty holdings for %s — keeping hardcoded values", etf)
            else:
                logger.info("FMP ETF holdings unavailable for %s (likely paid-only) — keeping hardcoded values", etf)
        except Exception as e:
            logger.warning("Failed to refresh %s components from FMP: %s — keeping hardcoded values", etf, e)
```

Also in `fmp_client.py`, make `fetch_etf_holdings` NOT raise on 402/403:

```python
async def fetch_etf_holdings(symbol: str, limit: int = 10) -> List[Dict]:
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping ETF holdings fetch")
        return []

    url = f"{FMP_BASE_URL}/etf/holdings"
    params = {"symbol": symbol, "apikey": FMP_API_KEY}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        if resp.status_code in (402, 403):
            logger.info("FMP ETF holdings endpoint is paid-only (status %d)", resp.status_code)
            return []
        resp.raise_for_status()
        data = resp.json()

    return data[:limit] if data else []
```

Note the endpoint path changed too: Stable API uses `/etf/holdings?symbol=XLF` not `/etf-holder/XLF`.

---

## FIX 4: Enrich Key Tickers with Polygon Data (Optional Enhancement)

For tickers that overlap with positions or watchlist (typically 10-30 tickers), we can enrich the missing fields using Polygon, which is already integrated. This is optional but improves the Chronos display.

In `chronos_ingest.py`, AFTER the main upsert loop, add an enrichment pass for book-impact tickers only:

```python
        # 3b. Enrich book-impact tickers with Polygon data (company name + market cap)
        try:
            from integrations.polygon_equities import get_snapshot
            book_tickers = [t for t in set(
                ticker for entry in earnings
                if (ticker := (entry.get("symbol") or "").upper())
                and (ticker in position_tickers or ticker in etf_component_set or ticker in watchlist_tickers)
            )]

            for bt in book_tickers[:30]:  # Limit to 30 to avoid API spam
                try:
                    snapshot = await get_snapshot(bt)
                    if snapshot:
                        market_cap = snapshot.get("market_cap") or snapshot.get("ticker", {}).get("market_cap")
                        name = snapshot.get("name") or snapshot.get("ticker", {}).get("name")
                        if market_cap or name:
                            await conn.execute("""
                                UPDATE earnings_calendar
                                SET market_cap = COALESCE($1, market_cap),
                                    company_name = COALESCE($2, company_name)
                                WHERE ticker = $3 AND report_date >= $4
                            """, _to_int(market_cap), name, bt, today)
                except Exception as enrich_err:
                    logger.debug("Chronos: enrichment failed for %s — %s", bt, enrich_err)
        except ImportError:
            logger.debug("Polygon equities not available for enrichment — skipping")
```

**NOTE:** Check the actual Polygon snapshot response structure. The field paths above (`snapshot.get("market_cap")`) may need adjustment based on how `get_snapshot()` returns data in this codebase. Search for existing usage of `get_snapshot` in the codebase to match the pattern.

If this is too complex for this fix cycle, skip it — the system works fine without company names and market caps. The earnings DATES are what matter.

---

## VERIFICATION

After deploying, run:
```
POST /api/chronos/refresh
Header: X-API-Key: rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk
```

Expected: `{"status": "ok", "message": "Earnings refresh complete"}` (no 500)

Then verify data populated:
```
GET /api/chronos/this-week
```

Expected: `total_earnings` > 0, with entries including BAC, C, WFC for mid-April.

Then verify the Chronos tab in Agora shows data in "Market Movers" section.

---

## FILES MODIFIED

| File | Action |
|------|--------|
| `backend/integrations/fmp_client.py` | **MODIFY** — Fix timing normalization, handle 402 on ETF holdings, fix ETF endpoint path |
| `backend/jobs/chronos_ingest.py` | **MODIFY** — Use None for missing fields, optional Polygon enrichment |
| `backend/utils/position_overlap.py` | **MODIFY** — Guard refresh_etf_components against paid-only endpoint |

---

## FIX 5: Sector Heatmap 502 — yfinance Timeout Crash

**Symptom:** `GET /api/sectors/heatmap` returns 502 (Railway timeout). Has been stuck for 2 days.

**Root cause:** The `_fetch_all_bars_sync()` function in `backend/api/sectors.py` calls `yf.download()` for 12 tickers via `run_in_executor`. When yfinance hangs (which it does frequently — it's a scraper), the executor thread blocks indefinitely. Railway's 30-second request timeout fires and returns 502. Since the result is never cached, every subsequent request also hangs, creating a permanent failure loop.

**The fix has three parts:**

### 5a. Add timeout to yfinance call

In `backend/api/sectors.py`, wrap the `_fetch_all_bars()` async wrapper with a timeout:

```python
async def _fetch_all_bars() -> Dict[str, List[float]]:
    """Async wrapper around synchronous yfinance batch download with timeout."""
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_all_bars_sync),
            timeout=15.0  # 15 second max — if yfinance is slow, bail out
        )
    except asyncio.TimeoutError:
        logger.warning("yfinance batch download timed out after 15s — using stale cache")
        return {}
    except Exception as e:
        logger.warning("yfinance batch download error: %s — using stale cache", e)
        return {}
```

This replaces the current `_fetch_all_bars()` which has no timeout.

### 5b. Return stale cache immediately if yfinance fails

In the `get_sector_heatmap()` endpoint, the code currently tries to load yfinance data and only falls back to stale cache at the very end if `has_real_data` is False. But Polygon snapshot data (the live daily data) is fine — it's only the weekly/monthly historical bars from yfinance that are failing.

Restructure the endpoint to be more resilient. After the yfinance call, if `all_closes` is empty, proceed with Polygon-only data (daily changes work, weekly/monthly will show as null):

Find this block:
```python
    if not all_closes:
        all_closes = await _fetch_all_bars()
```

Replace with:
```python
    if not all_closes:
        all_closes = await _fetch_all_bars()
        if not all_closes:
            logger.warning("Sector heatmap: no historical bars available (yfinance down). Daily data from Polygon only.")
```

This ensures the endpoint always returns something useful (Polygon daily changes) even when yfinance is completely dead. The weekly/monthly columns will show 0.0 or null, which is acceptable — "no data" is better than "entire heatmap dead."

### 5c. Replace yfinance with Polygon for historical bars (MANDATORY)

**Established project rule: Polygon.io is PRIMARY for ALL market data. yfinance is FALLBACK ONLY when Polygon is unavailable. This heatmap endpoint violates that rule by using yfinance as the primary source for weekly/monthly historical bars. Fix it.**

Remove the `_fetch_all_bars_sync()` and `_fetch_all_bars()` functions entirely. Replace with a Polygon-based implementation. The Stocks Starter plan ($29/mo) includes unlimited API calls and 5 years of daily bars — more than enough for 45 days of history on 12 tickers.

**Replace both functions** (`_fetch_all_bars_sync` and `_fetch_all_bars`) with a single async Polygon fetcher:

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
    to_date = (today - td(days=1)).isoformat()  # Yesterday — today's bar is partial
    
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

**Also remove** all references to `_fetch_all_bars_sync`, the `yfinance` import at the top of the file (`import yfinance as yf`), and the `TICKER_STR` variable (only used by the old yfinance batch call).

**Remove `yfinance` from the heatmap code path entirely.** The only acceptable use of yfinance in this file is: NONE. If Polygon fails for a ticker, that ticker shows null for weekly/monthly — do not fall back to yfinance.

In the heatmap endpoint, the cache flow stays the same — check `HEATMAP_HIST_KEY` in Redis first, if miss then call `_fetch_all_bars()` (now Polygon), cache for 30 min.

---

## UPDATED VERIFICATION

After deploying all fixes:

1. `POST /api/chronos/refresh` → should return 200 with `"message": "Earnings refresh complete"`
2. `GET /api/chronos/this-week` → should show `total_earnings` > 0
3. `GET /api/sectors/heatmap` → should return 200 with sector data (NOT 502)
4. Sector heatmap in Agora should display colored cells with daily changes
5. If weekly/monthly columns show 0.0, that's acceptable for V1 — daily is the critical data

## UPDATED FILES MODIFIED

| File | Action |
|------|--------|
| `backend/integrations/fmp_client.py` | **MODIFY** — Fix timing, handle 402, fix ETF path |
| `backend/jobs/chronos_ingest.py` | **MODIFY** — Null missing fields, optional enrichment |
| `backend/utils/position_overlap.py` | **MODIFY** — Guard refresh_etf_components |
| `backend/api/sectors.py` | **MODIFY** — Add timeout to yfinance, stale fallback, optional Polygon bars |
