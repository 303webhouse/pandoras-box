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
