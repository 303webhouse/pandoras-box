# Brief 06B — Holy Grail Pullback Continuation Pipeline Integration

**Priority:** MEDIUM — fills gap in signal coverage (pullback continuations)
**LLM cost impact:** ~$0.02/committee run (same as all signals)
**Estimated build time:** 3–4 hours
**Agent target:** Claude Code (implementation)
**Depends on:** Nothing (independent of Brief 06A)

---

## Problem

The signal pipeline catches breakouts (Hub Sniper) and structure breaks (Scout Sniper) but has zero coverage for **pullback continuation entries** — buying dips in strong trends. The Holy Grail Pullback Continuation indicator (Linda Raschke-style) fills this gap: it waits for ADX ≥ 25 (strong trend), a pullback to the 20 EMA, then a confirmation candle back in the trend direction.

This indicator already exists as a PineScript file (`holy_grail_pullback.pine`). This brief integrates it into the full signal pipeline: TradingView webhook → Railway scoring → VPS committee review → Discord.

## Committee Review Decision

The Trading Team committee reviewed this indicator and approved it with these parameters:

- **Full committee review** (not context-only) — Holy Grail signals define an entry, so they deserve 4-agent analysis
- **15m + 1h timeframes**, with 1h scoring higher (cleaner pullbacks, better R:R)
- **Pre-qualified for committee** (same as Hub Sniper / Scout Sniper — skips Gatekeeper score threshold)

---

## Architecture

```
TradingView: Holy Grail fires on 15m or 1h chart
  → alert() sends JSON webhook to /webhook/tradingview
  → Backend routes to process_holy_grail_signal()
  → Signal scored (base 40 for 15m, base 50 for 1h)
  → Persisted to DB, cached in Redis, broadcast via WebSocket
  → VPS signal notifier picks up signal
  → Posted to Discord with "Run Committee" button (pre-qualified)
  → Nick clicks "Run Committee" → full 4-agent analysis
```

---

## Part 1: PineScript Webhook Version

Take the existing Holy Grail indicator and add webhook alert output. Create a **separate copy** for webhooks (keep the original for visual chart use).

**New file:** `docs/pinescript/holy_grail_webhook_v1.pine`

Add these changes to a copy of the original indicator:

### 1A. Add webhook inputs after the existing `grpVisual` section

**FIND:**
```pinescript
showSignalLabels = input.bool(true, "Show Signal Labels", group=grpVisual)
```

**INSERT AFTER:**
```pinescript

grpWebhook = "Webhook"
enableWebhook = input.bool(true, "Enable Webhook Alerts", group=grpWebhook,
     tooltip="When enabled, fires alert() with JSON payload on signals for the Trading Hub pipeline.")
```

### 1B. Add pullback level tracking after the cooldown logic

We need the pullback bar's high/low for stop loss calculation. The stop for a long is below the pullback bar's low; for a short, above the pullback bar's high.

**FIND:**
```pinescript
if shortSignal
    lastShortSignalBar := bar_index
```

**INSERT AFTER:**
```pinescript

// ============================================================================
// WEBHOOK PAYLOAD
// ============================================================================

// Track pullback bar levels for stop loss
var float pullbackLow  = na
var float pullbackHigh = na

if longPullbackBar
    pullbackLow := low

if shortPullbackBar
    pullbackHigh := high

// Calculate stop and target levels
longStop   = pullbackLow
longRisk   = close - longStop
longTarget = longStop > 0 and longRisk > 0 ? close + (longRisk * 2.0) : na

shortStop   = pullbackHigh
shortRisk   = shortStop - close
shortTarget = shortStop > 0 and shortRisk > 0 ? close - (shortRisk * 2.0) : na

// DI spread (useful for scoring)
diSpread = plusDI - minusDI

// Fire webhook alerts
if enableWebhook and longSignal
    alert(str.format(
     '\{"ticker": "{0}", "strategy": "holy_grail", "direction": "LONG", "entry_price": {1}, "stop_loss": {2}, "target_1": {3}, "adx": {4}, "rsi": {5}, "timeframe": "{6}", "rvol": {7}\}',
     syminfo.ticker,
     math.round(close, 2),
     math.round(nz(longStop, close * 0.99), 2),
     math.round(nz(longTarget, close * 1.02), 2),
     math.round(adx, 1),
     math.round(ta.rsi(close, 14), 1),
     timeframe.period,
     math.round(nz(diSpread, 0), 1)
     ), alert.freq_once_per_bar)

if enableWebhook and shortSignal
    alert(str.format(
     '\{"ticker": "{0}", "strategy": "holy_grail", "direction": "SHORT", "entry_price": {1}, "stop_loss": {2}, "target_1": {3}, "adx": {4}, "rsi": {5}, "timeframe": "{6}", "rvol": {7}\}',
     syminfo.ticker,
     math.round(close, 2),
     math.round(nz(shortStop, close * 1.01), 2),
     math.round(nz(shortTarget, close * 0.98), 2),
     math.round(adx, 1),
     math.round(ta.rsi(close, 14), 1),
     timeframe.period,
     math.round(nz(diSpread, 0), 1)
     ), alert.freq_once_per_bar)
```

