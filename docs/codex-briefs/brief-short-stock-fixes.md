# Brief: Short Stock Position Fixes

## Problem

Three bugs prevent proper handling of short stock positions (e.g. CRCL — 5 shares shorted outright in RH):

1. **Frontend Edit Modal** — stock-blind: labels say "contracts", cost_basis uses `×100` (options multiplier) instead of `×1`, no way to directly edit quantity
2. **Frontend Close Flow** — PnL calculation for stock positions ignores direction. For SHORT stock, `(exit - entry)` produces inverted PnL (a profitable short shows as a loss)
3. **Backend Close Endpoint** — Same inverted PnL bug: `realized_pnl = (exit_price - entry_price) * close_qty` doesn't account for SHORT direction

## Files to Change

### 1. `frontend/app.js`

#### 1A. Edit Modal — stock-aware labels + cost_basis fix + direct qty field

**Location:** `function openPositionEditModal(position)` (~line 8678)

**IMPORTANT:** The `isStock` variable needs to be accessible in both the display code and save handler. Define it right after `const curEntry = position.entry_price || 0;`:

```javascript
const curQty = position.quantity || 0;
const curEntry = position.entry_price || 0;
const isStock = ['stock', 'stock_long', 'long_stock', 'stock_short', 'short_stock'].includes((position.structure || '').toLowerCase()) || (!position.structure && position.asset_type === 'EQUITY');
const unitLabel = isStock ? 'shares' : 'contracts';
```

**Find** the info display (around line 8763):
```javascript
infoEl.innerHTML = `<span>Current: ${curQty} contracts @ $${curEntry.toFixed(2)}</span>`;
```

**Replace with:**
```javascript
const dirLabel = position.direction === 'SHORT' ? ' (SHORT)' : '';
infoEl.innerHTML = `<span>Current: ${curQty} ${unitLabel}${dirLabel} @ $${curEntry.toFixed(2)}</span>`;
```

**Find** the "Additional Qty" label in the modal HTML (around line 8715):
```html
<label>Additional Qty</label>
```

**Replace with:**
```html
<label id="editAddQtyLabel">Additional Qty</label>
```

**Find** the "Cost per Contract" label in the modal HTML (around line 8718):
```html
<label>Cost per Contract</label>
```

**Replace with:**
```html
<label id="editAddCostLabel">Cost per Contract</label>
```

**After** the info display code, add:
```javascript
// Stock-aware labels
document.getElementById('editAddCostLabel').textContent = isStock ? 'Cost per Share' : 'Cost per Contract';
document.getElementById('editAddQtyLabel').textContent = isStock ? 'Additional Shares' : 'Additional Contracts';
```

**Find** the preview text (around line 8774):
```javascript
previewEl.innerHTML = `New: ${newTotalQty} contracts @ $${newAvgCost.toFixed(2)} avg`;
```

**Replace with:**
```javascript
previewEl.innerHTML = `New: ${newTotalQty} ${unitLabel} @ $${newAvgCost.toFixed(2)} avg`;
```

**Find** the cost_basis calculation in the save handler (around line 8793):
```javascript
updates.cost_basis = parseFloat((newAvgCost * newTotalQty * 100).toFixed(2));
```

**Replace with:**
```javascript
const costMultiplier = isStock ? 1 : 100;
updates.cost_basis = parseFloat((newAvgCost * newTotalQty * costMultiplier).toFixed(2));
```

**Add a direct Quantity field** to the modal HTML. Find the "Account" form-row block:
```html
<div class="form-row">
    <label>Account</label>
    <input type="text" id="editPositionAccount" readonly style="opacity: 0.6; cursor: not-allowed;">
</div>
```

**Insert AFTER it:**
```html
<div class="form-row">
    <label>Quantity</label>
    <input type="number" id="editQuantity" min="1" step="1">
</div>
```

**Populate it** after `document.getElementById('editPositionAccount').value = ...`:
```javascript
document.getElementById('editQuantity').value = position.quantity || '';
```

**In the save handler**, after the existing field extraction block (after `if (notes) updates.notes = notes;`), add quantity handling:
```javascript
const qtyVal = document.getElementById('editQuantity').value.trim();
if (qtyVal !== '' && parseInt(qtyVal) !== curQty) {
    updates.quantity = parseInt(qtyVal);
    // Recalculate cost_basis for new quantity at same entry price
    const costMultiplierDirect = isStock ? 1 : 100;
    updates.cost_basis = parseFloat((curEntry * parseInt(qtyVal) * costMultiplierDirect).toFixed(2));
}
```

Note: If BOTH direct quantity edit AND "Add to Position" are filled, the "Add to Position" values should take precedence (they already overwrite `updates.quantity` and `updates.cost_basis`).

#### 1B. Close Modal PnL — direction-aware for stock

**Location:** `function updateCloseSummary()` (~line 8227)

**Find:**
```javascript
if (isStock) {
    pnl = (exitPrice - closingPosition.entry_price) * closeQty;
}
```

**Replace with:**
```javascript
if (isStock) {
    if (closingPosition.direction === 'SHORT') {
        pnl = (closingPosition.entry_price - exitPrice) * closeQty;
    } else {
        pnl = (exitPrice - closingPosition.entry_price) * closeQty;
    }
}
```

#### 1C. Close Confirm PnL — same fix

**Location:** `async function confirmPositionClose()` (~line 8257)

**Find:**
```javascript
if (closeIsStock) {
    pnl = (exitPrice - entryPrice) * closeQty;
}
```

**Replace with:**
```javascript
if (closeIsStock) {
    if (closingPosition.direction === 'SHORT') {
        pnl = (entryPrice - exitPrice) * closeQty;
    } else {
        pnl = (exitPrice - entryPrice) * closeQty;
    }
}
```

### 2. `backend/api/unified_positions.py`

#### 2A. Close endpoint — direction-aware PnL for stock

**Location:** `async def close_position()` — the realized_pnl calculation block (~line 1088-1093)

**Find:**
```python
if is_stock:
    realized_pnl = round((req.exit_price - entry_price) * close_qty, 2)
```

**Replace with:**
```python
if is_stock:
    direction = (pos.get("direction") or "LONG").upper()
    if direction == "SHORT":
        realized_pnl = round((entry_price - req.exit_price) * close_qty, 2)
    else:
        realized_pnl = round((req.exit_price - entry_price) * close_qty, 2)
```

## Verification

After deploying:

1. **Edit modal:** Open CRCL edit — should show "5 shares (SHORT) @ $118.56", labels should say "shares" not "contracts", direct Quantity field should be editable
2. **Add to position:** Add 1 share at $120.00 → preview should show "6 shares @ $118.80 avg", cost_basis should be ~$712.80 (not ×100)
3. **Close flow:** Open CRCL close modal, enter exit price of $110.00 → PnL preview should show **+$42.80** (5 × ($118.56 - $110.00) = profit), NOT -$42.80
4. **Close a profitable short:** Should classify as WIN and NOT trigger loss classification modal
5. **Backend PnL:** `realized_pnl` in the response should be positive when closing a short at a lower price

## Notes

- The `_compute_unrealized_pnl()` helper function already handles SHORT stock correctly — this bug is isolated to the close flow and edit modal
- `executePositionClose()` sends `trade_outcome` from the frontend's PnL calc, so fixing the frontend also fixes outcome classification
- No test changes needed — existing tests don't cover short stock close PnL (consider adding one)
