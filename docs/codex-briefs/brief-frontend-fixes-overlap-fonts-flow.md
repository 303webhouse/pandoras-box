# Brief — Frontend Fixes: Factor Overlap, Sector Fonts, Headlines Size, Flow Tab Review

**Priority:** MEDIUM — cosmetic but affects daily usability
**Touches:** `frontend/styles.css`, `frontend/app.js`, `frontend/index.html`
**Estimated time:** 1–1.5 hours (Parts 1–3 only; Part 4 is a review, not a build)

---

## Part 1 — Factor List Overlap on Portfolio Box

### Problem

When you click "Factors >" on any of the Intraday/Swing/Macro cards, the expanded factor list overflows and visually overlaps the Portfolio Summary card below it.

### Root Cause

The layout uses a flex column (`.bias-right-stack`) where the TF row is locked at exactly 30% height:

```css
/* ~line 232 */
.bias-right-tf-row {
    display: flex;
    gap: 10px;
    flex: 0 0 30%;   /* LOCKED: can't grow when factors expand */
    min-height: 0;
}
```

When factors expand inside a `.tf-card`, the card content exceeds the 30% allocation, but the flex container doesn't grow — so the content visually overflows onto the portfolio card.

### Fix

**File: `frontend/styles.css`**

**Find (~line 232):**
```css
.bias-right-tf-row {
    display: flex;
    gap: 10px;
    flex: 0 0 30%;
    min-height: 0;
}
```

**Replace with:**
```css
.bias-right-tf-row {
    display: flex;
    gap: 10px;
    flex: 0 0 auto;
    min-height: 0;
}
```

This lets the row grow naturally when factors expand, pushing the portfolio card down instead of overlapping it.

**ALSO** — cap the factor list height so it doesn't push the portfolio card completely off-screen when all 3 timeframes are expanded simultaneously.

**Find (~line 1607):**
```css
.tf-factors {
    margin-top: 6px;
    display: flex;
    flex-direction: column;
    gap: 3px;
}
```

**Replace with:**
```css
.tf-factors {
    margin-top: 6px;
    display: flex;
    flex-direction: column;
    gap: 3px;
    max-height: 180px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(20, 184, 166, 0.3) transparent;
}
```

This ensures each factor list scrolls internally at 180px max, preventing the column from growing unbounded.

---

## Part 2 — Sector Heatmap Text Overlap / Missing Text

### Problem

The sector heatmap cells auto-scale font size using a CSS custom property `--s` (set per cell via JS). When cells are small (low-weight sectors), the scaled-down text for name, ETF, change%, and RS all overlap each other or get completely hidden because the cell can't fit 4 lines of text even at the smallest scale.

### Root Cause

Each cell renders 4 text elements stacked vertically:
1. `.sector-hm-name` (sector name like "TECHNOLOGY")
2. `.sector-hm-etf` (ETF ticker like "XLK")
3. `.sector-hm-change` (daily change like "+1.23%")
4. `.sector-hm-rs` (relative strength like "RS: +0.45%")

All use `font-size: calc(Xpx * var(--s, 1))`. For small cells, `--s` drops below 0.5, making all 4 lines tiny but still fighting for vertical space.

### Fix

**File: `frontend/styles.css`**

**Find (~line 353):**
```css
.sector-hm-name {
    font-size: calc(13px * var(--s, 1));
    font-weight: 500;
    color: var(--text-secondary);
    text-align: center;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
```

**Replace with (tighter line-height):**
```css
.sector-hm-name {
    font-size: calc(13px * var(--s, 1));
    font-weight: 500;
    color: var(--text-secondary);
    text-align: center;
    line-height: 1.1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
```

**File: `frontend/app.js` — `renderSectorHeatmap()` (~line 7119)**

After the line computing `fontScale`:
```javascript
const fontScale = (0.5 + 0.7 * t).toFixed(3);
```

Add cell-size detection:
```javascript
const isSmallCell = r.w < 90 || r.h < 80;
const isTinyCell = r.w < 65 || r.h < 55;
```

Also add a minimum font scale floor:

**Find:**
```javascript
const fontScale = (0.5 + 0.7 * t).toFixed(3);
```

**Replace with:**
```javascript
const fontScale = Math.max(0.45, (0.5 + 0.7 * t)).toFixed(3);
const isSmallCell = r.w < 90 || r.h < 80;
const isTinyCell = r.w < 65 || r.h < 55;
```

Then update the cell inner HTML. Find the lines that render the spans (~lines 7137-7140):
```javascript
<span class="sector-hm-name">${escapeHtml(sector.name)}</span>
<span class="sector-hm-etf">${sector.etf}</span>
<span class="sector-hm-change" style="color:${hm.changeColor}">${changeSign}${changeVal}% <span class="sector-hm-trend ${trendClass}">${trendArrow}</span></span>
<span class="sector-hm-rs" style="color:${rsDaily >= 0 ? '#7CFF6B' : '#FF6B35'}">RS: ${rsDailyStr}%</span>
```

