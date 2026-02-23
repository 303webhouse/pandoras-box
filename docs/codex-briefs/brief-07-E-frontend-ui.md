# Brief 07-E — Frontend Portfolio Dashboard UI

**Phase:** 3 (SERIAL — needs 07-B's API endpoints deployed first)
**Touches:** `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
**Depends on:** 07-B (portfolio API must be live)
**Estimated time:** 1.5-2 hours

---

## Task

Add two UI components to the main dashboard:
1. **Account Balance Box** — compact card showing all 4 accounts + total
2. **Open Positions Table** — wire the existing positions area to the new API

**CRITICAL:** These frontend files are massive (`index.html` = 121KB, `app.js` = 361KB, `styles.css` = 197KB). Use **targeted insertions**, not full rewrites. Find exact anchor points and add code there.

---

## Component 1: Account Balance Box

### Location in `index.html`

Find the main dashboard layout area. The balance box should be placed in the top row alongside existing bias indicator cards. Look for the existing card grid/flex container that holds the bias cards and add the balance card as a new item.

If there's an existing row that contains bias cards, add this after the last bias card. If the layout uses CSS grid, it should occupy roughly 1/4 width on desktop, full width on mobile.

### HTML to add (in `index.html`)

```html
<!-- Account Balances Card -->
<div class="card portfolio-balances-card" id="portfolio-balances">
    <div class="card-header">
        <h3>💰 Portfolio</h3>
        <span class="balance-updated" id="balance-updated-time">—</span>
    </div>
    <div class="card-body">
        <div class="balance-rows" id="balance-rows">
            <div class="balance-loading">Loading...</div>
        </div>
        <div class="balance-total-row" id="balance-total-row">
            <span class="balance-label">Total</span>
            <span class="balance-value" id="balance-total">—</span>
        </div>
    </div>
</div>
```

### CSS to add (in `styles.css`)

```css
/* Portfolio Balance Card */
.portfolio-balances-card {
    min-width: 220px;
}

.portfolio-balances-card .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.balance-updated {
    font-size: 0.7rem;
    color: var(--text-muted, #888);
}

.balance-rows {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.balance-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 0.85rem;
}

.balance-row.active-account {
    font-weight: 600;
}

.balance-row.passive-account {
    opacity: 0.6;
    font-size: 0.8rem;
}

.balance-label {
    color: var(--text-secondary, #aaa);
}

.balance-value {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
}

.balance-sub {
    font-size: 0.7rem;
    color: var(--text-muted, #888);
    margin-left: auto;
    padding-left: 8px;
}

.balance-total-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 8px;
    margin-top: 8px;
    border-top: 1px solid var(--border-color, #333);
    font-weight: 700;
    font-size: 1rem;
}

.balance-value.positive { color: var(--success, #4ade80); }
.balance-value.negative { color: var(--danger, #f87171); }
```

### JavaScript to add (in `app.js`)

Find an appropriate section boundary (look for `// =====` style section headers). Add:

```javascript
// ==================== PORTFOLIO BALANCES ====================

async function loadPortfolioBalances() {
    try {
        const res = await fetch(`${API_BASE}/api/portfolio/balances`);
        if (!res.ok) return;
        const accounts = await res.json();

        const container = document.getElementById('balance-rows');
        const totalEl = document.getElementById('balance-total');
        const updatedEl = document.getElementById('balance-updated-time');

        if (!container || !accounts.length) return;

        let total = 0;
        let latestUpdate = null;
        let html = '';

        for (const acct of accounts) {
            const bal = parseFloat(acct.balance);
            total += bal;

            if (acct.updated_at && (!latestUpdate || new Date(acct.updated_at) > new Date(latestUpdate))) {
                latestUpdate = acct.updated_at;
            }

            const isRH = acct.broker === 'robinhood';
            const rowClass = isRH ? 'active-account' : 'passive-account';

            html += `<div class="balance-row ${rowClass}">
                <span class="balance-label">${acct.account_name}</span>
                <span class="balance-value">$${bal.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
            </div>`;

            if (isRH && acct.cash != null) {
                html += `<div class="balance-row active-account">
                    <span class="balance-sub">Cash: $${parseFloat(acct.cash).toLocaleString('en-US', {minimumFractionDigits: 2})} · BP: $${parseFloat(acct.buying_power).toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
                </div>`;
            }
        }

        container.innerHTML = html;
        totalEl.textContent = `$${total.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        if (latestUpdate) {
            const ago = getTimeAgo(new Date(latestUpdate));
            updatedEl.textContent = `Updated ${ago}`;
        }
    } catch (err) {
        console.error('Failed to load portfolio balances:', err);
    }
}

function getTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

setInterval(loadPortfolioBalances, 60000);
```

Then call `loadPortfolioBalances()` from the dashboard init function (look for `DOMContentLoaded` or an `init()` function).

---

## Component 2: Open Positions Table

Look for any existing "Open Positions" section. If one exists, wire it to the new API. If not, add below the balance card area.

### HTML

```html
<!-- Open Positions -->
<div class="card positions-card" id="open-positions-card">
    <div class="card-header">
        <h3>📊 Open Positions</h3>
        <span class="positions-count" id="positions-count">0</span>
    </div>
    <div class="card-body">
        <table class="positions-table" id="positions-table">
            <thead>
                <tr>
                    <th>Ticker</th>
                    <th>Position</th>
                    <th>Qty</th>
                    <th>Cost</th>
                    <th>Value</th>
                    <th>P&L</th>
                </tr>
            </thead>
            <tbody id="positions-tbody">
                <tr><td colspan="6" class="loading">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</div>
```

### CSS

```css
/* Positions Table */
.positions-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}

.positions-table th {
    text-align: left;
    padding: 6px 8px;
    font-size: 0.75rem;
    text-transform: uppercase;
    color: var(--text-muted, #888);
    border-bottom: 1px solid var(--border-color, #333);
}

.positions-table td {
    padding: 8px;
    border-bottom: 1px solid var(--border-color, #222);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
}

.positions-table .pnl-positive { color: var(--success, #4ade80); }
.positions-table .pnl-negative { color: var(--danger, #f87171); }

.positions-count {
    background: var(--bg-secondary, #333);
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.75rem;
}
```

### JavaScript

```javascript
// ==================== OPEN POSITIONS ====================

async function loadOpenPositions() {
    try {
        const res = await fetch(`${API_BASE}/api/portfolio/positions`);
        if (!res.ok) return;
        const positions = await res.json();

        const tbody = document.getElementById('positions-tbody');
        const countEl = document.getElementById('positions-count');
        if (!tbody) return;

        countEl.textContent = positions.length;

        if (positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888;">No open positions</td></tr>';
            return;
        }

        let html = '';
        for (const pos of positions) {
            let desc = '';
            if (pos.position_type === 'option_spread') {
                desc = `${pos.option_type || ''} ${pos.strike}/${pos.short_strike} ${pos.spread_type || ''}`;
                if (pos.expiry) desc += ` ${formatExpiry(pos.expiry)}`;
            } else if (pos.position_type === 'option_single') {
                desc = `${pos.option_type || ''} ${pos.strike}`;
                if (pos.expiry) desc += ` ${formatExpiry(pos.expiry)}`;
            } else if (pos.position_type === 'short_stock') {
                desc = 'Short';
            } else {
                desc = 'Stock';
            }

            const cost = pos.cost_basis != null ? `$${parseFloat(pos.cost_basis).toFixed(2)}` : '—';
            const value = pos.current_value != null ? `$${parseFloat(pos.current_value).toFixed(2)}` : '—';

            let pnlHtml = '—';
            if (pos.unrealized_pnl != null) {
                const pnl = parseFloat(pos.unrealized_pnl);
                const pnlPct = pos.unrealized_pnl_pct != null ? ` (${parseFloat(pos.unrealized_pnl_pct).toFixed(1)}%)` : '';
                const cls = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
                const sign = pnl >= 0 ? '+' : '';
                pnlHtml = `<span class="${cls}">${sign}$${pnl.toFixed(2)}${pnlPct}</span>`;
            }

            html += `<tr>
                <td><strong>${pos.ticker}</strong></td>
                <td>${desc}</td>
                <td>${pos.quantity}</td>
                <td>${cost}</td>
                <td>${value}</td>
                <td>${pnlHtml}</td>
            </tr>`;
        }

        tbody.innerHTML = html;
    } catch (err) {
        console.error('Failed to load positions:', err);
    }
}

function formatExpiry(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T00:00:00');
    return `${d.getMonth()+1}/${d.getDate()}`;
}

setInterval(loadOpenPositions, 60000);
```

Call `loadOpenPositions()` alongside `loadPortfolioBalances()` in dashboard init.

---

## Style Notes

- Match existing dark theme — reuse existing `.card` styles and CSS custom properties
- Balance card should be compact, not dominant
- Mobile: cards stack vertically, positions table scrolls horizontally

## Verification

1. Visit `https://pandoras-box-production.up.railway.app/app`
2. Balance card shows 4 accounts with Robinhood highlighted
3. Total shows ~$22,971.50
4. Positions table shows "No open positions" (until first screenshot sync)
5. Both poll every 60s without console errors

## Commit

```
feat: add portfolio balance card and positions table to dashboard (brief 07-E)
```

## Definition of Done

- [ ] Balance card visible on dashboard with all 4 accounts
- [ ] RH row shows cash/buying power sub-line
- [ ] Total row at bottom
- [ ] "Updated X ago" timestamp
- [ ] Positions table renders (empty state and with data)
- [ ] P&L colored green/red
- [ ] Both components poll every 60s
- [ ] Mobile responsive (stacks, table scrolls)
- [ ] No console errors
