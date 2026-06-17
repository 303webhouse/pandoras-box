# Fix: Options Position Pricing & P&L (Iron Condor + Multi-Leg)

## Problem
Options positions show wildly wrong P&L because:
1. **Mark is wrong** — positions show underlying stock price or stale data instead of net spread mark
2. **No auto-refresh for options** — there's no endpoint that fetches current option leg prices from Polygon.io
3. **Iron condors unsupported** — `get_spread_value()` only handles 2-leg same-type spreads (all puts or all calls)

Example: IBIT iron condor shows Mark: $5.27 and P&L: +$756 when reality is -$6.

## Architecture

The backend P&L formula (`_compute_unrealized_pnl()` in unified_positions.py) is already correct — it properly handles credit vs debit structures. The bug is that `current_price` never gets set to the right value for options.

**Existing infrastructure (already built, just not wired up):**
- `backend/integrations/polygon_options.py` has `get_options_snapshot()`, `find_contract()`, `get_contract_mid()`, `get_spread_value()`
- `_compute_unrealized_pnl()` in unified_positions.py correctly uses `CREDIT_STRUCTURES`
- Polygon API key is configured, chain caching works (5-min TTL)
- `legs` JSONB column exists on `unified_positions` table

## Fix: 3 parts

### Part 1 — `polygon_options.py`: Add `get_multi_leg_value()`
### Part 2 — `unified_positions.py`: Add `POST /v2/positions/refresh-prices`
### Part 3 — `frontend/app.js`: Call refresh endpoint instead of stock price

---

## Part 1: Multi-Leg Pricer

**File:** `backend/integrations/polygon_options.py`

### Step 1A: Add `get_multi_leg_value()` after `get_spread_value()`

Find this line:
```python
async def get_single_option_value(
```

Insert BEFORE it:
```python
async def get_multi_leg_value(
    underlying: str,
    legs: List[Dict[str, Any]],
    expiry: str,
) -> Optional[Dict[str, Any]]:
    """
    Price a multi-leg options position (iron condor, straddle, strangle, etc.).

    Each leg dict must have:
        action: "BUY" or "SELL"
        option_type: "call" or "put" (or "CALL"/"PUT")
        strike: float
        quantity: int (optional, defaults to 1)
        premium: float (optional, entry premium for reference)

    Returns:
        net_mark: current net value per share (what you'd pay/receive to close)
        leg_details: list of per-leg pricing data
        underlying_price: current underlying price
    """
    if not legs:
        return None

    # Determine strike range and types needed
    strikes = [float(leg["strike"]) for leg in legs]
    needs_puts = any(leg.get("option_type", "").lower() == "put" for leg in legs)
    needs_calls = any(leg.get("option_type", "").lower() == "call" for leg in legs)

    strike_lo = min(strikes) - 0.5
    strike_hi = max(strikes) + 0.5
    exp_str = str(expiry)[:10]

    # Fetch chain — if we need both puts and calls, fetch without type filter
    if needs_puts and needs_calls:
        chain = await get_options_snapshot(
            underlying,
            expiration_date=exp_str,
            strike_gte=strike_lo,
            strike_lte=strike_hi,
        )
    elif needs_puts:
        chain = await get_options_snapshot(
            underlying, expiration_date=exp_str,
            strike_gte=strike_lo, strike_lte=strike_hi,
            contract_type="put",
        )
    else:
        chain = await get_options_snapshot(
            underlying, expiration_date=exp_str,
            strike_gte=strike_lo, strike_lte=strike_hi,
            contract_type="call",
        )

    if not chain:
        return None

    net_mark = 0.0
    leg_details = []
    underlying_price = None

    for leg in legs:
        opt_type = leg.get("option_type", "").lower()
        strike = float(leg["strike"])
        action = leg.get("action", "BUY").upper()
        qty = leg.get("quantity", 1)

        contract = find_contract(chain, strike, expiry, opt_type)
        if not contract:
            logger.warning(
                "Multi-leg: missing %s %s %s %s",
                underlying, strike, exp_str, opt_type,
            )
            return None  # Can't price incomplete position

        mid = get_contract_mid(contract)
        if mid is None:
            logger.warning("Multi-leg: no mid for %s %s %s", underlying, strike, opt_type)
            return None

        # BUY legs add to position value, SELL legs subtract
        sign = 1 if action == "BUY" else -1
        net_mark += mid * sign * qty

        if not underlying_price:
            ua = contract.get("underlying_asset", {})
            if ua and ua.get("price"):
                underlying_price = float(ua["price"])

        leg_details.append({
            "action": action,
            "option_type": opt_type,
            "strike": strike,
            "quantity": qty,
            "mid": mid,
            "greeks": get_contract_greeks(contract),
        })

    # Normalize net_mark per single contract set (divide by max leg qty if legs have different quantities)
    # For standard iron condors all legs have qty=1 per contract set
    # net_mark is already per-share (not multiplied by 100)

    return {
        "net_mark": round(net_mark, 4),
        "leg_details": leg_details,
        "underlying_price": underlying_price,
    }


```

