# Brief: Fix Earnings Data Pipeline — Two Root Causes

**Priority:** URGENT — earnings season starting  
**Scope:** Backend API fixes + frontend earnings tab layout  
**Root causes identified — both are data-level, not rendering bugs**

---

## DIAGNOSIS

### Issue 1: Earnings tab only showing DAL
The `/chronos/this-week` endpoint returns earnings for Mon–Fri of the current week. This week (Apr 6–10) is pre-earnings season — genuinely light. But worse: the "Market Movers" section sorts by `market_cap`, and **`market_cap` is always NULL** because FMP's free Stable tier doesn't include it. The ingest hardcodes `None` for market_cap. So sorting by `(market_cap or 0)` is meaningless — it returns a random 15-item slice.

**Fix:** Show the next 14 days instead of just this week, and stop depending on market_cap for sorting.

### Issue 2: No earnings on trade idea cards or position cards  
Nick's positions are ETFs: HYG, SMH, SPY, XLE, XLF. The `next-earnings-batch` endpoint does an **exact ticker match** against `earnings_calendar`. That table stores individual company earnings (AAPL, JPM, DAL). ETFs don't have rows there. So the batch returns `{}` for all position tickers → earningsCache is empty → no badges render.

**Fix:** Enhance `next-earnings-batch` to resolve ETF components using the existing `ETF_COMPONENTS` mapping. When the endpoint receives "XLF", it should check JPM, BAC, GS, etc. and return the earliest upcoming component earnings.

---

## FIX 1: Enhance `next-earnings-batch` to Resolve ETF Components

**File: `backend/api/chronos.py`**

Find the `get_next_earnings_batch` function (around line 222):

```python
# ── GET /chronos/next-earnings-batch ───────────────────────────────
@router.get("/next-earnings-batch")
async def get_next_earnings_batch(tickers: str = Query(..., description="Comma-separated tickers")):
    """Batch fetch next earnings dates for multiple tickers."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"earnings": {}}

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT ON (ticker) ticker, report_date, timing
               FROM earnings_calendar
               WHERE ticker = ANY($1) AND report_date >= CURRENT_DATE
               ORDER BY ticker, report_date ASC""",
            ticker_list
        )
    result = {}
    for r in rows:
        result[r["ticker"]] = {"date": r["report_date"].isoformat(), "timing": r["timing"]}
    return {"earnings": result}
```

**Replace the entire function with:**

```python
# ── GET /chronos/next-earnings-batch ───────────────────────────────
@router.get("/next-earnings-batch")
async def get_next_earnings_batch(tickers: str = Query(..., description="Comma-separated tickers")):
    """Batch fetch next earnings dates for multiple tickers.
    For ETF tickers, resolves component holdings and returns earliest component earnings.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"earnings": {}}

    pool = await get_postgres_client()
    result = {}

    # Separate direct tickers from ETF tickers
    direct_tickers = []
    etf_tickers = {}  # { "XLF": ["JPM", "BAC", ...] }
    for t in ticker_list:
        components = ETF_COMPONENTS.get(t, [])
        if components:
            etf_tickers[t] = components
        else:
            direct_tickers.append(t)

    async with pool.acquire() as conn:
        # 1. Direct ticker lookups (individual stocks)
        if direct_tickers:
            rows = await conn.fetch(
                """SELECT DISTINCT ON (ticker) ticker, report_date, timing
                   FROM earnings_calendar
                   WHERE ticker = ANY($1) AND report_date >= CURRENT_DATE
                   ORDER BY ticker, report_date ASC""",
                direct_tickers
            )
            for r in rows:
                result[r["ticker"]] = {
                    "date": r["report_date"].isoformat(),
                    "timing": r["timing"]
                }

        # 2. ETF component lookups — find earliest component earnings for each ETF
        for etf_ticker, components in etf_tickers.items():
            if not components:
                continue
            comp_rows = await conn.fetch(
                """SELECT ticker, report_date, timing
                   FROM earnings_calendar
                   WHERE ticker = ANY($1) AND report_date >= CURRENT_DATE
                   ORDER BY report_date ASC
                   LIMIT 10""",
                components
            )
            if comp_rows:
                first = comp_rows[0]
                result[etf_ticker] = {
                    "date": first["report_date"].isoformat(),
                    "timing": first["timing"],
                    "component": first["ticker"],
                    "components_reporting": len(comp_rows),
                    "is_etf": True
                }

    return {"earnings": result}
```

