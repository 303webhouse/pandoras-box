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

### C. Signal Deduplication — New Signals Merge Into Lightning Card

**This is critical UX logic.** When a scanner signal (Artemis, Phalanx, Scout, Trojan Horse, etc.) fires on a ticker that ALREADY has an active lightning card, the system should NOT create a separate signal card in the Insights feed. Instead, it should be absorbed into the existing lightning card as a confirmation.

**Backend change — in the signal ingestion path:**

Find where new scanner signals are inserted into the trade signals / insights pipeline (the function that creates new signal cards for the Insights panel). BEFORE inserting a new signal card, check if there's an active lightning card for the same ticker:

```python
# Before creating a new signal card, check for active lightning card match
async def check_lightning_card_match(ticker: str) -> Optional[str]:
    """Returns lightning card ID if an active card exists for this ticker, else None."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM lightning_cards WHERE ticker = $1 AND status = 'active'",
            ticker
        )
        return str(row["id"]) if row else None
```

If a match is found:
1. Do NOT create a new signal card in the Insights feed
2. Instead, append the signal to the lightning card's confirmation list:

```python
# Add the signal as a confirmation on the lightning card
async def add_lightning_confirmation(card_id: str, signal_data: dict):
    """Merge a new scanner signal into an existing lightning card as a confirmation."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Get existing confirmations
        row = await conn.fetchrow(
            "SELECT confirmations FROM lightning_cards WHERE id = $1", card_id
        )
        existing = json.loads(row["confirmations"]) if row and row["confirmations"] else []
        
        # Add new confirmation
        existing.append({
            "strategy": signal_data.get("strategy", "unknown"),
            "direction": signal_data.get("direction", ""),
            "score": signal_data.get("score", 0),
            "confirmed_at": datetime.now(timezone.utc).isoformat()
        })
        
        await conn.execute(
            """UPDATE lightning_cards 
               SET confirmations = $1, updated_at = NOW() 
               WHERE id = $2""",
            json.dumps(existing), card_id
        )
    
    # Push WebSocket update to trigger flash animation on frontend
    await manager.broadcast({
        "type": "lightning_confirmation",
        "card_id": card_id,
        "ticker": signal_data.get("ticker"),
        "strategy": signal_data.get("strategy"),
        "direction": signal_data.get("direction"),
        "score": signal_data.get("score")
    })
```

**NOTE:** This requires adding a `confirmations JSONB DEFAULT '[]'` column to the `lightning_cards` table. Add this migration in `init_database()`:

```sql
ALTER TABLE lightning_cards ADD COLUMN IF NOT EXISTS confirmations JSONB DEFAULT '[]';
```

**Frontend change — flash animation on confirmation:**

When the WebSocket receives a `lightning_confirmation` message, the lightning card should visually flash to draw attention:

```javascript
// In the WebSocket onmessage handler:
if (msg.type === 'lightning_confirmation') {
    const card = document.querySelector(`[data-lightning-id="${msg.card_id}"]`);
    if (card) {
        // Add the new confirmation to the confluence strip
        let strip = card.querySelector('.lightning-confluence');
        if (!strip) {
            // Create the strip if it doesn't exist yet
            const actionsEl = card.querySelector('.lightning-actions');
            strip = document.createElement('div');
            strip.className = 'lightning-confluence';
            strip.innerHTML = '<span class="confluence-label">Hub confirms:</span>';
            actionsEl.parentNode.insertBefore(strip, actionsEl);
        }
        
        const badge = document.createElement('span');
        badge.className = 'confluence-signal flash-new';
        badge.textContent = `${msg.strategy} ${msg.direction} ${msg.score}`;
        strip.appendChild(badge);
        
        // Flash the entire card border
        card.classList.add('lightning-confirmed');
        setTimeout(() => card.classList.remove('lightning-confirmed'), 3000);
    }
}
```

**CSS for flash animation:**

```css
/* Lightning card confirmation flash */
.lightning-confirmed {
    animation: lightning-pulse 0.5s ease-in-out 3;
}

@keyframes lightning-pulse {
    0%, 100% { border-color: #334; }
    50% { border-color: #c9a04e; box-shadow: 0 0 8px rgba(201, 160, 78, 0.3); }
}

/* New confirmation badge flash-in */
.confluence-signal.flash-new {
    animation: badge-flash 0.6s ease-out;
}

@keyframes badge-flash {
    0% { background: #c9a04e; color: #0a0e17; transform: scale(1.2); }
    100% { background: #c9a04e22; color: #c9a04e; transform: scale(1); }
}
```

**The result:** When SMH has a lightning card active and then Artemis fires a SELL signal on SMH 20 minutes later, instead of a separate "Artemis SMH SELL" card cluttering the Insights feed, the existing SMH lightning card pulses gold three times and a new "Artemis SELL 72" badge flashes into the confluence strip. One card, multiple confirmations, zero clutter.

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
