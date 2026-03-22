# Brief — Fix: Two-Tab Layout for Intelligence Center (Sectors + Argus)

**Priority:** HIGH — current layout is broken (heatmap eats all vertical space, radar invisible)
**Touches:** `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
**Estimated time:** 1 hour
**Context:** The stacked Market Map + Flow Radar layout doesn't work — the sector heatmap's `height: 100%` / `min-height: 320px` expands to fill the entire column, crushing the pulse strip and radar section into zero space at the bottom. Fix: restore a clean two-tab design.

---

## Design

Two tabs at the top of the middle column, same tab style as the original SECTORS/FLOW/HEADLINES:

**Tab 1: SECTORS** — the sector heatmap at full height, exactly as it was before the intelligence center brief. No pulse strip, no headlines, no radar. Just the heatmap filling the available space.

**Tab 2: ARGUS** — the flow intelligence tab, filling the full column height when active:
- Market pulse strip (regime + P/C + premium) at the top
- Headlines strip (3 compact headlines) below pulse
- Flow Radar (scrollable): position flow → unusual activity → sector rotation

Default active tab: **SECTORS** (since that has data all the time; Argus only has data during market hours).

The name "Argus" comes from Greek mythology — the hundred-eyed giant who sees everything. Fits the surveillance/monitoring theme.

---

## Part 1 — HTML

### File: `frontend/index.html`

**Find** the entire `intel-center` block (the broken stacked layout). It should look roughly like:

```html
<!-- Intelligence Center (column 2) -->
<div class="intel-center" id="intelCenter">
    <!-- MARKET MAP: sector heatmap + pulse + headlines -->
    <div class="market-map-section">
        <div class="sector-heatmap" id="sectorHeatmap">
            ...
        </div>
        <div class="market-pulse-strip" id="marketPulseStrip">
            ...
        </div>
        <div class="headlines-strip" id="headlinesStrip">
            ...
        </div>
    </div>
    <!-- FLOW RADAR -->
    <div class="flow-radar-section" id="flowRadarSection">
        ...
    </div>
</div>
```

**Replace with:**

```html
<!-- Intelligence Center (column 2) -->
<div class="intel-center" id="intelCenter">
    <div class="intel-tabs">
        <button class="intel-tab active" data-tab="sectors">SECTORS</button>
        <button class="intel-tab" data-tab="argus">ARGUS</button>
    </div>
    <div class="intel-tab-content" id="sectorsTabContent">
        <div class="sector-heatmap" id="sectorHeatmap">
            <p class="empty-state">Loading sectors...</p>
        </div>
    </div>
    <div class="intel-tab-content" id="argusTabContent" style="display:none;">
        <div class="market-pulse-strip" id="marketPulseStrip">
            <span class="pulse-regime" id="pulseRegime">--</span>
            <span class="pulse-separator">·</span>
            <span class="pulse-pc" id="pulsePcRatio">P/C --</span>
            <span class="pulse-separator">·</span>
            <span class="pulse-premium" id="pulsePremium">$--</span>
            <span class="pulse-separator">·</span>
            <span class="pulse-status" id="pulseStatus">--</span>
        </div>
        <div class="headlines-strip" id="headlinesStrip">
            <div class="headline-compact">Loading headlines...</div>
        </div>
        <div class="flow-radar-section" id="flowRadarSection">
            <div class="radar-header">
                <span class="radar-title">FLOW RADAR</span>
                <span class="radar-status" id="radarStatus">--</span>
            </div>
            <div class="radar-content" id="radarContent">
                <p class="empty-state">Waiting for flow data...</p>
            </div>
        </div>
    </div>
</div>
```

---

## Part 2 — CSS

### File: `frontend/styles.css`

Keep all the existing `.intel-center`, `.market-pulse-strip`, `.headlines-strip`, `.flow-radar-section`, `.radar-*` styles from the previous brief — they're all still used inside the Argus tab.

**Add/update these rules:**

```css
/* Intel Center tabs (same style as the old headlines tabs) */
.intel-tabs {
    display: flex;
    gap: 2px;
    margin-bottom: 0;
    flex-shrink: 0;
    background: var(--dark-bg);
    border-radius: 6px;
    padding: 2px;
    margin: 10px 12px 8px 12px;
}

.intel-tab {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-family: 'Orbit', sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    padding: 5px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s;
}

.intel-tab:hover {
    color: var(--text-primary);
    background: rgba(20, 184, 166, 0.08);
}

.intel-tab.active {
    background: rgba(20, 184, 166, 0.15);
    color: var(--accent-teal);
}