**IMPORTANT:** This import already exists at the top of the file:
```python
from utils.position_overlap import ETF_COMPONENTS
```

No new imports needed.

---

## FIX 2: Update Frontend Earnings Badge for ETF Components

**File: `frontend/app.js`**

The `getEarningsBadgeHtml` function needs to show the component ticker for ETF positions.

Find (around line 415):

```javascript
function getEarningsBadgeHtml(ticker) {
    const earn = earningsCache[ticker];
    if (!earn || !earn.date) return '';
    const earnDate = new Date(earn.date + 'T00:00:00');
    const now = new Date();
    const daysUntil = Math.ceil((earnDate - now) / (1000 * 60 * 60 * 24));
    if (daysUntil < 0 || daysUntil > 30) return '';
    const dateStr = earnDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const timingStr = earn.timing ? ` ${earn.timing}` : '';
    const urgencyClass = daysUntil <= 3 ? 'earnings-badge-urgent' : daysUntil <= 7 ? 'earnings-badge-soon' : 'earnings-badge-normal';
    return `<span class="earnings-badge ${urgencyClass}" title="Earnings in ${daysUntil} day${daysUntil !== 1 ? 's' : ''}">\u26A0 Earn: ${dateStr}${timingStr}</span>`;
}
```

**Replace with:**

```javascript
function getEarningsBadgeHtml(ticker) {
    const earn = earningsCache[ticker];
    if (!earn || !earn.date) return '';
    const earnDate = new Date(earn.date + 'T00:00:00');
    const now = new Date();
    const daysUntil = Math.ceil((earnDate - now) / (1000 * 60 * 60 * 24));
    if (daysUntil < 0 || daysUntil > 30) return '';
    const dateStr = earnDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const timingStr = earn.timing ? ` ${earn.timing}` : '';
    // For ETF tickers, show which component is reporting
    const componentStr = earn.component ? ` (${earn.component})` : '';
    const countStr = earn.components_reporting && earn.components_reporting > 1 ? ` +${earn.components_reporting - 1} more` : '';
    const urgencyClass = daysUntil <= 3 ? 'earnings-badge-urgent' : daysUntil <= 7 ? 'earnings-badge-soon' : 'earnings-badge-normal';
    const titleText = earn.is_etf
        ? `${earn.components_reporting} component${earn.components_reporting !== 1 ? 's' : ''} reporting within 30 days. Next: ${earn.component} on ${dateStr}`
        : `Earnings in ${daysUntil} day${daysUntil !== 1 ? 's' : ''}`;
    return `<span class="earnings-badge ${urgencyClass}" title="${titleText}">\u26A0 Earn: ${dateStr}${timingStr}${componentStr}${countStr}</span>`;
}
```

Also update the position card inline earnings block. Find (around line 9367):

```javascript
            ${(() => {
                const earn = earningsCache[pos.ticker];
                if (!earn || !earn.date) return '';
                const earnDate = new Date(earn.date + 'T00:00:00');
                const now = new Date();
                const daysUntil = Math.ceil((earnDate - now) / (1000 * 60 * 60 * 24));
                if (daysUntil < 0 || daysUntil > 30) return '';
                const dateStr = earnDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                const timingStr = earn.timing ? ' ' + earn.timing : '';
                let expiryWarning = '';
                if (pos.expiry) {
                    const expiryDate = new Date(pos.expiry + 'T00:00:00');
                    if (earnDate <= expiryDate) {
                        expiryWarning = ' <span class="earnings-before-expiry">BEFORE EXPIRY</span>';
                    }
                }
                const urgencyClass = daysUntil <= 3 ? 'earnings-badge-urgent' : daysUntil <= 7 ? 'earnings-badge-soon' : 'earnings-badge-normal';
                return '<div class="position-earnings-row ' + urgencyClass + '">' +
                    '\u26A0 Earnings: ' + dateStr + timingStr +
                    ' (' + daysUntil + 'd)' + expiryWarning + '</div>';
            })()}
```