**Note on `rvol` field:** We're repurposing the existing `rvol` field in TradingViewAlert to carry the DI spread value (plusDI − minusDI). This avoids adding a new field to the Pydantic model. The DI spread tells the scorer how decisive the directional move is — a spread of 15+ is strong, under 5 is weak. The scorer already gives a bonus for `rvol > 1.5`, and DI spreads above 1.5 will naturally trigger this. If we want DI-specific scoring later, we add a dedicated field in a future brief.

### 1C. Tighten tolerance for webhook version

Per committee recommendation, tighten the EMA touch band for automated signals.

**CHANGE the default value:**
```pinescript
touchTolerancePct = input.float(0.15, "EMA Touch Tolerance %", minval=0.0, step=0.05, group=grpSetup,
```

(Changed from 0.30 to 0.15 — tighter band for webhook signals, fewer false touches.)

---

## Part 2: Backend Signal Handler (Railway)

### 2A. Add `holy_grail` route in webhook handler

**File:** `backend/webhooks/tradingview.py`

**FIND:**
```python
        if "scout" in strategy_lower:
            return await process_scout_signal(alert, start_time)
        elif "exhaustion" in strategy_lower:
```

**REPLACE WITH:**
```python
        if "scout" in strategy_lower:
            return await process_scout_signal(alert, start_time)
        elif "holy_grail" in strategy_lower or "holygrail" in strategy_lower:
            return await process_holy_grail_signal(alert, start_time)
        elif "exhaustion" in strategy_lower:
```

### 2B. Add `process_holy_grail_signal()` function

**INSERT AFTER the `process_scout_signal()` function (before `process_exhaustion_signal`):**

```python
async def process_holy_grail_signal(alert: TradingViewAlert, start_time: datetime):
    """
    Process Holy Grail Pullback Continuation signals (Raschke-style).

    These are continuation entries: strong trend (ADX >= 25), pullback to 20 EMA,
    confirmation candle back in trend direction. Full committee review signals.

    Timeframe affects signal type:
    - 1H  -> HOLY_GRAIL_1H  (higher base score — cleaner pullbacks)
    - 15m -> HOLY_GRAIL_15M (lower base score — noisier)
    """

    # Determine signal type based on timeframe
    tf = (alert.timeframe or "15").upper().replace("M", "").replace("MIN", "")
    if tf in ("60", "1H", "H", "1"):
        signal_type_suffix = "1H"
    else:
        signal_type_suffix = "15M"

    if alert.direction.upper() in ["LONG", "BUY"]:
        signal_type = f"HOLY_GRAIL_{signal_type_suffix}"
    else:
        signal_type = f"HOLY_GRAIL_{signal_type_suffix}"

    # Calculate risk/reward
    rr = calculate_risk_reward(alert)

    # Build signal data
    signal_id = f"HG_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "Holy_Grail",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "stop_loss": alert.stop_loss,
        "target_1": alert.target_1,
        "target_2": alert.target_2,
        "risk_reward": rr["primary"],
        "risk_reward_t1": rr["t1_rr"],
        "risk_reward_t2": rr["t2_rr"],
        "timeframe": alert.timeframe,
        "trade_type": "CONTINUATION",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
        "rsi": alert.rsi,
        "adx": alert.adx,
        "rvol": alert.rvol,  # Carries DI spread from PineScript
    }

    # Unified pipeline handles scoring, persistence, caching, and broadcast
    signal_data = await process_signal_unified(signal_data, source="tradingview")

    elapsed = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"✅ Holy Grail signal processed: {alert.ticker} {signal_type} ({alert.timeframe}) in {elapsed:.1f}ms")

    return {
        "status": "success",
        "signal_id": signal_id,
        "signal_type": signal_data.get("signal_type", signal_type),
        "processing_time_ms": round(elapsed, 1)
    }
```

