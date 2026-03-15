# Brief 4B — Abacus Frontend Rebuild (Cockpit + Laboratory)

**Target:** Claude Code (VSCode)
**Phase:** 4 (Knowledge Base Cleanup / Abacus Rebuild)
**Depends on:** Brief 4A items 1, 3, 4 must be deployed first
**Estimated scope:** Replace `frontend/analytics.js` (112KB) with `frontend/cockpit.js` + `frontend/laboratory.js`

---

## Context

The current Abacus UI has 4 tabs (Strategos, Chronicle, Symposium, Footprint) with ~3,000 lines of vanilla JS in a single IIFE. The information hierarchy is inverted — abstract strategy grades and Oracle narratives appear first, while the P&L chart and actionable metrics are buried in secondary tabs. Nick is a trader, not a data analyst. He needs a trading cockpit, not a data warehouse.

**Current tab structure (being replaced):**
- Strategos: Health cards, Oracle narrative, strategy scorecards, risk budget, alerts
- Chronicle: Trade journal, equity chart, key metrics
- Symposium: Signal explorer, factor lab, backtest
- Footprint: Footprint correlation forward test

**New tab structure:**
- **Cockpit** — Everything Nick needs daily, zero scrolling for essentials
- **Laboratory** — Deep-dive tools for investigation sessions

---

## File Structure

**Delete:** `frontend/analytics.js` (after new files are confirmed working)

**Create:**
- `frontend/cockpit.js` — Cockpit tab (daily view)
- `frontend/laboratory.js` — Laboratory tab (investigation tools)

**Modify:**
- `frontend/index.html` — Replace single analytics.js script tag with cockpit.js + laboratory.js. Replace 4-tab navigation with 2-tab navigation (Cockpit | Laboratory).
- `frontend/styles.css` (or wherever analytics CSS lives) — New layout classes for Cockpit grid

**Keep unchanged:**
- `frontend/app.js` — Main dashboard (Hub mode) is untouched
- Aegis bar (persistent header) — Keep as-is, it already works
- All API endpoints — Only consuming new response fields added in Brief 4A

---

## Cockpit Tab — `frontend/cockpit.js`

This is what Nick sees every time he opens the analytics view. The entire essential view must fit in a single viewport on a standard monitor (1920x1080) without scrolling.

### Layout (top to bottom):

