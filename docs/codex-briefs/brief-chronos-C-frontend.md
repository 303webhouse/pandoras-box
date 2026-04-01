# BRIEF: Chronos Phase C — Frontend (New Row: Hydra + Watchlist/Chronos Tabs)
## Priority: P0 | System: Agora Frontend (index.html + app.js + styles.css)
## Date: 2026-04-01
## Related: Chronos Phase A (Watchlist Backend), Phase B (Earnings Backend)
## Dependency: Phase A and Phase B must be deployed first (endpoints must exist)

---

## CONTEXT FOR CLAUDE CODE

This brief adds a **new row** to the Agora dashboard, positioned between the existing `main-content` section (TradingView chart / Insights / Ledger) and the existing `watchlist-section` (RADAR ticker screener).

The new row is split 50/50:
- **Left 50%:** Hydra Squeeze Monitor (MOVED from its current location in `bias-right-stack`)
- **Right 50%:** Tabbed panel with two tabs: **Watchlist** (Long/Short ideas) and **Chronos** (Earnings radar)

**Important:** The existing Hydra panel in `bias-right-stack` (the `<div class="hydra-panel" id="hydra-panel">` block) gets REMOVED from its current location and placed in the new row. All existing Hydra JS logic (`toggleHydraPanel()`, `switchHydraTab()`, `refreshHydra()`, etc.) should continue to work — just re-parented in the DOM.

**Design language:** Match Agora's existing dark theme exactly. Background: `#0a0e17`. Card backgrounds: `#111627`. Borders: `#1a1f2e`. Text: `#ccc` primary, `#889` secondary, `#556` tertiary. Accent: `#c9a04e` (gold). Green: `#2a5` / `#00e676`. Red: `#e54` / `#e5370e`. Orange: `#ff9800`.

---

## STEP 1: HTML Structure — `index.html`

### A. Remove Hydra from `bias-right-stack`

Find and REMOVE the entire `<div class="hydra-panel" id="hydra-panel">...</div>` block from inside `<div class="bias-right-stack">`. This block starts around line 350 of index.html and includes the hydra-header, hydra-body, hydra-tabs, hydra-table, etc.