**Replace with:**
```javascript
${isTinyCell ? '' : `<span class="sector-hm-name">${escapeHtml(sector.name)}</span>`}
<span class="sector-hm-etf">${sector.etf}</span>
<span class="sector-hm-change" style="color:${hm.changeColor}">${changeSign}${changeVal}%${isSmallCell ? '' : ` <span class="sector-hm-trend ${trendClass}">${trendArrow}</span>`}</span>
${isSmallCell ? '' : `<span class="sector-hm-rs" style="color:${rsDaily >= 0 ? '#7CFF6B' : '#FF6B35'}">RS: ${rsDailyStr}%</span>`}
```

Logic:
- **Tiny cells** (<65px wide or <55px tall): Show ONLY ETF ticker + change%. Hide name and RS.
- **Small cells** (<90px wide or <80px tall): Show name + ETF + change%. Hide RS and trend arrow.
- **Normal cells**: Show everything (name, ETF, change% with trend arrow, RS).

---

## Part 3 — Headlines Font Size +20%

### Problem

Headlines tab text is too small to scan quickly.

### Fix

**File: `frontend/styles.css`**

**Find (~line 510):**
```css
.headline-link {
    font-size: 11px;
    line-height: 1.35;
```

**Replace with:**
```css
.headline-link {
    font-size: 13px;
    line-height: 1.35;
```

(11px x 1.2 = 13.2px, rounded to 13px)

**Also bump the headline meta text proportionally. Find (~line 523):**
```css
.headline-meta {
    font-size: 9px;
```

**Replace with:**
```css
.headline-meta {
    font-size: 10px;
```

---

## Part 4 — Flow Tab: Review and Recommendation (NOT A BUILD TASK)

### Current State

The Flow tab is effectively dead. The API endpoint `GET /api/flow/summary` returns all zeros: no sentiment data, no hot tickers, no recent signals. Two data sources feed it:

1. **Redis keys `uw:flow:*`** — per-ticker flow summaries from UW Watcher. These are not populating (or expiring before the summary reads them).
2. **Postgres `signals` table where `signal_category = 'FLOW_INTEL'`** — none exist recently.

UW Watcher IS running on VPS and posting to Discord, but its Redis output format may not match what `flow_summary.py` expects, or keys are namespaced differently.

### What the Flow Tab Shows (When It Has Data)

Three sections:
1. Smart Money Sentiment Gauge (P/C ratio bar)
2. Hottest Tickers (top 8 by premium)
3. Recent Flow Signals (last 5 FLOW_INTEL signals, 4h window)

### Why It's Not Useful Even With Data

The current display is a "dumb summary" — aggregated numbers with no actionable edge. A P/C ratio gauge and ticker list with premium totals doesn't tell you whether flow is smart money or retail, opening or closing, aligned with your positions/watchlist, or spiking above normal noise.

### Recommended Action

Run an **Olympus Committee + Titans joint review** (simulated in this Claude.ai project, not via VPS API) to determine:
- What options flow data do we actually have access to? (UW alerts, Whale Hunter, Trojan Horse v2, Polygon)
- What would be genuinely actionable for Nick's trading?
- Should the Flow tab become a "Position Radar" showing flow on tickers he already watches/holds?
- Should flow intelligence be integrated into position cards / signal cards instead?

---

## Build Order

| Step | File | What |
|------|------|------|
| 1 | `styles.css` | Fix tf-row flex to `auto`, add factor list max-height + scroll |
| 2 | `styles.css` | Bump headline font 11 to 13px, meta 9 to 10px |
| 3 | `app.js` | Add cell-size detection to sector heatmap, conditionally hide text |
| 4 | `index.html` | Cache bust |

Part 4 (Flow tab) is a review task — no code changes in this brief.

---

## Verification Checklist

- [ ] Click "Factors >" on Intraday — factor list appears, portfolio card pushes down (no overlap)
- [ ] Click "Factors >" on all 3 TF cards simultaneously — each factor list scrolls at ~180px, portfolio card still visible
- [ ] Close factor lists — portfolio card returns to normal position
- [ ] Sector heatmap: smallest cells show only ETF ticker + change% (no overlapping text)
- [ ] Sector heatmap: medium cells show name + ETF + change% (no RS line)
- [ ] Sector heatmap: largest cells show all 4 lines (name, ETF, change%, RS)
- [ ] Headlines tab: text visibly larger than before (~20%)
- [ ] No horizontal overflow or clipping on headlines

---

## Commit

```
fix: factor overlap, sector heatmap text, headline font size
```
