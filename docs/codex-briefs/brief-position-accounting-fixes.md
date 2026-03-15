# Brief: Position Accounting Fixes — Short Stock Cash, Closing Bell MTM, Stale Detection

## Context

Follow-up to `brief-short-stock-fixes.md` which covered frontend/close PnL direction.
This brief fixes the **backend accounting** bugs that cause portfolio balance mismatches.

Root cause discovered via CRCL (5 shares shorted in RH): cash adjustment on create
treated short stock as a debit (subtracted cash) when it should be a credit (added cash).
Combined with the summary formula bug, this caused a ~$1,100 discrepancy vs RH actual.

**Manual fixes already applied (do NOT revert):**
- CRCL direction corrected to SHORT, P&L recalculated to -$4.20
- RH cash reconciled to $3,628.23
- IGV cost_basis corrected to $332.00
- UNG structure changed to call_debit_spread with short_strike=20.0

## Files to Change

1. `backend/api/unified_positions.py` — 6 fixes
2. `backend/main.py` — 1 fix (closing bell MTM)

---

## Fix 1: Short stock cash adjustment on CREATE (~line 485)

**Bug:** Short stock sells shares and receives cash proceeds. Code always subtracts
cost_basis for non-credit structures, including short stock.

**Find:**
```python
    # Auto-adjust cash: deduct cost for debit, add premium for credit
    cash_ok = True
    if cost_basis:
        s = (req.structure or "").lower()
        cash_delta = cost_basis if s in CREDIT_STRUCTURES else -cost_basis
```

**Replace with:**
```python
    # Auto-adjust cash: deduct cost for debit, add premium for credit
    # Short stock: selling shares generates cash proceeds (like a credit)
    cash_ok = True
    if cost_basis:
        s = (req.structure or "").lower()
        d = (direction or "").upper()
        is_short_equity = d == "SHORT" and s in ("stock", "stock_short", "short_stock", "")
        cash_delta = cost_basis if (s in CREDIT_STRUCTURES or is_short_equity) else -cost_basis
```

Note: `direction` variable is already in scope at this point (set earlier in the function
from `req.direction` or auto-inferred from `calculate_position_risk`).

---

## Fix 2: Short stock cash adjustment on ADD-TO-EXISTING (~line 391)

**Find:**
```python
        # Adjust cash for the added portion only
        add_cost = abs(add_entry) * add_qty * (1 if is_stock else 100)
        cash_ok = True
        if add_cost:
            cash_delta = add_cost if s in CREDIT_STRUCTURES else -add_cost
```

**Replace with:**
```python
        # Adjust cash for the added portion only
        add_cost = abs(add_entry) * add_qty * (1 if is_stock else 100)
        cash_ok = True
        if add_cost:
            d_existing = (existing.get("direction") or "").upper()
            is_short_equity = d_existing == "SHORT" and is_stock
            cash_delta = add_cost if (s in CREDIT_STRUCTURES or is_short_equity) else -add_cost
```

Note: `existing` is the fetched position dict, `is_stock` and `s` are already in scope.

---

## Fix 3: Short stock cash adjustment on CLOSE (~line 1247)

**Bug:** Closing a short stock means buying back shares = cash outflow. But code treats
it as cash inflow (like selling a long position).

**Find:**
```python
    # Auto-adjust cash for the closed portion
    close_cash_ok = True
    if req.exit_price is not None:
        multiplier = 1 if is_stock else 100
        exit_value = round(abs(req.exit_price) * multiplier * close_qty, 2)
        cash_delta = -exit_value if s in CREDIT_STRUCTURES else exit_value
```

**Replace with:**
```python
    # Auto-adjust cash for the closed portion
    # Short stock close = buying back shares = cash outflow
    close_cash_ok = True
    if req.exit_price is not None:
        multiplier = 1 if is_stock else 100
        exit_value = round(abs(req.exit_price) * multiplier * close_qty, 2)
        d_close = (pos.get("direction") or "").upper()
        is_short_equity = d_close == "SHORT" and is_stock
        cash_delta = -exit_value if (s in CREDIT_STRUCTURES or is_short_equity) else exit_value
```

---

## Fix 4: Short stock cash reversal on DELETE (~line 1337)

**Find:**
```python
        s = (pos.get("structure") or "").lower()
        cost = float(pos["cost_basis"])
        # Reverse: credit structures added cash at open → now subtract. Debit subtracted → now add.
        cash_delta = -cost if s in CREDIT_STRUCTURES else cost
```

