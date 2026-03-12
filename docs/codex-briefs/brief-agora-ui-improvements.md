# Brief: Agora Dashboard UI Improvements

**Target Agent:** Claude Code (VSCode)
**Priority:** Medium — quality-of-life improvements while Phase 3 builds proceed
**Repo:** `303webhouse/pandoras-box` (branch: `main`)
**Deploy:** Push to `main` → Railway auto-deploys frontend + backend

---

## Overview

Four improvements to the Agora (hub) dashboard. All changes are in `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, and two new backend endpoints. No database schema changes.

**Design language:** Match existing Pandora dark theme (`#0a0e27` background, `#14b8a6` teal accent, `#7CFF6B` green, `#FF6B35` orange, `#e5370e` red). Use `escapeHtml()` for all user-facing data. Use existing `authHeaders()` and `API_URL` constants.

---

## Part 1: Sector Heatmap Tab

### What to build

A weighted treemap visualization showing S&P 500 sectors. Each rectangle is sized proportionally to the sector's weight in SPY, colored by daily performance (red-to-green gradient).

### Backend: New endpoint

**File:** `backend/api/sectors.py` (new file)
**Mount in:** `backend/main.py`

```python
# GET /api/sectors/heatmap
# Returns sector data for treemap rendering
# No auth required (public market data)

# Static SPY sector weights (update quarterly)
SECTOR_WEIGHTS = {
    "XLK": {"name": "Technology", "weight": 0.312},
    "XLF": {"name": "Financials", "weight": 0.139},
    "XLV": {"name": "Health Care", "weight": 0.117},
    "XLY": {"name": "Consumer Disc.", "weight": 0.105},
    "XLC": {"name": "Communication", "weight": 0.091},
    "XLI": {"name": "Industrials", "weight": 0.084},
    "XLP": {"name": "Consumer Staples", "weight": 0.058},
    "XLE": {"name": "Energy", "weight": 0.034},
    "XLRE": {"name": "Real Estate", "weight": 0.023},
    "XLU": {"name": "Utilities", "weight": 0.025},
    "XLB": {"name": "Materials", "weight": 0.019},
}

# For each sector ETF, fetch daily change from the existing
# enrichment pipeline. The watchlist enrichment system already
# fetches price data for sector ETFs via Polygon.
#
# Implementation approach:
# 1. Check Redis for cached sector heatmap data (key: "sector_heatmap", TTL 5 min)
# 2. If cache miss, query the watchlist enrichment data for sector ETFs
# 3. Fallback: hit Polygon /v2/snapshot/locale/us/markets/stocks/tickers
#    for the 11 sector ETF tickers in a single batch call
#
# Response shape:
{
    "sectors": [
        {
            "etf": "XLK",
            "name": "Technology",
            "weight": 0.312,
            "change_1d": 1.23,
            "change_1w": -0.45,
            "price": 215.67,
            "strength_rank": 1
        }
    ],
    "spy_change_1d": 0.87,
    "timestamp": "2026-03-12T14:30:00Z"
}
```

**Key implementation detail:** The existing `fetchEnrichedWatchlist()` pipeline already fetches sector-level data. Look at `backend/watchlist/enrichment.py` — it computes `change_1d`, `change_1w`, and `strength_rank` for sectors. The new endpoint can reuse that data by reading from the same Redis cache or calling the same enrichment functions. Avoid duplicating Polygon API calls.

### Frontend: HTML changes

**File:** `frontend/index.html`

Find the `headlines-card` div (inside the `bias-section`). Replace the tab structure:

```html
<!-- FIND THIS: -->
<div class="headlines-card" id="headlinesCard">
    <div class="headlines-tabs">
        <button class="headlines-tab active" data-tab="flow">FLOW</button>
        <button class="headlines-tab" data-tab="headlines">HEADLINES</button>
    </div>

<!-- REPLACE WITH: -->
<div class="headlines-card" id="headlinesCard">
    <div class="headlines-tabs">
        <button class="headlines-tab active" data-tab="sectors">SECTORS</button>
        <button class="headlines-tab" data-tab="flow">FLOW</button>
        <button class="headlines-tab" data-tab="headlines">HEADLINES</button>
    </div>
    <div class="headlines-tab-content" id="sectorsTabContent">
        <div class="sector-heatmap" id="sectorHeatmap">
            <p class="empty-state">Loading sectors...</p>
        </div>
    </div>
```

Also update the existing flow tab content to be hidden by default (sectors is now the default tab):

```html
<div class="headlines-tab-content" id="flowTabContent" style="display:none;">
```

### Frontend: CSS changes

**File:** `frontend/styles.css`

The `headlines-card` currently has a fixed width in the bias-section grid. Widen it by ~20%. Find the CSS rule for `.headlines-card` and adjust. The bias-section uses CSS grid — look for the `grid-template-columns` that places the headlines card between the timeframe cards. Increase the headlines card's column span or fraction.

New CSS for the treemap is in the full brief file (see downloadable version).

### Frontend: JS changes

**File:** `frontend/app.js`

1. Update tab switching logic to include `sectorsTabContent` as the third tab. Set `sectors` as the default active tab.
2. Add `loadSectorHeatmap()`, `renderSectorHeatmap()`, and `getHeatmapColor()` functions.
3. Call `loadSectorHeatmap()` on init and refresh every 5 minutes.
4. Click handler on sector cells calls `changeChartSymbol(etf)`.

Full JS code is in the downloadable brief.

---

## Part 2: Flow Tab Redesign

### Backend: New endpoint

**File:** `backend/api/flow_summary.py` (new file)

`GET /api/flow/summary` — aggregates existing UW flow data into sentiment gauge, hot tickers, and recent flow signals. Uses existing flow data pipeline + signals table query for FLOW_INTEL category.

### Frontend

Replace the `flowCompactList` stub with three zones: sentiment gauge bar, hot ticker chips, and recent flow signal mini-cards. Full render code in downloadable brief.

---

## Part 3: RADAR (Watchlist Tickers Redesign)

### No backend changes needed

### Frontend

- Rename "WATCHLIST TICKERS" → "RADAR"
- Replace dropdown sort/filter with compact pill buttons
- Replace text row list with compact card grid (90px min cards)
- Each card shows: ticker, daily change %, relative volume bar, CTA zone pip
- Position overlap shows label beneath ticker ("LONG: put_debit_spread")
- Signal dot indicator for tickers with active signals

Full HTML/CSS/JS in downloadable brief.

---

## Part 4: Single Ticker Analyzer Overhaul

### Backend

- `GET /api/analyze/{ticker}/signals?days=14` — recent signals from signals table
- `POST /api/analyze/{ticker}/olympus` — on-demand committee analysis (auth + rate limit + cache)

### Frontend

- Header bar: ticker, price, CTA zone badge, composite score ring
- Three-column summary: Technical / Flow & Signals / Fundamentals
- Recent signals panel showing 14-day history
- Olympus button triggers 4-agent committee analysis inline

Full implementation code in downloadable brief.

---

## Build Order

1. Part 1: Sector Heatmap
2. Part 2: Flow Tab
3. Part 3: RADAR
4. Part 4: Analyzer

Each part is independently deployable.