---

## Part 2: Refresh Prices Endpoint

**File:** `backend/api/unified_positions.py`

### Step 2A: Add the refresh-prices endpoint

Find this line (the greeks endpoint, around line 740):
```python
@router.get("/v2/positions/greeks")
```

Insert BEFORE it:
```python
@router.post("/v2/positions/refresh-prices")
async def refresh_position_prices():
    """
    Refresh current_price and unrealized_pnl for all OPEN positions.

    For OPTION positions:
      - If legs JSONB exists: use get_multi_leg_value() to price all legs via Polygon
      - If no legs but has long_strike + short_strike: use get_spread_value() via Polygon
      - If single leg: use get_single_option_value() via Polygon
    For EQUITY/STOCK positions:
      - Use yfinance for stock price (existing behavior)

    Updates current_price, unrealized_pnl, cost_basis, and price_updated_at in DB.
    Returns summary of what was updated.
    """
    from integrations.polygon_options import (
        get_multi_leg_value,
        get_spread_value,
        get_single_option_value,
        POLYGON_API_KEY,
    )

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM unified_positions WHERE status = 'OPEN'"
        )

    if not rows:
        return {"status": "no_positions", "updated": 0, "errors": []}

    updated = 0
    errors = []
    results = []

    for row in rows:
        pos = _row_to_dict(row)
        pos_id = pos["position_id"]
        ticker = pos["ticker"]
        structure = (pos.get("structure") or "").lower()
        asset_type = (pos.get("asset_type") or "").upper()
        entry_price = pos.get("entry_price")
        quantity = pos.get("quantity") or 1
        direction = pos.get("direction") or ""
        expiry = pos.get("expiry")

        is_stock = structure in ("stock", "stock_long", "long_stock", "stock_short", "short_stock") or (not structure and asset_type == "EQUITY")

        new_price = None

        try:
            if is_stock:
                # Stock: use yfinance
                try:
                    import yfinance as yf
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d")
                    if not hist.empty:
                        new_price = round(float(hist["Close"].iloc[-1]), 2)
                except Exception as e:
                    errors.append({"position_id": pos_id, "ticker": ticker, "error": f"yfinance: {e}"})
                    continue

            elif asset_type == "OPTION" and POLYGON_API_KEY:
                # Options: try legs first, then spread, then single
                legs_data = pos.get("legs")
                if legs_data:
                    # Parse legs from JSONB
                    if isinstance(legs_data, str):
                        legs_data = json.loads(legs_data)

                    if isinstance(legs_data, list) and len(legs_data) >= 2:
                        result = await get_multi_leg_value(ticker, legs_data, expiry or "")
                        if result and result.get("net_mark") is not None:
                            new_price = abs(result["net_mark"])
                            # For multi-leg, net_mark sign tells us:
                            # positive = net debit position (costs to close)
                            # negative = net credit position to close (you'd receive)
                            # We store the absolute value as current_price;
                            # _compute_unrealized_pnl handles credit/debit via CREDIT_STRUCTURES

                elif pos.get("long_strike") and pos.get("short_strike"):
                    # 2-leg spread without legs JSONB
                    result = await get_spread_value(
                        ticker,
                        float(pos["long_strike"]),
                        float(pos["short_strike"]),
                        str(expiry or ""),
                        structure,
                    )
                    if result and result.get("spread_value") is not None:
                        new_price = abs(result["spread_value"])

                elif pos.get("long_strike"):
                    # Single leg
                    opt_type = "put" if "put" in structure else "call"
                    result = await get_single_option_value(
                        ticker,
                        float(pos["long_strike"]),
                        str(expiry or ""),
                        opt_type,
                    )
                    if result and result.get("option_value") is not None:
                        new_price = result["option_value"]

            if new_price is not None and entry_price is not None:
                unrealized = _compute_unrealized_pnl(
                    entry_price, new_price, quantity, structure,
                    asset_type=asset_type, direction=direction,
                )
                cost_basis = abs(entry_price) * quantity * (1 if is_stock else 100)

                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE unified_positions
                        SET current_price = $2, unrealized_pnl = $3,
                            cost_basis = $4, price_updated_at = NOW(), updated_at = NOW()
                        WHERE position_id = $1
                    """, pos_id, new_price, unrealized, cost_basis)

                updated += 1
                results.append({
                    "position_id": pos_id,
                    "ticker": ticker,
                    "structure": structure,
                    "current_price": new_price,
                    "unrealized_pnl": unrealized,
                })
            elif new_price is None:
                errors.append({"position_id": pos_id, "ticker": ticker, "error": "Could not fetch price"})

        except Exception as e:
            logger.error("Price refresh failed for %s %s: %s", pos_id, ticker, e)
            errors.append({"position_id": pos_id, "ticker": ticker, "error": str(e)})

    # Broadcast update to websocket clients
    try:
        await manager.broadcast_position_update({
            "action": "PRICES_REFRESHED",
            "updated": updated,
        })
    except Exception:
        pass

    return {
        "status": "ok",
        "updated": updated,
        "total_positions": len(rows),
        "errors": errors,
        "results": results,
    }


```

