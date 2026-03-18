# Codex Brief: Signal Pipeline Fixes — Artemis Rename + Phalanx Alert Fix + Scout Sniper Tuning

**Priority:** HIGH — These three issues combined mean zero signals from Artemis, Phalanx, and Scout Sniper have reached the committee pipeline since launch.  
**Branch:** `main`  
**Estimated scope:** 6 files backend, 2 PineScript (docs only — Nick must manually paste into TradingView), 1 frontend  
**Olympus Review:** APPROVED with additions (see Part 3C-3D)

---

## Context

An audit of the TradingView alert log (March 4–18, 414 webhook deliveries) found **zero** alerts from Artemis, Phalanx, or Scout Sniper. Root causes differ per strategy:

1. **Artemis PineScript** sends `"strategy": "Sniper"` which routes to the wrong handler (legacy Ursa/Taurus `process_sniper_signal` instead of `process_artemis_signal`). The indicator name is still "Hub Sniper" — rename everything to "Artemis."
2. **Phalanx PineScript** gates the `alert()` call on `barstate.isconfirmed`, which is unreliable in TradingView's server-side watchlist evaluation. Diamonds appear on charts but alerts never fire.
3. **Scout Sniper server-side scanner** requires RSI(14) below 30 (or above 70) on the *current* 15-min bar — too strict for equities. Runs every 15 min on ~200 tickers with zero signals ever produced.

---

## Part 1: Artemis Rename (Hub Sniper → Artemis)

### 1A. PineScript — `docs/pinescript/webhooks/hub_sniper_v2.1.pine`

> **Nick must paste the updated script into TradingView manually and re-save the indicator. CC commits the file to the repo for version control only.**

**Rename the file** from `hub_sniper_v2.1.pine` to `artemis_v3.pine` (new file, delete old).

Find (line 2):
```pine
indicator("Hub Sniper v2.1", overlay=true, max_lines_count=500)
```
Replace:
```pine
indicator("Artemis v3", overlay=true, max_lines_count=500)
```

Find (line 390, LONG alert — the full `alert_msg` assignment):
```pine
    alert_msg = '{"ticker": "' + syminfo.ticker + '", "strategy": "Sniper", "direction": "LONG",
```
Replace `"strategy": "Sniper"` with `"strategy": "Artemis"` in this string. Leave everything else identical.

Find (line 396, SHORT alert — same pattern):
```pine
    alert_msg = '{"ticker": "' + syminfo.ticker + '", "strategy": "Sniper", "direction": "SHORT",
```
Replace `"strategy": "Sniper"` with `"strategy": "Artemis"` in this string.

Find plotshape labels (lines 324–327) — rename display text from "SNIPE" to "ART":
```pine
plotshape(normal_long, style=shape.triangleup, location=location.belowbar, color=color.green, size=size.small, text="SNIPE", textcolor=color.white, title="Normal Long")
plotshape(flush_long, style=shape.triangleup, location=location.belowbar, color=color.lime, size=size.normal, text="SNIPE", textcolor=color.white, title="Flush Long")
plotshape(normal_short, style=shape.triangledown, location=location.abovebar, color=color.red, size=size.small, text="SNIPE", textcolor=color.white, title="Flush Short")
plotshape(flush_short, style=shape.triangledown, location=location.abovebar, color=color.fuchsia, size=size.normal, text="SNIPE", textcolor=color.white, title="Flush Short")
```
Replace all four `text="SNIPE"` with `text="ART"` (short enough for chart readability).

### 1B. Backend webhook routing — `backend/webhooks/tradingview.py`

Find (line 243–246):
```python
        elif "artemis" in strategy_lower or "hub_sniper" in strategy_lower or "hubsniper" in strategy_lower:
            return await process_artemis_signal(alert, start_time)
        elif "sniper" in strategy_lower:
            return await process_sniper_signal(alert, start_time)
```
Replace:
```python
        elif "artemis" in strategy_lower or "hub_sniper" in strategy_lower or "hubsniper" in strategy_lower or strategy_lower == "sniper":
            return await process_artemis_signal(alert, start_time)
```