**Replace with:**

```javascript
            ${(() => {
                const earn = earningsCache[pos.ticker];
                if (!earn || !earn.date) return '';
                const earnDate = new Date(earn.date + 'T00:00:00');
                const now = new Date();
                const daysUntil = Math.ceil((earnDate - now) / (1000 * 60 * 60 * 24));
                if (daysUntil < 0 || daysUntil > 30) return '';
                const dateStr = earnDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                const timingStr = earn.timing ? ' ' + earn.timing : '';
                const componentStr = earn.component ? ' (' + earn.component + ')' : '';
                const countStr = earn.components_reporting && earn.components_reporting > 1 ? ' +' + (earn.components_reporting - 1) + ' more' : '';
                let expiryWarning = '';
                if (pos.expiry) {
                    const expiryDate = new Date(pos.expiry + 'T00:00:00');
                    if (earnDate <= expiryDate) {
                        expiryWarning = ' <span class="earnings-before-expiry">BEFORE EXPIRY</span>';
                    }
                }
                const urgencyClass = daysUntil <= 3 ? 'earnings-badge-urgent' : daysUntil <= 7 ? 'earnings-badge-soon' : 'earnings-badge-normal';
                return '<div class="position-earnings-row ' + urgencyClass + '">' +
                    '\u26A0 Earnings: ' + dateStr + timingStr + componentStr + countStr +
                    ' (' + daysUntil + 'd)' + expiryWarning + '</div>';
            })()}
```

---

## FIX 3: Earnings Tab — Show 14 Days, Two Columns, No market_cap Dependency

### 3A: Backend — new endpoint for upcoming 14-day view

**File: `backend/api/chronos.py`**

Find the line (just before the final blank lines at end of file):

```python
    return {"earnings": result}
```

(This is the last line of `get_next_earnings_batch`.)

**Insert AFTER the end of `get_next_earnings_batch` (after its return statement), before any trailing blank lines:**

```python


# ── GET /chronos/upcoming ──────────────────────────────────────────
@router.get("/upcoming")
async def get_upcoming_earnings(days: int = Query(14, ge=1, le=30)):
    """Upcoming earnings for the next N days, with position/watchlist flags."""
    today = date.today()
    d_to = today + timedelta(days=days)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT ticker, company_name, report_date, timing,
                      eps_estimate, in_position_book, in_watchlist,
                      position_overlap_details
               FROM earnings_calendar
               WHERE report_date BETWEEN $1 AND $2
               ORDER BY report_date ASC, ticker ASC""",
            today, d_to
        )

    entries = [dict(r) for r in rows]
    book_impact = [e for e in entries if e.get("in_position_book")]

    return {
        "range": f"{today.isoformat()} to {d_to.isoformat()}",
        "total": len(entries),
        "book_impact": book_impact,
        "all_earnings": entries,
    }
```

### 3B: Frontend — Rewire earnings tab to use /upcoming with two-column layout

**File: `frontend/app.js`**

Find the `loadEarningsIntelTab` function (around line 12702). Replace the **entire function** from `async function loadEarningsIntelTab()` through its closing `}`:

```javascript
async function loadEarningsIntelTab() {
    try {
        const resp = await fetch(`${API_URL}/chronos/upcoming?days=14`, { headers: authHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();

        // === Book Impact section ===
        const bookContainer = document.getElementById('earningsBookImpact');
        const bookCount = document.getElementById('earningsBookCount');
        const bookItems = data.book_impact || [];
        if (bookCount) bookCount.textContent = bookItems.length > 0 ? `${bookItems.length} affecting positions` : '';

        if (bookContainer) {
            if (bookItems.length === 0) {
                bookContainer.innerHTML = '<p class="empty-state">No position-linked earnings in next 14 days</p>';
            } else {
                bookContainer.innerHTML = bookItems.map(e => {
                    const dateObj = new Date(e.report_date + 'T00:00:00');
                    const dayName = dateObj.toLocaleDateString('en-US', { weekday: 'short' });
                    const dateStr = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    const timing = e.timing || '\u2014';
                    let overlapStr = '';
                    if (e.position_overlap_details) {
                        try {
                            const details = typeof e.position_overlap_details === 'string' ? JSON.parse(e.position_overlap_details) : e.position_overlap_details;
                            if (details.etf_positions) overlapStr = details.etf_positions.join(', ');
                        } catch(ex) {}
                    }
                    return `<div class="earnings-intel-entry book-impact-entry">
                        <span class="earnings-intel-ticker">${e.ticker}</span>
                        <span class="earnings-intel-date">${dayName} ${dateStr}</span>
                        <span class="earnings-intel-timing">${timing}</span>
                        ${overlapStr ? `<span class="earnings-intel-overlap" title="Affects position">${overlapStr}</span>` : ''}
                    </div>`;
                }).join('');
            }
        }

        // === All Upcoming Earnings — two-column grid ===
        const moversContainer = document.getElementById('earningsMarketMovers');
        const allEarnings = data.all_earnings || [];
        if (moversContainer) {
            if (allEarnings.length === 0) {
                moversContainer.innerHTML = '<p class="empty-state">No earnings in next 14 days</p>';
            } else {
                // Group by date for cleaner display
                const byDate = {};
                allEarnings.forEach(e => {
                    const key = e.report_date;
                    if (!byDate[key]) byDate[key] = [];
                    byDate[key].push(e);
                });

                let html = '<div class="earnings-date-groups">';
                for (const [dateKey, entries] of Object.entries(byDate)) {
                    const dateObj = new Date(dateKey + 'T00:00:00');
                    const dayLabel = dateObj.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
                    html += `<div class="earnings-date-group">`;
                    html += `<div class="earnings-date-label">${dayLabel} <span class="earnings-date-count">(${entries.length})</span></div>`;
                    html += `<div class="earnings-date-tickers">`;
                    entries.forEach(e => {
                        const timing = e.timing || '';
                        const inBook = e.in_position_book ? ' book-flag' : '';
                        html += `<span class="earnings-ticker-chip${inBook}" title="${e.ticker} ${timing}">${e.ticker}${timing ? ' ' + timing : ''}</span>`;
                    });
                    html += `</div></div>`;
                }
                html += '</div>';
                moversContainer.innerHTML = html;
            }
        }
    } catch (err) {
        console.error('Earnings intel tab load error:', err);
        const el = document.getElementById('earningsBookImpact');
        if (el) el.innerHTML = '<p class="empty-state">Earnings data unavailable</p>';
    }
}
```

### 3C: Update earnings tab HTML — rename second section

**File: `frontend/index.html`**

Find (the second section title inside the earnings tab content):

```html
                            <span class="earnings-intel-section-title">Top Earnings This Week</span>
```

**Replace with:**

```html
                            <span class="earnings-intel-section-title">Upcoming Earnings (14 days)</span>
```

### 3D: CSS for date-grouped earnings display

**File: `frontend/styles.css`**

Find the `.earnings-intel-book-flag` block (at the end of the earnings CSS section added in the previous brief). After the closing `}` of `.earnings-intel-book-flag`, **insert:**

