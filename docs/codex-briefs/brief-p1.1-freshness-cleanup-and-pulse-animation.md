# Brief — P1.1: Freshness Indicator Cleanup + Live Refresh Pulse Animation

**Status:** Ready for CC
**Source:** Tonight's P1 verification with Nick — visual issues + UX gap on auto-refreshing panels
**Estimated effort:** ~30 min (all frontend, no deploy wait)
**Dependencies:** Builds on P1 (commit which shipped freshness indicators). Apply BEFORE P2 frontend work to avoid stacking app.js merge conflicts.

---

## Intent

P1's freshness indicators work correctly on panels with manually-loaded or rarely-changing data (position cards going red after 30 min — verified live). But they don't fit two specific places:

1. **Auto-refreshing live data feeds** (heatmap + macro strip ticker tape) — both refresh every 10 seconds, so the indicator just flickers gray→amber→red→green every cycle. Useless visual noise.
2. **Sector drill-down popup** — the indicator is positioned at the modal bottom-right, but that space contains a table row, so it overlaps real data (visible bug on AMD row in tonight's screenshots).

Plus a couple of small cleanups:
3. **ISO tooltip is dev-noise** — `2026-04-27T17:04:51.123Z` shown to a trader on hover adds nothing; the visible "as of HH:MM:SS" is sufficient.
4. **Optional: HYDRA's "Updated:" line is now redundant** with the new freshness indicator.

The replacement for live feeds is a **subtle pulse animation** — a small dim-green dot near each panel header that briefly flashes bright on each successful data fetch. Standard pattern in Bloomberg / TradingView / Polygon dashboards. If the feed stalls (no fetch in >30s), the dot turns amber to signal a problem. This honestly conveys "data is flowing" without the noise of a constantly-updating timestamp.

---

## Pre-flight checks

```bash
cd /c/trading-hub
git status                                    # Clean
git pull --rebase                             # Pull P1 changes
grep -c "renderStalenessIndicator" frontend/app.js
# Should output a number > 1 (function definition + 12 panel wires)
```

If `renderStalenessIndicator` is missing, abort — P1 hasn't landed and this brief depends on it.

---

## Phase A — Drop freshness indicator from heatmap and macro strip

**File:** `frontend/app.js`

### A.1 — Find the staleness wires for these two panels

Search for `renderStalenessIndicator` calls in app.js. Two of them target:
- The sector heatmap container (`document.getElementById('sectorHeatmap')` or its parent)
- The macro strip (`macroStripInner` or its parent)

**Delete those two specific calls.** The function definition stays. The other 10 wires stay.

If the wires aren't easy to identify by element, look for these comment markers added during P1 (or grep `sectorHeatmap` and `macroStrip` near `renderStalenessIndicator` calls).

### A.2 — Verify the deletions

After edits:

```bash
grep -n "renderStalenessIndicator" frontend/app.js | wc -l
# Should be 11 (was 13 — 1 definition + 12 wires; minus 2 = 11)
```

If the count is wrong, report back which wires you removed and we'll reconcile.

---

## Phase B — Reposition sector drill-down popup indicator

**File:** `frontend/app.js`

The indicator currently lands inside the popup's table area, overlapping ticker rows. Move it to the popup's footer — the existing footer area that contains the `Show All 20` button or the modal's bottom edge.

### B.1 — Find the current wire

In `_fetchSectorLeaders`, find:

```javascript
var popupModal = document.querySelector('.sector-popup-modal');
renderStalenessIndicator(popupModal, data.updated_at);
```

### B.2 — Replace with a footer-anchored target

```javascript
// Anchor staleness indicator to popup footer to avoid overlap with table rows (P1.1)
var popupFooter = document.querySelector('.sector-popup-modal .sector-popup-footer')
                  || document.querySelector('.sector-popup-modal .sector-popup-header')
                  || document.querySelector('.sector-popup-modal');
renderStalenessIndicator(popupFooter, data.updated_at);
```

The fallback chain ensures it lands somewhere safe even if the markup varies. Footer first (preferred), header second (acceptable), modal-itself last (current behavior — no regression).

### B.3 — If the popup has no `.sector-popup-footer` element today, add one

Find the popup HTML generator (probably in a function like `_initSectorPopupHTML` or in the `_fetchSectorLeaders` initial setup). At the bottom of the modal, just before the closing `</div>` of `.sector-popup-modal`, add:

```html
<div class="sector-popup-footer"></div>
```

Then in `frontend/styles.css`, add a small style:

```css
.sector-popup-footer {
    position: relative;
    min-height: 24px;
    padding: 8px 16px 4px;
    border-top: 1px solid var(--border-color, #2a2a2a);
    margin-top: 8px;
}
```

(The freshness indicator's existing absolute-positioning will pin to the bottom-right of this new footer, no longer colliding with table rows.)

---

## Phase C — Drop the ISO tooltip from indicators

**File:** `frontend/app.js` (the `renderStalenessIndicator` function definition)

### C.1 — Find and remove the title attribute

Search for the `renderStalenessIndicator` function. It will set a `title` attribute somewhere with an ISO timestamp. Find the line that looks like:

```javascript
indicator.setAttribute('title', new Date(timestamp).toISOString());
```

OR (if inline as part of innerHTML construction):

```javascript
'<span ... title="' + new Date(timestamp).toISOString() + '" ...>'
```

**Delete just the `title` attribute / `setAttribute('title', ...)` call.** Leave everything else. The visible "as of HH:MM:SS" stays.

### C.2 — Remove the cursor:help styling

**File:** `frontend/styles.css`

Search for the staleness indicator class rules (`.staleness-indicator`, `.stale-amber`, `.stale-red` from P1). One of them has:

```css
cursor: help;
```

**Delete that line.** The cursor stays default (arrow), no more confusing question mark on hover.

---

## Phase D — Add live refresh pulse animation to heatmap and macro strip

**Files:** `frontend/app.js` + `frontend/styles.css`

### D.1 — CSS: pulse dot styles

Add to `frontend/styles.css`:

```css
/* ── P1.1: Live refresh pulse animation ────────────────────── */

.live-data-indicator {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-left: 12px;
    font-size: 0.7em;
    color: var(--text-secondary, #888);
    letter-spacing: 0.5px;
    text-transform: uppercase;
    vertical-align: middle;
}

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

/* Brief pulse animation triggered on each successful fetch */
.live-data-dot.pulsing {
    animation: live-data-pulse 600ms ease-out;
}

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

/* Stalled state — no successful fetch in >30s */
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

### D.2 — JS: helper to manage pulse state

Add this helper function to `frontend/app.js`. Place it next to `renderStalenessIndicator` (logically related — both are data-status helpers):

```javascript
// ===== Live refresh pulse animation (P1.1) =====
// Fires a brief pulse on each successful data fetch. If no pulse fires within
// 30 seconds, the dot transitions to "stalled" amber state.

var _liveDataState = {};  // dotId -> { lastPulse: timestamp, stalled: bool }

function ensureLiveDataIndicator(container, dotId, label) {
    if (!container) return null;
    // Check if indicator already exists
    var existing = container.querySelector('.live-data-indicator[data-dot-id="' + dotId + '"]');
    if (existing) return existing.querySelector('.live-data-dot');

    var indicator = document.createElement('span');
    indicator.className = 'live-data-indicator';
    indicator.setAttribute('data-dot-id', dotId);
    indicator.innerHTML = '<span class="live-data-dot"></span>'
                        + '<span class="live-data-label">' + (label || 'LIVE') + '</span>';
    container.appendChild(indicator);
    return indicator.querySelector('.live-data-dot');
}

function pulseLiveDataIndicator(dotId) {
    var indicator = document.querySelector('.live-data-indicator[data-dot-id="' + dotId + '"]');
    if (!indicator) return;
    var dot = indicator.querySelector('.live-data-dot');
    if (!dot) return;

    // Clear stalled state if previously stalled
    indicator.classList.remove('stalled');
    dot.classList.remove('stalled');

    // Trigger pulse animation
    dot.classList.remove('pulsing');
    // Force reflow so re-adding the class re-triggers animation
    void dot.offsetWidth;
    dot.classList.add('pulsing');

    _liveDataState[dotId] = { lastPulse: Date.now(), stalled: false };
}

// Stall watcher — checks every 5s whether any registered dot has gone >30s without a pulse
setInterval(function() {
    var now = Date.now();
    Object.keys(_liveDataState).forEach(function(dotId) {
        var state = _liveDataState[dotId];
        if (!state) return;
        var ageMs = now - state.lastPulse;
        var indicator = document.querySelector('.live-data-indicator[data-dot-id="' + dotId + '"]');
        if (!indicator) return;
        var dot = indicator.querySelector('.live-data-dot');
        if (!dot) return;

        if (ageMs > 30000 && !state.stalled) {
            indicator.classList.add('stalled');
            dot.classList.add('stalled');
            state.stalled = true;
        } else if (ageMs <= 30000 && state.stalled) {
            indicator.classList.remove('stalled');
            dot.classList.remove('stalled');
            state.stalled = false;
        }
    });
}, 5000);
```

### D.3 — Wire pulse into heatmap fetch

Find `loadSectorHeatmap` in app.js (around line 7950). Looks like:

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

**Replace with:**

```javascript
async function loadSectorHeatmap() {
    try {
        const response = await fetch(`${API_URL}/sectors/heatmap`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        renderSectorHeatmap(data.sectors, data);

        // P1.1: live refresh pulse — ensure indicator exists in heatmap header, then pulse
        var heatmapHeader = document.querySelector('#sectorHeatmap .heatmap-header')
                          || document.querySelector('#sectorHeatmap')
                          || document.getElementById('sectorHeatmap');
        ensureLiveDataIndicator(heatmapHeader, 'heatmap', 'LIVE');
        pulseLiveDataIndicator('heatmap');
    } catch (error) {
        console.error('Sector heatmap load failed:', error);
        // Pulse failure → stall watcher will catch it after 30s
    }
}
```

### D.4 — Wire pulse into macro strip fetch

Find `loadMacroStrip` in app.js (around line 11882). Looks like:

```javascript
async function loadMacroStrip() {
    try {
        const resp = await fetch(`${API_URL}/macro/strip`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderMacroStrip(data.tickers);
    } catch (e) {
        console.error('Macro strip load failed:', e);
    }
}
```

**Replace with:**

```javascript
async function loadMacroStrip() {
    try {
        const resp = await fetch(`${API_URL}/macro/strip`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderMacroStrip(data.tickers);

        // P1.1: live refresh pulse — ensure indicator exists in macro strip header, then pulse
        // Anchor to the parent of the scrolling inner element so the pulse stays visible
        var stripInner = document.getElementById('macroStripInner');
        var stripContainer = stripInner ? stripInner.parentElement : null;
        // Prefer a dedicated label slot if it exists, otherwise the parent itself
        var pulseTarget = stripContainer
            ? (stripContainer.querySelector('.macro-strip-status') || stripContainer)
            : null;
        ensureLiveDataIndicator(pulseTarget, 'macroStrip', 'LIVE');
        pulseLiveDataIndicator('macroStrip');
    } catch (e) {
        console.error('Macro strip load failed:', e);
    }
}
```

### D.5 — Anchor positioning safeguard for the macro strip

Because the macro strip uses a horizontally-scrolling animation, the pulse indicator could get clipped or scroll off-screen if it's appended into the scrolling element. The fallback in D.4 anchors to the **parent** of `macroStripInner`, which is the static container.

If the parent element doesn't have stable positioning (and the indicator visually jumps around), add to `frontend/styles.css`:

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
    backdrop-filter: blur(4px);
    padding: 2px 8px;
    border-radius: 10px;
    pointer-events: none;
}
```

Adapt the class name `.macro-strip-container` to whatever the macro strip's actual outer container class is — find it by looking for the parent element of `macroStripInner` in app.js's render code.

---

## Phase E — (Optional) Drop redundant HYDRA "Updated:" line

**File:** `frontend/app.js`

The HYDRA Squeeze Monitor shows both `Updated: 5:14:25 PM` (existing manual-refresh timestamp) and the new `as of 5:14:45 PM` (P1 freshness indicator). The first is now redundant.

Search for `Updated:` in app.js, scoped to HYDRA-related rendering:

```bash
grep -n "Updated:" frontend/app.js | head -10
```

Locate the one that renders inside the HYDRA panel (look for nearby references to `hydra`, `squeezeMonitor`, or similar). Either:

**Option E.1 (simplest):** Delete the `Updated: HH:MM:SS` line entirely.

**Option E.2 (safer):** Wrap it in a conditional so it only shows if the new freshness indicator is somehow missing:

```javascript
// Before: var updatedText = 'Updated: ' + formatTime(lastRefresh);
// After:
var updatedText = '';  // Removed in P1.1 — superseded by freshness indicator
```

If you can't cleanly identify the right `Updated:` line (they might exist in multiple panels), **skip this phase entirely** and report back. Not critical.

---

## Sequenced commit plan

Single commit (all frontend, no deploy wait):

```bash
# Apply Phase A (delete 2 staleness wires)
# Apply Phase B (popup footer reposition)
# Apply Phase C (remove ISO tooltip + cursor:help)
# Apply Phase D (live pulse CSS + JS helpers + 2 fetch hooks)
# Apply Phase E if cleanly possible, else skip

node --check frontend/app.js
git add frontend/app.js frontend/styles.css
git commit -m "P1.1: drop heatmap/macro freshness indicators (replaced by live pulse), reposition popup indicator, drop ISO tooltip"
git push origin main
```

---

## Verification checklist

Open https://pandoras-box-production.up.railway.app and load Agora. Run all 8 checks:

1. **Heatmap has NO "as of HH:MM:SS"** anywhere on it. PASS/FAIL.

2. **Heatmap has a small green dot pulsing** in its header area, briefly flashing brighter every ~10 seconds. PASS/FAIL.

3. **Macro strip ticker tape has NO "as of HH:MM:SS"** indicator. PASS/FAIL.

4. **Macro strip has a small green dot** in or near its container, pulsing every ~10 seconds. PASS/FAIL.

5. **Click any sector to open the drill-down popup. The "as of HH:MM:SS" indicator** is visible at the bottom of the popup, NOT overlapping any ticker row. PASS/FAIL.

6. **Hover any "as of HH:MM:SS" indicator** for 2 full seconds. NO question mark cursor. NO ISO tooltip pops up. The visible label is the only timestamp shown. PASS/FAIL.

7. **Open browser DevTools Console.** Watch for 60 seconds while panels refresh. NO red errors mentioning `live-data`, `pulseLiveDataIndicator`, or `ensureLiveDataIndicator`. PASS/FAIL.

8. **Stall test (optional but valuable):** Open DevTools Network tab. Block requests to `/sectors/heatmap` (right-click any heatmap request → "Block request URL"). Wait 35 seconds. The pulse dot should turn amber and "LIVE · STALLED" should appear. PASS/FAIL. (Unblock when done.)

### Plus check 9 if Phase E was applied:

9. **HYDRA Squeeze Monitor shows ONE timestamp** ("as of HH:MM:SS"), not two. The "Updated: HH:MM:SS" line is gone. PASS/FAIL.

---

## Known risks & non-goals

- **Pulse animation could feel busy on slow connections.** If a fetch takes >5 seconds the pulse fires once it returns rather than at the start of the request. This is correct semantics (pulse = data successfully arrived) but could appear less "live" on slow connections. Acceptable.
- **Stall threshold (30s) may be too aggressive on slow connections.** Heatmap and macro strip refresh every 10s, so 30s = 3 missed cycles before stall warning. If Nick sees frequent false-positive stalls, bump to 45s or 60s in `setInterval` watcher.
- **Non-goal: per-panel pulse customization.** Other panels could benefit from pulse animations too (watchlist, flow radar, etc.) but those refresh on different cadences and have different staleness semantics. Keep pulse scoped to heatmap + macro strip until the pattern proves out.
- **Non-goal: replacing freshness indicators on position cards / watchlist / HYDRA.** Those panels have data that genuinely CAN be stale and where staleness affects trade decisions. The "as of HH:MM:SS" indicator is the right pattern there. Verified working tonight (GLD card red on 2-day-old data).
- **Phase E is optional.** If the `Updated:` text is hard to locate cleanly, skip without penalty.

---

## Rollback plan

```bash
git revert <p1.1-commit-sha>
git push origin main
```

All-frontend, no DB or backend changes. Revert restores P1's original behavior (timestamps everywhere, ISO tooltips, no pulse).

---

## What this delivers

After P1.1 lands:

- The heatmap and macro strip stop showing useless flickering "as of" timestamps and instead show **a small pulsing green dot** that flashes on each 10-second refresh — clean visual signal that data is flowing
- If either feed stalls (network issue, backend hung), the dot turns amber within 30 seconds — silent failure becomes visible failure
- Sector drill-down popup's freshness indicator no longer collides with table rows
- Hover behavior on indicators is clean — no confusing question mark cursor, no machine-readable ISO timestamp tooltip
- The redundant "Updated:" line in HYDRA goes away (if Phase E succeeds)

Total new code surface: ~80 lines JS + ~50 lines CSS. Zero backend changes.

---

## Follow-up principle for PROJECT_RULES.md (capture, don't apply now)

When eventually updating `PROJECT_RULES.md` (next time it gets touched), add a UI principle:

> **Freshness indicators belong on panels where data CAN be stale and where staleness matters to a trade decision** (positions, watchlist, signals, bias readings, alerts). **Auto-refreshing live data feeds get a refresh-pulse animation instead** (heatmap, macro ticker tape, real-time price feeds). The pulse fires on each successful fetch and stalls amber after 30s of no pulse. This avoids visual noise on always-fresh data while still signaling that the feed is alive.

Captured in TODO. No need to update PROJECT_RULES.md as part of this brief.