CUT this entire block (you'll paste it into the new section).

### B. Add New Row Between `main-content` and `watchlist-section`

Find this boundary in index.html:
```html
        </section>  <!-- end of .main-content -->

        <!-- Watchlist v3 -->
        <section class="watchlist-section">
```

INSERT the new row between them:

```html
        </section>  <!-- end of .main-content -->

        <!-- CHRONOS ROW: Hydra Squeeze (left 50%) + Watchlist/Chronos Tabs (right 50%) -->
        <section class="chronos-row">
            <!-- LEFT: Hydra Squeeze Monitor (moved from bias-right-stack) -->
            <div class="chronos-hydra-col">
                <!-- PASTE the entire hydra-panel div here, unchanged -->
                <div class="hydra-panel" id="hydra-panel">
                    <!-- ... all existing hydra HTML ... -->
                </div>
            </div>

            <!-- RIGHT: Watchlist / Chronos Tabs -->
            <div class="chronos-tabs-col">
                <div class="chronos-tab-bar">
                    <button class="chronos-tab active" data-chronos-tab="watchlist" onclick="switchChronosTab('watchlist')">WATCHLIST</button>
                    <button class="chronos-tab" data-chronos-tab="earnings" onclick="switchChronosTab('earnings')">CHRONOS</button>
                </div>

                <!-- Watchlist Tab Content -->
                <div class="chronos-tab-content" id="chronos-watchlist-content">
                    <div class="watchlist-columns">
                        <!-- LONG Column -->
                        <div class="watchlist-col" id="watchlist-long-col">
                            <div class="watchlist-col-header long">
                                <span class="watchlist-col-label">LONG IDEAS</span>
                                <span class="watchlist-col-line"></span>
                            </div>
                            <div class="watchlist-cards" id="watchlist-long-cards">
                                <p class="empty-state">No long ideas yet</p>
                            </div>
                        </div>
                        <!-- SHORT Column -->
                        <div class="watchlist-col" id="watchlist-short-col">
                            <div class="watchlist-col-header short">
                                <span class="watchlist-col-label">SHORT IDEAS</span>
                                <span class="watchlist-col-line"></span>
                            </div>
                            <div class="watchlist-cards" id="watchlist-short-cards">
                                <p class="empty-state">No short ideas yet</p>
                            </div>
                        </div>
                    </div>
                    <div class="watchlist-add-bar">
                        <button class="watchlist-add-btn" id="watchlistAddBtn" onclick="openWatchlistAddModal()">+ Add Ticker</button>
                    </div>
                </div>

                <!-- Chronos/Earnings Tab Content -->
                <div class="chronos-tab-content" id="chronos-earnings-content" style="display: none;">
                    <div class="chronos-sections">
                        <div class="chronos-section">
                            <h4 class="chronos-section-title">This Week — Book Impact</h4>
                            <div id="chronos-book-impact" class="chronos-entries">
                                <p class="empty-state">Loading earnings...</p>
                            </div>
                        </div>
                        <div class="chronos-section">
                            <h4 class="chronos-section-title">Market Movers</h4>
                            <div id="chronos-market-movers" class="chronos-entries">
                                <p class="empty-state">Loading...</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Watchlist v3 (existing RADAR) -->
        <section class="watchlist-section">
```

---

### C. Add Watchlist Add/Edit Modal

Add this modal overlay at the bottom of the page (near the other modals):

```html
<!-- Watchlist Add Modal -->
<div class="modal-overlay" id="watchlistAddModal" style="display: none;">
    <div class="modal-content watchlist-add-modal">
        <div class="modal-header">
            <h3 id="watchlistModalTitle">Add to Watchlist</h3>
            <button class="modal-close" id="closeWatchlistModalBtn" onclick="closeWatchlistAddModal()">&times;</button>
        </div>
        <div class="modal-body">
            <div class="form-row">
                <div class="form-group">
                    <label>Ticker</label>
                    <input type="text" id="wlTicker" placeholder="AAPL" maxlength="10">
                </div>
                <div class="form-group">
                    <label>Direction</label>
                    <select id="wlDirection">
                        <option value="LONG">LONG</option>
                        <option value="SHORT">SHORT</option>
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Entry Target Price</label>
                    <input type="number" id="wlEntryTarget" step="0.01" placeholder="42.00">
                </div>
                <div class="form-group">
                    <label>Bucket</label>
                    <select id="wlBucket">
                        <option value="">—</option>
                        <option value="THESIS">Thesis</option>
                        <option value="TACTICAL">Tactical</option>
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Source</label>
                    <select id="wlSource">
                        <option value="MANUAL">Manual</option>
                        <option value="UW_FLOW">UW Flow</option>
                        <option value="SCANNER">Scanner</option>
                        <option value="COMMITTEE">Committee</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Committee Grade</label>
                    <select id="wlGrade">
                        <option value="">—</option>
                        <option value="A">A</option>
                        <option value="A-">A-</option>
                        <option value="B+">B+</option>
                        <option value="B">B</option>
                        <option value="B-">B-</option>
                        <option value="C">C</option>
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group full-width">
                    <label>Thesis Note</label>
                    <input type="text" id="wlThesis" placeholder="One-line thesis...">
                </div>
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn-cancel" onclick="closeWatchlistAddModal()">Cancel</button>
            <button class="btn-confirm" id="confirmWatchlistAddBtn" onclick="submitWatchlistEntry()">Add to Watchlist</button>
        </div>
    </div>
</div>
```

---

## STEP 2: CSS — `styles.css`

Add these styles. Match existing Agora patterns exactly.

```css
/* === CHRONOS ROW === */
.chronos-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: #1a1f2e;
    border-top: 1px solid #1a1f2e;
    border-bottom: 1px solid #1a1f2e;
}

.chronos-hydra-col,
.chronos-tabs-col {
    background: #0a0e17;
    padding: 12px 16px;
}

/* Hydra panel in new location — remove the old margin/rounding if any */
.chronos-hydra-col .hydra-panel {
    margin: 0;
    border-radius: 0;
}

/* Tab bar */
.chronos-tab-bar {
    display: flex;
    gap: 2px;
    background: #111627;
    border-radius: 4px;
    padding: 2px;
    margin-bottom: 12px;
}

.chronos-tab {
    flex: 1;
    text-align: center;
    padding: 6px 12px;
    background: transparent;
    color: #556;
    border: none;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: all 0.2s;
}

.chronos-tab.active {
    background: #1a2235;
    color: #ccc;
}

/* Watchlist columns */
.watchlist-columns {
    display: flex;
    gap: 12px;
}

.watchlist-col {
    flex: 1;
    min-width: 0;
}

.watchlist-col-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
}

.watchlist-col-header .watchlist-col-label {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.5px;
}

.watchlist-col-header.long .watchlist-col-label { color: #00e676; }
.watchlist-col-header.short .watchlist-col-label { color: #e5370e; }

.watchlist-col-header .watchlist-col-line {
    flex: 1;
    height: 0.5px;
}

.watchlist-col-header.long .watchlist-col-line { background: #0a2e1a; }
.watchlist-col-header.short .watchlist-col-line { background: #2e0a0a; }

/* Watchlist card */
.watchlist-card {
    background: #111627;
    border-radius: 6px;
    padding: 8px 10px;
    margin-bottom: 6px;
    cursor: pointer;
    transition: border-color 0.2s;
}

.watchlist-card.long { border-left: 2px solid #00e676; }
.watchlist-card.short { border-left: 2px solid #e5370e; }

.watchlist-card:hover { border-color: #c9a04e; }

.watchlist-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.watchlist-card-ticker {
    color: #ccc;
    font-weight: 500;
    font-size: 12px;
}

.watchlist-card-price {
    color: #889;
    font-size: 10px;
}

.watchlist-card-mid {
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
}

.watchlist-card-target {
    color: #556;
    font-size: 9px;
}

.watchlist-card-distance {
    font-size: 9px;
}

.watchlist-card-distance.close { color: #00e676; }
.watchlist-card-distance.medium { color: #ff9800; }
.watchlist-card-distance.far { color: #889; }

.watchlist-card-badges {
    display: flex;
    gap: 4px;
    margin-top: 4px;
    flex-wrap: wrap;
}

.watchlist-badge {
    padding: 1px 5px;
    border-radius: 2px;
    font-size: 8px;
}

.watchlist-badge.grade { background: #0a2e1a; color: #00e676; }
.watchlist-badge.grade-b { background: #1a2e0a; color: #ff9800; }
.watchlist-badge.grade-c { background: #2e0a0a; color: #e54; }
.watchlist-badge.earnings { background: #111; color: #556; }
.watchlist-badge.earnings-soon { background: #e5370e22; color: #e54; font-weight: 500; }
.watchlist-badge.source { background: #111; color: #556; }

.watchlist-card-thesis {
    color: #556;
    font-size: 8px;
    margin-top: 3px;
    font-style: italic;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.watchlist-add-bar {
    margin-top: 10px;
    text-align: center;
}

.watchlist-add-btn {
    color: #334;
    font-size: 10px;
    border: 0.5px dashed #334;
    padding: 6px 16px;
    border-radius: 4px;
    background: transparent;
    cursor: pointer;
    transition: all 0.2s;
}

.watchlist-add-btn:hover {
    border-color: #c9a04e;
    color: #c9a04e;
}

/* Chronos earnings section */
.chronos-sections {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.chronos-section-title {
    font-size: 10px;
    color: #667;
    font-weight: 500;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}

.chronos-entry {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 0;
    border-bottom: 0.5px solid #111627;
    font-size: 10px;
}

.chronos-entry-ticker {
    color: #ccc;
    font-weight: 500;
    min-width: 50px;
}

.chronos-entry-date {
    color: #889;
}

.chronos-entry-timing {
    color: #556;
    font-size: 9px;
}

.chronos-entry-overlap {
    color: #e54;
    font-size: 9px;
    font-weight: 500;
}

/* Watchlist add modal — reuse existing modal styles */
.watchlist-add-modal {
    max-width: 480px;
}
```

---

## STEP 3: JavaScript — `app.js`

Add these functions to app.js. Place them near the existing Hydra functions (search for `toggleHydraPanel` to find the right area).

### Tab Switching

```javascript
// === CHRONOS TAB SWITCHING ===
function switchChronosTab(tabName) {
    // Update tab bar
    document.querySelectorAll('.chronos-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.chronos-tab[data-chronos-tab="${tabName}"]`).classList.add('active');
    
    // Show/hide content
    document.getElementById('chronos-watchlist-content').style.display = tabName === 'watchlist' ? '' : 'none';
    document.getElementById('chronos-earnings-content').style.display = tabName === 'earnings' ? '' : 'none';
    
    // Load data for the active tab
    if (tabName === 'watchlist') loadWatchlist();
    if (tabName === 'earnings') loadChronosEarnings();
}
```

### Watchlist Functions

```javascript
// === TRADE WATCHLIST ===
async function loadWatchlist() {
    try {
        const resp = await fetch(`${API_URL}/trade-watchlist`, { headers: authHeaders() });
        const data = await resp.json();
        renderWatchlistCards(data.long_ideas || [], 'watchlist-long-cards', 'long');
        renderWatchlistCards(data.short_ideas || [], 'watchlist-short-cards', 'short');
    } catch (err) {
        console.error('Watchlist load error:', err);
    }
}

