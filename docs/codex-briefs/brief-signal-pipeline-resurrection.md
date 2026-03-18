# Codex Brief: Signal Pipeline Resurrection

**Priority:** HIGH — Three strategies producing zero signals  
**Scope:** PineScript × 2, Backend × 2, Frontend × 1, Scanner × 1  
**Branch:** `main`

---

## Context

Three strategies (Artemis, Phalanx, Scout Sniper) have been producing **zero signals** despite running on 200+ tickers. Root causes diagnosed:

1. **Artemis (PineScript):** Sends wrong strategy name `"Sniper"` → routed to wrong handler. Also, signal conditions evaluate on the forming bar, which watchlist alerts miss.
2. **Phalanx (PineScript):** `barstate.isconfirmed` gate in the `alert()` call prevents firing in TradingView watchlist evaluation mode. Diamonds render on charts (via `plotshape`) but alerts never trigger.
3. **Scout Sniper (Server-side):** RSI thresholds (30/70) too strict for equity 15-min charts. Scanner runs but never finds qualifying setups.

Evidence: TradingView alert log shows 414 webhooks over 2 weeks. Zero are Artemis, Phalanx, or Scout Sniper. All are Breadth, TICK, McClellan, Circuit Breaker, Holy Grail, or Whale Hunter.

---

## Part 1 — Artemis PineScript Rename + Watchlist Fix

**File:** `docs/pinescript/webhooks/hub_sniper_v2.1.pine`  
**Rename to:** `docs/pinescript/webhooks/artemis_v3.pine`

### 1A. Change strategy name in alert payloads

Find (appears twice — once for LONG, once for SHORT):
```
"strategy": "Sniper"
```
Replace with:
```
"strategy": "Artemis"
```

### 1B. Fix watchlist alert evaluation

The current `long_signal` / `short_signal` conditions use real-time values (`close`, `low`, `high`) on the current forming bar. In watchlist mode, TradingView evaluates each ticker at a random point during the bar — conditions that are true at bar close may not be true mid-bar when TV checks.

Fix: Create `[1]`-offset versions of the signal conditions so the `alert()` fires based on the **previous confirmed bar**, which is always evaluatable.

Find the alert block (around line 387):
```pinescript
if long_signal
```
Replace with:
```pinescript
// Watchlist-safe: fire alert based on previous confirmed bar
long_signal_confirmed = long_signal[1]
if long_signal_confirmed
```

And the corresponding payload must use `[1]` offset prices. Find (LONG alert):
```pinescript
    alert_msg = '{"ticker": "' + syminfo.ticker + '", "strategy": "Sniper", "direction": "LONG", "entry_price": ' + str.tostring(close) + ', "stop_loss": ' + str.tostring(long_sl) + ', "target_1": ' + str.tostring(long_tp1) + ', "target_2": ' + str.tostring(long_tp2) + ', "risk_reward": ' + rr_str + ', "timeframe": "' + timeframe.period + '", "adx": ' + str.tostring(adx_val, "#.#") + ', "adx_rising": ' + (adx_rising ? "true" : "false") + ', "rsi": ' + str.tostring(rsi_val, "#.#") + ', "rvol": ' + str.tostring(rvol, "#.##") + ', "mode": "' + mode_str + '", "avwap_ctx": ' + str.tostring(avwapCtx, "#.##") + ', "avwap_buf_atr": ' + str.tostring(gate_buffer_atr, "#.##") + ', "prox_atr": ' + str.tostring(prox_atr, "#.##") + '}'
```
Replace with (note: `"strategy": "Artemis"`, and use `[1]` offsets for price data):
```pinescript
    float prev_close = close[1]
    float prev_long_sl = low[1] - (atr[1] * atr_sl_buffer)
    float prev_long_risk = prev_close - prev_long_sl
    float prev_long_tp1 = prev_close + (prev_long_risk * 1.5)
    float prev_long_tp2 = prev_close + (prev_long_risk * 2)
    string prev_rr_str = prev_long_risk > 0 ? str.tostring((prev_long_tp1 - prev_close) / prev_long_risk, "#.#") : "?"
    string prev_mode_str = flush_down[1] ? "Flush" : "Normal"
    alert_msg = '{"ticker": "' + syminfo.ticker + '", "strategy": "Artemis", "direction": "LONG", "entry_price": ' + str.tostring(prev_close) + ', "stop_loss": ' + str.tostring(prev_long_sl) + ', "target_1": ' + str.tostring(prev_long_tp1) + ', "target_2": ' + str.tostring(prev_long_tp2) + ', "risk_reward": ' + prev_rr_str + ', "timeframe": "' + timeframe.period + '", "adx": ' + str.tostring(adx_val[1], "#.#") + ', "adx_rising": ' + (adx_rising[1] ? "true" : "false") + ', "rsi": ' + str.tostring(rsi_val[1], "#.#") + ', "rvol": ' + str.tostring(rvol[1], "#.##") + ', "mode": "' + prev_mode_str + '", "avwap_ctx": ' + str.tostring(avwapCtx[1], "#.##") + ', "avwap_buf_atr": ' + str.tostring(gate_buffer_atr[1], "#.##") + ', "prox_atr": ' + str.tostring(prox_atr[1], "#.##") + '}'
```