```
┌─────────────────────────────────────────────────────────────────────────┐
│ AEGIS BAR (already exists — persistent header across both tabs)        │
│ [P&L total] [Equity/Crypto split] [Win Rate] [Streak] [Grade]         │
├─────────────────────────────────────────────────────────────────────────┤
│ ACTIVE TEST BANNER (only if a forward test is running)                 │
│ "⚡ Footprint Correlation test: 13 days remaining — 4W/2L so far"     │
├──────────────────────────────────────┬──────────────────────────────────┤
│                                      │                                  │
│  HERO METRICS                        │  QUICK STATS                     │
│                                      │                                  │
│  ┌─────────────┐ ┌─────────────┐     │  Win Rate: 55% (61W / 50L)       │
│  │  REALIZED    │ │ UNREALIZED  │     │  Avg Win: +$88 vs Avg Loss: -$65│
│  │  +$2,129     │ │   +$340     │     │  Expectancy: +$19/trade          │
│  │  (big green) │ │ (smaller)   │     │  Profit Factor: 1.65             │
│  └─────────────┘ └─────────────┘     │  Sharpe: 1.70                    │
│                                      │  Max Drawdown: -$794 (-35.8%)    │
│  Current Streak: W3 🔥              │  Best: +$841 / Worst: -$271      │
│                                      │                                  │
├──────────────────────────────────────┴──────────────────────────────────┤
│                                                                         │
│  P&L CHART (takes up ~50% of remaining viewport)                       │
│  [Daily] [Weekly] [Monthly] [All-Time] toggle buttons                  │
│                                                                         │
│  ████████████████████████████████████████████████████████████           │
│  ██ Equity curve with drawdown shading ██████████████████████           │
│  ██ Withdrawal annotations as vertical dotted lines █████████           │
│  ██ SPY B&H benchmark as faint dotted line (optional) ███████           │
│  ████████████████████████████████████████████████████████████           │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  STRATEGY SCORECARDS (horizontal row of cards)                          │
│                                                                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ Hub Sniper   │ │ Scout Sniper │ │ Holy Grail   │ │ CSV Import   │   │
│  │ 15W / 8L     │ │ 8W / 12L     │ │ 5W / 2L      │ │ 33W / 22L    │   │
│  │ +$420        │ │ -$180        │ │ +$310        │ │ +$1,580      │   │
│  │              │ │              │ │              │ │              │   │
│  │ Score 70-80: │ │ Score 70-80: │ │ Score 70-80: │ │ (no score    │   │
│  │  62% win     │ │  45% win     │ │  80% win     │ │  data)       │   │
│  │ Score 80+:   │ │ Score 80+:   │ │ Score 80+:   │ │              │   │
│  │  78% win     │ │  60% win     │ │  100% win    │ │              │   │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
│                                                                         │
│  BIAS SYSTEM HEALTH (small card, bottom right)                          │
│  Current: URSA_MINOR (-0.23) | Accuracy: collecting data (3 days)      │
│  Gatekeeper: blocked 45 signals, 70% correctly filtered                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Cockpit Data Sources (all existing endpoints + Brief 4A additions):

| Section | Endpoint | Fields Used |
|---------|----------|-------------|
| Hero Metrics | `/api/analytics/trade-stats?days=365` | `pnl.realized_dollars`, `pnl.unrealized_dollars`, `win_rate`, `pnl.avg_win_dollars`, `pnl.avg_loss_dollars`, `pnl.expectancy_per_trade`, `risk_metrics.*` |
| P&L Chart | `/api/analytics/trade-stats?days=X` | `equity_curve` array + `benchmarks` |
| Withdrawals | `/api/analytics/cash-flows` | Annotations on chart |
| Strategy Scorecards | `/api/analytics/trade-stats?days=90` | `by_signal_source` (see note below) |
| Score-Band Accuracy | `/api/analytics/signal-stats?source=X` | `accuracy_by_score_band` (from Brief 4A item 3) |
| Bias Health | `/api/analytics/bias-accuracy` | `directional_accuracy.overall`, `gatekeeper.*` (from Brief 4A item 6) |
| Active Tests | Hardcoded or config | Footprint test ends Mar 28, 2026 |
| Streak | `/api/analytics/oracle?days=30` | `system_health.current_streak` |

**Note on Strategy Scorecards:** The current trade-stats endpoint has `by_structure` (put_spread, call_spread, etc.) and `by_account` but NOT `by_signal_source`. Brief 4A's proximity attribution will populate `signal_source` on trades. The trade-stats query needs a new `by_signal_source` breakdown added:

```python
# Add to trade-stats computation (similar to existing by_structure pattern):
by_signal_source = {}
for trade in closed_trades:
    src = trade.signal_source or 'unattributed'
    if src not in by_signal_source:
        by_signal_source[src] = {'trades': 0, 'wins': 0, 'pnl': 0}
    by_signal_source[src]['trades'] += 1
    if trade.pnl_dollars and trade.pnl_dollars > 0:
        by_signal_source[src]['wins'] += 1
    by_signal_source[src]['pnl'] += trade.pnl_dollars or 0
# Compute win_rate for each source
for src in by_signal_source:
    s = by_signal_source[src]
    s['win_rate'] = s['wins'] / s['trades'] if s['trades'] > 0 else 0
