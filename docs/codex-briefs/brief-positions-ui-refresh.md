# Brief: Positions UI — Auto-Refresh Prices + Type Grouping

**Priority:** HIGH — Nick uses this daily. Current prices show null until the 15-min MTM background loop runs.
**Target:** Frontend (`frontend/app.js`) + minor backend
**Estimated time:** 45–60 minutes

---

## Context

The Open Positions section currently has two problems:
1. **No on-demand price refresh** — Prices only update via the 60-second `updateCurrentPrices()` polling loop (which calls `hybrid/price/{ticker}` per-ticker) or the 15-minute backend mark-to-market loop. When Nick logs a new position, it shows null current price until the next cycle.
2. **No visual grouping** — All positions are sorted by DTE regardless of type. Nick wants to see Options (Long), Options (Short), and Stocks separated with subtle dividers.

## Feature 1: Trigger price refresh on position changes

### 1a: After creating a new position

In `app.js`, find every place where a new position is successfully created (look for `POSITION_OPENED` broadcasts or success handlers after `POST /v2/positions`). After the position list is refreshed, immediately trigger a price update:

```javascript
// After successful position creation:
await loadOpenPositionsEnhanced();  // refreshes position list
await updateCurrentPrices();         // immediately fetch current prices
```

### 1b: After closing a position

Same pattern — after a successful close, refresh prices on remaining positions:

```javascript
// After successful position close:
await loadOpenPositionsEnhanced();
await updateCurrentPrices();
```

### 1c: Manual refresh button

There should be a "Refresh" button in the positions section header. Find the positions section header in the HTML (in `index.html` or generated in `app.js`). If a refresh button already exists, wire it to:

```javascript
async function refreshPositions() {
    // Show brief loading indicator
    const refreshBtn = document.querySelector('.positions-refresh-btn');
    if (refreshBtn) {
        refreshBtn.classList.add('refreshing');
        refreshBtn.disabled = true;
    }
    
    try {
        await loadOpenPositionsEnhanced();  // refresh position data
        await triggerMarkToMarket();         // trigger backend MTM
        await updateCurrentPrices();         // fetch latest prices from hybrid scanner
    } finally {
        if (refreshBtn) {
            refreshBtn.classList.remove('refreshing');
            refreshBtn.disabled = false;
        }
    }
}

async function triggerMarkToMarket() {
    try {
        await fetch(`${API_URL}/v2/positions/mark-to-market`, {
            method: 'POST',
            headers: authHeaders()
        });
    } catch (e) {
        console.warn('MTM trigger failed:', e);
    }
}
```

If no refresh button exists, add one next to the positions section title. Style it as a subtle circular arrow icon.

Attach the click handler:
```javascript
document.querySelector('.positions-refresh-btn')?.addEventListener('click', refreshPositions);
```

### 1d: After-hours price handling

The `updateCurrentPrices()` function already calls `hybrid/price/{ticker}` which uses yfinance. After market hours, yfinance returns the closing price — so this already works for the "use closing price after hours" requirement.

However, the backend mark-to-market (`run_mark_to_market()`) skips outside market hours. When the manual refresh button triggers `triggerMarkToMarket()`, it should work regardless of market hours.

In `backend/api/unified_positions.py`, find `run_mark_to_market()`. The background loop in `main.py` already gates on market hours, but the HTTP endpoint wrapper should NOT gate — it's an on-demand request:

```python
@router.post("/v2/positions/mark-to-market")
async def mark_to_market(_=Depends(require_api_key)):
    """HTTP wrapper for mark-to-market. Always runs (no market-hours gate)."""
    return await run_mark_to_market()
```

Verify that `run_mark_to_market()` itself does NOT have market-hours gating inside the function body — only the background loop in `main.py` should gate. If `run_mark_to_market()` has internal hour checks, remove them so the manual trigger works after hours.

**For options after hours:** Polygon won't return live option quotes after 4 PM ET. The yfinance fallback only works for equity/stock positions. For options positions after hours, current_price will stay at the last known value from market hours. This is acceptable — options don't have real after-hours prices anyway. The `price_updated_at` timestamp tells Nick how fresh the data is.

## Feature 2: Group positions by type with dividers

Modify `renderPositionsEnhanced()` to group positions into three categories before rendering:

```javascript
function renderPositionsEnhanced() {
    const container = document.getElementById('openPositions');
    if (!container) return;

    // Filter by active account tab
    const filteredPositions = activePositionsAccount === 'ALL'
        ? openPositions
        : openPositions.filter(p =>
            (p.account || 'ROBINHOOD').toUpperCase() === activePositionsAccount
        );

    if (!filteredPositions || filteredPositions.length === 0) {
        container.innerHTML = '<p class="empty-state">No open positions</p>';
        return;
    }

    // Categorize positions
    const optionsLong = [];
    const optionsShort = [];
    const stocks = [];

    for (const pos of filteredPositions) {
        const struct = (pos.structure || '').toLowerCase();
        const isStock = struct === 'stock' || struct === 'stock_long' || struct === 'long_stock' ||
                        struct === 'stock_short' || struct === 'short_stock' ||
                        (!struct && (pos.asset_type || '').toUpperCase() === 'EQUITY');

        if (isStock) {
            stocks.push(pos);
        } else {
            // Options — determine long vs short based on direction and structure
            const dir = (pos.direction || '').toUpperCase();
            const isShortDir = dir === 'SHORT' || dir === 'BEARISH';
            const isCreditSpread = struct.includes('credit') || struct.includes('short_call') ||
                                   struct.includes('short_put') || struct.includes('naked');
            
            // Put debit spreads are bearish (SHORT direction) but you paid for them (LONG options)
            // Credit spreads are SHORT options
            if (isCreditSpread) {
                optionsShort.push(pos);
            } else {
                optionsLong.push(pos);  // Debit spreads, long calls/puts
            }
        }
    }

    // Sort each group by DTE (soonest first), then ticker
    const sortByDte = (a, b) => {
        const dteA = a.dte ?? 9999;
        const dteB = b.dte ?? 9999;
        if (dteA !== dteB) return dteA - dteB;
        return (a.ticker || '').localeCompare(b.ticker || '');
    };

    optionsLong.sort(sortByDte);
    optionsShort.sort(sortByDte);
    stocks.sort((a, b) => (a.ticker || '').localeCompare(b.ticker || ''));

    // Render with section dividers
    let html = '';

    if (optionsLong.length > 0) {
        html += '<div class="position-group-divider">Options (Long)</div>';
        html += optionsLong.map(pos => renderPositionCard(pos)).join('');
    }

    if (optionsShort.length > 0) {
        html += '<div class="position-group-divider">Options (Short)</div>';
        html += optionsShort.map(pos => renderPositionCard(pos)).join('');
    }

    if (stocks.length > 0) {
        html += '<div class="position-group-divider">Stocks</div>';
        html += stocks.map(pos => renderPositionCard(pos)).join('');
    }

    container.innerHTML = html;

    // Re-attach event listeners (same as current code)
    // ... keep existing event attachment code ...
}
```

Extract the existing card HTML template from the current `sorted.map(pos => { ... })` into a separate function:

```javascript
function renderPositionCard(pos) {
    // ... move the existing per-card template here, return the HTML string ...
}
```

This is a pure refactor — move the card rendering into its own function, then call it from the grouped sections.

### Divider styling

Add to `frontend/styles.css`:

```css
.position-group-divider {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-secondary, #8b9dc3);
    padding: 0.5rem 0.75rem 0.25rem;
    margin-top: 0.5rem;
    border-top: 1px solid var(--border-color, rgba(255,255,255,0.06));
}

.position-group-divider:first-child {
    margin-top: 0;
    border-top: none;
}
```

Keep it subtle — thin line + small uppercase label. Should feel like a natural grouping, not a loud separator.

---

## Definition of Done

1. Creating a new position triggers immediate price refresh on all positions
2. Closing a position triggers immediate price refresh on remaining positions
3. Refresh button (or existing refresh control) triggers `loadOpenPositionsEnhanced()` + `triggerMarkToMarket()` + `updateCurrentPrices()`
4. Mark-to-market HTTP endpoint works after hours (no market-hours gate on the endpoint itself)
5. Positions grouped into Options (Long), Options (Short), Stocks with subtle dividers
6. Each group sorted by DTE (soonest first), stocks sorted alphabetically
7. Empty groups don't show dividers
8. All existing position card functionality preserved (edit, close, remove buttons, P&L display, mark prices, counter-signals)

---

## Verification

1. Open dashboard → positions section should show grouped with dividers
2. Add a test position → prices should refresh immediately, new position shows current price
3. Close a position → remaining positions re-render with fresh prices
4. Click refresh → brief loading state, prices update
5. After market hours → refresh button should still work, showing closing prices for stocks, last known prices for options
6. Check with Nick's current positions: XLE (Options Long), IGV (Options Long — put debit spread, bearish but debit), XLF (Options Long — same), TSLQ (Stocks)

**Note on categorization:** Nick's current positions are all debit spreads (you pay premium = long options) and one stock. The "Options (Short)" group would appear when he has credit spreads, covered calls, cash-secured puts, etc.