**Rationale:** The old `process_sniper_signal` (Ursa/Taurus) is legacy dead code — no TradingView alert sends it. The only thing that ever sent `"strategy": "Sniper"` was the Hub Sniper PineScript (now renamed to Artemis). Routing `strategy_lower == "sniper"` (exact match) to Artemis handles backwards compatibility for any cached/queued signals while the new PineScript hasn't been pasted yet. The `"scout" in strategy_lower` check on line 237 fires first, so Scout Sniper is unaffected.

Find (line 298, Scout signal note):
```python
        "note": "Early warning - confirm with 1H Sniper before entry"
```
Replace:
```python
        "note": "Early warning - confirm with 1H Artemis before entry"
```

### 1C. Confluence lenses — `backend/confluence/lenses.py`

Find (line 19):
```python
    "Sniper": "MEAN_REVERSION",          # Hub Sniper (VWAP bands)
```
Replace:
```python
    "Artemis": "MEAN_REVERSION",         # Artemis (VWAP band mean reversion)
    "Sniper": "MEAN_REVERSION",          # Legacy alias — routes to Artemis
```

### 1D. Frontend analytics hub — `frontend/app.js`

Find (line 3750):
```javascript
        'sniper': 'Sniper', 'exhaustion': 'Exhaustion',
```
Replace:
```javascript
        'sniper': 'Artemis', 'exhaustion': 'Exhaustion',
```

### 1E. Scoring — `backend/scoring/trade_ideas_scorer.py`

No changes needed. Lines 53–60 already have both `"SNIPER": 40` (legacy) and `"ARTEMIS": 45` entries. The Artemis handler at `tradingview.py:676` already sets `"strategy": "Artemis"`, which the scorer resolves to `ARTEMIS` (base 45). Correct as-is.

### 1F. Strategy cooldowns — `backend/webhooks/tradingview.py`

Find `STRATEGY_COOLDOWNS` (lines 54–58). If "Artemis" is missing, add:
```python
    "Artemis": {"equity": 1800, "crypto": 1800},       # 30 min both
```
The `process_artemis_signal` function already calls `check_strategy_cooldown` with `"Artemis"` as the strategy name, so this just needs to exist in the dict. If it's already there, skip.

---

## Part 2: Phalanx Alert Fix (`barstate.isconfirmed` Watchlist Issue)

### 2A. PineScript — `docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine`

> **Nick must paste the updated script into TradingView manually. CC commits to repo.**

**Rename file** to `absorption_wall_detector_v2.pine` to mark the version bump.

The problem: `wall` requires `barstate.isconfirmed` (line 154), and the `alert()` on line 231 gates on `wall and barstate.isconfirmed` again. In watchlist mode, TradingView's server-side evaluation frequently evaluates mid-bar, sees `isconfirmed = false`, skips the alert, and moves to the next ticker.

**Fix:** Use a `[1]` lookback to detect the wall on the *previous* (already confirmed) bar, then fire the alert on the current bar.

Find (lines 154–159):
```pine
bool wall = wallRaw and barstate.isconfirmed

// Direction context: did price drift down into the wall (support) or up into it (resistance)?
float slope = ta.sma(ta.change(close), approachLen)[1]
bool bullWall = wall and (slope < 0)   // falling into wall => support => bullish setup
bool bearWall = wall and (slope > 0)   // rising into wall => resistance => bearish setup
```
Replace:
```pine
// For chart rendering: require confirmed bar (no repaint on live charts)
bool wall = wallRaw and barstate.isconfirmed

// For alerts: detect wall on PREVIOUS confirmed bar (watchlist-safe)
bool wallPrev = wallRaw[1]

// Direction context: did price drift down into the wall (support) or up into it (resistance)?
float slope = ta.sma(ta.change(close), approachLen)[1]
bool bullWall = wall and (slope < 0)   // falling into wall => support => bullish setup
bool bearWall = wall and (slope > 0)   // rising into wall => resistance => bearish setup

// Watchlist-safe direction (based on previous bar)
float slopePrev = ta.sma(ta.change(close), approachLen)[2]
bool bullWallPrev = wallPrev and (slopePrev < 0)
bool bearWallPrev = wallPrev and (slopePrev > 0)
```

