# BRIEF: Chronos Phase B — Earnings Calendar + FMP Integration
## Priority: P0 | System: Railway Postgres + FastAPI + FMP API
## Date: 2026-04-01
## Related: Chronos Phase A (Watchlist), Phase C (Frontend)
## Dependency: FMP API key must be in Railway env vars as `FMP_API_KEY`

---

## CONTEXT FOR CLAUDE CODE

Chronos is an earnings awareness system that answers: "which companies reporting earnings this week affect my positions or watchlist?" It pulls earnings dates from Financial Modeling Prep (FMP) free API, stores them in Postgres, and cross-references with Nick's positions and watchlist.

**Why this matters for an options trader:** Earnings reports cause "IV crush" — the implied volatility premium baked into options prices collapses after the announcement, even if the stock moves in the right direction. Nick holds put spreads on ETFs (XLF, SMH, HYG, IYR, IWM). When the top holdings of those ETFs report earnings, the ETFs move like they have their own earnings event. Nick needs to see this coming.

**FMP Free Tier:** 250 API calls/day, no credit card required.
- Earnings calendar: `GET https://financialmodelingprep.com/api/v3/earning_calendar?from={date}&to={date}&apikey={key}`
- ETF holdings: `GET https://financialmodelingprep.com/api/v3/etf-holder/{symbol}?apikey={key}`

**Database is Railway Postgres** (NOT Supabase). Use `get_postgres_client()`.

---

## STEP 1: Database — `earnings_calendar` Table

Add to `init_database()` in `database/postgres_client.py`:

```sql
CREATE TABLE IF NOT EXISTS earnings_calendar (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    company_name TEXT,
    report_date DATE NOT NULL,
    fiscal_period TEXT,
    fiscal_year INTEGER,
    timing TEXT CHECK (timing IN ('BMO', 'AMC', 'TNS', NULL)),
    eps_estimate NUMERIC(10,4),
    eps_actual NUMERIC(10,4),
    revenue_estimate BIGINT,
    revenue_actual BIGINT,
    market_cap BIGINT,
    in_position_book BOOLEAN DEFAULT FALSE,
    in_watchlist BOOLEAN DEFAULT FALSE,
    position_overlap_details JSONB,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_earnings_ticker_date UNIQUE (ticker, report_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_calendar (report_date);
CREATE INDEX IF NOT EXISTS idx_earnings_book ON earnings_calendar (in_position_book) WHERE in_position_book = TRUE;
```

**Key:** The `UNIQUE (ticker, report_date)` constraint allows the same ticker to appear for multiple quarters. The daily cron upserts on this constraint.

---

## STEP 2: FMP Integration — `integrations/fmp_client.py`

Create a new file for FMP API calls. Keep it simple — two functions.

```python
"""
Financial Modeling Prep (FMP) API Client
Free tier: 250 calls/day
Used for: earnings calendar, ETF holdings
"""
import os
import logging
import httpx
from datetime import date, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger("fmp_client")

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
FMP_API_KEY = os.getenv("FMP_API_KEY", "")


async def fetch_earnings_calendar(date_from: date, date_to: date) -> List[Dict]:
    """
    Fetch earnings calendar from FMP for a date range.
    Max range: 3 months per call.
    Returns list of dicts with keys: symbol, date, eps, epsEstimated,
    revenue, revenueEstimated, fiscalDateEnding, time, etc.
    """
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping earnings fetch")
        return []

    url = f"{FMP_BASE_URL}/earning_calendar"
    params = {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "apikey": FMP_API_KEY
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    # FMP returns a flat list of earnings entries
    # Normalize the 'time' field: "bmo" → "BMO", "amc" → "AMC", else "TNS"
    for entry in data:
        raw_time = (entry.get("time") or "").lower()
        if "bmo" in raw_time or "before" in raw_time:
            entry["_timing"] = "BMO"
        elif "amc" in raw_time or "after" in raw_time:
            entry["_timing"] = "AMC"
        else:
            entry["_timing"] = "TNS"

    return data


async def fetch_etf_holdings(symbol: str, limit: int = 10) -> List[Dict]:
    """
    Fetch top holdings for an ETF from FMP.
    Returns list of dicts with keys: asset, name, weight, etc.
    """
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping ETF holdings fetch")
        return []

    url = f"{FMP_BASE_URL}/etf-holder/{symbol}"
    params = {"apikey": FMP_API_KEY}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    # FMP returns holdings sorted by weight descending
    return data[:limit] if data else []
```