### 2C. Add Holy Grail base scores to scorer

**File:** `backend/scoring/trade_ideas_scorer.py`

**FIND:**
```python
    # Sniper signals
    "SNIPER": 40,
    "SNIPER_URSA": 40,
    "SNIPER_TAURUS": 40,
```

**INSERT AFTER:**
```python
    
    # Holy Grail Pullback Continuation (Raschke-style)
    # 1H scores higher — cleaner pullbacks, better R:R
    # 15M scores lower — noisier, mid-move risk
    "HOLY_GRAIL": 45,
    "HOLY_GRAIL_1H": 50,
    "HOLY_GRAIL_15M": 40,
```

---

## Part 3: VPS Committee Integration

### 3A. Add `holy_grail` to pre-qualified strategies

**File:** `/opt/openclaw/workspace/scripts/pivot2_committee.py`

**FIND:**
```python
TV_COMMITTEE_STRATEGIES = {"sniper", "scout", "exhaustion"}
```

**REPLACE WITH:**
```python
TV_COMMITTEE_STRATEGIES = {"sniper", "scout", "exhaustion", "holy_grail"}
```

This makes Holy Grail signals skip the Gatekeeper score threshold (same treatment as Hub Sniper and Scout Sniper). The signal is posted to Discord with a "Run Committee" button. Nick decides when to run the full committee analysis.

---

## Part 4: Strategy Documentation

**New file:** `docs/approved-strategies/holy-grail-pullback.md`

Content provided in the strategy doc section of this brief.

---

## Files Changed Summary

| File | Action | Location | Lines |
|------|--------|----------|-------|
| `docs/pinescript/holy_grail_webhook_v1.pine` | **NEW** | Repo | Full indicator (~180 lines) |
| `backend/webhooks/tradingview.py` | MODIFY | Railway (auto-deploy) | ~50 added |
| `backend/scoring/trade_ideas_scorer.py` | MODIFY | Railway (auto-deploy) | ~6 added |
| `scripts/pivot2_committee.py` | MODIFY | VPS | 1 line changed |
| `docs/approved-strategies/holy-grail-pullback.md` | **NEW** | Repo | ~80 lines |

---

## Verification Steps

1. **PineScript:** Load webhook version on TradingView, apply to SPY 15m. Confirm signals fire with JSON in alert log.
2. **Webhook test:** `curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview -H "Content-Type: application/json" -d '{"ticker":"SPY","strategy":"holy_grail","direction":"LONG","entry_price":572.50,"stop_loss":570.80,"target_1":575.90,"adx":28.5,"rsi":45.2,"timeframe":"60"}'`
3. **Scoring:** Confirm response includes `signal_type: "HOLY_GRAIL_1H"` and score in expected range (50-70 with bonuses).
4. **VPS routing:** SSH to VPS, confirm `holy_grail` is in `TV_COMMITTEE_STRATEGIES`. Restart not needed (committee runs on-demand).
5. **End-to-end:** Wait for a real Holy Grail signal on TradingView, confirm it appears in Discord with "Run Committee" button, run committee, verify agents discuss the pullback continuation context.

---

## What This Does NOT Do

- Does NOT modify committee prompts (agents learn about each signal from context, not system prompts)
- Does NOT add new database tables (uses existing signal pipeline)
- Does NOT require new Python packages
- Does NOT change the Whale Hunter or any other signal flow
- Does NOT add a new webhook endpoint (uses existing `/webhook/tradingview`)
- Does NOT require Nick to change his existing TradingView alerts (new indicator is separate)

## Dependencies

- TradingView account (Nick already has this)
- Holy Grail PineScript indicator (provided in this brief)
- No new API keys, packages, or infrastructure
