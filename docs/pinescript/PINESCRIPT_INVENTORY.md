# PineScript Inventory

**Last Updated:** March 6, 2026
**Purpose:** Single source of truth for all TradingView indicators/alerts feeding the Pandora's Box pipeline.

**Status:** ✅ ALL SCRIPTS NOW IN REPO (completed Mar 6, 2026)

---

## Status Legend

- ✅ **IN REPO + ACTIVE** — Script stored here, TV alert configured, confirmed sending webhooks
- 🟡 **IN REPO / NOT WIRED** — Script stored here but TV alert not configured or no Railway handler
- 📊 **IN REPO / VISUAL ONLY** — Chart overlay, no webhooks
- 🔴 **SUPERSEDED** — Replaced by a newer version

---

## Trade Signal Scripts (Generate Trade Ideas)

### ✅ Holy Grail Webhook v1 — `webhooks/holy_grail_webhook_v1.pine`
- **Signal types:** `HOLY_GRAIL_1H`, `HOLY_GRAIL_15M`
- **Route:** `/webhook/tradingview` → `process_holy_grail_signal()`
- **Trade Ideas (all time):** 8
- **Payload:** JSON — ticker, strategy ("holy_grail"), direction, entry_price, stop_loss, target_1, adx, rsi, timeframe, rvol (DI spread)

### ✅ Scout Sniper v3.1 — `webhooks/scout_sniper_v3.1.pine`
- **Signal types:** `SCOUT_ALERT`
- **Route:** `/webhook/tradingview` → `process_scout_signal()`
- **Trade Ideas (all time):** 21
- **Payload:** JSON — ticker, strategy ("ScoutSniper"), direction, tier (A/B), status (TRADEABLE/IGNORE), score (0-6), sma_regime, price, rsi, rvol, entry, stop, tp1, tp2, htf_vwap, d_vwap
- **Note:** TRADEABLE/IGNORE status sent but not enforced server-side

### ✅ Hub Sniper v2.1 — `webhooks/hub_sniper_v2.1.pine`
- **Signal types:** `BULLISH_TRADE`, `BEAR_CALL` (upgradeable to `APIS_CALL`/`KODIAK_CALL` at score ≥ 85)
- **Route:** `/webhook/tradingview` → `process_sniper_signal()`
- **Trade Ideas (all time):** 6
- **Payload:** JSON — ticker, strategy ("Sniper"), direction, entry_price, stop_loss, target_1, target_2, risk_reward, timeframe, adx, adx_rising, rsi, rvol, mode (Normal/Flush), avwap_ctx

### 🟡 Dark Pool Whale Hunter v2 — `webhooks/whale_hunter_v2.pine`
- **Signal types:** `WHALE` (lean: BULLISH/BEARISH/CONTESTED)
- **Route:** `/webhook/whale` → `whale.py`
- **Trade Ideas (all time):** 0 — **TV alert not configured yet**
- **Payload:** JSON — ticker, tf, lean, poc, price, entry, stop, tp1, tp2, rvol, consec_bars, structural, regime, adx
- **TODO:** Configure TV alert on target charts; verify `whale.py` handler parses v2 JSON format

### 🟡 Absorption Wall Detector v1.5 — `webhooks/absorption_wall_detector_v1.5.pine`
- **Signal types:** `absorption_wall`, `absorption_wall_bull`, `absorption_wall_bear`
- **Route:** No Railway handler exists
- **Trade Ideas (all time):** 0 — **No handler to receive data**
- **Payload:** Pipe-delimited (NOT JSON) — type, symbol, tf, time, price, vol, deltaRatio, buyPct, buyVol, sellVol, totVol, minDist
- **TODO:** Either build a Railway handler that parses pipe-delimited format, or rewrite the alert payload to JSON and route through the generic handler

---

## Bias Factor Data Scripts (Feed Bias Engine, NOT Trade Signals)

### ✅ TICK Reporter — `webhooks/tick_reporter.pine`
- **Route:** `/webhook/tick`
- **Factor:** `tick_breadth`
- **Payload:** JSON — tick_high, tick_low, tick_close, tick_avg
- **Fires:** Every bar during market hours (9:30-4:00 ET) on $TICK chart

### ✅ Breadth Webhook — `webhooks/breadth_webhook.pine`
- **Route:** `/webhook/breadth`
- **Factor:** `breadth_intraday`
- **Payload:** JSON — uvol, dvol
- **Fires:** Every confirmed bar. Set up Mar 5, first fire expected Mar 6.
- **Note:** PineScript v6