**Replace with:**
```python
        s = (pos.get("structure") or "").lower()
        cost = float(pos["cost_basis"])
        d_del = (pos.get("direction") or "").upper()
        is_short_equity = d_del == "SHORT" and s in ("stock", "stock_short", "short_stock", "")
        # Reverse: credit structures added cash at open → now subtract. Debit subtracted → now add.
        cash_delta = -cost if (s in CREDIT_STRUCTURES or is_short_equity) else cost
```

---

## Fix 5: Summary position_value formula for short stock (~line 676)

**Bug:** Code does `position_value += pnl` for short stock, with comment "proceeds already
in cash." But when cash is reconciled to the broker's actual value (which DOES include
proceeds), this overcounts by exactly cost_basis. The correct accounting is:
position_value = -(current_price * qty) = pnl - cost_basis (the buyback liability).

**Find:**
```python
        if is_short_stock:
            # Short stock: the position is a liability (cost to buy back)
            # Net value = unrealized P&L only (proceeds already in cash)
            pnl = p.get("unrealized_pnl") or 0
            total_position_value += pnl
```

**Replace with:**
```python
        if is_short_stock:
            # Short stock: position is a liability (cost to buy back)
            # Value = -(current_price * qty) = unrealized_pnl - cost_basis
            # This correctly represents the buyback liability when cash
            # already includes the short sale proceeds (as reported by broker)
            pnl = p.get("unrealized_pnl") or 0
            cost = p.get("cost_basis") or 0
            total_position_value += pnl - cost
```

---

## Fix 6: Update endpoint — recalc PnL on direction or structure change (~line 976)

**Bug:** Changing direction from LONG to SHORT (or vice versa) doesn't trigger PnL
recalculation. Must re-send current_price manually as workaround.

**Find:**
```python
    # Recalculate unrealized P&L if current_price or entry_price was updated
    if (req.current_price is not None or req.entry_price is not None or req.quantity is not None) and result.get("entry_price") and result.get("current_price"):
```

**Replace with:**
```python
    # Recalculate unrealized P&L if price, quantity, direction, or structure changed
    if (req.current_price is not None or req.entry_price is not None or req.quantity is not None or req.direction is not None or req.structure is not None) and result.get("entry_price") and result.get("current_price"):
```

---

## Fix 7: Closing bell MTM run (backend/main.py ~line 124)

**Bug:** MTM loop runs every 15 min during market hours but stops at 5 PM ET. Last run
is often ~3:15-3:45 PM, meaning weekend/overnight prices don't reflect Friday close.

**Find:**
```python
    async def mark_to_market_loop():
        """Fetch live Polygon prices for open positions during market hours."""
        import pytz
        from datetime import datetime as dt_cls

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                # Market hours + buffer: 9:00 AM - 4:30 PM ET, weekdays
                if et.weekday() < 5 and 9 <= et.hour < 17:
                    from api.unified_positions import run_mark_to_market
                    result = await run_mark_to_market()
                    updated = result.get("updated", 0)
                    errors = result.get("errors", [])
                    if updated > 0:
                        logger.info("📊 Mark-to-market: updated %d positions", updated)
                    if errors:
                        logger.warning("📊 Mark-to-market: %d errors", len(errors))
                else:
                    logger.debug("Mark-to-market: outside market hours, skipping")
            except Exception as e:
                logger.warning("Mark-to-market loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes
```

**Replace with:**
```python
    async def mark_to_market_loop():
        """Fetch live Polygon prices for open positions during market hours.
        Runs every 15 min 9 AM - 5 PM ET weekdays.
        Forces a closing bell run at 4:15 PM ET to capture near-close prices.
        """
        import pytz
        from datetime import datetime as dt_cls

        closing_bell_fired_today = None  # Track date to fire once per day

        while True:
            try:
                et = dt_cls.now(pytz.timezone("America/New_York"))
                today_date = et.date()
                is_weekday = et.weekday() < 5
                in_market_window = is_weekday and 9 <= et.hour < 17

                # Closing bell run: 4:15-4:30 PM ET, once per day
                is_closing_bell = (
                    is_weekday
                    and et.hour == 16 and 15 <= et.minute < 30
                    and closing_bell_fired_today != today_date
                )

                if in_market_window or is_closing_bell:
                    from api.unified_positions import run_mark_to_market
                    result = await run_mark_to_market()
                    updated = result.get("updated", 0)
                    errors = result.get("errors", [])
                    if is_closing_bell:
                        closing_bell_fired_today = today_date
                        logger.info("🔔 Closing bell MTM: updated %d positions", updated)
                    elif updated > 0:
                        logger.info("📊 Mark-to-market: updated %d positions", updated)
                    if errors:
                        logger.warning("📊 Mark-to-market: %d errors", len(errors))
                else:
                    logger.debug("Mark-to-market: outside market hours, skipping")
            except Exception as e:
                logger.warning("Mark-to-market loop error: %s", e)
            await asyncio.sleep(900)  # 15 minutes
```