```

### P&L Chart Toggle Logic:

The equity_curve from trade-stats returns one point per trade close. For daily/weekly/monthly views:

- **All-Time:** Use raw equity_curve as-is. Call with `days=9999`.
- **Daily:** Call with `days=1`. Show intraday if multiple trades closed today, otherwise show last N days.
- **Weekly:** Call with `days=7`.
- **Monthly:** Call with `days=30`.

The toggle buttons should re-fetch with the appropriate `days` parameter. Keep it simple — no client-side aggregation.

### Withdrawal Annotations on Chart:

Fetch `/api/analytics/cash-flows` once on Cockpit load. For each cash flow with `flow_type = 'withdrawal'`, add a vertical dotted line on the chart at that date with a small label showing the amount. Use Chart.js annotation plugin or a simple vertical line dataset.

### Active Test Banner:

Hardcode for now (configurable later):

```javascript
function renderActiveTestBanner() {
    const banner = byId('activeTestBanner');
    if (!banner) return;
    
    // Active forward tests (hardcoded; move to config/DB later)
    const tests = [
        { name: 'Footprint Correlation', end_date: '2026-03-28', tab: 'footprint' }
    ];
    
    const now = new Date();
    const active = tests.filter(t => new Date(t.end_date) > now);
    
    if (!active.length) {
        banner.hidden = true;
        return;
    }
    
    const t = active[0];
    const daysLeft = Math.ceil((new Date(t.end_date) - now) / 86400000);
    banner.hidden = false;
    banner.innerHTML = `⚡ <strong>${t.name}</strong> test: ${daysLeft} days remaining`;
    banner.onclick = () => setActiveTab('laboratory');
}
```

---

## Laboratory Tab — `frontend/laboratory.js`

This is the deep-dive investigation view. It has sub-tabs for the existing tools, relocated from Strategos/Chronicle/Symposium/Footprint.

### Sub-tabs:

1. **Journal** — Trade journal with all existing filters, detail panel, CSV import, trade logging (moved from Chronicle)
2. **Signals** — Signal explorer with all existing filters, stats panel, MFE/MAE charts (moved from Symposium)
3. **Factors** — Factor lab with timeline chart, correlation matrix, factor stats (moved from Symposium)
4. **Backtest** — Backtest runner with compare mode (moved from Symposium)
5. **Footprint** — Footprint correlation forward test (moved from its own tab)
6. **Oracle** — Oracle narrative + Prometheus (override review) + Cassandra (counterfactuals) (moved from Strategos)

### Implementation:

Copy the existing rendering functions from analytics.js into laboratory.js. The function signatures and API calls stay identical — we're just relocating code into a separate file and wiring it to sub-tab navigation within the Laboratory tab.

**Sub-tab navigation pattern:**

```javascript
const LAB_TABS = ['journal', 'signals', 'factors', 'backtest', 'footprint', 'oracle'];

function setLabSubTab(tabName) {
    const tab = LAB_TABS.includes(tabName) ? tabName : 'journal';
    state.labActiveSubTab = tab;
    
    // Toggle sub-tab buttons
    document.querySelectorAll('.lab-subtab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.labTab === tab);
    });
    
    // Toggle sub-tab panes
    LAB_TABS.forEach(name => {
        const pane = byId(`labPane_${name}`);
        if (pane) {
            pane.hidden = name !== tab;
        }
    });
    
    // Load data for active sub-tab
    if (tab === 'journal') loadTradeJournal();
    if (tab === 'signals') loadSignalExplorer();
    if (tab === 'factors') loadFactorLab();
    if (tab === 'footprint') loadFootprintCorrelation();
    if (tab === 'oracle') loadOracleNarrative();
}
```

---

## HTML Changes — `frontend/index.html`

### Replace tab navigation:

Find the existing analytics sub-tab buttons (Strategos, Chronicle, Symposium, Footprint). Replace with:

```html
<div class="analytics-tabs" id="analyticsTabBar">
    <button class="analytics-subtab active" data-analytics-tab="cockpit" aria-selected="true">Cockpit</button>
    <button class="analytics-subtab" data-analytics-tab="laboratory" aria-selected="false">Laboratory</button>
