# BRIEF: Sector Drill-Down Popup (Phase 2)

**Priority:** P0
**Depends on:** Polygon Pre-Filter brief (Phase 1 — shared snapshot cache must be built first)
**Touches:** Backend (main.py / routes), Frontend (app.js), Supabase (new table)

---

## Summary

Replace the static Sector Overview section at the bottom of the UI with interactive sector popups triggered from the existing "Sectors" tab at the top. Clicking any sector ETF (e.g., XLK) opens a modal showing the top 20 stocks in that sector sorted by sector-relative performance. Stocks outperforming the sector appear above a divider; underperformers below. Data refreshes every 5 seconds for price fields during market hours. Clicking any ticker opens the Single Ticker Analyzer and loads the ticker on the TradingView widget.

---

## Architecture Overview

### What "sector-relative performance" means

If XLK (the sector ETF) is down 1.5% today, and AAPL is down 0.3%, then AAPL is *outperforming* its sector by +1.2%. That +1.2% is the sort key. A stock that's down 3% in a sector that's down 1.5% is underperforming by -1.5%. The divider row IS the sector ETF itself — everything above it is beating the sector, everything below is lagging.

### Data flow

```
Polygon snapshot cache (Redis, 5s TTL)
        ↓
/api/sectors/{sector}/leaders endpoint
        ↓
  Reads sector_constituents table (Supabase) for membership
  Reads snapshot cache for real-time price data
  Reads RSI cache (Redis) for RSI values
  Calculates volume ratio from snapshot vs 20-day avg
  Queries flow_events table for flow direction
        ↓
  Returns sorted JSON to frontend
        ↓
Frontend renders modal, polls every 5 seconds
```

### Two-tier refresh (CRITICAL — do not poll everything every 5 seconds)

| Tier | Fields | Refresh Rate | Source |
|------|--------|-------------|--------|
| Fast | price, day_change_pct | 5 seconds | Polygon snapshot cache |
| Slow | rsi_14, week_change_pct, month_change_pct, volume_ratio | 5 minutes | Redis calculation cache |
| Static | market_cap, ticker, company_name, sector | On popup open | Supabase sector_constituents |

The endpoint should accept a `?fast=true` query param. When `fast=true`, only return fast-tier fields (for the 5-second polls). Full data returned on initial load and every 5 minutes.

---

## Backend Changes

### 1. New Supabase table: `sector_constituents`

```sql
CREATE TABLE sector_constituents (
    id SERIAL PRIMARY KEY,
    sector_etf VARCHAR(10) NOT NULL,        -- e.g., 'XLK'
    sector_name VARCHAR(50) NOT NULL,       -- e.g., 'Technology'
    ticker VARCHAR(10) NOT NULL,
    company_name VARCHAR(100) NOT NULL,
    market_cap BIGINT,                       -- for sorting top 20
    rank_in_sector INTEGER,                  -- 1-20 by market cap
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sector_etf, ticker)
);

CREATE INDEX idx_sector_constituents_etf ON sector_constituents(sector_etf);
```