### ✅ McClellan Webhook — `webhooks/mcclellan_webhook.pine`
- **Route:** `/webhook/mcclellan`
- **Factor:** `mcclellan_oscillator`
- **Payload:** JSON — advn, decln
- **Fires:** Daily on confirmed bar close. Building 40-day baseline (set up Mar 5).
- **Note:** PineScript v6

### ✅ Circuit Breaker (VIX) — `webhooks/circuit_breaker_vix.pine`
- **Route:** `/webhook/circuit_breaker`
- **Triggers:** `vix_spike` (15%+ intraday), `vix_extreme` (VIX > 25)
- **Payload:** JSON — type ("circuit_breaker"), trigger
- **Fires:** On state change only (NORMAL → SPIKE → EXTREME → RECOVERED)

### ✅ Circuit Breaker (SPY) — `webhooks/circuit_breaker_spy.pine`
- **Route:** `/webhook/circuit_breaker`
- **Triggers:** `spy_down_1pct`, `spy_down_2pct`, `spy_up_2pct`, `spy_recovery`
- **Payload:** JSON — type ("circuit_breaker"), trigger
- **Fires:** On state change only

---

## Visual Overlays (Chart Aids Only — No Webhooks)

### 📊 CTA Context Indicator — `cta_context_indicator.pine`
CTA zones (MAX_LONG, DE_LEVERAGING, etc.) based on 20/50/120 SMA alignment.

### 📊 CTA Signals Indicator — `cta_signals_indicator.pine`
Visual signal markers for CTA setups. Actual signal generation runs server-side.

### 📊 Enhanced CTA VWAP Indicator — `enhanced_cta_vwap_indicator.pine`
CTA framework + VWAP integration overlay.

### 📊 LBR 3/10 Oscillator — `lbr_3_10_oscillator.pine`
Linda Raschke 3/10 momentum oscillator. Integration decision pending (bias factor vs. signal source vs. visual-only).

---

## Superseded

### 🔴 Holy Grail Pullback (Non-Webhook) — `holy_grail_pullback.pine`
Superseded by `webhooks/holy_grail_webhook_v1.pine`. Same logic, no webhook. Should be moved to archive.

---

## Server-Side Scanners (Python on Railway — No PineScript)

| Scanner | File | Signal Types | Trade Ideas | Status |
|---|---|---|---|---|
| CTA Scanner | `scanners/cta_scanner.py` (79KB) | PULLBACK_ENTRY, RESISTANCE_REJECTION, TWO_CLOSE_VOLUME, GOLDEN_TOUCH*, TRAPPED_SHORTS/LONGS, BEARISH_BREAKDOWN, DEATH_CROSS | 285 | ✅ Active |
| Exhaustion | `strategies/exhaustion.py` | EXHAUSTION_BULL, EXHAUSTION_BEAR | 13 | ✅ Active |
| Crypto Scanner | `scanners/???` | Unknown | 57 | ✅ Active (Phase 2 audit) |
| Hybrid Scanner | `scanners/hybrid_scanner.py` (42KB) | N/A | 0 | ⚠️ UI killed, backend still mounted in main.py |

*GOLDEN_TOUCH has never fired — fix brief in progress (`brief-golden-touch-fix.md`)

---

## Folder Structure (Current)

```
docs/pinescript/
├── PINESCRIPT_INVENTORY.md              ← This file
├── webhooks/                            ← All webhook-capable scripts
│   ├── holy_grail_webhook_v1.pine       ✅ Active
│   ├── scout_sniper_v3.1.pine           ✅ Active
│   ├── hub_sniper_v2.1.pine             ✅ Active
│   ├── whale_hunter_v2.pine             🟡 Not wired to TV yet
│   ├── absorption_wall_detector_v1.5.pine 🟡 No Railway handler
│   ├── tick_reporter.pine               ✅ Active (bias factor)
│   ├── breadth_webhook.pine             ✅ Active (bias factor)
│   ├── mcclellan_webhook.pine           ✅ Active (bias factor)
│   ├── circuit_breaker_vix.pine         ✅ Active (bias factor)
│   └── circuit_breaker_spy.pine         ✅ Active (bias factor)
├── cta_context_indicator.pine           📊 Visual overlay
├── cta_signals_indicator.pine           📊 Visual overlay
├── enhanced_cta_vwap_indicator.pine     📊 Visual overlay
├── lbr_3_10_oscillator.pine             📊 Visual overlay
└── holy_grail_pullback.pine             🔴 Superseded — move to archive
```