Apply the same `[1]` offset pattern to the SHORT alert block:
```pinescript
short_signal_confirmed = short_signal[1]
if short_signal_confirmed
```
With corresponding `[1]` offset prices for the SHORT payload (use `close[1]`, `high[1]`, `atr[1]`, etc.) and `"strategy": "Artemis"`.

### 1C. Rename the indicator title

Find the `indicator()` declaration at the top of the file. Change the title from any reference to "Hub Sniper" or "Sniper" to "Artemis". Example:
```pinescript
indicator("Artemis v3 (VWAP Mean Reversion)", overlay=true, max_lines_count=500)
```

### 1D. Update the label panel

Find the line that generates the table/label display panel (around line 335, inside `if barstate.islast`). The SIGNAL row currently shows `long_signal ? "LONG" : short_signal ? "SHORT" : "--"`. Keep this as-is (it shows real-time state on the chart, which is useful for visual confirmation even though the alert fires on `[1]`).

---

## Part 2 — Phalanx PineScript Watchlist Fix

**File:** `docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine`

### 2A. Fix the alert() condition

Find:
```pinescript
if wall and barstate.isconfirmed and (bullWall or bearWall)
```
Replace with:
```pinescript
if wall[1] and (bullWall[1] or bearWall[1])
```

### 2B. Update the alert payload to use `[1]` offsets

The payload currently references real-time values. Update to use `[1]` offsets:

Find:
```pinescript
    alert_payload = '{"ticker":"' + syminfo.ticker +
         '","strategy":"AbsorptionWall"' +
         ',"direction":"' + direction +
         '","signal_type":"' + wallType +
         '","entry_price":' + str.tostring(close) +
         ',"timeframe":"' + timeframe.period +
         '","delta_ratio":' + str.tostring(deltaRatio, "#.####") +
         ',"buy_pct":' + str.tostring(buyPct, "#.####") +
         ',"buy_vol":' + str.tostring(buyVol) +
         ',"sell_vol":' + str.tostring(sellVol) +
         ',"total_vol":' + str.tostring(totVol) +
         ',"rvol":' + str.tostring(totVol / avgTotVol, "#.##") +
         '}'
    alert(alert_payload, alert.freq_once_per_bar)
```
Replace with:
```pinescript
    string prev_direction = bullWall[1] ? "LONG" : "SHORT"
    string prev_wallType = bullWall[1] ? "BULL_WALL" : "BEAR_WALL"
    alert_payload = '{"ticker":"' + syminfo.ticker +
         '","strategy":"Phalanx"' +
         ',"direction":"' + prev_direction +
         '","signal_type":"' + prev_wallType +
         ',"entry_price":' + str.tostring(close[1]) +
         ',"timeframe":"' + timeframe.period +
         '","delta_ratio":' + str.tostring(deltaRatio[1], "#.####") +
         ',"buy_pct":' + str.tostring(buyPct[1], "#.####") +
         ',"buy_vol":' + str.tostring(buyVol[1]) +
         ',"sell_vol":' + str.tostring(sellVol[1]) +
         ',"total_vol":' + str.tostring(totVol[1]) +
         ',"rvol":' + str.tostring(totVol[1] / avgTotVol[1], "#.##") +
         '}'
    alert(alert_payload, alert.freq_once_per_bar)
```

