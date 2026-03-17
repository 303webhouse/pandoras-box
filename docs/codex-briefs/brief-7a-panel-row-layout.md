# Brief 7A: Panel Row Layout Overhaul

**Target Agent:** Claude Code (VSCode)
**Priority:** Medium
**Scope:** ONLY the `.bias-section` panel row. Do NOT touch the heatmap, TradingView chart, or anything below.

---

## What This Does

Restructures the panel row below the header from a flat 5-column grid into a 3-column layout with a stacked right column:

```
| Market Bias | Sectors/Headlines |  Intraday | Swing | Macro  |  (30%)
| (narrow,    | (wider, +20%      |  Portfolio Tracker          |  (45%)
|  +20% tall) |  tall, 3-tab box) |  Single Ticker Analyzer     |  (25%)
```

Left two columns span full row height. Right column stacks three sub-sections vertically.

---

## Current State

**HTML** (`frontend/index.html`): Inside `<section class="bias-section">`:
- `.bias-composite-panel#biasCompositePanel` — Market Bias
- `#tfIntraday` — Intraday card
- `.headlines-card#headlinesCard` — Sectors/Headlines 3-tab box
- `#tfSwing` — Swing card
- `#tfMacro` — Macro card
- `.portfolio-summary-card#portfolio-summary-card` — Portfolio tracker

The Single Ticker Analyzer (`.analyzer-panel`) is currently inside `.watchlist-right` in a completely different `<section class="watchlist-section">` further down the page.

**CSS** (`frontend/styles.css`):
```css
/* Line 222-230 */
.bias-section {
    display: grid;
    grid-template-columns: 1.3fr 1.3fr 1fr 1fr 1fr;
    grid-template-rows: auto 1fr;
    gap: 16px;
    margin-bottom: 20px;
    align-items: stretch;
}

/* Line 232-235 */
.bias-composite-panel {
    grid-column: 1;
    grid-row: 1 / 3;
}

/* Line 237-239 */
.headlines-card {
    grid-column: 2;
    grid-row: 1 / 3;
    /* ... other styles ... */
}

/* Line 250 */
#tfIntraday { grid-column: 3; grid-row: 1; }

/* Line 552-555 */
#tfSwing { grid-column: 4; grid-row: 1; }

/* Line 557-559 */
#tfMacro { grid-column: 5; grid-row: 1; }

/* Line 561+ */
.portfolio-summary-card {
    grid-column: 3 / 6;
    grid-row: 2;
    /* ... other styles ... */
}
```

---

## Step 1: Wrap Right Column in a Container (HTML)

**File:** `frontend/index.html`

The three timeframe cards and portfolio card need to be wrapped in a container div, and the Single Ticker Analyzer needs to be moved into it.

### 1A. Wrap existing right-column elements

**Find** the Intraday card (it appears after `.headlines-card` closing tag):
```html
            <!-- Timeframe Factor Group Cards (replace old Daily/Weekly/Cyclical) -->
            <div class="tf-card" id="tfIntraday" data-timeframe="intraday">
```

**Insert BEFORE it:**
```html
            <!-- Right Stack: TF cards + Portfolio + Single Ticker Analyzer -->
            <div class="bias-right-stack">
                <div class="bias-right-tf-row">
```

Then **find** the closing `</div>` of `#tfMacro` (it ends with `<div class="tf-expand-toggle" data-target="tfMacroFactors">Factors ></div>` followed by `</div>`).

**After** `#tfMacro`'s closing `</div>`, insert:
```html
                </div><!-- /.bias-right-tf-row -->
```

Then **find** the closing `</div>` of `.portfolio-summary-card` (look for `</div>` after the last `.portfolio-account` block).

**After** `.portfolio-summary-card`'s closing `</div>`, insert:
```html
            </div><!-- /.bias-right-stack -->
```

Note: the `.headlines-card` sits between `#tfIntraday` and `#tfSwing` in the HTML source order, but the grid placement puts it in column 2. After the restructure, **move `.headlines-card` before the `.bias-right-stack`** wrapper so the HTML source order matches the visual left-to-right order:

1. `.bias-composite-panel` (Market Bias)
2. `.headlines-card` (Sectors/Headlines)
3. `.bias-right-stack` containing:
   - `.bias-right-tf-row` containing `#tfIntraday`, `#tfSwing`, `#tfMacro`
   - `.portfolio-summary-card`
   - `.analyzer-panel` (moved from watchlist section)

CC: You may need to reorder the HTML elements inside `.bias-section` to achieve this. The current DOM order is: biasCompositePanel, tfIntraday, headlinesCard, tfSwing, tfMacro, portfolio-summary-card. Reorder to: biasCompositePanel, headlinesCard, bias-right-stack.

### 1B. Move Single Ticker Analyzer into the right stack

**Find** in the `.watchlist-section` (around line 356):
```html
                <div class="watchlist-right">
                    <div class="analyzer-panel">
```

**Cut** the entire `.analyzer-panel` div (from `<div class="analyzer-panel">` through its closing `</div>`) out of `.watchlist-right`.

**Paste** it inside `.bias-right-stack`, after `.portfolio-summary-card` and before the closing `</div><!-- /.bias-right-stack -->`.

Leave `.watchlist-right` as an empty div (or remove it if nothing else is inside it).

---

## Step 2: Restructure the CSS Grid

**File:** `frontend/styles.css`

### 2A. Change `.bias-section` grid

**Find:**
```css
/* Bias Section — 5-col 2-row grid */
.bias-section {
    display: grid;
    grid-template-columns: 1.3fr 1.3fr 1fr 1fr 1fr;
    grid-template-rows: auto 1fr;
    gap: 16px;
    margin-bottom: 20px;
    align-items: stretch;
}
```

**Replace with:**
```css
/* Bias Section — 3-col layout: Market Bias | Sectors/Headlines | Right Stack */
.bias-section {
    display: grid;
    grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.4fr) minmax(0, 2fr);
    grid-template-rows: 1fr;
    gap: 16px;
    margin-bottom: 20px;
    align-items: stretch;
    min-height: 420px; /* +20% from ~350px baseline */
}
```

### 2B. Update Market Bias grid placement

**Find:**
```css
.bias-composite-panel {
    grid-column: 1;
    grid-row: 1 / 3;
}
```

**Replace with:**
```css
.bias-composite-panel {
    grid-column: 1;
    grid-row: 1;
}
```

### 2C. Update Headlines grid placement

The `.headlines-card` has grid placement mixed in with other styles. **Find** just the grid lines inside `.headlines-card`:
```css
.headlines-card {
    grid-column: 2;
    grid-row: 1 / 3;
```

**Replace with:**
```css
.headlines-card {
    grid-column: 2;
    grid-row: 1;
```

### 2D. Remove old individual grid placements for TF cards

**Find and remove** (or comment out) these rules since the TF cards are now inside the flex container:
```css
#tfIntraday {
    grid-column: 3;
    grid-row: 1;
}
```

```css
#tfSwing
    grid-column: 4;
    grid-row: 1;
}
```

(Note: the `#tfSwing` rule may be missing an opening `{` — check and fix if so.)

```css
#tfMacro {
    grid-column: 5;
    grid-row: 1;
}
```

### 2E. Update Portfolio grid placement

**Find:**
```css
.portfolio-summary-card {
    grid-column: 3 / 6;
    grid-row: 2;
```

**Replace with:**
```css
.portfolio-summary-card {
    /* Grid placement removed — now inside .bias-right-stack flex container */
```

(Keep all other `.portfolio-summary-card` styles like background, border, padding, etc. Only remove `grid-column` and `grid-row`.)

### 2F. Add new right-stack styles

**Add** these new rules after the `.bias-section` block (around line 230):

