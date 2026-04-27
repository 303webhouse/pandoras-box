# CC Brief — P1 Freshness Indicators

**Date:** 2026-04-27
**Author:** Opus + Titans audit (via Nick)
**Status:** P1 — highest leverage from Titans audit
**Scope:** frontend-only — `frontend/app.js` + `frontend/styles.css`. No backend changes.

---

## Background — why this brief exists

Today's incident: production MTM was broken from Friday morning through Monday 9:30 AM. It went unnoticed for ~75 trading hours because **no Agora panel surfaces the freshness of the data it displays.** Nick had to wait for a noticeable trading-day failure to detect a feed that had silently frozen days earlier.

The Titans audit (run today) made this its #1 finding (HELIOS H1). Quote from the audit: *"This is the single highest-leverage fix in this audit. Costs nothing in UW budget. Universal value across all panels. Would have prevented today's incident."*

Backend already provides timestamp fields (`price_updated_at`, `timestamp`, `last_updated`, etc.) on most data-bearing endpoints. The frontend currently ignores them.

This brief adds a small, **subtle** "as of HH:MM:SS" indicator to every Agora panel that displays market data, color-coded by staleness.

---

## Design specification

### Visual treatment — SUBTLE (Nick's choice over always-on)

- Small text in lower-right corner of each panel
- Format: `as of 2:34:17 PM`
- Color states:
  - **Default (≤ 60s old):** muted gray (`#888` or panel's existing muted text color)
  - **Amber (60s < age ≤ 5 min):** `#f59e0b` (Tailwind amber-500)
  - **Red (> 5 min):** `#ef4444` (Tailwind red-500)
- Font size: ~10-11px (smaller than panel body text)
- Position: absolute, bottom-right of panel, with ~6px padding
- No leading dot, no icon — just the text

### Behavior

- Indicator updates every 1 second (recompute age relative to current time)
- If timestamp is more than 24 hours old: display `as of 2026-04-25 14:30` (date + time, full format) instead of just time
- If timestamp is `null`/missing: display `no timestamp` in red
- Tooltip on hover: full ISO timestamp (e.g., `2026-04-27T20:15:23Z`)

---

## File 1: `frontend/styles.css` — add the staleness indicator class

### Edit 1.1 — Append CSS block at the end of `styles.css`

**FIND** the last line of the file (whatever it currently is — likely a closing `}` or final rule).

**APPEND AFTER IT:**
```css
/* === Staleness indicators (P1) === */
.staleness-indicator {
  position: absolute;
  bottom: 6px;
  right: 8px;
  font-size: 10px;
  line-height: 1;
  color: #888;
  font-family: monospace;
  letter-spacing: 0.02em;
  pointer-events: auto;
  cursor: help;
  z-index: 1;
  user-select: none;
}

.staleness-indicator.stale-amber {
  color: #f59e0b;
}

.staleness-indicator.stale-red {
  color: #ef4444;
  font-weight: 500;
}

/* Ensure parent panels have position relative so absolute positioning works */
.panel,
.card,
.widget,
[data-staleness-target] {
  position: relative;
}
```

*(CC: if the existing CSS already uses different class names like `.panel-card`, `.section-card`, or similar, add those to the parent rule list. Goal is that any container holding a staleness indicator becomes a positioning context.)*

---

## File 2: `frontend/app.js` — add the helper functions

### Edit 2.1 — Add at the top of `app.js` (after existing global declarations, before any render functions)

CC: search for an early section in `app.js` like `// === Helpers ===` or the first major comment block. Insert the following after existing helpers, before any render functions:

```javascript
// === Staleness Indicators (P1) ===
// Single source of truth for displaying data freshness across all Agora panels.

/**
 * Format a timestamp into a staleness display string + color class.
 * @param {string|number|Date|null|undefined} timestamp - ISO string, epoch ms, or Date
 * @returns {{text: string, className: string, fullTimestamp: string|null, ageSeconds: number|null}}
 */
function computeStaleness(timestamp) {
  if (timestamp === null || timestamp === undefined || timestamp === '') {
    return {
      text: 'no timestamp',
      className: 'staleness-indicator stale-red',
      fullTimestamp: null,
      ageSeconds: null,
    };
  }

  let date;
  try {
    date = (timestamp instanceof Date) ? timestamp : new Date(timestamp);
    if (isNaN(date.getTime())) throw new Error('invalid date');
  } catch {
    return {
      text: 'invalid timestamp',
      className: 'staleness-indicator stale-red',
      fullTimestamp: String(timestamp),
      ageSeconds: null,
    };
  }

  const ageMs = Date.now() - date.getTime();
  const ageSeconds = Math.floor(ageMs / 1000);
  const fullTimestamp = date.toISOString();

  // > 24 hours: show date + time
  let text;
  if (ageSeconds > 86400) {
    text = `as of ${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
  } else {
    text = `as of ${date.toLocaleTimeString()}`;
  }

  // Color by staleness
  let className = 'staleness-indicator';
  if (ageSeconds > 300) {
    className += ' stale-red';
  } else if (ageSeconds > 60) {
    className += ' stale-amber';
  }

  return { text, className, fullTimestamp, ageSeconds };
}

