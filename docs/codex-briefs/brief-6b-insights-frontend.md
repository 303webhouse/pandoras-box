# Brief 6B: Insights Quality Overhaul — Frontend

**Target Agent:** Claude Code (VSCode)
**Phase:** 6 — Insights Quality
**Depends On:** Brief 6A (backend endpoints must exist first)
**Titans Approved:** March 17, 2026

---

## What This Does

Redesigns the Insights / Trade Ideas cards in the Agora UI to show:
1. Primary setup clearly identified (strategy, entry/stop/target)
2. Confirming signals from different strategies (not duplicates)
3. Score factor breakdown (what's boosting the score)
4. "Last updated" relative timestamp
5. Accept/Reject buttons with immediate removal from feed
6. Score threshold toggle (70+ default, show all for auditing)

---

## Step 1: Find the Insights Rendering Code

The grouped Trade Ideas are served by `GET /api/trade-ideas/grouped`. Find where the frontend renders these:

```
grep -n "trade-ideas/grouped\|tradeIdeasGrouped\|grouped\|insights\|renderGroup\|renderTradeIdea" frontend/app.js
```

Also check:
```
grep -n "signal_count\|confluence_tier\|related_signals\|primary_signal" frontend/app.js
```

Identify the function that fetches and renders the grouped cards.

---

## Step 2: Update the Fetch Call

The fetch call to `/api/trade-ideas/grouped` currently may not pass `min_score`. Update it:

**Find** the fetch call (something like):
```javascript
fetch('/api/trade-ideas/grouped')
```

**Replace with:**
```javascript
const showAll = document.getElementById('insights-show-all')?.checked || false;
const url = showAll
    ? '/api/trade-ideas/grouped?show_all=true'
    : '/api/trade-ideas/grouped';
fetch(url, { headers: { 'Authorization': `Bearer ${getAuthToken()}` } })
```

---

## Step 3: Redesign the Insight Card

Each group from the API has this shape:
```json
{
    "ticker": "AAPL",
    "direction": "LONG",
    "primary_signal": { "strategy": "Holy_Grail", "score": 82, "entry_price": 178.50, ... },
    "related_signals": [ { "strategy": "Artemis", "score": 75, "timestamp": "..." }, ... ],
    "strategies": ["Holy_Grail", "Artemis"],
    "distinct_strategy_count": 2,
    "last_signal_at": "2026-03-17T14:45:00",
    "highest_score": 82,
    "confluence_tier": "CONFIRMED",
    "composite_rank": 52.3
}
```

Render each card with this structure:

```html
<div class="insight-card" data-ticker="AAPL" data-direction="LONG">
    <!-- Header: ticker, direction, score, last updated -->
    <div class="insight-header">
        <div class="insight-ticker-row">
            <span class="insight-ticker">AAPL</span>
            <span class="insight-direction direction-long">LONG</span>
            <span class="insight-score score-strong">82</span>
        </div>
        <div class="insight-meta">
            <span class="insight-updated" title="2026-03-17T14:45:00">15m ago</span>
            <span class="insight-strategies">2 strategies</span>
        </div>
    </div>

    <!-- Primary setup -->
    <div class="insight-primary">
        <div class="insight-primary-label">Primary: Holy Grail 1H</div>
        <div class="insight-levels">
            <span>Entry: $178.50</span>
            <span>Stop: $176.20</span>
            <span>T1: $182.00</span>
        </div>
    </div>

    <!-- Confirming signals (only if distinct_strategy_count > 1) -->
    <div class="insight-confirming">
        <div class="insight-confirming-label">Confirming:</div>
        <div class="insight-confirming-item">
            <span class="confirming-strategy">Artemis LONG</span>
            <span class="confirming-time">2:15 PM</span>
        </div>
    </div>

    <!-- Score factors -->
    <div class="insight-factors">
        <span class="factor-pill">Base: 50</span>
        <span class="factor-pill">Bias: \u00d71.10</span>
        <span class="factor-pill factor-positive">Zone: +6</span>
        <span class="factor-pill factor-positive">R:R: +10</span>
    </div>

    <!-- Action buttons -->
    <div class="insight-actions">
        <button class="insight-btn insight-accept" onclick="actOnInsight('AAPL', 'LONG', 'ACCEPTED')">
            \u2713 Accept
        </button>
        <button class="insight-btn insight-reject" onclick="actOnInsight('AAPL', 'LONG', 'REJECTED')">
            \u2717 Pass
        </button>
    </div>
</div>
```

---

## Step 4: Relative Timestamp Helper

Add a helper function to convert ISO timestamps to relative times:

```javascript
function relativeTime(isoString) {
    if (!isoString) return '';
    const now = new Date();
    const then = new Date(isoString);
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    return `${Math.floor(diffHr / 24)}d ago`;
}
```

Use this for the `insight-updated` span: `relativeTime(group.last_signal_at)`

---

## Step 5: Score Factor Pills

Extract the top scoring factors from `primary_signal.triggering_factors` and render as pills:

```javascript
function renderScoreFactors(triggeringFactors) {
    if (!triggeringFactors) return '';
    const pills = [];
    const calc = triggeringFactors.calculation || {};

    if (calc.base_score) pills.push({ label: `Base: ${calc.base_score}`, type: 'neutral' });
    if (calc.alignment_multiplier && calc.alignment_multiplier !== 1.0) {
        const type = calc.alignment_multiplier > 1 ? 'positive' : 'negative';
        pills.push({ label: `Bias: \u00d7${calc.alignment_multiplier.toFixed(2)}`, type });
    }

    // Technical details
    const tech = triggeringFactors.technical_confluence?.details || {};
    for (const [key, val] of Object.entries(tech)) {
        if (val?.bonus && val.bonus !== 0) {
            const sign = val.bonus > 0 ? '+' : '';
            const type = val.bonus > 0 ? 'positive' : 'negative';
            const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            pills.push({ label: `${label}: ${sign}${val.bonus}`, type });
        }
    }

    // R:R bonus
    if (triggeringFactors.risk_reward?.bonus) {
        pills.push({ label: `R:R: +${triggeringFactors.risk_reward.bonus}`, type: 'positive' });
    }

    // Sector
    if (triggeringFactors.sector_priority?.bonus && triggeringFactors.sector_priority.bonus !== 0) {
        const sb = triggeringFactors.sector_priority.bonus;
        pills.push({ label: `Sector: ${sb > 0 ? '+' : ''}${sb}`, type: sb > 0 ? 'positive' : 'negative' });
    }

    return pills.slice(0, 6).map(p =>
        `<span class="factor-pill factor-${p.type}">${p.label}</span>`
    ).join('');
}
```

---

## Step 6: Accept/Reject Action Function

```javascript
async function actOnInsight(ticker, direction, action) {
    try {
        const resp = await fetch('/api/trade-ideas/group-action', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getAuthToken()}`
            },
            body: JSON.stringify({ action, ticker, direction })
        });
        if (!resp.ok) {
            console.error('Group action failed:', await resp.text());
            return;
        }

        // Immediately remove the card from the DOM
        const card = document.querySelector(
            `.insight-card[data-ticker="${ticker}"][data-direction="${direction}"]`
        );
        if (card) {
            card.style.transition = 'opacity 0.3s, transform 0.3s';
            card.style.opacity = '0';
            card.style.transform = action === 'ACCEPTED' ? 'translateX(50px)' : 'translateX(-50px)';
            setTimeout(() => card.remove(), 300);
        }
    } catch (e) {
        console.error('Insight action error:', e);
    }
}
```

---

## Step 7: Show All Toggle

Add a toggle in the Insights section header:

**Find** the Insights/Trade Ideas section header in `frontend/index.html`. Add:

```html
<label class="insights-toggle">
    <input type="checkbox" id="insights-show-all" onchange="refreshInsights()">
    <span>Show all scores</span>