---

## Part 3: Frontend Price Refresh

**File:** `frontend/app.js`

The frontend currently fetches underlying stock prices for position cards. For options positions, it should call the new `POST /v2/positions/refresh-prices` endpoint instead and use the backend-computed `unrealized_pnl` and `current_price`.

### Step 3A: Find the price refresh function

Search `app.js` for the function that updates position card prices. It likely:
- Iterates over open positions
- Calls `GET /api/hybrid/price/{ticker}` or similar for each ticker
- Updates the Mark and Unrealized P&L display on the card

**Replace the price fetch logic** so that:
1. For OPTION positions (identified by `asset_type === 'OPTION'` or `position_type !== 'stock'`), do NOT fetch `hybrid/price/{ticker}`
2. Instead, call `POST /v2/positions/refresh-prices` ONCE on page load (or on a refresh button click)
3. After the endpoint returns, re-fetch the positions list (`GET /v2/positions?status=OPEN&asset_type=OPTION`) to get the updated `current_price` and `unrealized_pnl` from the DB
4. Render the card using the backend-provided `unrealized_pnl` — do NOT compute P&L client-side

### Step 3B: Add a "Refresh Prices" button to the options positions UI

Add a button near the options position list header that calls the refresh endpoint:

```javascript
// Add this button in the options positions header area
const refreshBtn = document.createElement('button');
refreshBtn.textContent = '↻ Refresh Prices';
refreshBtn.className = 'btn-refresh-prices';
refreshBtn.onclick = async () => {
    refreshBtn.disabled = true;
    refreshBtn.textContent = '↻ Refreshing...';
    try {
        const resp = await fetch(`${API_URL}/v2/positions/refresh-prices`, {
            method: 'POST',
            headers: authHeaders(),
        });
        const data = await resp.json();
        console.log('Prices refreshed:', data);
        // Reload positions to show updated P&L
        await loadOptionsPositions();
    } catch (e) {
        console.error('Price refresh failed:', e);
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.textContent = '↻ Refresh Prices';
    }
};
```