function renderWatchlistCards(entries, containerId, direction) {
    const container = document.getElementById(containerId);
    if (!entries.length) {
        container.innerHTML = '<p class="empty-state">No ideas yet</p>';
        return;
    }
    
    container.innerHTML = entries.map(e => {
        const dist = Math.abs(e.distance_to_target_pct || 0);
        const distClass = dist < 3 ? 'close' : dist < 10 ? 'medium' : 'far';
        const distLabel = e.entry_target ? `${dist.toFixed(1)}% away` : '—';
        
        // Grade badge styling
        let gradeBadgeClass = 'grade';
        if (e.committee_grade && e.committee_grade.startsWith('B')) gradeBadgeClass = 'grade-b';
        if (e.committee_grade && e.committee_grade.startsWith('C')) gradeBadgeClass = 'grade-c';
        
        // Earnings badge
        let earningsBadge = '';
        if (e.next_earnings_date) {
            const daysToEarnings = Math.ceil((new Date(e.next_earnings_date) - new Date()) / 86400000);
            const earnClass = daysToEarnings <= 14 ? 'earnings-soon' : 'earnings';
            const timing = e.earnings_timing ? ` ${e.earnings_timing}` : '';
            earningsBadge = `<span class="watchlist-badge ${earnClass}">Earn: ${e.next_earnings_date}${timing}</span>`;
        }
        
        return `
        <div class="watchlist-card ${direction}" data-wl-id="${e.id}" onclick="openWatchlistDetail('${e.id}')">
            <div class="watchlist-card-top">
                <span class="watchlist-card-ticker">${e.ticker}</span>
                <span class="watchlist-card-price">$${Number(e.current_price || 0).toFixed(2)}</span>
            </div>
            <div class="watchlist-card-mid">
                <span class="watchlist-card-target">${e.entry_target ? 'Target: $' + Number(e.entry_target).toFixed(2) : '—'}</span>
                <span class="watchlist-card-distance ${distClass}">${distLabel}</span>
            </div>
            <div class="watchlist-card-badges">
                ${e.committee_grade ? `<span class="watchlist-badge ${gradeBadgeClass}">${e.committee_grade}</span>` : ''}
                ${earningsBadge}
                <span class="watchlist-badge source">${e.source || 'Manual'}</span>
            </div>
            ${e.thesis_note ? `<div class="watchlist-card-thesis">${e.thesis_note}</div>` : ''}
        </div>`;
    }).join('');
}

