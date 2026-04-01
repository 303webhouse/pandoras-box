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
- Actions: Analyze, Accept, Pass buttons
