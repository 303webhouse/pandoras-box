# Brief — P1.2: Heatmap Toggle Restyle + Macro Strip Ticker Restoration + Live-Indicator Color Fix

**Status:** Ready for CC
**Source:** Tonight's verification 2026-04-27 — Nick reviewed P1.1 + P2 frontend output and surfaced 4 issues (toggle styling/sizing, flow mode visual broken, "LIVE" badge floating, ticker tape missing)
**Estimated effort:** ~30 min (all frontend, no backend, no Railway deploy wait)
**Dependencies:** Builds on P1.1 (commit `0047ddec`) + P2 (commit `b28a4bad`). Apply BEFORE any further P3/P4 work to avoid stacking app.js conflicts.

---

## Intent — what's broken and why

Three real bugs, plus one cosmetic mismatch:

### 🔴 Bug 1 (URGENT) — Macro ticker tape disappeared, "LIVE" badge floats over heatmap

**Root cause:** P1.1's CSS rule for absolute-positioning the live-indicator inside the macro strip was scoped to class `.macro-strip-container`. The actual hub class is `.macro-strip`. The selector never matched, so the `<span class="live-data-indicator">` was inserted as a sibling flex-child inside `<div class="macro-strip">` (which uses `display:flex; justify-content:center; overflow:hidden`). The flex layout placed the LIVE badge inline with the scrolling content, displacing or hiding it.

**Confirmed by inspecting the live code:** `index.html:78` declares `<div class="macro-strip" id="macroStrip">` (NOT `.macro-strip-container`). `styles.css:13675-13690` has the `.macro-strip-container .live-data-indicator` rule that never fires. Reverting to inline-flex layout means the LIVE badge took flex space the ticker needed.

### 🟠 Bug 2 — Heatmap Price/Flow toggle is too big and uses wrong color

CC's implementation per P2 brief: toggle injected via `insertAdjacentHTML('afterbegin', ...)` into `#sectorsTabContent`, wrapped in inline-styled `<div style="padding:6px 8px 2px">`. CSS uses `var(--accent-blue, #2196f3)` for active state — neither variable exists in the hub root tokens. Falls back to Material Blue, doesn't match hub teal.