```css
/* Earnings date-grouped display */
.earnings-date-groups {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.earnings-date-group {
    padding: 4px 0;
}

.earnings-date-label {
    color: var(--text-secondary);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 4px;
    padding-left: 2px;
}

.earnings-date-count {
    color: var(--text-tertiary, #556);
    font-weight: 400;
}

.earnings-date-tickers {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.earnings-ticker-chip {
    display: inline-block;
    font-size: 10px;
    font-family: 'Orbit', monospace;
    padding: 2px 6px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-secondary);
    border: 1px solid rgba(255, 255, 255, 0.06);
    white-space: nowrap;
}

.earnings-ticker-chip:hover {
    background: rgba(255, 255, 255, 0.08);
    color: var(--text-primary);
}

.earnings-ticker-chip.book-flag {
    border-color: rgba(236, 201, 75, 0.3);
    color: #ecc94b;
    background: rgba(236, 201, 75, 0.08);
}
```

---

## FIX 4: Add XLE and SPY Components to ETF_COMPONENTS

The position overlap utility is missing components for XLE and SPY. Without these, the batch endpoint won't resolve earnings for those positions either.

**File: `backend/utils/position_overlap.py`**

Find:

```python
ETF_COMPONENTS = {
    "XLF": ["JPM", "BRK.B", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "AXP"],
    "SMH": ["NVDA", "TSM", "AVGO", "ASML", "TXN", "QCOM", "AMD", "AMAT", "LRCX", "MU"],
    "HYG": [],
    "IYR": ["PLD", "AMT", "EQIX", "WELL", "SPG", "DLR", "PSA", "O", "CCI", "VICI"],
    "IWM": [],
    "IBIT": [],
}
```

**Replace with:**

```python
ETF_COMPONENTS = {
    "XLF": ["JPM", "BRK.B", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "AXP"],
    "SMH": ["NVDA", "TSM", "AVGO", "ASML", "TXN", "QCOM", "AMD", "AMAT", "LRCX", "MU"],
    "XLE": ["XOM", "CVX", "EOG", "SLB", "COP", "MPC", "PSX", "WMB", "VLO", "OKE"],
    "SPY": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "BRK.B", "AVGO", "JPM", "LLY"],
    "HYG": [],
    "IYR": ["PLD", "AMT", "EQIX", "WELL", "SPG", "DLR", "PSA", "O", "CCI", "VICI"],
    "IWM": [],
    "IBIT": [],
    "UNG": [],
}
```

---

## VERIFICATION CHECKLIST

1. **Positions panel:** Each ETF position (XLF, SMH, XLE, SPY) should now show an earnings row like `⚠ Earnings: Apr 14 (JPM) +3 more (6d)` — showing the next component to report, how many others are reporting soon, and days until
2. **Trade idea cards:** Any trade idea for an individual stock with upcoming earnings should show a badge. Any trade idea for an ETF should show component earnings badge
3. **Earnings tab:** Click "EARNINGS" in the Intel Center → should show "Position Book Impact" (component earnings linked to your positions) and "Upcoming Earnings (14 days)" with ticker chips grouped by date. Chips highlighted in yellow if they affect your book
4. **Console check:** Open browser dev tools → Console. Look for `Earnings batch load failed` errors. If present, check the network tab for the `/chronos/next-earnings-batch` call — verify it returns data

---

## FILES CHANGED SUMMARY

| File | What changed |
|------|-------------|
| `backend/api/chronos.py` | Enhanced `next-earnings-batch` to resolve ETF components via ETF_COMPONENTS; added `/chronos/upcoming` endpoint (14-day view) |
| `backend/utils/position_overlap.py` | Added XLE, SPY, UNG to ETF_COMPONENTS |
| `frontend/app.js` | Updated `getEarningsBadgeHtml` for ETF component display; updated position card earnings block; rewrote `loadEarningsIntelTab` to use `/upcoming` with date-grouped layout |
| `frontend/index.html` | Renamed section title to "Upcoming Earnings (14 days)" |
| `frontend/styles.css` | Added date-grouped earnings chip styles |