**Fallback:** If FMP returns errors or the API key is missing, log a warning and return empty lists. Never crash the cron job.

---

## STEP 3: Daily Earnings Ingestion Cron — Background Loop in `main.py`

Add this background task in `lifespan()`:

```python
# Chronos: refresh earnings calendar daily at 6 AM ET
async def chronos_earnings_loop():
    """Daily earnings calendar refresh from FMP."""
    import pytz
    from datetime import datetime as dt_cls, date, timedelta
    
    await asyncio.sleep(60)  # 1 min startup delay
    
    while True:
        try:
            et = dt_cls.now(pytz.timezone("America/New_York"))
            # Run once daily around 6 AM ET on weekdays
            # Also run on startup if data is stale
            if et.weekday() < 5 and (5 <= et.hour <= 6):
                from jobs.chronos_ingest import run_chronos_earnings_ingest
                await run_chronos_earnings_ingest()
            elif et.hour == 7 and et.minute < 15:
                # Catch-up run if 6 AM was missed
                from jobs.chronos_ingest import run_chronos_earnings_ingest
                await run_chronos_earnings_ingest()
        except Exception as e:
            logger.warning("Chronos earnings loop error: %s", e)
        await asyncio.sleep(3600)  # Check every hour (only runs at 6-7 AM)

chronos_task = asyncio.create_task(chronos_earnings_loop())
```

Add `chronos_task.cancel()` to the shutdown section.

### The Ingestion Job — `jobs/chronos_ingest.py`

Create a new file `backend/jobs/chronos_ingest.py`:

```python
"""
Chronos Earnings Ingestion
Runs daily at 6 AM ET. Pulls 21 days of earnings from FMP,
cross-references with positions and watchlist, upserts to DB.
"""
import logging
import json
from datetime import date, timedelta

from database.postgres_client import get_postgres_client
from integrations.fmp_client import fetch_earnings_calendar
from utils.position_overlap import check_position_overlap, ETF_COMPONENTS

logger = logging.getLogger("chronos_ingest")


async def run_chronos_earnings_ingest():
    """Main ingestion function called by the background loop."""
    logger.info("📅 Chronos: starting earnings ingestion...")
    
    today = date.today()
    date_from = today
    date_to = today + timedelta(days=21)
    
    # 1. Fetch earnings from FMP
    earnings = await fetch_earnings_calendar(date_from, date_to)
    if not earnings:
        logger.warning("Chronos: FMP returned no earnings data")
        return
    
    logger.info(f"Chronos: fetched {len(earnings)} earnings entries from FMP")
    
    client = await get_postgres_client()
    
    # 2. Get current positions and watchlist tickers for overlap checking
    position_rows = await client.fetch(
        "SELECT ticker FROM unified_positions WHERE status = 'OPEN'"
    )
    position_tickers = set(r["ticker"] for r in position_rows)
    
    watchlist_rows = await client.fetch(
        "SELECT ticker FROM trade_watchlist WHERE is_active = TRUE"
    )
    watchlist_tickers = set(r["ticker"] for r in watchlist_rows)
    
    # Build a set of all component tickers from held ETFs
    etf_component_set = set()
    etf_overlap_map = {}  # ticker -> [list of ETF positions it belongs to]
    for pos_ticker in position_tickers:
        components = ETF_COMPONENTS.get(pos_ticker, [])
        for comp in components:
            etf_component_set.add(comp)
            etf_overlap_map.setdefault(comp, []).append(pos_ticker)
    
    # 3. Upsert each earnings entry
    upserted = 0
    for entry in earnings:
        ticker = entry.get("symbol", "").upper()
        if not ticker:
            continue
        
        report_date = entry.get("date")
        if not report_date:
            continue
        
        # Check overlaps
        in_book = ticker in position_tickers or ticker in etf_component_set
        in_wl = ticker in watchlist_tickers
        overlap_details = None
        if ticker in etf_overlap_map:
            overlap_details = json.dumps({"etf_positions": etf_overlap_map[ticker]})
        
        await client.execute("""
            INSERT INTO earnings_calendar 
                (ticker, company_name, report_date, fiscal_period, fiscal_year,
                 timing, eps_estimate, revenue_estimate, market_cap,
                 in_position_book, in_watchlist, position_overlap_details, last_updated)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
            ON CONFLICT (ticker, report_date) DO UPDATE SET
                timing = EXCLUDED.timing,
                eps_estimate = EXCLUDED.eps_estimate,
                revenue_estimate = EXCLUDED.revenue_estimate,
                in_position_book = EXCLUDED.in_position_book,
                in_watchlist = EXCLUDED.in_watchlist,
                position_overlap_details = EXCLUDED.position_overlap_details,
                last_updated = NOW()
        """,
            ticker,
            entry.get("name") or entry.get("company_name"),
            report_date,
            entry.get("fiscalDateEnding"),
            entry.get("fiscal_year"),
            entry.get("_timing"),
            entry.get("epsEstimated"),
            entry.get("revenueEstimated"),
            entry.get("marketCap"),
            in_book,
            in_wl,
            overlap_details
        )
        upserted += 1
    
    # 4. Also update trade_watchlist entries with next earnings dates
    for wl_ticker in watchlist_tickers:
        next_earn = await client.fetchrow("""
            SELECT report_date, timing FROM earnings_calendar
            WHERE ticker = $1 AND report_date >= $2
            ORDER BY report_date ASC LIMIT 1
        """, wl_ticker, today)
        
        if next_earn:
            await client.execute("""
                UPDATE trade_watchlist 
                SET next_earnings_date = $1, earnings_timing = $2, updated_at = NOW()
                WHERE ticker = $3 AND is_active = TRUE
            """, next_earn["report_date"], next_earn["timing"], wl_ticker)
    
    logger.info(f"📅 Chronos: upserted {upserted} earnings entries, updated watchlist dates")
```

---

## STEP 4: API Routes — `api/chronos.py`

Create `backend/api/chronos.py`:

```python
"""
Chronos Earnings Calendar API

Endpoints:
- GET /chronos/calendar          — Earnings for date range
- GET /chronos/book-impact       — Earnings affecting current positions
- GET /chronos/this-week         — This week's earnings summary
- GET /chronos/market-movers     — Top 15 by market cap reporting this week
- POST /chronos/refresh          — Manually trigger earnings refresh
"""
```

### Route Details:

**GET `/chronos/calendar`**
- Query params: `date_from` (default: today), `date_to` (default: today + 14 days), `ticker` (optional filter)
- Returns all earnings entries in date range, sorted by `report_date ASC`

**GET `/chronos/book-impact`**
- No params needed — auto-derives from `unified_positions`
- Returns earnings entries where `in_position_book = TRUE` for the next 14 days
- Groups by position ticker: `{"XLF": [{"ticker": "JPM", "report_date": "2026-04-14", ...}, ...], "SMH": [...]}`
- Include an `earnings_density` score per position: count of reporting components / total top-10 components

**GET `/chronos/this-week`**
- Returns all earnings from Monday to Friday of the current week
- Split into: `book_impact` (overlaps with positions), `watchlist` (overlaps with watchlist), `market_movers` (top 15 by market cap, no overlap filter)