---

## Fix 8: Stale position detection (~line 744 in unified_positions.py)

**Bug:** Uses a flat 2-hour threshold. On weekends/evenings, all positions show as
"not stale" because price_updated_at is from Friday afternoon — technically within a
recent window relative to the check. The real question is: "was this priced during the
most recent market session?"

**Find:**
```python
    # BUG 5: Flag positions with stale pricing (no update in 2+ hours)
    now_utc = datetime.now(timezone.utc)
    stale_count = 0
    for p in positions:
        pua = p.get("price_updated_at")
        if not pua:
            stale_count += 1
        else:
            try:
                if isinstance(pua, str):
                    pua_dt = datetime.fromisoformat(pua).replace(tzinfo=timezone.utc) if "+" not in pua and "Z" not in pua else datetime.fromisoformat(pua.replace("Z", "+00:00"))
                else:
                    pua_dt = pua if pua.tzinfo else pua.replace(tzinfo=timezone.utc)
                if pua_dt < now_utc - timedelta(hours=2):
                    stale_count += 1
            except Exception:
                stale_count += 1
```

**Replace with:**
```python
    # Flag positions with stale pricing
    # During market hours: stale if no update in 30+ minutes
    # Outside market hours: stale if not updated after 4:00 PM ET on most recent trading day
    import pytz
    now_utc = datetime.now(timezone.utc)
    et_tz = pytz.timezone("America/New_York")
    now_et = now_utc.astimezone(et_tz)
    is_market_hours = now_et.weekday() < 5 and 9 <= now_et.hour < 17

    if is_market_hours:
        stale_threshold = now_utc - timedelta(minutes=30)
    else:
        # Find most recent 4:00 PM ET (closing bell)
        last_close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        if now_et.hour < 16 or now_et.weekday() >= 5:
            # Before market close today or weekend — go back to last weekday
            days_back = 1
            if now_et.weekday() == 0 and now_et.hour < 16:
                days_back = 3  # Monday before close → Friday
            elif now_et.weekday() == 6:
                days_back = 2  # Sunday → Friday
            elif now_et.weekday() == 5:
                days_back = 1  # Saturday → Friday
            last_close_et = last_close_et - timedelta(days=days_back)
        stale_threshold = last_close_et.astimezone(timezone.utc)

    stale_count = 0
    for p in positions:
        pua = p.get("price_updated_at")
        if not pua:
            stale_count += 1
        else:
            try:
                if isinstance(pua, str):
                    pua_dt = datetime.fromisoformat(pua).replace(tzinfo=timezone.utc) if "+" not in pua and "Z" not in pua else datetime.fromisoformat(pua.replace("Z", "+00:00"))
                else:
                    pua_dt = pua if pua.tzinfo else pua.replace(tzinfo=timezone.utc)
                if pua_dt < stale_threshold:
                    stale_count += 1
            except Exception:
                stale_count += 1
```

---

## Verification

After deploying, run these checks:

1. **Summary balance:** `GET /api/v2/positions/summary?account=ROBINHOOD`
   - `account_balance` should be close to RH actual (~$4,278)
   - `cash` should be $3,628.23
   - CRCL should subtract from position_value (negative contribution)

2. **Stale detection:** On a weekend, `stale_positions` should be > 0 if last
   price update was before 4 PM ET Friday

3. **Create short stock test:** Create a test short stock position, verify cash
   INCREASES by cost_basis. Then delete it, verify cash decreases back.

4. **Closing bell:** On next trading day, check logs at ~4:15 PM ET for
   "Closing bell MTM" message. Weekend prices should reflect Friday close.

## Tests to Add

Add to `backend/tests/test_unified_positions.py`:
- `test_short_stock_cash_adjustment_on_create` — verify cash increases
- `test_short_stock_cash_adjustment_on_close` — verify cash decreases
- `test_short_stock_summary_position_value` — verify liability subtracted
- `test_stale_detection_outside_market_hours` — mock weekend datetime
- `test_update_direction_triggers_pnl_recalc` — change direction, verify PnL flips