function openWatchlistAddModal() {
    document.getElementById('watchlistAddModal').style.display = 'flex';
    document.getElementById('wlTicker').value = '';
    document.getElementById('wlDirection').value = 'LONG';
    document.getElementById('wlEntryTarget').value = '';
    document.getElementById('wlThesis').value = '';
    document.getElementById('wlGrade').value = '';
    document.getElementById('wlSource').value = 'MANUAL';
    document.getElementById('wlBucket').value = '';
    document.getElementById('wlTicker').focus();
}

function closeWatchlistAddModal() {
    document.getElementById('watchlistAddModal').style.display = 'none';
}

async function submitWatchlistEntry() {
    const ticker = document.getElementById('wlTicker').value.trim().toUpperCase();
    if (!ticker) return;
    
    const body = {
        ticker,
        direction: document.getElementById('wlDirection').value,
        entry_target: parseFloat(document.getElementById('wlEntryTarget').value) || null,
        thesis_note: document.getElementById('wlThesis').value.trim() || null,
        committee_grade: document.getElementById('wlGrade').value || null,
        source: document.getElementById('wlSource').value,
        bucket: document.getElementById('wlBucket').value || null,
    };
    
    try {
        const resp = await fetch(`${API_URL}/trade-watchlist`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(body)
        });
        if (resp.ok) {
            closeWatchlistAddModal();
            loadWatchlist();
        } else {
            const err = await resp.json();
            alert(err.detail || 'Failed to add entry');
        }
    } catch (err) {
        console.error('Watchlist add error:', err);
    }
}