**Root cause: my P2 brief.** I prescribed `--accent-blue` (not a hub token) and didn't pin the toggle's position, so it landed as a separate row above the heatmap creating ~30px of dead vertical space. Verified in `styles.css:1-17` — hub uses `--accent-teal` (#14b8a6) for tab active states.

### 🟡 Bug 3 — Flow mode does nothing visible except remove sector outlines

After-hours, all sectors return `flow_direction: "neutral"` and `flow_call_pct: null` (P2 verification check 3 confirmed). With null call_pct, intensity collapses to 0.3 (the floor) and all cells render the same muted neutral color — no border distinction between sectors.

**This is partly an after-hours data issue** (verified) AND **partly a missing fallback** for the "everything neutral" state. Without a hint to the user, it looks broken.

### 🟢 Bug 4 — Live-indicator green uses fallback Material green, not hub lime

`styles.css:13637` uses `var(--accent-green, #00e676)`. Hub root tokens (`styles.css:1-17`) define `--accent-lime: #7CFF6B` for bullish/positive states. Same for `--accent-amber` fallback `#ffa726` — should use hub orange or a defined warning color.

---

## Pre-flight checks

```bash
cd /c/trading-hub
git status                                    # Should be clean
git pull --rebase                             # Pull latest

# Confirm the bug — these grep results explain everything
grep -n "macro-strip-container" frontend/styles.css   # Should appear once or twice
grep -n "id=\"macroStrip\"" frontend/index.html       # Confirms class is "macro-strip" (not "container")
grep -n "var(--accent-blue" frontend/styles.css       # Should appear in heatmap-toggle rules
grep -n "var(--accent-green" frontend/styles.css      # Should appear in live-data rules
```

If `macro-strip-container` doesn't appear in styles.css, abort — P1.1's CSS may have been edited or P1.2 already partially landed.

---

## Phase A — URGENT: Fix macro strip ticker disappearance

**File:** `frontend/styles.css`

The fix is a single class rename. The CSS rule was written for `.macro-strip-container`; the actual class is `.macro-strip`.

### A.1 — Rename selectors

**Find:**

```css
/* P1.1: Macro strip live indicator positioning */
.macro-strip-container {
    position: relative;
}

.macro-strip-container .live-data-indicator {
    position: absolute;
    top: 50%;
    right: 12px;
    transform: translateY(-50%);
    z-index: 2;
    background: rgba(0, 0, 0, 0.4);
    -webkit-backdrop-filter: blur(4px);
    backdrop-filter: blur(4px);
    padding: 2px 8px;
    border-radius: 10px;
    pointer-events: none;
}
```

**Replace with:**

```css
/* P1.2: Macro strip live indicator positioning (fixes ticker disappearance) */
.macro-strip {
    position: relative;
}

.macro-strip .live-data-indicator {
    position: absolute;
    top: 50%;
    right: 12px;
    transform: translateY(-50%);
    z-index: 2;
    background: rgba(10, 14, 39, 0.7);
    -webkit-backdrop-filter: blur(4px);
    backdrop-filter: blur(4px);
    padding: 2px 8px;
    border-radius: 10px;
    pointer-events: none;
    margin-left: 0;  /* Override the 12px default margin from .live-data-indicator */
}
```

> **Why these specific changes:**
> - `.macro-strip-container` → `.macro-strip` makes the rule apply
> - `rgba(10, 14, 39, 0.7)` (hub `--dark-bg` with alpha) instead of generic black, so the badge blends with the strip background
> - `margin-left: 0` cancels the 12px left-margin that `.live-data-indicator` applies by default — irrelevant when absolutely positioned, but safer

### A.2 — Verify macro strip CSS is unchanged

The actual `.macro-strip` rule already has `display: flex; align-items: center; overflow: hidden`. Adding `position: relative` to it (via Phase A.1) is the only change needed — this allows the absolutely-positioned LIVE indicator to anchor inside it instead of breaking flex layout.

After Phase A.1, the macro strip ticker should re-render normally with the LIVE indicator pinned to the top-right of the strip itself.

---

## Phase B — Heatmap Price/Flow toggle restyle + reposition

**Files:** `frontend/app.js` + `frontend/styles.css`

The current toggle takes a full row above the heatmap. We're moving it to absolute-positioned top-right of the heatmap container itself — zero dead vertical space, always visible while viewing sectors, matches the financial-dashboard pattern (think Bloomberg/Polygon/TV).

### B.1 — Remove the inline `style` and reposition target

**File:** `frontend/app.js`, around line 8020

**Find:**

```javascript
    // P2: heatmap Flow/Price toggle
    (function initHeatmapToggle() {
        var tabContent = document.getElementById('sectorsTabContent');
        if (!tabContent || tabContent.querySelector('.heatmap-toggle')) return;
        var toggleHtml = '<div class="heatmap-toggle" style="padding:6px 8px 2px">'
            + '<button class="heatmap-toggle-btn active" data-metric="price">Price</button>'
            + '<button class="heatmap-toggle-btn" data-metric="flow">Flow</button>'
            + '</div>';
        tabContent.insertAdjacentHTML('afterbegin', toggleHtml);
        tabContent.querySelectorAll('.heatmap-toggle-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var metric = btn.dataset.metric;
                if (metric === _heatmapMetric) return;
                _heatmapMetric = metric;
                tabContent.querySelectorAll('.heatmap-toggle-btn').forEach(function(b) {
                    b.classList.toggle('active', b.dataset.metric === metric);
                });
                loadSectorHeatmap();
            });
        });
    })();
```

**Replace with:**

```javascript
    // P1.2: heatmap Flow/Price toggle — anchored to heatmap container (was: row above)
    (function initHeatmapToggle() {
        var heatmapEl = document.getElementById('sectorHeatmap');
        if (!heatmapEl || heatmapEl.parentElement.querySelector('.heatmap-toggle')) return;
        var toggleHtml = '<div class="heatmap-toggle">'
            + '<button class="heatmap-toggle-btn active" data-metric="price" title="Color cells by daily price change">Price</button>'
            + '<button class="heatmap-toggle-btn" data-metric="flow" title="Color cells by aggregate options flow direction">Flow</button>'
            + '</div>';
        // Insert into the heatmap's parent so the toggle can absolute-position relative to it
        heatmapEl.parentElement.insertAdjacentHTML('afterbegin', toggleHtml);
        heatmapEl.parentElement.querySelectorAll('.heatmap-toggle-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var metric = btn.dataset.metric;
                if (metric === _heatmapMetric) return;
                _heatmapMetric = metric;
                heatmapEl.parentElement.querySelectorAll('.heatmap-toggle-btn').forEach(function(b) {
                    b.classList.toggle('active', b.dataset.metric === metric);
                });
                loadSectorHeatmap();
            });
        });
    })();
```

**Key changes:**
- Anchors to `#sectorHeatmap` parent (which is `#sectorsTabContent`) — same DOM location, but we're now using the heatmap as the positioning reference
- Removes inline `style="padding:6px 8px 2px"` (style now lives in CSS)
- Adds `title=` tooltips on each button so the buttons explain themselves on hover
- Idempotency check now scans `heatmapEl.parentElement` (same scope as before)

### B.2 — Restyle the toggle CSS

**File:** `frontend/styles.css`, around line 13588

**Find:**

```css
/* Heatmap Flow/Price toggle */
.heatmap-toggle {
    display: inline-flex;
    gap: 0;
    border: 1px solid var(--border-color, #333);
    border-radius: 6px;
    overflow: hidden;
    margin-left: 12px;
}

.heatmap-toggle-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary, #888);
    padding: 4px 12px;
    font-size: 0.85em;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
}

.heatmap-toggle-btn:hover {
    background: var(--surface-2, #2a2a2a);
}

.heatmap-toggle-btn.active {
    background: var(--accent-blue, #2196f3);
    color: white;
    font-weight: 600;
}
```

**Replace with:**

```css
/* P1.2: Heatmap Flow/Price toggle — compact pill, absolute-positioned top-right of heatmap */
#sectorsTabContent {
    position: relative;
}

.heatmap-toggle {
    position: absolute;
    top: 4px;
    right: 8px;
    z-index: 3;
    display: inline-flex;
    gap: 1px;
    background: rgba(10, 14, 39, 0.7);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    overflow: hidden;
    -webkit-backdrop-filter: blur(4px);
    backdrop-filter: blur(4px);
    pointer-events: auto;
    font-family: 'Orbit', sans-serif;
}

.heatmap-toggle-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 2px 9px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
    line-height: 16px;
}

.heatmap-toggle-btn:hover {
    background: rgba(20, 184, 166, 0.08);
    color: var(--text-primary);
}

.heatmap-toggle-btn.active {
    background: var(--accent-teal);
    color: var(--dark-bg);
    font-weight: 700;
}
```

**Key changes:**
- `position: absolute; top: 4px; right: 8px` — anchors top-right of heatmap, zero vertical space taken
- Hub `--accent-teal` for active state (matches existing tab styling)
- Hub `--dark-bg` for active text (high contrast against teal — same pattern as `.intel-tab.active`)
- `font-size: 9px` and `padding: 2px 9px` (was 0.85em / 4px 12px) — much more compact
- `Orbit` font + `text-transform: uppercase` + `letter-spacing` — matches existing intel-tab typography
- Semi-transparent dark background with backdrop-filter so it doesn't obscure the cell underneath
- Removed `margin-left: 12px` — now absolute-positioned, irrelevant

---

## Phase C — Flow mode visual fallback (after-hours hint)

**Files:** `frontend/app.js` + `frontend/styles.css`

When 80%+ of sectors return `flow_direction: "neutral"` (the after-hours / sparse-data state), show a subtle hint instead of letting the heatmap render as visually broken.

### C.1 — Add hint detection logic

**File:** `frontend/app.js`, in `loadSectorHeatmap` (around line 8069)

**Find:**

```javascript
async function loadSectorHeatmap() {
    try {
        const response = await fetch(`${API_URL}/sectors/heatmap?metric=${_heatmapMetric || 'price'}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderSectorHeatmap(data.sectors, data);

        // P1.1: live refresh pulse
        var heatmapHeader = document.querySelector('#sectorHeatmap .heatmap-header')
                          || document.getElementById('sectorHeatmap');
        ensureLiveDataIndicator(heatmapHeader, 'heatmap', 'LIVE');
        pulseLiveDataIndicator('heatmap');
    } catch (error) {
        console.error('Sector heatmap load failed:', error);
    }
}
```

**Replace with:**

```javascript
async function loadSectorHeatmap() {
    try {
        const response = await fetch(`${API_URL}/sectors/heatmap?metric=${_heatmapMetric || 'price'}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderSectorHeatmap(data.sectors, data);

        // P1.2: in flow mode, show "limited flow data" hint when most sectors are neutral
        var heatmapEl = document.getElementById('sectorHeatmap');
        var existingHint = heatmapEl && heatmapEl.parentElement.querySelector('.heatmap-flow-hint');
        if (_heatmapMetric === 'flow' && data.sectors && data.sectors.length > 0) {
            var neutralCount = data.sectors.filter(function(s) {
                return !s.flow_direction || s.flow_direction === 'neutral';
            }).length;
            var neutralPct = neutralCount / data.sectors.length;
            if (neutralPct >= 0.8) {
                if (!existingHint) {
                    var hintHtml = '<div class="heatmap-flow-hint">Limited flow data — populates during market hours</div>';
                    heatmapEl.parentElement.insertAdjacentHTML('beforeend', hintHtml);
                }
            } else if (existingHint) {
                existingHint.remove();
            }
        } else if (existingHint) {
            existingHint.remove();
        }

        // P1.1: live refresh pulse
        var heatmapHeader = document.querySelector('#sectorHeatmap .heatmap-header')
                          || document.getElementById('sectorHeatmap');
        ensureLiveDataIndicator(heatmapHeader, 'heatmap', 'LIVE');
        pulseLiveDataIndicator('heatmap');
    } catch (error) {
        console.error('Sector heatmap load failed:', error);
    }
}
```

### C.2 — Add hint CSS

**File:** `frontend/styles.css`, append after the `.heatmap-toggle-btn.active` rule from Phase B.2:

```css
/* P1.2: Flow mode "limited data" hint */
.heatmap-flow-hint {
    position: absolute;
    bottom: 8px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 3;
    background: rgba(10, 14, 39, 0.85);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 10px;
    color: var(--text-secondary);
    letter-spacing: 0.3px;
    -webkit-backdrop-filter: blur(4px);
    backdrop-filter: blur(4px);
    pointer-events: none;
    font-family: 'Orbit', sans-serif;
}
```

> **Behavior:** Hint only appears when (a) flow mode is active AND (b) ≥80% of sectors are neutral. Auto-clears when switching back to price mode or when sufficient flow data loads.

---

## Phase D — Live-indicator color tokens (use hub palette, not Material defaults)

**File:** `frontend/styles.css`

Three small token swaps so the LIVE pulse matches the rest of the hub.

### D.1 — Update `.live-data-dot` background

**Find:**

```css
.live-data-dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent-green, #00e676);
    opacity: 0.45;
    box-shadow: 0 0 0 0 transparent;
    transition: background 0.3s, opacity 0.3s;
}
```

**Replace with:**

```css
.live-data-dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent-lime);
    opacity: 0.45;
    box-shadow: 0 0 0 0 transparent;
    transition: background 0.3s, opacity 0.3s;
}
```

### D.2 — Update pulse keyframes

**Find:**

```css
@keyframes live-data-pulse {
    0% {
        opacity: 1;
        transform: scale(1.6);
        box-shadow: 0 0 8px var(--accent-green, #00e676);
    }
    50% {
        opacity: 0.9;
        transform: scale(1.2);
        box-shadow: 0 0 4px var(--accent-green, #00e676);
    }
    100% {
        opacity: 0.45;
        transform: scale(1);
        box-shadow: 0 0 0 0 transparent;
    }
}
```

**Replace with:**

```css
@keyframes live-data-pulse {
    0% {
        opacity: 1;
        transform: scale(1.6);
        box-shadow: 0 0 8px var(--accent-lime);
    }
    50% {
        opacity: 0.9;
        transform: scale(1.2);
        box-shadow: 0 0 4px var(--accent-lime);
    }
    100% {
        opacity: 0.45;
        transform: scale(1);
        box-shadow: 0 0 0 0 transparent;
    }
}
```

### D.3 — Update stalled state

**Find:**

```css
.live-data-dot.stalled {
    background: var(--accent-amber, #ffa726);
    opacity: 0.55;
    animation: none;
}

.live-data-indicator.stalled .live-data-label::after {
    content: " · STALLED";
    color: var(--accent-amber, #ffa726);
}
```

**Replace with:**

```css
.live-data-dot.stalled {
    background: var(--pnl-negative);
    opacity: 0.7;
    animation: none;
}

.live-data-indicator.stalled .live-data-label::after {
    content: " · STALLED";
    color: var(--pnl-negative);
}
```

> **Why `--pnl-negative` (#ff9800):** Hub doesn't define an explicit "amber/warning" token. `--pnl-negative` is amber-orange and is already used elsewhere for "things going wrong but not catastrophic" (loss states). Don't use `--accent-red`/`--accent-orange` (#e5370e) for stall — that's reserved for bearish/error states, not warnings.

---

## Sequenced commit plan

Single commit, all frontend, no Railway deploy wait.

```bash
# Apply Phase A (macro strip CSS class fix — fixes ticker disappearance)
# Apply Phase B (toggle reposition + restyle)
# Apply Phase C (flow mode "limited data" hint)
# Apply Phase D (live-indicator color tokens)

node --check frontend/app.js
git add frontend/app.js frontend/styles.css
git commit -m "P1.2: fix macro ticker disappearance, restyle heatmap toggle, flow-mode hint, hub color tokens"
git push origin main
```

---

## Verification checklist

Open https://pandoras-box-production.up.railway.app and load Agora. Run all 8 checks:

1. **Macro ticker tape is visible** — scrolling horizontally across the top of the page. PASS/FAIL.
   *(This is the most important check. If ticker is missing, Phase A didn't apply correctly.)*

2. **LIVE pulse indicator is in the macro strip** — small `● LIVE` badge on the right side of the ticker, NOT floating above the sectors panel. Pulses every ~10 seconds. PASS/FAIL.

3. **Sectors heatmap has NO toggle row taking up vertical space above it** — heatmap should start immediately below the SECTORS/ARGUS/EARNINGS tab row. PASS/FAIL.

4. **Toggle is visible top-right of the heatmap** — small pill control with "PRICE / FLOW" labels. Active button uses hub teal (#14b8a6), not Material blue. PASS/FAIL.

5. **Toggle hover shows tooltip** — hovering "Flow" shows "Color cells by aggregate options flow direction". PASS/FAIL.

6. **Click "Flow" — heatmap recolors and "Limited flow data" hint appears** at the bottom of the heatmap (after-hours; will go away during market hours when flow populates). PASS/FAIL.

7. **Click "Price" — heatmap returns to normal coloring, hint disappears.** PASS/FAIL.

8. **Live pulse dot is hub-lime green** (#7CFF6B), brighter/more saturated than before. The "stalled" amber state (test by blocking `/macro/strip` for 35s in DevTools) uses hub orange, not Material amber. PASS/FAIL — stall test optional.

---

## Known risks & non-goals

- **Toggle still exists.** Nick questioned whether the Price/Flow toggle should exist at all. P1.2 keeps it (smaller, prettier) so we can evaluate utility tomorrow during market hours when flow data is real. If the toggle still doesn't add value with live data, removal goes into a P1.3 brief: rip the toggle out, replace with per-cell flow direction icon (small arrow in corner of each sector cell). Captured for tomorrow's discussion.
- **The `intel-tab-content` styled `position: relative` rule applies to `#sectorsTabContent` only by ID** in Phase B.2. The other intel tabs (`#argusTabContent`, `#earningsTabContent`) are unaffected. If we eventually want absolute-positioned controls in those tabs, scope the rule differently.
- **Flow mode visual is improved but still degraded by sparse data.** The "limited data" hint manages user expectations during after-hours. During market hours with active flow data, sectors should color-code distinctly. If during tomorrow's market-hours test the colors are STILL muddy with active flow data, that's a P1.3 issue (likely the intensity math floor needs raising).
- **Non-goal: changing the live-indicator stall threshold.** Currently 30s. Bumping to 45s/60s if false positives surface is captured in TODO; not P1.2.
- **Non-goal: redoing P1.1's HYDRA "Updated:" line cleanup.** Phase E was skipped intentionally; revisit only if a HYDRA freshness redesign happens.

---

## Rollback plan

```bash
git revert <p1.2-commit-sha>
git push origin main
```

All-frontend, isolated changes. Revert restores the broken pre-P1.2 state (toggle bulky, ticker missing) — only do this if P1.2 introduces a NEW visual regression worse than the current state.

---

## What this delivers

After P1.2 lands:

- **Macro ticker tape is back** — single CSS selector fix restores the scrolling animation
- **LIVE pulse is contained inside the macro strip** — no longer floating above unrelated panels
- **Heatmap toggle takes zero vertical space** — small pill in the corner of the heatmap, hub teal active state
- **Toggle behavior is self-explanatory** via hover tooltips
- **Flow mode shows context** when data is sparse (after-hours) instead of looking broken
- **All live-indicator colors match the hub palette** — lime green pulse, hub-orange stall

**Total code surface: ~70 lines net (mostly CSS swaps and ~30 lines new JS for the flow-hint logic).** Zero backend changes. Zero new dependencies.

---

## Follow-ups captured for TODO (not in P1.2)

- **Toggle utility check:** Tomorrow during market hours, evaluate whether Price/Flow toggle adds value. If not, P1.3 will rip it out and replace with per-cell flow indicators.
- **Flow intensity math floor:** If colors are still muddy even with active flow data tomorrow, raise the intensity floor or use a different color-mapping strategy.
- **Stall threshold tuning:** If 30s false-positives surface in production, bump to 45s/60s in `_liveDataState` watcher.