**NOTE:** Strategy name also changed from `"AbsorptionWall"` to `"Phalanx"`. The backend already routes both names to the Phalanx handler (`"phalanx"` or `"absorption"` in strategy_lower), but using the canonical name is cleaner.

---

## Part 3 — Backend: Artemis Routing + Name Alignment

**File:** `backend/webhooks/tradingview.py`

### 3A. Add backward-compat routing for "sniper" → Artemis

Currently (around line 237-248):
```python
        if "scout" in strategy_lower:
            return await process_scout_signal(alert, start_time)
        elif "holy_grail" in strategy_lower or "holygrail" in strategy_lower:
            return await process_holy_grail_signal(alert, start_time)
        elif "exhaustion" in strategy_lower:
            return await process_exhaustion_signal(alert, start_time)
        elif "artemis" in strategy_lower or "hub_sniper" in strategy_lower or "hubsniper" in strategy_lower:
            return await process_artemis_signal(alert, start_time)
        elif "sniper" in strategy_lower:
            return await process_sniper_signal(alert, start_time)
        elif "phalanx" in strategy_lower or "absorption" in strategy_lower or "wall" in strategy_lower:
            return await process_phalanx_signal(alert, start_time)
```

Replace the Artemis line to also catch bare `"sniper"` (since the old PineScript sent that):
```python
        elif "artemis" in strategy_lower or "hub_sniper" in strategy_lower or "hubsniper" in strategy_lower or strategy_lower == "sniper":
            return await process_artemis_signal(alert, start_time)
```

And REMOVE the generic sniper handler fallthrough entirely:
```python
        # DELETE THIS LINE — "Sniper" signals are Artemis
        # elif "sniper" in strategy_lower:
        #     return await process_sniper_signal(alert, start_time)
```

**Why `strategy_lower == "sniper"` (exact match) instead of `"sniper" in strategy_lower`:** The `in` check would also match "scout_sniper", but Scout is already caught by the `"scout" in strategy_lower` check above it. Using exact match is safest.

### 3B. Update STRATEGY_COOLDOWNS

Find (around line 54-58):
```python
STRATEGY_COOLDOWNS = {
```
If there is a `"Sniper"` entry, rename it to `"Artemis"`. If `"Artemis"` already exists, remove the `"Sniper"` entry.

---

## Part 4 — Frontend: Strategy Name Mapping

**File:** `frontend/app.js`

### 4A. Update formatStrategyName mapping

Find (around line 3750):
```javascript
        'sniper': 'Sniper', 'exhaustion': 'Exhaustion',
```
Replace with:
```javascript
        'sniper': 'Artemis', 'exhaustion': 'Exhaustion',
```

### 4B. Update formatSignalType mapping

Find (around line 3770):
```javascript
        'SNIPER_URSA': 'Sniper Ursa', 'SNIPER_TAURUS': 'Sniper Taurus',
```
Replace with:
```javascript
        'SNIPER_URSA': 'Artemis Long', 'SNIPER_TAURUS': 'Artemis Short',
```

Also find (around line 3774):
```javascript
        'BULLISH_TRADE': 'Bullish Trade', 'BEAR_CALL': 'Bear Call',
```
Replace with:
```javascript
        'BULLISH_TRADE': 'Artemis Long', 'BEAR_CALL': 'Artemis Short',
```

(These are the signal types that `process_sniper_signal` used to generate. Now that "Sniper" routes to Artemis, any old signals with these types should display as Artemis.)

---

## Part 5 — Scout Sniper Parameter Loosening

**File:** `backend/scanners/scout_sniper_scanner.py`

### 5A. Widen RSI thresholds

Find (around line 23-24):
```python
    "rsi_oversold": 30,
    "rsi_overbought": 70,
```
Replace with:
```python
    "rsi_oversold": 35,
    "rsi_overbought": 65,
```

### 5B. Multi-bar lookback (check last 3 bars, not just latest)

Currently, `check_scout_signals` only checks `df.iloc[-1]`. Change it to check the last 3 bars.