```css
/* Right stack: TF cards (30%) + Portfolio (45%) + Analyzer (25%) */
.bias-right-stack {
    grid-column: 3;
    grid-row: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 0;
}

.bias-right-tf-row {
    display: flex;
    gap: 8px;
    flex: 0 0 30%; /* 30% of right stack height */
}

.bias-right-tf-row .tf-card {
    flex: 1;
    min-width: 0;
}

.bias-right-stack .portfolio-summary-card {
    flex: 0 0 45%; /* 45% of right stack height */
    grid-column: unset;
    grid-row: unset;
}

.bias-right-stack .analyzer-panel {
    flex: 0 0 25%; /* 25% of right stack height */
    overflow: auto;
}
```

---

## Step 3: Fix the Responsive Breakpoint

The responsive override at ~line 5072 sets `.bias-section` to single-column. Update the child overrides to match the new structure.

**Find** (around line 5072):
```css
    .bias-section {
        grid-template-columns: 1fr;
    }
```

Keep this, but also **find** the responsive block that resets grid placements (around line 10459):
```css
    .bias-composite-panel,
    #tfIntraday,
    #tfSwing
    #tfMacro,
    .portfolio-summary-card,
    .headlines-card {
        grid-column: 1;
        grid-row: auto;
```

**Replace with:**
```css
    .bias-composite-panel,
    .headlines-card,
    .bias-right-stack {
        grid-column: 1;
        grid-row: auto;
    }

    .bias-right-stack {
        flex-direction: column;
    }

    .bias-right-tf-row {
        flex-direction: row;
    }
```

---

## Step 4: Verify Analyzer JS Still Works

The Single Ticker Analyzer's JavaScript (in `app.js`) references elements by ID: `#analyzeTickerInput`, `#analyzeTickerBtn`, `#analyzerResultsV3`, `#addToWatchlistBtn`. Since we're moving the DOM element (not recreating it), these ID references should still work. But verify:

```
grep -n "analyzeTickerInput\|analyzeTickerBtn\|analyzerResultsV3\|addToWatchlistBtn" frontend/app.js
```

All `document.getElementById()` or `document.querySelector()` calls should still find the elements in their new location. No JS changes should be needed.

---

## What NOT to Touch

- The sector heatmap (`.sector-rotation-strip`) — stays where it is
- The TradingView chart (`.chart-area`) — stays where it is
- The Insights panel (`.trades-panel`) — stays where it is
- The Ledger panel (`.positions-panel`) — stays where it is
- The Watchlist section (`.watchlist-section`) — stays where it is (minus the analyzer panel)
- Any JavaScript logic — DOM moves don't break ID-based selectors

---

## Testing Checklist

1. **Layout matches wireframe:** Market Bias (left, narrow, full height) → Sectors/Headlines (middle, wider, full height) → Right stack (Intraday/Swing/Macro top 30%, Portfolio middle 45%, Single Ticker Analyzer bottom 25%)
2. **Bottom edges aligned:** Market Bias, Sectors/Headlines, and the right stack all end at the same vertical position
3. **+20% height:** The panel row is visibly taller than before (~420px vs ~350px)
4. **TF cards unchanged:** Intraday, Swing, Macro cards render the same content, just in the top of the right stack
5. **Portfolio tracker works:** Balances display, accounts expand, all interactions work
6. **Single Ticker Analyzer works:** Enter a ticker, click Analyze, results display. "Add to Watchlist" button works.
7. **Heatmap/Chart unaffected:** Everything below the panel row renders exactly as before
8. **Responsive layout:** At <1200px, panels stack vertically. No horizontal overflow.
9. **No JS errors:** Console shows no new errors after the DOM move

## Definition of Done
- [ ] `.bias-section` uses 3-column grid (Market Bias | Headlines | Right Stack)
- [ ] Right stack contains: TF row (30%) → Portfolio (45%) → Analyzer (25%)
- [ ] Single Ticker Analyzer moved from `.watchlist-section` into `.bias-section`
- [ ] Panel row height increased ~20%
- [ ] Bottom edges of all three columns aligned
- [ ] All existing functionality preserved (bias display, TF factors, portfolio, analyzer)
- [ ] Responsive breakpoint updated
- [ ] No new JS errors