**GET `/chronos/market-movers`**
- Query param: `period` (default: "this_week", also accepts "next_week")
- Returns top 15 earnings entries by market cap for the period
- Sorted by market_cap DESC

**POST `/chronos/refresh`**
- Protected by API key auth
- Manually triggers `run_chronos_earnings_ingest()`
- Returns `{"status": "ok", "entries_upserted": N}`

---

## STEP 5: Wire Into `main.py`

**Import** (with other router imports):
```python
from api.chronos import router as chronos_router
```

**Registration:**
```python
app.include_router(chronos_router, prefix="/api", tags=["chronos"])
```

**Init** in lifespan (after trade watchlist init):
```python
# Initialize earnings calendar table
try:
    from api.chronos import init_chronos_table
    await init_chronos_table()
    logger.info("✅ Chronos earnings table ready")
except Exception as e:
    logger.warning(f"⚠️ Could not initialize Chronos table: {e}")
```

Also trigger an initial earnings ingest on startup (so data is available immediately, not just at 6 AM):
```python
# Initial Chronos data load
try:
    from jobs.chronos_ingest import run_chronos_earnings_ingest
    asyncio.create_task(run_chronos_earnings_ingest())
    logger.info("📅 Chronos initial earnings load queued")
except Exception as e:
    logger.warning(f"Chronos initial load error: {e}")
```

---

## STEP 6: Update Position Overlap Utility

In `utils/position_overlap.py` (created in Phase A), add a function to refresh ETF_COMPONENTS from FMP:

```python
async def refresh_etf_components():
    """
    Refresh ETF_COMPONENTS dict from FMP ETF holdings API.
    Call this weekly (or on demand) to keep holdings current.
    Falls back to hardcoded values if FMP fails.
    """
    from integrations.fmp_client import fetch_etf_holdings
    
    etf_tickers = ["XLF", "SMH", "IYR"]  # Only ETFs with meaningful single-stock components
    
    for etf in etf_tickers:
        try:
            holdings = await fetch_etf_holdings(etf, limit=10)
            if holdings:
                ETF_COMPONENTS[etf] = [h.get("asset", "").upper() for h in holdings if h.get("asset")]
                logger.info(f"Refreshed {etf} components: {ETF_COMPONENTS[etf]}")
        except Exception as e:
            logger.warning(f"Failed to refresh {etf} components from FMP: {e}")
            # Keep existing hardcoded values as fallback
```

Wire this into the `chronos_earnings_loop` — call `refresh_etf_components()` once per week (check day-of-week in the loop).

---

## VERIFICATION CHECKLIST

1. Set `FMP_API_KEY` in Railway environment variables
2. `POST /api/chronos/refresh` → should return `{"status": "ok", "entries_upserted": N}` where N > 0
3. `GET /api/chronos/this-week` → should return earnings for current week
4. `GET /api/chronos/book-impact` → should show which position ETF components are reporting
5. `GET /api/chronos/market-movers` → should return top 15 by market cap
6. Check `trade_watchlist` entries have `next_earnings_date` populated after cron runs
7. Logs should show `📅 Chronos: upserted N earnings entries` during the daily 6 AM run

---

## FILES CREATED/MODIFIED

| File | Action |
|------|--------|
| `backend/integrations/fmp_client.py` | **CREATE** — FMP API client (earnings + ETF holdings) |
| `backend/jobs/chronos_ingest.py` | **CREATE** — Daily earnings ingestion job |
| `backend/api/chronos.py` | **CREATE** — Chronos API routes |
| `backend/utils/position_overlap.py` | **MODIFY** — Add refresh_etf_components() |
| `backend/main.py` | **MODIFY** — Add router, init call, background loop |
| `backend/database/postgres_client.py` | **MODIFY** — Add CREATE TABLE in init_database() |

**Dependency:** `httpx` (likely already in requirements.txt — verify)
**Env var required:** `FMP_API_KEY` — Nick must set this in Railway before deploying
