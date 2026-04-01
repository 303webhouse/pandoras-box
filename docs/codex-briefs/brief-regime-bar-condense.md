# BUG FIX: Condense Regime Bar + Move Into Market Bias Panel
## Priority: Quick UI fix
## Date: 2026-04-01

---

## THE PROBLEM

The Regime Bar (`#regimeBar`, class `regime-bar`) sits as a full-width row below the Macro Ticker Strip. It displays the auto-generated regime label (e.g., "Hostile environment (composite 28/100). Avoid new longs. Focus on capital preservation and catalyst-aligned trades only.") — a long sentence that takes up vertical space without adding enough value in its current prominent position.

Nick wants it:
1. **Removed** from its current standalone location (between macro strip and bias section)
2. **Condensed** into a compact indicator
3. **Moved inside** the Market Bias panel (`#biasCompositePanel`), placed just ABOVE the Trip Wire section (`#tripWireSection`)

The regime and trip wires are conceptually related (both are about the current market environment), so they belong together.

---

## STEP 1: Hide the Standalone Regime Bar

In `frontend/index.html`, find the entire `<div id="regimeBar" class="regime-bar">...</div>` block (including its child `regime-bar-content`, `regime-label-area`, `regime-controls`, `regime-pills`, reversal toggle, and override button).

Set `style="display: none;"` on the outer `#regimeBar` div. Do NOT delete it yet — the JS that populates it still runs, and other code may reference it. We just hide the standalone version.

---

## STEP 2: Add Condensed Regime Indicator Inside Market Bias Panel

In `frontend/index.html`, find the Trip Wire section inside `biasCompositePanel`:

```html
<!-- Trip Wire Monitor -->
<div class="trip-wire-section" id="tripWireSection">
```

INSERT this new element DIRECTLY ABOVE it (still inside `biasCompositePanel`):

```html
<!-- Condensed Regime Indicator -->
<div class="regime-condensed" id="regimeCondensed">
    <div class="regime-condensed-row">
        <span class="regime-condensed-dot" id="regimeCondensedDot"></span>
        <span class="regime-condensed-label" id="regimeCondensedLabel">Loading...</span>
        <span class="regime-condensed-source" id="regimeCondensedSource">AUTO</span>
        <button class="regime-condensed-override" id="regimeCondensedOverrideBtn" title="Override regime" onclick="document.getElementById('regimeOverrideModal').style.display='flex';">&#x270E;</button>
    </div>
</div>
```

---

## STEP 3: CSS for Condensed Regime

Add to `frontend/styles.css`:

```css
/* Condensed Regime Indicator (inside Market Bias panel) */
.regime-condensed {
    padding: 6px 10px;
    margin: 8px 0;
    background: #0c1020;
    border-radius: 4px;
    border-left: 2px solid #556;
}

.regime-condensed-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.regime-condensed-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #556;
    flex-shrink: 0;
}

.regime-condensed-dot.hostile { background: #e5370e; }
.regime-condensed-dot.unfavorable { background: #ff9800; }
.regime-condensed-dot.cautious { background: #ff9800; }
.regime-condensed-dot.favorable { background: #00e676; }

.regime-condensed.hostile { border-left-color: #e5370e; }
.regime-condensed.unfavorable { border-left-color: #ff9800; }
.regime-condensed.cautious { border-left-color: #ff9800; }
.regime-condensed.favorable { border-left-color: #00e676; }

.regime-condensed-label {
    color: #889;
    font-size: 10px;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.regime-condensed-source {
    color: #445;
    font-size: 8px;
    letter-spacing: 0.5px;
    flex-shrink: 0;
}

.regime-condensed-override {
    background: none;
    border: none;
    color: #445;
    cursor: pointer;
    font-size: 11px;
    padding: 0 2px;
    flex-shrink: 0;
}

.regime-condensed-override:hover { color: #c9a04e; }
```

---

## STEP 4: JavaScript — Populate Condensed Indicator

In `frontend/app.js`, find the function that fetches and displays the regime data (search for `/regime/current` or `regimeLabel` or `regimeBar`). It currently populates:
- `#regimeLabel` (the label text)
- `#regimeSourceBadge` (AUTO/MANUAL)
- `#regimePills` (direction pills)
- `#regimeExpiry` (expiry time)

ADD logic to ALSO populate the condensed indicator. After the existing regime data is fetched, add:

```javascript
// Populate condensed regime indicator in Market Bias panel
const condensedEl = document.getElementById('regimeCondensed');
const condensedDot = document.getElementById('regimeCondensedDot');
const condensedLabel = document.getElementById('regimeCondensedLabel');
const condensedSource = document.getElementById('regimeCondensedSource');

if (condensedEl && data) {
    const label = data.regime_label || '';
    const source = data.source || 'auto';
    
    // Determine severity from the label text
    let severity = 'neutral';
    if (label.toLowerCase().includes('hostile')) severity = 'hostile';
    else if (label.toLowerCase().includes('unfavorable')) severity = 'unfavorable';
    else if (label.toLowerCase().includes('cautious')) severity = 'cautious';
    else if (label.toLowerCase().includes('favorable')) severity = 'favorable';
    
    // Condense the label: extract just the key phrase + score
    // "Hostile environment (composite 28/100). Avoid new longs..." → "Hostile (28/100)"
    let shortLabel = label;
    const scoreMatch = label.match(/\(composite (\d+)\/100\)/);
    if (scoreMatch) {
        const envType = severity.charAt(0).toUpperCase() + severity.slice(1);
        shortLabel = `${envType} (${scoreMatch[1]}/100)`;
    }
    // If manual override, just show the full label (it's already custom text)
    if (source === 'manual_override') {
        shortLabel = label.length > 60 ? label.substring(0, 57) + '...' : label;
    }
    
    condensedLabel.textContent = shortLabel;
    condensedSource.textContent = source === 'manual_override' ? 'MANUAL' : 'AUTO';
    
    // Apply severity classes
    condensedEl.className = 'regime-condensed ' + severity;
    condensedDot.className = 'regime-condensed-dot ' + severity;
}
```

**Do NOT remove** the existing regime bar population code — other features (reversal mode toggle, regime pills, override modal) still reference those elements. Just hide the bar visually and populate both the old (hidden) and new (condensed) elements.

---

## STEP 5: Regime Override Modal Still Works

The override modal (`#regimeOverrideModal`) is a separate modal overlay that doesn't live inside the regime bar. It should still work when triggered from the condensed indicator's edit button. Verify that clicking the pencil icon on the condensed indicator opens the modal and that submitting an override updates both the hidden regime bar AND the condensed indicator.

---

## VERIFICATION

1. The standalone regime bar between macro strip and bias section is HIDDEN (no vertical space consumed)
2. Inside the Market Bias panel, just above Trip Wires, the condensed indicator shows: colored dot + short label (e.g., "Hostile (28/100)") + AUTO badge + edit button
3. The dot and left border change color based on severity (red for hostile, orange for cautious/unfavorable, green for favorable)
4. Clicking the edit pencil opens the regime override modal
5. After setting a manual override, the condensed indicator updates to show "MANUAL" badge and the custom label
6. Trip Wires section appears directly below the condensed regime indicator
7. No JS errors in console related to missing regime elements

---

## FILES MODIFIED

| File | Action |
|------|--------|
| `frontend/index.html` | **MODIFY** — Hide `#regimeBar`, add condensed indicator above Trip Wires |
| `frontend/styles.css` | **MODIFY** — Add `.regime-condensed` styles |
| `frontend/app.js` | **MODIFY** — Add condensed indicator population alongside existing regime fetch |
