# Brief: Surface Earnings Data + Macro Strip Overhaul

**Priority:** HIGH — earnings season is active  
**Scope:** Frontend-only (all backend endpoints already exist and are deployed)  
**Files modified:** `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`, `backend/api/macro_strip.py`

---

## CONTEXT FOR CLAUDE CODE

The Chronos earnings backend is **fully deployed** on Railway:
- `GET /api/chronos/next-earnings-batch?tickers=SPY,AAPL,MSFT` — returns `{ earnings: { "AAPL": { date: "2026-04-24", timing: "AMC" }, ... } }`
- `GET /api/chronos/this-week` — returns `{ book_impact: [...], market_movers: [...], total_earnings: N }`
- `GET /api/chronos/book-impact` — returns `{ positions_affected: N, impact: { "XLF": { earnings: [...], earnings_density: 0.4 } } }`

The `earnings_calendar` table is populated daily at 6 AM ET by `jobs/chronos_ingest.py` via FMP.

**The problem:** None of this data is surfaced where Nick actually needs it. This brief wires it into 3 places in the frontend and overhauls the macro ticker strip.

---

## DIAGNOSTIC STEP (do this first)

Before building, verify the backend is returning data. Run:

```bash
curl -s "https://pandoras-box-production.up.railway.app/api/chronos/this-week" -H "X-API-Key: rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk" | python3 -m json.tool | head -30
```

If `total_earnings` is 0 or the table is empty, trigger a manual refresh first:

```bash
curl -s -X POST "https://pandoras-box-production.up.railway.app/api/chronos/refresh" -H "X-API-Key: rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk" | python3 -m json.tool
```

If that fails, check that `FMP_API_KEY` is set in Railway env vars. If earnings data is confirmed flowing, proceed with the build.

---

## CHANGE 1: Earnings Badges on Trade Idea Cards (Grouped View)

### 1A: Add global earnings cache + fetch helper

**File: `frontend/app.js`**

Find this line (around line 395):

```javascript
let tradeIdeasPagination = {
```

**Insert ABOVE it:**