### Step 3C: Update position card rendering

In the position card template, ensure the card uses the backend-provided values:
- `Mark` should display `position.current_price` from the API response (not a client-side fetch)
- `Unrealized P&L` should display `position.unrealized_pnl` from the API response
- If `current_price` is null or `price_updated_at` is missing, show "—" with "Needs refresh" tooltip
- Show `price_updated_at` as relative time (e.g. "2m ago", "15m ago") next to the Mark value

### Step 3D: Auto-refresh on options tab load

When the options tab is opened, automatically trigger a price refresh:

```javascript
// In the options tab initialization or tab switch handler:
async function loadOptionsPositions() {
    // First trigger a price refresh from Polygon
    try {
        await fetch(`${API_URL}/v2/positions/refresh-prices`, {
            method: 'POST',
            headers: authHeaders(),
        });
    } catch (e) {
        console.warn('Auto price refresh failed:', e);
    }

    // Then load positions (which now have updated prices)
    // ... existing position loading code ...
}
```

**Important: Do NOT refresh prices on every card render or scroll — only on tab load and manual button click.** Polygon Starter plan has 5 calls/min rate limit. One refresh-prices call handles all positions in a single batch.

### Step 3E: Style for the refresh button

Add to `frontend/styles.css`:

```css
.btn-refresh-prices {
    background: transparent;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    padding: 6px 14px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.2s;
}
.btn-refresh-prices:hover {
    border-color: var(--accent-primary);
    color: var(--accent-primary);
}
.btn-refresh-prices:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
```

---

## Data Flow After Fix

```
User opens Options tab
  → Frontend calls POST /v2/positions/refresh-prices
    → Backend loops OPEN positions:
      → STOCK: yfinance stock price
      → OPTION with legs: Polygon get_multi_leg_value() → net all legs
      → OPTION spread (no legs): Polygon get_spread_value()
      → OPTION single: Polygon get_single_option_value()
    → Writes current_price + unrealized_pnl to DB
    → Returns summary
  → Frontend calls GET /v2/positions?status=OPEN&asset_type=OPTION
    → Gets positions with correct current_price and unrealized_pnl
  → Renders cards with backend-computed P&L (no client-side math)
```

## Iron Condor Example (IBIT)

```
Legs stored in JSONB:
  [{"action":"BUY","option_type":"put","strike":36,"quantity":1,"premium":1.30},
   {"action":"SELL","option_type":"put","strike":30,"quantity":1,"premium":0.40},
   {"action":"BUY","option_type":"call","strike":45,"quantity":1,"premium":0.84},
   {"action":"SELL","option_type":"call","strike":50,"quantity":1,"premium":0.25}]

Polygon fetches mids: 36P=$1.19, 30P=$0.36, 45C=$0.87, 50C=$0.26
net_mark = (1.19 × BUY) + (-0.36 × SELL) + (0.87 × BUY) + (-0.26 × SELL)
         = 1.19 - 0.36 + 0.87 - 0.26 = 1.44

current_price stored as 1.44 (absolute value of net debit to close)
entry_price = 1.49 (net debit paid at open)
structure = "iron_condor" → NOT in CREDIT_STRUCTURES

Wait — iron_condor IS in CREDIT_STRUCTURES. But this IBIT position was entered
as a NET DEBIT ($1.49 paid). This is a debit iron condor (wings cost more than
credit received from short strikes).

IMPORTANT: The _compute_unrealized_pnl() function checks CREDIT_STRUCTURES,
but iron condors can be EITHER credit or debit depending on strike selection.
This one is net debit. Need to verify the structure field stored in DB.
```

## CRITICAL SUBTLETY: Iron Condor Credit vs Debit

An iron condor can be either:
- **Net credit** (short strikes closer to ATM than long strikes → received premium)
- **Net debit** (long strikes closer to ATM than short strikes → paid premium)

