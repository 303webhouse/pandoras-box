# BUG FIX: Lightning Card Display in Insights Panel
## Priority: Quick fix (do alongside Brief A)
## Date: 2026-04-01

---

## THE BUG

Lightning Cards (from `/api/hydra/lightning`) render in the Insights/trade signals panel but are **visually truncated**. Only the top row (ticker + SQUEEZE LONG badge + close button) is visible. The card body (entry price, stop, target, score badges, Analyze/Accept/Pass buttons) is clipped/hidden.

Screenshot confirms: SMH lightning card appears at top of Insights but is cut off after the header row.

## HOW TO FIND THE CODE

1. In `frontend/app.js`, search for `lightning` or `/hydra/lightning` to find where lightning cards are fetched and rendered
2. In `frontend/styles.css`, search for `lightning` to find the card styling
3. The card is rendered INSIDE the `#tradeSignals` container (the signals-container div in the Insights panel)

## LIKELY CAUSES (check in order)

1. **The lightning card container has `overflow: hidden` or a fixed `max-height`** that clips the card body. Remove or increase the height constraint.

2. **The card body section has `display: none` or `height: 0`** by default and the expand/toggle logic isn't firing on render. Check if there's a collapsed state that isn't being toggled open.

3. **The parent `.signals-container` or `.trades-panel`** has CSS that constrains child height. Lightning cards may need different overflow rules than regular signal cards.

4. **Z-index stacking issue** where the card body renders behind the next signal card (LUNR in the screenshot). Check if the lightning card needs `position: relative` and proper stacking.

## FIX APPROACH

Find the lightning card HTML template in app.js. Ensure the full card body (with entry/stop/target row, score badges row, and action buttons row) is visible and not collapsed. The card should look like the regular LUNR/UNIT signal cards below it — same height, same structure, same visibility.

## VERIFICATION

After fix, the SMH lightning card should show all rows:
- Header: Ticker + SQUEEZE LONG badge + close button
- Body: Entry price, Stop, Target
- Badges: Base score, component scores
- **Recent signals strip** (see below)
- Actions: Analyze, Accept, Pass buttons

---

## ADDITIONAL FEATURE: Action Buttons + Recent Signal Cross-Reference

### A. Action Buttons (Analyze / Accept / Pass)

Lightning cards currently lack the Analyze/Accept/Pass buttons that regular signal cards have in the Insights panel. Add them.

Find the lightning card HTML template in app.js (search for the function that renders lightning cards into `#tradeSignals`). At the bottom of each card, add an action button row matching the existing signal card pattern:

```html
<div class="lightning-actions">
    <button class="lightning-btn analyze" onclick="analyzeLightningCard('{card_id}', '{ticker}')">Analyze</button>
    <button class="lightning-btn accept" onclick="acceptLightningCard('{card_id}')">Accept</button>
    <button class="lightning-btn pass" onclick="passLightningCard('{card_id}')">Pass</button>
</div>
```

**Button behavior:**
- **Analyze**: Opens the Single Ticker Analyzer modal for that ticker (reuse existing `analyzeTickerFromSignal()` or similar function). If no such function exists, populate the analyzer input with the ticker and trigger the analyze button click.
- **Accept**: PATCH `/api/hydra/lightning/{card_id}/status` with `{"status": "acted_on"}`. This marks the card as accepted and can visually dim it or add a checkmark. The trader has acknowledged it and may act on it.
- **Pass**: PATCH `/api/hydra/lightning/{card_id}/status` with `{"status": "dismissed"}`. Removes the card from the active feed.

Style the buttons to match existing signal card action buttons. Use the same class names if possible, or create `.lightning-actions` / `.lightning-btn` styles that mirror them.

### B. Recent Signal Cross-Reference (last 30 minutes)

Each lightning card should show whether the hub's other scanners have independently flagged the same ticker recently. This is a confluence indicator — "Hydra sees a squeeze setup AND Artemis fired a signal on the same ticker 20 min ago" = higher conviction.

**Backend addition** — in the lightning card endpoint (`GET /api/hydra/lightning`), for each active card, query for recent signals on the same ticker:

```python
# For each lightning card, check for recent corroborating signals
for card in cards:
    ticker = card.get("ticker")
    if ticker:
        recent_signals = await conn.fetch("""
            SELECT strategy, direction, score, created_at
            FROM trade_signals
            WHERE ticker = $1
            AND created_at > NOW() - INTERVAL '30 minutes'
            AND status != 'expired'
            ORDER BY created_at DESC
            LIMIT 3
        """, ticker)
        card["recent_signals"] = [dict(s) for s in recent_signals] if recent_signals else []
```

NOTE: The table name for signals may be `trade_signals`, `signals`, or `scanner_signals` — check the actual schema. Search for whichever table stores Artemis/Phalanx/Scout/Trojan Horse output.

**Frontend rendering** — if `recent_signals` is non-empty, show a compact strip on the card above the action buttons:

```html
<div class="lightning-confluence">
    <span class="confluence-label">Hub signals (30m):</span>
    <span class="confluence-signal">Artemis SELL 72</span>
    <span class="confluence-signal">Scout SELL 65</span>
</div>
```

If no recent signals, show nothing (don't render the strip at all — clean and quiet when there's no confluence).

**CSS for new elements:**

```css
.lightning-actions {
    display: flex;
    gap: 4px;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 0.5px solid #1a1f2e;
}

.lightning-btn {
    flex: 1;
    padding: 4px 8px;
    border: 0.5px solid #334;
    border-radius: 3px;
    background: transparent;
    color: #889;
    font-size: 9px;
    cursor: pointer;
    transition: all 0.2s;
}

.lightning-btn.analyze:hover { border-color: #c9a04e; color: #c9a04e; }
.lightning-btn.accept:hover { border-color: #00e676; color: #00e676; }
.lightning-btn.pass:hover { border-color: #e5370e; color: #e5370e; }

.lightning-confluence {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 4px;
    flex-wrap: wrap;
}

.confluence-label {
    color: #556;
    font-size: 8px;
}

.confluence-signal {
    background: #c9a04e22;
    color: #c9a04e;
    padding: 1px 6px;
    border-radius: 2px;
    font-size: 8px;
    font-weight: 500;
}
```
