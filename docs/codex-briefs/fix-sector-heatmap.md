# Sector Heatmap Fix — Apply These Changes

## Problem
1. Colors wrong: using generic red/green, need Pandora orange (#FF6B35) for negative, Pandora green (#7CFF6B) for positive
2. Font too thick: sector-name uses font-weight 600, sector-change uses 700
3. Text overlapping: boxes too small for long names like "Consumer Staples"
4. Boxes overflow: the treemap doesn't fill the container, some boxes clip outside

## Fix 1: Replace `getHeatmapColor()` in `frontend/app.js`

Find the existing `getHeatmapColor` function and replace it entirely with:

```javascript
function getHeatmapColor(changePct) {
    // Pandora theme: #7CFF6B green for positive, #FF6B35 orange for negative
    // Clamp to ±3% for color scaling
    const clamped = Math.max(-3, Math.min(3, changePct));
    const intensity = Math.abs(clamped) / 3;

    if (clamped > 0.05) {
        // Positive: blend from dark base (#0f1a14) to Pandora green (#7CFF6B)
        const r = Math.round(15 + (124 - 15) * intensity * 0.5);
        const g = Math.round(26 + (255 - 26) * intensity * 0.6);
        const b = Math.round(20 + (107 - 20) * intensity * 0.4);
        return `rgb(${r}, ${g}, ${b})`;
    } else if (clamped < -0.05) {
        // Negative: blend from dark base (#1a130f) to Pandora orange (#FF6B35)
        const r = Math.round(26 + (255 - 26) * intensity * 0.6);
        const g = Math.round(19 + (107 - 19) * intensity * 0.35);
        const b = Math.round(15 + (53 - 15) * intensity * 0.25);
        return `rgb(${r}, ${g}, ${b})`;
    } else {
        // Flat / near zero: neutral slate
        return '#1a2228';
    }
}
```

## Fix 2: Replace `renderSectorHeatmap()` in `frontend/app.js`

The current treemap uses absolute pixel widths which break on resize and cause overflow.
Replace the entire function with this CSS-grid approach that always fills the container:

```javascript
function renderSectorHeatmap(sectors, spyChange) {
    const container = document.getElementById('sectorHeatmap');
    if (!container) return;
    if (!sectors || sectors.length === 0) {
        container.innerHTML = '<p class="empty-state">No sector data</p>';
        return;
    }

    // Sort by weight descending
    const sorted = [...sectors].sort((a, b) => b.weight - a.weight);

    // 3-row layout: row 1 = top 3 (Tech, Financials, Health), row 2 = next 4, row 3 = last 4
    // This ensures each box is wide enough for full sector names
    const rows = [
        sorted.slice(0, 3),
        sorted.slice(3, 7),
        sorted.slice(7)
    ];

    // Row heights proportional to combined weight
    const rowWeights = rows.map(r => r.reduce((s, c) => s + c.weight, 0));
    const totalWeight = rowWeights.reduce((s, w) => s + w, 0);

    let html = '';
    rows.forEach((row, ri) => {
        const rowPct = ((rowWeights[ri] / totalWeight) * 100).toFixed(1);
        // Each cell width is proportional to its weight within the row
        const rowTotal = row.reduce((s, c) => s + c.weight, 0);
        const cellsHtml = row.map(sector => {
            const widthPct = ((sector.weight / rowTotal) * 100).toFixed(2);
            const bgColor = getHeatmapColor(sector.change_1d);
            const changeSign = sector.change_1d >= 0 ? '+' : '';
            const changeVal = sector.change_1d != null ? sector.change_1d.toFixed(2) : '0.00';
            return `<div class="sector-heatmap-cell"
                style="width:${widthPct}%;background:${bgColor};"
                data-etf="${sector.etf}"
                title="${escapeHtml(sector.name)} (${sector.etf})\nDaily: ${changeSign}${changeVal}%\nWeekly: ${(sector.change_1w || 0) >= 0 ? '+' : ''}${(sector.change_1w || 0).toFixed(2)}%\nSPY Weight: ${(sector.weight * 100).toFixed(1)}%">
                <span class="sector-hm-name">${escapeHtml(sector.name)}</span>
                <span class="sector-hm-etf">${sector.etf}</span>
                <span class="sector-hm-change">${changeSign}${changeVal}%</span>
            </div>`;
        }).join('');

        html += `<div class="sector-heatmap-row" style="height:${rowPct}%;">${cellsHtml}</div>`;
    });

    container.innerHTML = html;

    // Click handler: change chart to sector ETF
    container.querySelectorAll('.sector-heatmap-cell').forEach(cell => {
        cell.addEventListener('click', () => {
            const etf = cell.dataset.etf;
            if (etf) changeChartSymbol(etf);
        });
    });
}
```

## Fix 3: Replace sector heatmap CSS in `frontend/styles.css`

Find and replace ALL existing `.sector-heatmap` CSS rules with:

```css
/* Sector Heatmap — fills container, 3-row layout */
.sector-heatmap {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px;
    height: 100%;
    width: 100%;
    box-sizing: border-box;
    overflow: hidden;
}

.sector-heatmap-row {
    display: flex;
    gap: 2px;
    width: 100%;
    box-sizing: border-box;
}

.sector-heatmap-cell {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    border-radius: 3px;
    padding: 2px 4px;
    cursor: pointer;
    transition: opacity 0.15s;
    overflow: hidden;
    box-sizing: border-box;
    min-width: 0;
}

.sector-heatmap-cell:hover {
    opacity: 0.8;
}

.sector-hm-name {
    font-size: 10px;
    font-weight: 400;
    color: rgba(255,255,255,0.9);
    text-shadow: 0 1px 3px rgba(0,0,0,0.6);
    text-align: center;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}

.sector-hm-etf {
    font-size: 9px;
    font-weight: 400;
    color: rgba(255,255,255,0.55);
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.sector-hm-change {
    font-size: 11px;
    font-weight: 500;
    color: #fff;
    text-shadow: 0 1px 3px rgba(0,0,0,0.6);
}
```

NOTE: The new CSS uses class names `sector-hm-name`, `sector-hm-etf`, `sector-hm-change` (not the old `sector-name`, `sector-etf`, `sector-change` which conflict with existing watchlist sector card styles). Make sure the old `.sector-heatmap-cell .sector-name` etc rules are removed.