Find (around line 199):
```python
    latest = df.iloc[-1]

    rsi = latest.get("rsi")
    rsi_prev = latest.get("rsi_prev")
```
Replace with:
```python
    # Check last 3 bars for qualifying setups (not just latest)
    lookback_range = min(3, len(df) - 1)
    for bar_offset in range(lookback_range):
        bar_idx_actual = len(df) - 1 - bar_offset
        latest = df.iloc[bar_idx_actual]

        rsi = latest.get("rsi")
        rsi_prev = latest.get("rsi_prev")
```

Then indent the entire body of the signal checking logic (from the `rsi_prev` line through the end of the `for direction, sig, tradeable in [...]` loop) inside this new `for bar_offset` loop. Add a `break` after a signal is found to avoid duplicate signals from adjacent bars:

At the end of the `for direction, sig, tradeable in [...]` inner loop, after `_cooldown_tracker[ticker] = bar_idx`, add:
```python
        if signals:
            break  # Found signal in this bar, don't check older bars
```

And update the cooldown check to use `bar_idx_actual` instead of `bar_idx`:
```python
    # Cooldown check
    last_signal_idx = _cooldown_tracker.get(ticker, -999)
    if (bar_idx_actual - last_signal_idx) < SCOUT_CONFIG["cooldown_bars"]:
        continue  # changed from `return signals` to `continue` for multi-bar loop
```

And at the signal append, use `bar_idx_actual`:
```python
        _cooldown_tracker[ticker] = bar_idx_actual
```

### 5C. Add diagnostic logging

Add a filter funnel log at the end of `run_scout_scan` to show where tickers are being filtered out. After the scan loop (around line 390), before the `logger.info("Scout scan: ...")` line, add:

```python
    # Diagnostic: log filter funnel stats
    if not all_signals:
        logger.info(
            "Scout scan: 0 signals from %d tickers — all filtered. "
            "Check RSI thresholds (need <%d or >%d on 15m), "
            "RVOL gate (need >%.1fx), and bull/bear hook + candle patterns.",
            len(tickers),
            SCOUT_CONFIG["rsi_oversold"],
            SCOUT_CONFIG["rsi_overbought"],
            SCOUT_CONFIG["tier_b_rvol"],
        )
```

---

## Part 6 — Delete Old PineScript File

After creating the new `artemis_v3.pine`, delete the old file:

**Delete:** `docs/pinescript/webhooks/hub_sniper_v2.1.pine`

---

## Post-Deploy Checklist (Nick — manual steps)

After CC deploys these changes:

1. **Copy updated `artemis_v3.pine`** into TradingView as a new indicator
2. **Delete the old "Hub Sniper" / "Sniper" alert** from the PREY LIST watchlist
3. **Create new Artemis alert** on the PREY LIST watchlist:
   - Condition: `Artemis v3 (VWAP Mean Reversion)` → `Any alert() function call`
   - Webhook URL: `https://pandoras-box-production.up.railway.app/webhook/tradingview`
   - Interval: 15m (or preferred timeframe)
   - Expiration: Open-ended
4. **Delete the old Phalanx alert** from the PREY LIST watchlist
5. **Copy updated `absorption_wall_detector_v1.5.pine`** into TradingView
6. **Create new Phalanx alert** on the PREY LIST watchlist:
   - Condition: `Phalanx v1.5 (Absorption Wall Detector)` → `Any alert() function call`
   - Webhook URL: `https://pandoras-box-production.up.railway.app/webhook/tradingview`
   - Interval: 15m
   - Expiration: Open-ended
7. **Verify** within 1-2 market sessions that signals appear in the committee queue

---

## Files Modified (Summary)

| File | Action |
|------|--------|
| `docs/pinescript/webhooks/hub_sniper_v2.1.pine` | DELETE |
| `docs/pinescript/webhooks/artemis_v3.pine` | CREATE (renamed + fixed) |
| `docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine` | EDIT (barstate fix + strategy name) |
| `backend/webhooks/tradingview.py` | EDIT (routing: "sniper" → Artemis, remove generic handler) |
| `frontend/app.js` | EDIT (strategy name mappings) |
| `backend/scanners/scout_sniper_scanner.py` | EDIT (RSI thresholds, multi-bar lookback, logging) |