```javascript
// ===== EARNINGS CACHE =====
let earningsCache = {};  // { "AAPL": { date: "2026-04-24", timing: "AMC" }, ... }
let earningsCacheLoaded = false;

async function loadEarningsBatch(tickers) {
    if (!tickers || tickers.length === 0) return;
    try {
        const tickerStr = [...new Set(tickers)].join(',');
        const resp = await fetch(`${API_URL}/chronos/next-earnings-batch?tickers=${tickerStr}`, { headers: authHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.earnings) {
            Object.assign(earningsCache, data.earnings);
            earningsCacheLoaded = true;
        }
    } catch (e) {
        console.warn('Earnings batch load failed:', e);
    }
}

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
    return `<span class="earnings-badge ${urgencyClass}" title="Earnings in ${daysUntil} day${daysUntil !== 1 ? 's' : ''}">&#x26A0; Earn: ${dateStr}${timingStr}</span>`;
}
```

### 1B: Load earnings when grouped signals load

**File: `frontend/app.js`**

Find this function (around line 3604):

```javascript
async function loadGroupedSignals() {
    try {
        const showAll = document.getElementById('insights-show-all')?.checked || false;
        const url = showAll
            ? `${API_URL}/trade-ideas/grouped?show_all=true`
            : `${API_URL}/trade-ideas/grouped`;
        const response = await fetch(url);
        const data = await response.json();
        if (data.groups) {
            renderGroupedSignals(data.groups);
        }
```

**Replace with:**

```javascript
async function loadGroupedSignals() {
    try {
        const showAll = document.getElementById('insights-show-all')?.checked || false;
        const url = showAll
            ? `${API_URL}/trade-ideas/grouped?show_all=true`
            : `${API_URL}/trade-ideas/grouped`;
        const response = await fetch(url);
        const data = await response.json();
        if (data.groups) {
            // Fetch earnings for all visible tickers before rendering
            const tickers = data.groups.map(g => g.ticker).filter(Boolean);
            await loadEarningsBatch(tickers);
            renderGroupedSignals(data.groups);
        }
```

### 1C: Inject earnings badge into grouped signal cards

**File: `frontend/app.js`**

Inside `renderGroupedSignals()`, find this block (around line 3762):

```javascript
                <div class="signal-badges">
                    ${positionBadge}${counterBadge}
                </div>
```

**Replace with:**

```javascript
                <div class="signal-badges">
                    ${positionBadge}${counterBadge}${getEarningsBadgeHtml(group.ticker)}
                </div>
```

### 1D: Also inject into flat signal cards (fallback view)

**File: `frontend/app.js`**

Inside `createSignalCard()`, find this block (around line 4284):

```javascript
            <div class="signal-bias-indicator ${biasAlignmentClass}" title="${biasAlignmentText}">
                <span class="bias-icon">${biasAlignmentIcon}</span>
                <span class="bias-text">${biasAlignmentText}</span>
            </div>
```

**Replace with:**

```javascript
            ${getEarningsBadgeHtml(signal.ticker)}
            <div class="signal-bias-indicator ${biasAlignmentClass}" title="${biasAlignmentText}">
                <span class="bias-icon">${biasAlignmentIcon}</span>
                <span class="bias-text">${biasAlignmentText}</span>
            </div>
```

---

## CHANGE 2: Replace "THEME" Tab with "EARNINGS" Tab

The THEME tab in the Intel Center (column 2) has never displayed anything. Replace it with a dedicated earnings view that shows this week's important earnings.

### 2A: Rename the tab

**File: `frontend/index.html`**

Find (around line 237):

```html
                    <button class="intel-tab" data-tab="theme">THEME</button>
```

**Replace with:**

```html
                    <button class="intel-tab" data-tab="earnings">EARNINGS</button>
```

### 2B: Replace the THEME tab content with EARNINGS content

**File: `frontend/index.html`**

Find (around line 267-271):

```html
                <div class="intel-tab-content" id="themeTabContent" style="display:none;">
                    <div id="themeIntelContent" class="theme-intel-list">
                        <p class="empty-state">No theme-matched intel</p>
                    </div>
                </div>
```

**Replace with:**

```html
                <div class="intel-tab-content" id="earningsTabContent" style="display:none;">
                    <div class="earnings-intel-panel">
                        <div class="earnings-intel-section">
                            <div class="earnings-intel-section-header">
                                <span class="earnings-intel-section-title">Position Book Impact</span>
                                <span class="earnings-intel-section-meta" id="earningsBookCount"></span>
                            </div>
                            <div id="earningsBookImpact" class="earnings-intel-entries">
                                <p class="empty-state">Loading...</p>
                            </div>
                        </div>
                        <div class="earnings-intel-divider"></div>
                        <div class="earnings-intel-section">
                            <div class="earnings-intel-section-header">
                                <span class="earnings-intel-section-title">Top Earnings This Week</span>
                            </div>
                            <div id="earningsMarketMovers" class="earnings-intel-entries">
                                <p class="empty-state">Loading...</p>
                            </div>
                        </div>
                    </div>
                </div>
```

### 2C: Update the tab switching JS

**File: `frontend/app.js`**

Find the intel tab switching handler. Search for `intel-tab` click handlers. There should be a listener that toggles tab content visibility. It likely references `themeTabContent`. Find all references to `themeTabContent` and `theme` tab:

```bash
grep -n "themeTabContent\|themeIntelContent\|data-tab.*theme\|tab === .theme" frontend/app.js
```

For every reference to `themeTabContent`, replace with `earningsTabContent`. For every `tab === 'theme'` check, replace with `tab === 'earnings'`.

Then add the data loading function. Find the end of the `loadChronosEarnings` function (around line 12638):

```javascript
function renderChronosEntries(entries, containerId) {
```

**Insert ABOVE it (between the end of loadChronosEarnings and renderChronosEntries):**

```javascript
async function loadEarningsIntelTab() {
    try {
        const resp = await fetch(`${API_URL}/chronos/this-week`, { headers: authHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();

        // Book Impact section
        const bookContainer = document.getElementById('earningsBookImpact');
        const bookCount = document.getElementById('earningsBookCount');
        const bookItems = data.book_impact || [];
        if (bookCount) bookCount.textContent = bookItems.length > 0 ? `${bookItems.length} reporting` : '';

        if (bookContainer) {
            if (bookItems.length === 0) {
                bookContainer.innerHTML = '<p class="empty-state">No position-linked earnings this week</p>';
            } else {
                bookContainer.innerHTML = bookItems.map(e => {
                    const dateObj = new Date(e.report_date + 'T00:00:00');
                    const dayName = dateObj.toLocaleDateString('en-US', { weekday: 'short' });
                    const dateStr = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    const timing = e.timing || '—';
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

        // Market Movers section
        const moversContainer = document.getElementById('earningsMarketMovers');
        const movers = data.market_movers || [];
        if (moversContainer) {
            if (movers.length === 0) {
                moversContainer.innerHTML = '<p class="empty-state">No major earnings this week</p>';
            } else {
                moversContainer.innerHTML = movers.slice(0, 15).map(e => {
                    const dateObj = new Date(e.report_date + 'T00:00:00');
                    const dayName = dateObj.toLocaleDateString('en-US', { weekday: 'short' });
                    const dateStr = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    const timing = e.timing || '—';
                    const inBook = e.in_position_book ? '<span class="earnings-intel-book-flag">IN BOOK</span>' : '';
                    return `<div class="earnings-intel-entry">
                        <span class="earnings-intel-ticker">${e.ticker}</span>
                        <span class="earnings-intel-date">${dayName} ${dateStr}</span>
                        <span class="earnings-intel-timing">${timing}</span>
                        ${inBook}
                    </div>`;
                }).join('');
            }
        }
    } catch (err) {
        console.error('Earnings intel tab load error:', err);
        const el = document.getElementById('earningsBookImpact');
        if (el) el.innerHTML = '<p class="empty-state">Earnings data unavailable</p>';
    }
}
```

### 2D: Wire up the tab click to load earnings data

Find the intel tab click handler in `app.js`. Search for the event listener that handles `.intel-tab` clicks. It will have logic like:

```javascript
document.querySelectorAll('.intel-tab').forEach(tab => {
```

In that handler, after the existing tab content visibility toggling, add:

```javascript
if (selectedTab === 'earnings') loadEarningsIntelTab();
```

Also load on startup. Find the line (around line 1279):

```javascript
    loadChronosEarnings();
```

**Insert BELOW it:**

```javascript
    loadEarningsIntelTab();
```

---

## CHANGE 3: Earnings Badge on Open Positions

### 3A: Fetch earnings when positions load

**File: `frontend/app.js`**

Find `loadOpenPositionsEnhanced()` (around line 8684):

```javascript
async function loadOpenPositionsEnhanced() {
    try {
        const response = await fetch(`${API_URL}/v2/positions?status=OPEN`);
        const data = await response.json();

        if (data.positions) {
            openPositions = data.positions;
            renderPositionsEnhanced();
```

**Replace with:**

```javascript
async function loadOpenPositionsEnhanced() {
    try {
        const response = await fetch(`${API_URL}/v2/positions?status=OPEN`);
        const data = await response.json();

        if (data.positions) {
            openPositions = data.positions;
            // Fetch earnings for all position tickers
            const posTickers = openPositions.map(p => p.ticker).filter(Boolean);
            await loadEarningsBatch(posTickers);
            renderPositionsEnhanced();
```

### 3B: Add earnings badge to position cards

**File: `frontend/app.js`**

Inside `renderPositionCard()`, find (around line 9327-9331):

```javascript
            <div class="position-card-header">
                <span class="position-ticker" data-ticker="${pos.ticker}">${pos.ticker}</span>
                <span class="position-structure-badge">${structureDisplay}</span>
            </div>
            ${counterBanner}
```

**Replace with:**

```javascript
            <div class="position-card-header">
                <span class="position-ticker" data-ticker="${pos.ticker}">${pos.ticker}</span>
                <span class="position-structure-badge">${structureDisplay}</span>
            </div>
            ${(() => {
                const earn = earningsCache[pos.ticker];
                if (!earn || !earn.date) return '';
                const earnDate = new Date(earn.date + 'T00:00:00');
                const now = new Date();
                const daysUntil = Math.ceil((earnDate - now) / (1000 * 60 * 60 * 24));
                if (daysUntil < 0 || daysUntil > 30) return '';
                const dateStr = earnDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                const timingStr = earn.timing ? ' ' + earn.timing : '';
                // Check if earnings falls before expiry (critical for options!)
                let expiryWarning = '';
                if (pos.expiry) {
                    const expiryDate = new Date(pos.expiry + 'T00:00:00');
                    if (earnDate <= expiryDate) {
                        expiryWarning = ' <span class="earnings-before-expiry">BEFORE EXPIRY</span>';
                    }
                }
                const urgencyClass = daysUntil <= 3 ? 'earnings-badge-urgent' : daysUntil <= 7 ? 'earnings-badge-soon' : 'earnings-badge-normal';
                return '<div class="position-earnings-row ' + urgencyClass + '">' +
                    '&#x26A0; Earnings: ' + dateStr + timingStr +
                    ' (' + daysUntil + 'd)' + expiryWarning + '</div>';
            })()}
            ${counterBanner}
```

---

## CHANGE 4: Macro Strip Overhaul

### 4A: Update backend ticker list — replace TLT with 3 treasury ETFs

**File: `backend/api/macro_strip.py`**

Find:

```python
MACRO_TICKERS = {
    "SPY":  {"label": "SPY",  "name": "S&P 500"},
    "QQQ":  {"label": "QQQ",  "name": "Nasdaq"},
    "IWM":  {"label": "IWM",  "name": "Russell 2K"},
    "USO":  {"label": "OIL",  "name": "Crude Oil"},
    "GLD":  {"label": "GOLD", "name": "Gold"},
    "TLT":  {"label": "BONDS","name": "20Y Treasury"},
    "UUP":  {"label": "DXY",  "name": "US Dollar"},
    "HYG":  {"label": "HY",   "name": "High Yield"},
}
```

**Replace with:**

```python
MACRO_TICKERS = {
    "SPY":  {"label": "SPY",  "name": "S&P 500"},
    "QQQ":  {"label": "QQQ",  "name": "Nasdaq"},
    "IWM":  {"label": "IWM",  "name": "Russell 2K"},
    "USO":  {"label": "OIL",  "name": "Crude Oil"},
    "GLD":  {"label": "GOLD", "name": "Gold"},
    "SHY":  {"label": "2Y",   "name": "2Y Treasury"},
    "IEF":  {"label": "10Y",  "name": "7-10Y Treasury"},
    "TLT":  {"label": "20Y",  "name": "20Y Treasury"},
    "UUP":  {"label": "DXY",  "name": "US Dollar"},
    "HYG":  {"label": "HY",   "name": "High Yield"},
}
```

### 4B: Continuous scrolling marquee — update JS rendering

**File: `frontend/app.js`**

Find `renderMacroStrip` (around line 11559):

```javascript
function renderMacroStrip(tickers) {
    const container = document.getElementById('macroStripInner');
    if (!container || !tickers || tickers.length === 0) return;

    container.innerHTML = tickers.map((t, i) => {
        const sign = t.change_pct >= 0 ? '+' : '';
        const cls = t.change_pct >= 0 ? 'positive' : 'negative';
        const sep = i < tickers.length - 1 ? '<span class="macro-sep">&middot;</span>' : '';
        return `<div class="macro-cell" title="${escapeHtml(t.name)}">
            <span class="macro-cell-label">${escapeHtml(t.label)}</span>
            <span class="macro-cell-price">${t.price.toFixed(2)}</span>
            <span class="macro-cell-change ${cls}">${sign}${t.change_pct.toFixed(2)}%</span>
        </div>${sep}`;
    }).join('');
}
```

**Replace with:**

```javascript
function renderMacroStrip(tickers) {
    const container = document.getElementById('macroStripInner');
    if (!container || !tickers || tickers.length === 0) return;

    // Build one set of cells
    const cellsHtml = tickers.map((t, i) => {
        const sign = t.change_pct >= 0 ? '+' : '';
        const cls = t.change_pct >= 0 ? 'positive' : 'negative';
        const sep = '<span class="macro-sep">&middot;</span>';
        return `<div class="macro-cell" title="${escapeHtml(t.name)}">
            <span class="macro-cell-label">${escapeHtml(t.label)}</span>
            <span class="macro-cell-price">${t.price.toFixed(2)}</span>
            <span class="macro-cell-change ${cls}">${sign}${t.change_pct.toFixed(2)}%</span>
        </div>${sep}`;
    }).join('');

    // Duplicate content for seamless infinite scroll loop
    container.innerHTML = `<div class="macro-scroll-set">${cellsHtml}</div><div class="macro-scroll-set">${cellsHtml}</div>`;
}
```

### 4C: Continuous scroll CSS + vertical centering

**File: `frontend/styles.css`**

Find (around line 12035):

```css
.macro-strip {
    background: var(--dark-bg);
    border-bottom: 1px solid var(--border-color);
    padding: 4px 16px;
    overflow: hidden;
}

.macro-strip-inner {
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: center;
    flex-wrap: nowrap;
}
```

**Replace with:**

```css
.macro-strip {
    background: var(--dark-bg);
    border-bottom: 1px solid var(--border-color);
    padding: 0 0;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 32px;
}

.macro-strip-inner {
    display: flex;
    align-items: center;
    flex-wrap: nowrap;
    animation: macroScroll 40s linear infinite;
    width: max-content;
}

.macro-strip-inner:hover {
    animation-play-state: paused;
}

.macro-scroll-set {
    display: flex;
    align-items: center;
    gap: 0;
    flex-shrink: 0;
}

@keyframes macroScroll {
    0% { transform: translateX(0); }
    100% { transform: translateX(-50%); }
}
```

---

## CHANGE 5: Earnings Badge CSS

**File: `frontend/styles.css`**

Find (around line 12081):

```css
.macro-sep {
    color: var(--border-color);
    font-size: 8px;
    user-select: none;
}
```

**Insert AFTER the `.macro-sep` block (after line 12085):**

```css
/* ===== EARNINGS BADGES ===== */
.earnings-badge {
    display: inline-block;
    font-size: 9px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 3px;
    letter-spacing: 0.3px;
    white-space: nowrap;
}

.earnings-badge-urgent {
    background: rgba(229, 62, 62, 0.2);
    color: #e53e3e;
    border: 1px solid rgba(229, 62, 62, 0.3);
}

.earnings-badge-soon {
    background: rgba(236, 201, 75, 0.15);
    color: #ecc94b;
    border: 1px solid rgba(236, 201, 75, 0.25);
}

.earnings-badge-normal {
    background: rgba(160, 174, 192, 0.1);
    color: #a0aec0;
    border: 1px solid rgba(160, 174, 192, 0.15);
}

/* Position card earnings row */
.position-earnings-row {
    font-size: 10px;
    padding: 3px 8px;
    margin: 2px 0 4px 0;
    border-radius: 3px;
    font-weight: 500;
}

.position-earnings-row.earnings-badge-urgent {
    background: rgba(229, 62, 62, 0.15);
    color: #fc8181;
}

.position-earnings-row.earnings-badge-soon {
    background: rgba(236, 201, 75, 0.1);
    color: #ecc94b;
}

.position-earnings-row.earnings-badge-normal {
    background: rgba(160, 174, 192, 0.08);
    color: #a0aec0;
}

.earnings-before-expiry {
    background: rgba(229, 62, 62, 0.3);
    color: #fed7d7;
    font-size: 8px;
    font-weight: 700;
    padding: 0 4px;
    border-radius: 2px;
    margin-left: 4px;
    letter-spacing: 0.5px;
}

/* ===== EARNINGS INTEL TAB ===== */
.earnings-intel-panel {
    padding: 8px 0;
    max-height: 500px;
    overflow-y: auto;
}

.earnings-intel-section {
    padding: 4px 12px;
}

.earnings-intel-section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
}

.earnings-intel-section-title {
    color: var(--text-secondary);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.earnings-intel-section-meta {
    color: var(--text-tertiary, #667);
    font-size: 9px;
}

.earnings-intel-divider {
    height: 1px;
    background: var(--border-color);
    margin: 8px 12px;
}

.earnings-intel-entry {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 6px;
    border-radius: 4px;
    font-size: 11px;
    transition: background 0.15s;
}

.earnings-intel-entry:hover {
    background: rgba(255, 255, 255, 0.03);
}

.earnings-intel-entry.book-impact-entry {
    border-left: 2px solid #ecc94b;
    padding-left: 8px;
}

.earnings-intel-ticker {
    color: var(--text-primary);
    font-weight: 600;
    min-width: 48px;
    font-family: 'Orbit', monospace;
}

.earnings-intel-date {
    color: var(--text-secondary);
    font-size: 10px;
    min-width: 70px;
}

.earnings-intel-timing {
    color: var(--text-tertiary, #667);
    font-size: 9px;
    font-weight: 600;
    min-width: 30px;
    text-align: center;
}

.earnings-intel-overlap {
    color: #ecc94b;
    font-size: 9px;
    font-weight: 500;
    margin-left: auto;
}

.earnings-intel-book-flag {
    font-size: 8px;
    font-weight: 700;
    color: #ecc94b;
    background: rgba(236, 201, 75, 0.12);
    padding: 0 4px;
    border-radius: 2px;
    margin-left: auto;
}
```

---

## VERIFICATION CHECKLIST

After deploying, verify each change:

1. **Trade idea cards:** Open Agora → check Insights panel → cards for tickers with upcoming earnings should show a colored badge like `⚠ Earn: Apr 16 AMC`
2. **Earnings tab:** Click the "EARNINGS" tab in the Intel Center (column 2, where THEME used to be) → should show "Position Book Impact" (earnings overlapping your positions) and "Top Earnings This Week"
3. **Open positions:** Scroll to positions panel → each position with upcoming earnings shows an earnings row beneath the ticker. Options positions where earnings fall before expiry show a red "BEFORE EXPIRY" flag
4. **Macro strip scrolling:** The ticker strip at the top should scroll continuously left like a stock ticker. Hovering pauses it
5. **Macro strip tickers:** Should show: SPY, QQQ, IWM, OIL, GOLD, 2Y, 10Y, 20Y, DXY, HY — no more "BONDS" label
6. **Macro strip centering:** The strip should be vertically centered in its container (no visual offset)
7. **If any earnings data is empty:** Click the Chronos tab in the Chronos row (lower section) — if that's also empty, run the manual refresh curl command from the diagnostic step

---

## FILES CHANGED SUMMARY

| File | Changes |
|------|---------|
| `frontend/app.js` | Earnings cache + batch loader, badge helper, inject into grouped cards, flat cards, positions loading, positions cards, earnings intel tab loader, update renderMacroStrip for marquee |
| `frontend/index.html` | Rename THEME → EARNINGS tab, replace tab content HTML |
| `frontend/styles.css` | Earnings badge styles (urgent/soon/normal), earnings intel tab styles, macro strip marquee animation + vertical centering |
| `backend/api/macro_strip.py` | Replace TLT-only with SHY + IEF + TLT (2Y, 10Y, 20Y labels) |