Nick's IBIT position is a **net debit** iron condor (paid $1.49). But `iron_condor` is in `CREDIT_STRUCTURES`, which would compute P&L as `(entry - current)` instead of `(current - entry)`.

**Fix needed in `_compute_unrealized_pnl()`:** Instead of hardcoding iron_condor as credit, check the sign of entry_price or add a `is_credit` flag to the position.

### Step 2B: Fix P&L formula for ambiguous structures

In `backend/api/unified_positions.py`, update `_compute_unrealized_pnl()`:

Find:
```python
    if s in CREDIT_STRUCTURES:
        # Credit: received premium at open, pay to close → profit when current < entry
        return round((entry_price - current_price) * 100 * quantity, 2)
    # Debit: paid premium at open → profit when current > entry
    return round((current_price - entry_price) * 100 * quantity, 2)
```

Replace with:
```python
    if s in CREDIT_STRUCTURES:
        # Most credit structures: received premium at open, pay to close
        # Exception: iron condors/butterflies can be net debit depending on strikes
        # For multi-leg structures, the entry_price sign should determine credit vs debit:
        #   positive entry_price = net debit (paid to open) → debit formula
        #   negative entry_price = net credit (received to open) → credit formula
        # However, we always store entry_price as positive absolute value.
        # So we need a separate flag or heuristic.
        #
        # Heuristic: if structure is iron_condor or iron_butterfly AND direction
        # check doesn't help, look at whether entry_price > max_spread_width/2
        # (i.e., debit iron condors cost more than half the wing width)
        #
        # Simplest fix: check a 'trade_type' or 'is_credit' field if present,
        # otherwise fall through to the direction-based check.
        # For now, use 'direction' field: LONG iron condor = debit, SHORT = credit
        if s in ("iron_condor", "iron_butterfly"):
            if d == "LONG":
                # Debit iron condor: paid to open → profit when value increases
                return round((current_price - entry_price) * 100 * quantity, 2)
            # SHORT or unset → treat as credit (traditional)
        # Standard credit: profit when current < entry
        return round((entry_price - current_price) * 100 * quantity, 2)
    # Debit: paid premium at open → profit when current > entry
    return round((current_price - entry_price) * 100 * quantity, 2)
```

**Also: verify that the IBIT position has `direction = 'LONG'` in the DB.** If not, CC should update it via a DB migration or add logic to infer it from the legs.

---

## Verification After Deploy

### Verify IBIT Position
1. Confirm IBIT position has `legs` JSONB populated with all 4 legs
2. Confirm `direction` is `LONG` (since this is a debit iron condor)
3. Call `POST /v2/positions/refresh-prices`
4. Check response: IBIT `current_price` should be ~1.44 (not 5.27)
5. Check response: IBIT `unrealized_pnl` should be ~-$10 range (not +$756)
6. Verify frontend card shows correct Mark and P&L

### Verify Other Positions
- XLE call spread: should price correctly as 2-leg spread
- IGV put spread: should price correctly as 2-leg spread
- XLF put spread: should price correctly as 2-leg spread
- TSLQ stock: should still use yfinance (no change)

---

## Files Modified
- `backend/integrations/polygon_options.py` — add `get_multi_leg_value()` function
- `backend/api/unified_positions.py` — add `POST /v2/positions/refresh-prices` endpoint + fix `_compute_unrealized_pnl()` for debit iron condors
- `frontend/app.js` — call refresh endpoint, use backend P&L, add refresh button
- `frontend/styles.css` — refresh button styles

## Dependencies
- Polygon.io API key (already configured)
- yfinance (already installed)
- No new packages needed

## Polygon Rate Limits
- Starter plan: 5 calls/min
- Each refresh-prices call may make 1-3 Polygon API calls per options ticker (chain snapshots are cached 5 min)
- For 4 options positions on 3 tickers, that's ~3 API calls total (within limits)
- Frontend should NOT auto-refresh more than once per 5 minutes