**Sector ETF mapping (hardcode these — they don't change):**

| ETF | Sector Name |
|-----|-------------|
| XLK | Technology |
| XLF | Financials |
| XLE | Energy |
| XLV | Health Care |
| XLI | Industrials |
| XLP | Consumer Staples |
| XLY | Consumer Discretionary |
| XLC | Communication Services |
| XLRE | Real Estate |
| XLU | Utilities |
| XLB | Materials |

**Population strategy:** Create a one-time script (or management endpoint) that populates the table using Polygon's reference endpoint to look up tickers by SIC code / sector classification. Alternatively, hardcode the top 20 holdings of each SPDR ETF — these change slowly (quarterly). Include a `GET /api/sectors/refresh-constituents` admin endpoint that re-pulls from Polygon reference data. This does NOT need to run automatically — Nick will trigger it manually when needed, or we add a weekly cron later.

### 2. New endpoint: `GET /api/sectors/{sector_etf}/leaders`

**Path:** Add to existing routes file alongside other `/api/` endpoints.

**Parameters:**
- `sector_etf` (path): ETF ticker, e.g., `XLK`
- `fast` (query, optional, default false): If true, return only fast-tier fields

**Response shape (full load):**

```json
{
    "sector_etf": "XLK",
    "sector_name": "Technology",
    "sector_day_change_pct": -1.52,
    "constituents": [
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc",
            "price": 187.43,
            "day_change_pct": -0.31,
            "sector_relative_pct": 1.21,
            "week_change_pct": -2.1,
            "month_change_pct": -5.4,
            "rsi_14": 42,
            "volume_ratio": 2.3,
            "flow_direction": "bearish",
            "market_cap": 2890000000000
        }
    ],
    "updated_at": "2026-03-27T14:30:05Z",
    "is_market_hours": true
}
```

**Response shape (fast=true):**

```json
{
    "sector_etf": "XLK",
    "sector_day_change_pct": -1.52,
    "constituents": [
        {
            "ticker": "AAPL",
            "price": 187.43,
            "day_change_pct": -0.31,
            "sector_relative_pct": 1.21
        }
    ],
    "updated_at": "2026-03-27T14:30:05Z"
}
```

**Sorting:** `constituents` array is sorted by `sector_relative_pct` descending (best outperformers first, worst underperformers last).

**Implementation notes:**
- Read the `sector_constituents` table to get the ticker list for the requested sector
- Get sector ETF price change from the shared Polygon snapshot cache
- Get each constituent's price data from the same snapshot cache (this is ONE cache read, not 20 API calls — the snapshot contains ALL tickers)
- Calculate `sector_relative_pct` = `ticker_day_change_pct` - `sector_etf_day_change_pct`
- For slow-tier fields: read RSI from existing Redis RSI cache, calculate volume_ratio from snapshot volume vs stored 20-day average, query flow_events for last 24h grouped by ticker
- For flow_direction: query `flow_events` WHERE ticker = X AND created_at > now() - 24h. If net premium is >60% calls → "bullish", >60% puts → "bearish", else "neutral". If no flow events → "neutral"

### 3. Volume baseline storage

Need a way to store 20-day average volume for comparison. Options:

**Option A (recommended):** Add a `ticker_baselines` table or add columns to `sector_constituents`:

```sql
ALTER TABLE sector_constituents ADD COLUMN avg_volume_20d BIGINT;
```

Populate via a nightly job that pulls 20-day historical bars from Polygon and averages the volume. This is a batch job — NOT real-time. Store the average, compare against today's live volume from the snapshot.

**Option B:** Calculate on-the-fly from Polygon's aggregates endpoint. Works but adds API calls. Not recommended.

### 4. RSI availability

The scanner infrastructure already calculates RSI for tickers it's watching. For sector constituents that aren't in the scanner watchlist, RSI won't be pre-cached. Two approaches:

**Option A (recommended):** When the sector popup is first opened, if RSI isn't cached for a constituent, calculate it on-demand from Polygon bars (last 20 bars of the ticker's preferred timeframe) and cache it in Redis with a 5-minute TTL. This is lazy loading — only calculate what's actually being viewed.

**Option B:** Pre-calculate RSI for all 220 constituents every 5 minutes. Works but wastes compute on tickers nobody is looking at.

---

## Frontend Changes

### 1. Remove the Sector Overview section

Find the Sector Overview section at the bottom of the UI and remove it entirely. This is the static section that currently shows basic sector performance. Search for the HTML/JS that renders this section.

**Find anchor (in app.js or the HTML):** Search for text related to "Sector Overview" or "sectorOverview" or the container that holds the bottom-of-page sector display. Remove the rendering logic and the container element.

### 2. Add click handlers to sector tabs

The "Sectors" tab at the top of the UI already shows sector ETF buttons/tabs. Add a click event listener to each one that opens the sector popup modal.

**Find anchor:** Search for where the sector tabs are rendered — likely involves the sector ETF tickers (XLK, XLF, etc.) being displayed as clickable elements. Add an `onclick` handler that calls a new function like `openSectorPopup('XLK')`.

### 3. Sector Popup Modal

**Layout spec (fits 1920×1080 laptop screen):**