/* Tab content areas — each fills the remaining column height */
.intel-tab-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

/* Sectors tab: heatmap fills entire content area */
#sectorsTabContent .sector-heatmap {
    flex: 1;
    min-height: 0;
}

/* Argus tab: stacked sections with radar scrollable */
#argusTabContent {
    padding: 0 12px 10px 12px;
}

#argusTabContent .market-pulse-strip {
    flex-shrink: 0;
}

#argusTabContent .headlines-strip {
    flex-shrink: 0;
}

#argusTabContent .flow-radar-section {
    flex: 1;
    min-height: 0;
}
```

**Also remove or update** the old `.market-map-section` rule if it exists — it's no longer used.

**Check:** Make sure `.intel-center` still has `display: flex; flex-direction: column;` so the tabs + content stack vertically and the active content fills available space.

---

## Part 3 — JavaScript: Tab Switching

### File: `frontend/app.js`

**Find** the `initOptionsFlow()` function (or wherever the old tab switching was). The previous brief removed the old SECTORS/FLOW/HEADLINES tab handlers. Re-add tab switching for the new two-tab layout:

```javascript
// Intel Center tab switching (Sectors / Argus)
document.querySelectorAll('.intel-tab').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.intel-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const target = btn.dataset.tab;
        const sectorsEl = document.getElementById('sectorsTabContent');
        const argusEl = document.getElementById('argusTabContent');
        if (sectorsEl) sectorsEl.style.display = target === 'sectors' ? '' : 'none';
        if (argusEl) argusEl.style.display = target === 'argus' ? '' : 'none';
        
        // Trigger radar refresh when switching to Argus
        if (target === 'argus') {
            loadFlowRadar();
        }
    });
});
```

This should go in the same initialization block where the old tab handlers were. If `initOptionsFlow()` was gutted by the previous brief, put this in the `DOMContentLoaded` initialization sequence.

**Also update `loadSectorHeatmap()`:** The previous brief had it piggybacking `loadFlowRadar()` inside a `Promise.all`. Separate them — the heatmap should load independently:

```javascript
async function loadSectorHeatmap() {
    try {
        const response = await fetch(`${API_URL}/sectors/heatmap`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderSectorHeatmap(data.sectors, data);
    } catch (error) {
        console.error('Sector heatmap load failed:', error);
    }
}
```

The sector flow dots on the heatmap were a nice idea but they add complexity and require the heatmap to depend on radar data. Remove the `sectorFlowMap` parameter from `renderSectorHeatmap()` — restore it to its original signature that just takes `(sectors, spyData)`. The flow information is fully visible in the Argus tab now, so the heatmap doesn't need dots.

If `renderSectorHeatmap()` was modified to accept `sectorFlowMap`, revert that parameter. The flow dot HTML (`sector-flow-dot`) can be removed from the cell template.

**Load flow radar on page init AND on a 2-minute interval (keep existing):**

Make sure `loadFlowRadar()` is called on page load (in the init sequence) so Argus has data when the user clicks the tab. The 2-minute market-hours refresh from the previous brief should remain.

**Headlines:** Make sure `loadHeadlines()` still runs on page init and targets the `headlinesStrip` container (from the previous brief's update). Headlines should populate regardless of which tab is active.

---

## Part 4 — Cache Bust

### File: `frontend/index.html`

Bump CSS and JS version numbers.

---

## Build Order

| Step | File | What |
|------|------|------|
| 1 | `index.html` | Replace stacked layout with 2-tab (SECTORS / ARGUS) |
| 2 | `styles.css` | Tab styles, content area sizing, remove old `.market-map-section` |
| 3 | `app.js` | Tab switching, separate heatmap from radar loading, remove flow dots from heatmap |
| 4 | `index.html` | Cache bust |

---

## Verification Checklist

- [ ] Two tabs visible: SECTORS and ARGUS
- [ ] SECTORS tab active by default — heatmap fills entire column height (no crushed elements below)
- [ ] Click ARGUS — pulse strip + headlines + radar visible, properly spaced
- [ ] Click back to SECTORS — heatmap returns, no layout glitch
- [ ] Radar content scrollable when Argus has enough data
- [ ] Headlines populate in the Argus tab (via `loadHeadlines()` fallback)
- [ ] Flow radar refreshes when switching to Argus tab
- [ ] No old "FLOW" or "HEADLINES" tabs visible
- [ ] Heatmap no longer has flow dot overlays (removed)
- [ ] 2-minute auto-refresh still fires during market hours

---

## Commit

```
fix: two-tab layout (Sectors + Argus) — replace broken stacked design
```