/**
 * Render or update a staleness indicator inside a target element.
 * Idempotent — calling repeatedly updates the existing indicator rather than creating duplicates.
 * @param {HTMLElement} targetEl - The container element to add the indicator to
 * @param {string|number|Date|null} timestamp - The data timestamp
 */
function renderStalenessIndicator(targetEl, timestamp) {
  if (!targetEl) return;

  const { text, className, fullTimestamp } = computeStaleness(timestamp);

  let indicator = targetEl.querySelector(':scope > .staleness-indicator');
  if (!indicator) {
    indicator = document.createElement('span');
    targetEl.appendChild(indicator);
  }
  indicator.className = className;
  indicator.textContent = text;
  if (fullTimestamp) {
    indicator.title = fullTimestamp;
  } else {
    indicator.removeAttribute('title');
  }
}

/**
 * Refresh all staleness indicators on the page. Called on a 1s timer to keep
 * age calculations current without re-fetching data.
 */
function refreshAllStalenessIndicators() {
  const indicators = document.querySelectorAll('.staleness-indicator');
  indicators.forEach(indicator => {
    const fullTs = indicator.getAttribute('title');
    if (!fullTs) return;
    const { text, className } = computeStaleness(fullTs);
    indicator.className = className;
    indicator.textContent = text;
  });
}