```
┌─────────────────────────────────────────────────────┐
│  XLK — Technology                    ▼1.52%  [×]   │
│  ☐ Show All 20                                      │
├─────────────────────────────────────────────────────┤
│ TICKER │ PRICE   │ DAY%  │ WK%  │ MO%  │RSI│VOL│FLW│
│────────│─────────│───────│──────│──────│───│───│───│
│ AAPL   │ $187.43 │ -0.3% │-2.1% │-5.4% │ 42│ 🔥│ 🔴│  ← outperforming sector
│ MSFT   │ $398.21 │ -0.9% │-1.8% │-4.1% │ 48│ 📈│ ⚪│
│ ...    │         │       │      │      │   │   │   │
│════════│═════════│═══════│══════│══════│═══│═══│═══│
│ XLK    │ $198.50 │ -1.5% │-3.2% │-7.8% │ 38│   │   │  ← DIVIDER ROW (sector ETF)
│════════│═════════│═══════│══════│══════│═══│═══│═══│
│ NVDA   │ $842.10 │ -2.1% │-5.3% │-12%  │ 31│ 🔥│ 🔴│  ← underperforming sector
│ ...    │         │       │      │      │   │   │   │
└─────────────────────────────────────────────────────┘
```

**Size:** 900px wide × 600px tall (max). Use CSS `max-height` with overflow scroll for the table body if needed.

**Positioning:** Centered modal overlay with semi-transparent backdrop. Z-index above all dashboard content.

**Default view:** Top 5 outperformers + Bottom 5 underperformers + the sector ETF divider row = 11 rows. Toggle checkbox "Show All 20" expands to full list.

**Color coding (IMPORTANT):**
- Day%, Wk%, Mo% columns are colored relative to the SECTOR, not absolute:
  - Green text: ticker is beating the sector (even if the ticker itself is red on the day)
  - Red text: ticker is lagging the sector (even if the ticker itself is green on the day)
- The Price column always uses standard green/red based on absolute day change

**Volume indicator column (VOL):**
- 🔥 = volume_ratio > 2.0 (more than 2x average — heavy institutional activity)
- 📈 = volume_ratio 1.0 to 2.0 (above average)
- 😴 = volume_ratio < 0.5 (well below average — thin, unreliable move)
- (blank or dash) = volume_ratio 0.5 to 1.0 (normal, not notable)

**Flow indicator column (FLW):**
- 🟢 = bullish flow
- 🔴 = bearish flow
- ⚪ = neutral or no data

**Sort behavior:** Table is sorted by `sector_relative_pct` on initial load. Sort does NOT re-shuffle on every 5-second tick (prevents the table from jumping around while Nick is reading). Re-sort happens: (a) on initial open, (b) when toggling Show All, (c) every 30 seconds via a quiet re-sort.

**Row click behavior:** Clicking any ticker row should:
1. Call the existing Single Ticker Analyzer function (currently `analyzeTicker()` or similar — search app.js for the function that handles single ticker analysis)
2. Load the ticker on the TradingView widget (search for the TV widget symbol change function — likely something like `tvWidget.setSymbol()` or `changeSymbol()`)
3. Keep the sector popup open underneath (the ticker analyzer opens on top)

### 4. Polling logic

```javascript
// Pseudocode for the polling setup
let sectorPopupInterval = null;
let sectorFullRefreshInterval = null;

function openSectorPopup(sectorEtf) {
    // Initial full load
    fetchSectorData(sectorEtf, false);
    showSectorModal();

    // Fast refresh every 5 seconds (price only)
    sectorPopupInterval = setInterval(() => {
        fetchSectorData(sectorEtf, true);  // fast=true
    }, 5000);

    // Full refresh every 5 minutes (RSI, volume, flow)
    sectorFullRefreshInterval = setInterval(() => {
        fetchSectorData(sectorEtf, false);  // fast=false
    }, 300000);
}

function closeSectorPopup() {
    // CRITICAL: Clear intervals to prevent orphaned timers
    if (sectorPopupInterval) {
        clearInterval(sectorPopupInterval);
        sectorPopupInterval = null;
    }
    if (sectorFullRefreshInterval) {
        clearInterval(sectorFullRefreshInterval);
        sectorFullRefreshInterval = null;
    }
    hideSectorModal();
}
```

**Stale data indicator:** If a fetch fails or returns data older than 15 seconds, show a subtle "⚠️ Data may be stale" banner at the top of the modal. Don't hide the data — just flag it.

**Market hours check:** If `is_market_hours` is false in the response, reduce polling to every 60 seconds (no point hammering for unchanged data). Show a "(Market Closed)" badge in the header.

### 5. Maximum one sector popup open at a time

If a sector popup is already open and Nick clicks a different sector tab, close the current popup (clearing its intervals) and open the new one. Don't stack sector popups.

---

## Supabase Migration

Run this migration to create the table:

```sql
-- Migration: create sector_constituents table
CREATE TABLE IF NOT EXISTS sector_constituents (
    id SERIAL PRIMARY KEY,
    sector_etf VARCHAR(10) NOT NULL,
    sector_name VARCHAR(50) NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    company_name VARCHAR(100) NOT NULL,
    market_cap BIGINT,
    avg_volume_20d BIGINT,
    rank_in_sector INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sector_etf, ticker)
);

CREATE INDEX IF NOT EXISTS idx_sector_constituents_etf ON sector_constituents(sector_etf);
CREATE INDEX IF NOT EXISTS idx_sector_constituents_ticker ON sector_constituents(ticker);
```

---

## Population Script

Create a script or management endpoint to populate `sector_constituents`. This can be:

1. A Python script that uses Polygon's reference API (`/v3/reference/tickers?market=stocks&type=CS`) filtered by sector, sorted by market cap, limited to top 20 per sector
2. OR a hardcoded initial seed based on current SPDR ETF holdings (faster to implement, update manually)

**Recommended:** Start with hardcoded seed data for v1 (get the feature working), then add the Polygon reference endpoint refresh later. The top 20 stocks in each sector don't change week-to-week.

Include the sector ETF itself in each sector's data (needed for the divider row). Example seed:

```python
SECTOR_SEEDS = {
    "XLK": {
        "name": "Technology",
        "tickers": ["AAPL", "MSFT", "NVDA", "AVGO", "ADBE", "CRM", "CSCO", "ACN", "ORCL", "AMD",
                     "INTC", "INTU", "TXN", "QCOM", "AMAT", "MU", "NOW", "LRCX", "ADI", "KLAC"]
    },
    "XLF": {
        "name": "Financials",
        "tickers": ["BRK.B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "BLK",
                     "AXP", "C", "SCHW", "CB", "MMC", "PGR", "ICE", "CME", "AON", "MET"]
    },
    # ... etc for all 11 sectors
}
```

CC should fill in the remaining sectors using current knowledge. These are well-known and stable. Include company names for each ticker.

---

## Testing Checklist

1. **Endpoint returns data:** `GET /api/sectors/XLK/leaders` returns 20 constituents sorted by sector_relative_pct
2. **Fast mode works:** `GET /api/sectors/XLK/leaders?fast=true` returns only price fields
3. **Modal opens:** Clicking sector tab opens modal with correct data
4. **Divider row:** Sector ETF appears as a visually distinct row separating outperformers from underperformers
5. **Color coding:** A stock that's down 0.5% in a sector that's down 2% shows green relative coloring
6. **Polling works:** Price data updates every 5 seconds (verify in Network tab)
7. **Polling stops:** Closing the modal stops all intervals (verify no orphaned network calls)
8. **Ticker click:** Clicking a row triggers Single Ticker Analyzer and changes TV widget symbol
9. **Show All toggle:** Switching between top 5/bottom 5 and full 20 works correctly
10. **Market hours:** Outside market hours, polling slows to 60 seconds and shows "(Market Closed)"
11. **Stale data:** If backend is slow/down, stale data banner appears
12. **Only one popup:** Opening a new sector closes the previous one

---

## What This Brief Does NOT Cover

- Single Ticker Analyzer v2 redesign (Phase 3 — separate brief)
- Contextual Modifier / trade idea enrichment (Phase 4 — separate brief)
- Polygon pre-filter snapshot cache (Phase 1 — already written, must be built first)
- Committee review integration (Phase 3)
- Nightly batch jobs for beta calculation (Phase 3)

---

## Notes for Claude Code

- The frontend is vanilla JS in a single large `app.js` file (~420KB). Use Desktop Commander with `start_search` and `literalSearch: True` to find anchors.
- Search for "Sector Overview" or "sectorOverview" to find the section being replaced.
- Search for where sector tabs are rendered to add click handlers.
- Search for the existing Single Ticker Analyzer function name to wire up row clicks.
- Search for TradingView widget symbol change to wire up the TV integration.
- All new styles should go in the existing CSS section of the app — no separate stylesheet.
- The modal should match the existing UI's color scheme / dark theme.
- Use the existing API auth pattern (`X-API-Key` header) for the new endpoint.
- The Polygon snapshot cache (Redis key pattern) will be defined by the Phase 1 pre-filter brief. This brief's endpoint reads from that cache — it does NOT make its own Polygon API calls for price data.