</label>
```

Where `refreshInsights()` is whatever function currently re-fetches the grouped data.

---

## Step 8: CSS for New Card Layout

**In `frontend/styles.css`**, add:

```css
/* ===== Insight Card Redesign (Phase 6) ===== */
.insight-card {
    background: var(--card-bg, rgba(30, 30, 40, 0.8));
    border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    transition: opacity 0.3s, transform 0.3s;
}

.insight-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 8px;
}

.insight-ticker-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.insight-ticker {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary, #fff);
}

.insight-direction {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 3px;
    text-transform: uppercase;
}

.direction-long {
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
}

.direction-short {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
}

.insight-score {
    font-size: 18px;
    font-weight: 700;
    min-width: 32px;
    text-align: center;
}

.score-strong { color: #22c55e; }
.score-moderate { color: #f59e0b; }
.score-weak { color: #9ca3af; }

.insight-meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    font-size: 11px;
    color: var(--text-secondary, #9ca3af);
}

.insight-primary {
    padding: 8px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.insight-primary-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary, #fff);
    margin-bottom: 4px;
}

.insight-levels {
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: var(--text-secondary, #9ca3af);
}

.insight-confirming {
    padding: 6px 0;
    font-size: 12px;
}

.insight-confirming-label {
    color: var(--text-secondary, #9ca3af);
    margin-bottom: 4px;
    font-weight: 600;
}

.insight-confirming-item {
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
    color: var(--text-secondary, #9ca3af);
}

.confirming-strategy {
    color: #60a5fa;
}

.insight-factors {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 6px 0;
}

.factor-pill {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-secondary, #9ca3af);
}

.factor-positive {
    background: rgba(34, 197, 94, 0.1);
    color: #4ade80;
}

.factor-negative {
    background: rgba(239, 68, 68, 0.1);
    color: #f87171;
}

.insight-actions {
    display: flex;
    gap: 8px;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.insight-btn {
    flex: 1;
    padding: 6px 12px;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    transition: background 0.2s;
}

.insight-accept {
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
}

.insight-accept:hover {
    background: rgba(34, 197, 94, 0.25);
}

.insight-reject {
    background: rgba(156, 163, 175, 0.1);
    color: #9ca3af;
}

.insight-reject:hover {
    background: rgba(156, 163, 175, 0.2);
}

.insights-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
}

.insights-toggle input {
    cursor: pointer;
}
```

---

## Step 9: Score Color Helper

```javascript
function getScoreClass(score) {
    if (score >= 75) return 'score-strong';
    if (score >= 60) return 'score-moderate';
    return 'score-weak';
}
```

---

## Testing Checklist

1. **Card layout:** Each Insight card shows primary setup, confirming signals (if any), score factors, and action buttons
2. **Relative timestamp:** Cards show "Xm ago" or "Xh ago" based on most recent signal
3. **Confirming signals:** Only signals from DIFFERENT strategies appear. No duplicate Holy Grails.
4. **Accept button:** Clicking Accept slides the card right and removes it. It does not reappear on refresh.
5. **Reject button:** Clicking Pass slides the card left and removes it. It does not reappear on refresh.
6. **Suppression holds:** After rejecting AAPL LONG, new AAPL LONG signals arriving within 8 hours do not create a new card.
7. **Score threshold:** Default view only shows 70+ signals. "Show all" checkbox reveals lower scores.
8. **Score factors:** Factor pills correctly show base score, bias multiplier, and top technical bonuses
9. **Empty state:** When no signals qualify (all below 70 or all acted-on), show a clean empty state message

## Definition of Done
- [ ] Insight cards show three-section layout (primary / confirming / factors)
- [ ] Relative timestamp visible on each card
- [ ] Accept/Reject buttons work and immediately remove card
- [ ] Acted-on cards don't reappear on refresh (for 8 hours)
- [ ] Score threshold defaults to 70, toggle shows all
- [ ] Factor pills render top scoring contributors
- [ ] Confirming signals only show distinct strategies
- [ ] CSS matches existing dashboard theme