// Start the global staleness refresh timer once the DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    setInterval(refreshAllStalenessIndicators, 1000);
  });
} else {
  setInterval(refreshAllStalenessIndicators, 1000);
}
```

---

## Edit 2.2 — Wire up indicators in each panel's render function

For each panel in the **target list** below, find the render function (CC: search for the function that builds the panel's DOM, typically named like `renderXxx()`, `updateXxx()`, or similar). After the render function builds the panel content, call `renderStalenessIndicator()` with the panel's container element and its data timestamp.

### Pattern (apply to each target)

```javascript
// At the end of the render function, before the function returns:
const containerEl = document.getElementById('panel-container-id'); // or whatever selector accesses the panel root
const timestamp = data.timestamp || data.last_updated || data.price_updated_at; // pick whichever field the API returns
renderStalenessIndicator(containerEl, timestamp);
```

---

## Target list — panels that need indicators

CC: for each target below, locate the render function and apply the pattern from Edit 2.2. If a panel doesn't currently have a clearly-identifiable container element, **add a stable id or `data-staleness-target` attribute** to its root element first.

| # | Panel | Likely render function | API endpoint (timestamp source) |
|---|---|---|---|
| 1 | **Open Positions** | `renderPositions` / `updatePositionsPanel` / `renderUnifiedPositions` | `/api/v2/positions` → `positions[i].price_updated_at` (use min/max — show oldest position's timestamp at panel level) |
| 2 | **Sector Heatmap** | `renderSectorHeatmap` / `updateSectorPanel` | `/api/sectors/heatmap` → `last_updated` (top level) |
| 3 | **Sector drill-down popup** (constituents) | wherever the modal/popup is built | `/api/watchlist/sector-strength` or constituent endpoint → response timestamp |
| 4 | **Bias factors panel** (composite + timeframes) | `renderBias` / `renderCompositeBias` / `updateBiasPanel` | `/api/bias/composite/timeframes` → `timestamp` |
| 5 | **Watchlist** | `renderWatchlist` / `updateWatchlist` | `/api/watchlist/main` or similar → response timestamp |
| 6 | **Flow Radar** | `renderFlowRadar` | `/api/flow/radar` → response timestamp |
| 7 | **Hermes alerts** (catalysts) | `renderHermesAlerts` | `/api/hermes/alerts` → response timestamp |
| 8 | **Hydra scores** (squeeze setups) | `renderHydra` | `/api/hydra/scores` → response timestamp |
| 9 | **Macro strip** (top of page) | `renderMacroStrip` | `/api/macro-strip` → response timestamp |
| 10 | **Trade Ideas list** | `renderTradeIdeas` | `/api/trade-ideas` → response or per-idea timestamp |
| 11 | **Greeks display** (in Open Positions) | wherever greeks are rendered | `/api/v2/positions/greeks` → response timestamp |
| 12 | **Catalyst calendar** | `renderCatalystCalendar` / `renderChronos` | `/api/catalyst-calendar` or `/api/chronos` → response timestamp |

**Skip these panels** (not market-data-bearing):
- Static layout containers (header, nav, footer)
- Configuration/settings panels
- Knowledgebase reader
- Modals that open instantly with already-loaded data

---

## Verification

After deploy:

1. **Visual check** — open Agora in browser. For each panel in the target list, confirm a small "as of HH:MM:SS" appears in the lower-right corner.

2. **Color states** — manually verify by:
   - Loading a fresh page → all indicators should be **gray** (default, < 60s old)
   - Wait 65 seconds without refreshing → indicators should turn **amber**
   - Wait 5+ minutes → indicators should turn **red**

3. **Tooltip** — hover over an indicator. Browser tooltip should show full ISO timestamp.

4. **Edge cases**:
   - If a panel has missing data, indicator should show `no timestamp` in red
   - If a panel timestamp is from yesterday, indicator should show `as of M/D/YYYY HH:MM:SS PM` (date + time)

5. **No console errors** — open browser dev tools Console tab. Should be no `ReferenceError` or `TypeError` related to staleness functions.

6. **No layout breakage** — confirm all panels still render correctly. Indicators should overlay panel content in lower-right without pushing content around or breaking flexbox/grid layouts.

7. **Performance** — confirm 1s refresh timer doesn't cause noticeable CPU/memory pressure. (Should be negligible — `querySelectorAll` + DOM updates on ~12 small elements.)

---

## Rollback plan

If anything looks wrong:
```bash
cd C:\trading-hub
git revert HEAD
git push origin main
```

This brief is purely additive (new CSS class, new JS functions, new render-function calls). Rollback restores the pre-P1 state — no data integrity concerns.

---

## Out of scope

- **Backend timestamp consistency** — some endpoints return `timestamp`, others `last_updated`, others `price_updated_at`. The brief handles this by trying multiple field names per panel. **Future cleanup** (P3 or later) could standardize backend response shapes, but that's out of scope here.

- **Per-row freshness indicators** — Open Positions could in theory show staleness per row (per position). This brief shows panel-level staleness only (oldest position's timestamp). Per-row is deferred.

- **Backend health badges** — separate from data freshness. The audit AE-flagged a future "UW API health" badge but that's a different feature.

- **Live tape widget** (HELIOS H4) — deferred to P4 per Titans prioritization.

---

## Commit message

```
feat(ui): P1 freshness indicators on all Agora data panels

Adds subtle "as of HH:MM:SS" timestamp indicator to every Agora panel that
displays market data. Color-coded by staleness:
- Gray (default) for ≤ 60s old
- Amber for 60s-5min old
- Red for > 5min old or missing timestamp

Implementation:
- New helper functions in app.js: computeStaleness, renderStalenessIndicator,
  refreshAllStalenessIndicators (1s timer)
- New CSS class .staleness-indicator with .stale-amber and .stale-red modifiers
- Integration into 12 Agora panel render functions

Surfaces data freshness universally so frozen feeds (like the MTM scheduler
that died Friday → Monday 9:30 AM and went unnoticed) become visible
immediately. Backend timestamps already exist on all relevant endpoints —
this PR is purely frontend.

Source: Titans audit 2026-04-27 finding HELIOS H1 (highest-leverage fix).
```

---

## Session checklist for CC

1. `cd C:\trading-hub && git pull origin main`
2. Read this brief in full.
3. Apply Edit 1.1 (CSS append).
4. Apply Edit 2.1 (helper functions in app.js).
5. For each target in the list (1-12), locate the render function and apply Edit 2.2 pattern. **Important:** if a panel's container doesn't have a stable id, add one before wiring the indicator — don't rely on fragile selectors like nth-child.
6. Test locally if possible (load app in browser, confirm indicators appear).
7. Run syntax check: `node -c frontend/app.js` (basic Node syntax pass) — note: this won't catch DOM-related issues but catches typos.
8. Commit with the message above.
9. `git push origin main`
10. Wait ~90s for Railway deploy.
11. Run all 7 verification checks in browser.
12. If all PASS, post: "P1 freshness indicators shipped. All Agora panels now show data age. Verified in browser: color states transition correctly, tooltips work, no console errors."
13. If any panel render function couldn't be located cleanly, report which ones and request a follow-up — do NOT skip silently.
