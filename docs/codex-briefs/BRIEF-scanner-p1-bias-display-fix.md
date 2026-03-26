# BRIEF: Bias Composite Display Fix — Frontend Gauge (P1)

## Problem
The bias composite gauge shows "-0/100" because `Math.round(-0.139)` produces `-0` in JavaScript (negative zero). The raw score (-1.0 to +1.0) needs to be mapped to a 0-100 gauge scale for human readability.

## Context
The backend composite_score is working correctly: -0.139 (URSA_MINOR regime, 20 factors active). This is purely a frontend display issue.

## Changes Required

### 1. Fix gauge display in `frontend/app.js`

Search for where the composite score is rendered as a gauge or numeric display. Look for patterns like:
- `Math.round(compositeScore)` or `Math.round(score)`
- Any reference to `/100` near composite display
- The bias gauge component rendering

The fix depends on the display intent:

**Option A: Map to 0-100 scale (RECOMMENDED)**
```javascript
// Convert -1.0..+1.0 to 0..100 gauge
const gaugeValue = Math.round(((compositeScore + 1) / 2) * 100);
// -1.0 = 0 (max bearish), 0.0 = 50 (neutral), +1.0 = 100 (max bullish)
// Current -0.139 would show as 43/100
```

**Option B: Show as percentage with sign**
```javascript
// Convert to percentage: -0.139 → "-14%"
const displayPct = Math.round(compositeScore * 100);
const displayStr = (displayPct > 0 ? '+' : '') + displayPct + '%';
```

**Option C: Minimum fix — just eliminate negative zero**
```javascript
const displayValue = Math.round(compositeScore) || 0;  // -0 → 0
```

Option A is best because it gives a meaningful gauge reading. Nick sees "43/100" and immediately knows it's mildly bearish (below 50 = bearish, above 50 = bullish).

### 2. Update the gauge label
If using Option A, also update any nearby label text:
- "0 = max bearish, 50 = neutral, 100 = max bullish" or similar
- The URSA_MINOR / TORO_MAJOR text label should still come from `bias_level`

## Finding the Code
The file is `frontend/app.js` (~420KB+). Search for:
- `composite` near any `Math.round` or `.toFixed`
- `gaugeValue` or `biasGauge` or `compositeGauge`
- `/100` display pattern near bias section
- The render function for the bias/composite section of the dashboard

Use `findstr /n "composite" frontend\app.js` via Desktop Commander to locate the relevant lines.

## Testing
- Load the Trading Hub in browser
- Check the bias gauge — should show ~43/100 (or whatever the current score maps to)
- Verify the regime label still shows URSA_MINOR correctly
- Test edge cases: score = 0.0 → 50/100, score = -1.0 → 0/100, score = 1.0 → 100/100

## Risk
Very low. Display-only change, no backend impact.