async function deleteWatchlistEntry(id) {
    if (!confirm('Remove from watchlist?')) return;
    try {
        await fetch(`${API_URL}/trade-watchlist/${id}`, {
            method: 'DELETE',
            headers: authHeaders()
        });
        loadWatchlist();
    } catch (err) {
        console.error('Watchlist delete error:', err);
    }
}

function openWatchlistDetail(id) {
    // Phase 2: open a detail/edit modal for the entry
    // For V1, clicking a card could load the ticker in the TradingView chart
    console.log('Watchlist detail:', id);
}
```

### Chronos Earnings Functions

```javascript
// === CHRONOS EARNINGS ===
async function loadChronosEarnings() {
    try {
        const resp = await fetch(`${API_URL}/chronos/this-week`, { headers: authHeaders() });
        const data = await resp.json();
        
        renderChronosEntries(data.book_impact || [], 'chronos-book-impact');
        renderChronosEntries(data.market_movers || [], 'chronos-market-movers');
    } catch (err) {
        console.error('Chronos load error:', err);
        document.getElementById('chronos-book-impact').innerHTML = '<p class="empty-state">Earnings data unavailable</p>';
    }
}

function renderChronosEntries(entries, containerId) {
    const container = document.getElementById(containerId);
    if (!entries.length) {
        container.innerHTML = '<p class="empty-state">No earnings this period</p>';
        return;
    }
    
    container.innerHTML = entries.slice(0, 10).map(e => `
        <div class="chronos-entry">
            <span class="chronos-entry-ticker">${e.ticker}</span>
            <span class="chronos-entry-date">${e.report_date}</span>
            <span class="chronos-entry-timing">${e.timing || '—'}</span>
            ${e.in_position_book ? `<span class="chronos-entry-overlap">${(e.position_overlap_details?.etf_positions || []).join(', ')}</span>` : ''}
        </div>
    `).join('');
}
```

### WebSocket Handler for Watchlist Alerts

Find the existing WebSocket message handler in app.js (search for `manager.broadcast` or the `onmessage` handler). Add a case for watchlist alerts:

```javascript
// Inside the WebSocket onmessage handler, add:
if (msg.type === 'watchlist_alert') {
    // Show a brief notification banner (reuse Hermes flash pattern if possible)
    console.log(`🎯 WATCHLIST ALERT: ${msg.ticker} hit target $${msg.entry_target}`);
    // Refresh the watchlist to show the alert-fired state
    loadWatchlist();
}
```

### Initial Load

In the app's initialization section (the startup function that runs on page load), add:

```javascript
// Load watchlist on startup (if Chronos row is visible)
loadWatchlist();
```

---

## STEP 4: Hydra Panel — Default to Expanded

Since Hydra is now in its own 50% column with more room, change the default state from collapsed to expanded:

Find the hydra-body `style="display:none;"` in the HTML and change it to `style="display:block;"`. Also update the toggle arrow to point down: change `&#x25B6;` (right arrow) to `&#x25BC;` (down arrow) in the hydra-toggle span.

---

## VERIFICATION CHECKLIST

1. Hydra panel appears in the LEFT 50% of the new row (removed from bias-right-stack)
2. Hydra Defensive/Offensive tabs still work
3. Watchlist tab shows Long/Short columns with cards
4. "+ Add Ticker" button opens modal, submission creates entry
5. Cards show: ticker, price, target, distance, grade badge, earnings date, thesis
6. Cards sorted by distance-to-target (closest first)
7. Earnings soon (<14 days) badge shows in red
8. Chronos tab shows "This Week — Book Impact" and "Market Movers"
9. Tab switching between Watchlist and Chronos works
10. Existing RADAR section below the new row is unchanged

---

## FILES MODIFIED

| File | Action |
|------|--------|
| `frontend/index.html` | **MODIFY** — Remove Hydra from bias-right-stack, add chronos-row section, add watchlist modal |
| `frontend/styles.css` | **MODIFY** — Add all `.chronos-*` and `.watchlist-*` styles |
| `frontend/app.js` | **MODIFY** — Add tab switching, watchlist CRUD, chronos loading, WebSocket handler |