Find (lines 230–234, the alert block condition):
```pine
// JSON webhook alert for Trading Hub pipeline
if wall and barstate.isconfirmed and (bullWall or bearWall)
    string direction = bullWall ? "LONG" : "SHORT"
    string wallType = bullWall ? "BULL_WALL" : "BEAR_WALL"
```
Replace:
```pine
// JSON webhook alert for Trading Hub pipeline
// Uses [1] lookback — watchlist-safe (no barstate.isconfirmed dependency)
if wallPrev and (bullWallPrev or bearWallPrev)
    string direction = bullWallPrev ? "LONG" : "SHORT"
    string wallType = bullWallPrev ? "BULL_WALL" : "BEAR_WALL"
```

Leave the rest of the alert payload block (lines 235–248) unchanged — it constructs the JSON and calls `alert()`. Only the `if` condition and the two variables inside it change.

**Note (from Olympus/URSA):** The alert payload still references current-bar `close`, `deltaRatio`, etc. — NOT the previous bar where the wall was detected. This is intentional and correct: the entry price should be the current price (when you'd enter the trade), not the wall detection price.

**Note on `alert.freq_once_per_bar`:** This already handles dedup — the alert fires at most once per bar even if evaluated multiple times. Combined with the `[1]` lookback, the signal is stable: it refers to the previous bar's data which won't change.

### 2B. Backend — No changes needed

The Phalanx webhook handler (`process_phalanx_signal`) already correctly:
- Expects `"strategy": "AbsorptionWall"` (PineScript sends this) ✅
- Routes via `"phalanx" in strategy_lower or "absorption" in strategy_lower or "wall" in strategy_lower` ✅
- Stores as `"strategy": "Phalanx"` ✅
- Has cooldown entry ✅
- Confluence lens maps `"AbsorptionWall"` and `"Phalanx"` to `"ORDER_FLOW_BALANCE"` ✅

---

## Part 3: Scout Sniper Server-Side Parameter Tuning

### 3A. Scanner config — `backend/scanners/scout_sniper_scanner.py`

Find `SCOUT_CONFIG` (lines 22–38):
```python
SCOUT_CONFIG = {
    "rsi_length": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "vol_length": 20,
    "tier_a_rvol": 1.6,
    "tier_b_rvol": 1.1,
    "wick_ratio": 0.5,
    "cooldown_bars": 4,
    "sma_lengths": [50, 120, 200],
    "structural_lookback": 20,
    # Stop and target
    "atr_buffer_mult": 0.15,
    "fallback_tp1_r": 1.5,
    "fallback_tp2_r": 2.0,
}
```
Replace:
```python
SCOUT_CONFIG = {
    "rsi_length": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "vol_length": 20,
    "tier_a_rvol": 1.6,
    "tier_b_rvol": 1.1,
    "wick_ratio": 0.5,
    "cooldown_bars": 4,
    "sma_lengths": [50, 120, 200],
    "structural_lookback": 20,
    "lookback_bars": 3,
    "min_quality_score": 3,
    # Stop and target
    "atr_buffer_mult": 0.15,
    "fallback_tp1_r": 1.5,
    "fallback_tp2_r": 2.0,
}
```

Changes: `rsi_oversold` 30→35, `rsi_overbought` 70→65, add `"lookback_bars": 3`, add `"min_quality_score": 3`.

### 3B. Multi-bar lookback — `backend/scanners/scout_sniper_scanner.py`

Currently `check_scout_signals` only examines `df.iloc[-1]` (the most recent bar). Change it to check the last N bars.

Find (line ~197–210):
```python
    latest = df.iloc[-1]

    rsi = latest.get("rsi")
    rsi_prev = latest.get("rsi_prev")
    rvol = latest.get("rvol")
    vwap = latest.get("vwap")
    atr = latest.get("atr")

    if any(pd.isna(x) for x in [rsi, rsi_prev, rvol, vwap, atr]):
        return signals

    # Cooldown check
    bar_idx = len(df) - 1
    last_signal_idx = _cooldown_tracker.get(ticker, -999)
    if (bar_idx - last_signal_idx) < SCOUT_CONFIG["cooldown_bars"]:
        return signals
```
Replace:
```python
    lookback = SCOUT_CONFIG.get("lookback_bars", 1)
    # Cooldown check (use latest bar index)
    bar_idx = len(df) - 1
    last_signal_idx = _cooldown_tracker.get(ticker, -999)
    if (bar_idx - last_signal_idx) < SCOUT_CONFIG["cooldown_bars"]:
        return signals

    # Check last N bars for signal conditions
    for offset in range(lookback):
        idx = -(offset + 1)
        if abs(idx) > len(df):
            break
        latest = df.iloc[idx]

        rsi = latest.get("rsi")
        rsi_prev = latest.get("rsi_prev")
        rvol = latest.get("rvol")
        vwap = latest.get("vwap")
        atr = latest.get("atr")

        if any(pd.isna(x) for x in [rsi, rsi_prev, rvol, vwap, atr]):
            continue
```

Then the existing time filter, RVOL gate, and signal checks continue as-is inside this loop. **Indent the entire block from the time filter through the signal append** one level deeper (inside the `for offset` loop). Add a `break` after the first signal is found for a ticker (one signal per scan per ticker is sufficient):

After the `signals.append({...})` and `_cooldown_tracker[ticker] = bar_idx` block, add:
```python
            break  # One signal per ticker per scan
```

### 3C. Quality gate (Olympus/URSA addition) — `backend/scanners/scout_sniper_scanner.py`

In `run_scout_scan`, after the scan loop collects `all_signals` but BEFORE feeding them to `process_signal_unified`, add a quality filter:

Find the loop that processes signals (after `await asyncio.sleep(0.05)`):
```python
    for signal in all_signals:
        try:
            from signals.pipeline import process_signal_unified
            await process_signal_unified(
```

Insert BEFORE this loop:
```python
    # Quality gate: only process signals scoring >= min_quality_score (Olympus review)
    min_score = SCOUT_CONFIG.get("min_quality_score", 3)
    quality_signals = [s for s in all_signals if s.get("score", 0) >= min_score]
    dropped = len(all_signals) - len(quality_signals)
    if dropped > 0:
        logger.info("Scout quality gate: dropped %d/%d signals below score %d", dropped, len(all_signals), min_score)
```

Then change the processing loop to iterate over `quality_signals` instead of `all_signals`:
```python
    for signal in quality_signals:
```

**Rationale (from Olympus/URSA):** Loosening RSI from 30/70 to 35/65 + 3-bar lookback could ~5-7x the candidate bars. The quality score (0-6) already exists and measures multi-factor strength. Requiring score ≥ 3 prevents low-quality signals from inflating confluence scores on otherwise marginal Holy Grail or Sell the Rip signals. Sub-threshold signals still count in the log for diagnostics.

### 3D. IGNORE signals excluded from confluence (Olympus/URSA addition) — `backend/confluence/lenses.py`

Verify that the confluence scoring engine does NOT count signals with `tradeable_status: "IGNORE"` toward confluence. Check if there is a filter in the confluence calculation. If there is NOT one already, add a filter wherever signals are aggregated for confluence scoring:

```python
# Only count TRADEABLE signals for confluence — IGNORE signals are logged but don't boost other strategies
if signal.get("tradeable_status") == "IGNORE":
    continue
```

If this filter already exists, skip. The key requirement: `IGNORE` signals should be stored (useful for analytics) but must NOT inflate confluence scores for other strategies.

### 3E. Add diagnostic logging — `backend/scanners/scout_sniper_scanner.py`

Find (lines 392–396):
```python
    logger.info(
        "Scout scan: %d signals from %d tickers in %.1fs",
        len(all_signals), len(tickers), elapsed,
    )
```
Replace:
```python
    logger.info(
        "Scout scan: %d signals (%d passed quality gate) from %d tickers in %.1fs (RSI range: %d/%d, lookback: %d bars)",
        len(all_signals), len(quality_signals), len(tickers), elapsed,
        SCOUT_CONFIG["rsi_oversold"], SCOUT_CONFIG["rsi_overbought"],
        SCOUT_CONFIG.get("lookback_bars", 1),
    )
```

### 3F. Notes for future iteration (from Olympus)

- **RVOL gate (TORO):** If Scout signals remain sparse after 1 week with loosened RSI, the next tuning pass should lower `tier_b_rvol` from 1.1 to 0.9.
- **Time filter (TECHNICALS):** The time filter currently uses `datetime.now()` (current wall-clock time), not the bar's own timestamp. On 15-min bars this is a max 45-minute discrepancy. Acceptable for v1; a future improvement should use `df.index[idx]` for time checks when using the multi-bar lookback.

---

## Testing Checklist

After deploying:

1. **Artemis:** Send a test webhook to Railway:
   ```bash
   curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview \
     -H "Content-Type: application/json" \
     -d '{"ticker":"TEST","strategy":"Artemis","direction":"LONG","entry_price":100,"stop_loss":98,"target_1":104,"target_2":108,"timeframe":"15","adx":25,"rsi":45,"rvol":1.5,"mode":"Normal","avwap_ctx":"1.2","avwap_buf_atr":"0.5","prox_atr":"0.3"}'
   ```
   Verify it routes to `process_artemis_signal` and stores with `strategy: "Artemis"`.

2. **Artemis backwards compat:** Send with `"strategy":"Sniper"` — should also route to Artemis handler.

3. **Phalanx:** After Nick pastes updated PineScript and recreates the watchlist alert, monitor the TradingView alert log for first Phalanx webhook delivery.

4. **Scout Sniper:** After deploy, check Railway logs during next market session for `Scout scan:` entries showing `RSI range: 35/65, lookback: 3 bars`. Monitor for first signal.

5. **Scout quality gate:** If Scout fires, verify the log shows quality gate filtering (e.g., `dropped 2/5 signals below score 3`).

6. **Confluence IGNORE check:** Verify that any Scout signal with `tradeable_status: "IGNORE"` does NOT appear in confluence scoring for co-occurring signals.

7. **Analytics Hub:** Open the dashboard, verify "Artemis" appears in the strategy dropdown/filter (not "Sniper").

---

## Files Changed Summary

| File | Change |
|---|---|
| `docs/pinescript/webhooks/hub_sniper_v2.1.pine` | DELETE (replaced by artemis_v3.pine) |
| `docs/pinescript/webhooks/artemis_v3.pine` | NEW — renamed indicator + strategy field |
| `docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine` | DELETE (replaced by v2) |
| `docs/pinescript/webhooks/absorption_wall_detector_v2.pine` | NEW — watchlist-safe alert using [1] lookback |
| `backend/webhooks/tradingview.py` | Merge "sniper" route into Artemis handler |
| `backend/confluence/lenses.py` | Add "Artemis" key + verify IGNORE filter |
| `backend/scanners/scout_sniper_scanner.py` | Loosen RSI, add multi-bar lookback, quality gate, logging |
| `frontend/app.js` | Map 'sniper' display name to 'Artemis' |

**PineScript note:** The `.pine` files in the repo are documentation/version control only. Nick must manually copy-paste the updated scripts into TradingView's Pine Editor, save, and recreate the watchlist alerts pointing to the correct webhook URL (`https://pandoras-box-production.up.railway.app/webhook/tradingview`).