</div>
```

### Replace tab panes:

Remove the 4 existing pane divs (analyticsPaneStrategos, analyticsPaneChronicle, analyticsPaneSymposium, analyticsPaneFootprint). Replace with 2 new pane containers.

**Cockpit pane:** New HTML structure matching the layout diagram above. Include:
- `id="activeTestBanner"` — hidden by default
- `id="cockpitHeroMetrics"` — grid container for realized P&L, unrealized P&L, streak
- `id="cockpitQuickStats"` — list of metric rows
- `id="cockpitPnlToggle"` — button group (Daily/Weekly/Monthly/All-Time)
- `id="cockpitPnlChart"` — canvas for Chart.js
- `id="cockpitStrategyScorecards"` — flex container for strategy cards
- `id="cockpitBiasHealth"` — small card for bias accuracy

**Laboratory pane:** Container with sub-tab navigation and 6 sub-panes. The sub-pane contents can be copied from the existing HTML (same filter dropdowns, same tables, same chart canvases — just relocated under new parent divs).

### Replace script tags:

Find:
```html
<script src="analytics.js?v=XX"></script>
```

Replace with:
```html
<script src="cockpit.js?v=1"></script>
<script src="laboratory.js?v=1"></script>
```

---

## Shared Utilities

Both cockpit.js and laboratory.js need the same utility functions (escapeHtml, formatDollar, formatPercent, asNumber, fetchJson, etc.). Two options:

**Option A (preferred for simplicity):** Put shared utilities at the top of cockpit.js and reference them from laboratory.js via a shared namespace:

```javascript
// cockpit.js — exposes shared utils on window.analyticsUtils
window.analyticsUtils = { escapeHtml, formatDollar, formatPercent, formatRatio, formatDate, formatDateTime, asNumber, safeArray, fetchJson, upsertChart, byId, slugToLabel, metricClass };
```

```javascript
// laboratory.js — imports from shared namespace
const { escapeHtml, formatDollar, ... } = window.analyticsUtils;
```

**Option B:** Create a third file `analytics-utils.js` loaded before both. Only do this if Option A gets messy.

---

## Styling Notes

### Hero Metrics:
- Realized P&L: Large font (2.5rem+), bold, green if positive / red if negative
- Unrealized P&L: Medium font (1.2rem), lighter weight, same color logic
- Streak: Icon + count. W3+ gets a 🔥, L3+ gets a ❄️ (or color change)

### Strategy Scorecards:
- Card border: green-left if net profitable, red-left if net loss
- Score-band breakdown: small text inside card, use green/yellow/red color for win rates
- Cards should be fixed-width, horizontally scrollable if more than 4

### P&L Chart:
- Height: at least 300px (preferably 40vh)
- Withdrawal annotations: vertical dashed lines in light gray with small labels
- Daily/Weekly/Monthly/All-Time: pill-style toggle buttons, active state = filled

### Active Test Banner:
- Full-width, subtle background (e.g. dark blue-gray), small text
- Clickable — navigates to Footprint sub-tab in Laboratory
- Hidden when no active tests

### General:
- Keep the existing dark teal theme and color palette
- Use the existing CSS class patterns from analytics.js (analytics-health-card, analytics-metric-item, etc.)
- Responsive is nice-to-have but not required — primary target is a desktop monitor

---

## Migration Checklist

1. Create `cockpit.js` with hero metrics, P&L chart, strategy scorecards, bias health, active test banner
2. Create `laboratory.js` with sub-tab navigation + all relocated features
3. Update `index.html` with new tab structure, pane containers, and script tags
4. Test Cockpit loads and renders with real data
5. Test Laboratory sub-tabs all load correctly (journal, signals, factors, backtest, footprint, oracle)
6. Verify Aegis bar still works across both tabs
7. Verify Hub mode (non-analytics) still works — app.js untouched
8. Delete `analytics.js` only after everything is confirmed working
9. Increment cache busting versions on cockpit.js and laboratory.js

## Deploy

```bash
git push origin main
# Verify:
curl https://pandoras-box-production.up.railway.app/health
# Open browser, switch to Analytics mode, verify Cockpit renders
# Switch to Laboratory, verify each sub-tab loads
```
