# PineScript Inventory

**Last Updated:** March 6, 2026
**Purpose:** Single source of truth for all TradingView indicators/alerts feeding the Pandora's Box pipeline.

---

## Status Legend

- ✅ **IN REPO + ACTIVE** — Script is stored here and confirmed sending webhooks
- ⚠️ **ACTIVE BUT NOT IN REPO** — Confirmed firing on TradingView, but the .pine source code is NOT saved here. **Nick needs to export these from TradingView.**
- 📊 **IN REPO / VISUAL ONLY** — Stored here but does NOT send webhooks. Chart overlay or visual aid only.
- 🔴 **DEAD / SUPERSEDED** — No longer in use or replaced by a newer version.

---

## Trade Signal Scripts (Generate Trade Ideas)

### ✅ Holy Grail Webhook v1 — `holy_grail_webhook_v1.pine`
- **Status:** IN REPO + ACTIVE
- **What it does:** Linda Raschke continuation entry. ADX ≥ 25, pullback to 20 EMA, confirmation candle. Sends JSON webhook.
- **Webhook route:** `/webhook/tradingview` → `process_holy_grail_signal()`
- **Signal types:** `HOLY_GRAIL_1H`, `HOLY_GRAIL_15M`
- **Trade Ideas count (all time):** 8
- **Fields sent:** ticker, strategy ("holy_grail"), direction, entry_price, stop_loss, target_1, adx, rsi, timeframe, rvol (DI spread)
- **Applied to:** QQQ, SPY, individual equities (multi-chart)

### ⚠️ Scout Sniper — NOT IN REPO
- **Status:** ACTIVE on TradingView, **SOURCE CODE NOT SAVED**
- **What it does:** 15-minute early warning reversal scanner. Lower priority, shorter TTL.
- **Webhook route:** `/webhook/tradingview` → `process_scout_signal()`
- **Signal types:** `SCOUT_ALERT`
- **Trade Ideas count (all time):** 21
- **Fields sent:** ticker, strategy ("scout"), direction, entry/stop/tp1/tp2 (alternate field names), rsi, rvol, timeframe, price, tier, status
- **⚠️ ACTION NEEDED:** Export this script from TradingView and save as `docs/pinescript/webhooks/scout_sniper_webhook.pine`

### ⚠️ Hub Sniper / Ursa-Taurus — NOT IN REPO
- **Status:** ACTIVE on TradingView, **SOURCE CODE NOT SAVED**
- **What it does:** Primary directional signal generator. Produces BULLISH_TRADE / BEAR_CALL signals.
- **Webhook route:** `/webhook/tradingview` → `process_sniper_signal()`
- **Signal types:** `BULLISH_TRADE`, `BEAR_CALL` (can upgrade to `APIS_CALL` / `KODIAK_CALL` at score ≥ 85)
- **Trade Ideas count (all time):** 6
- **Fields sent:** ticker, strategy ("sniper"), direction, entry_price, stop_loss, target_1, target_2, rsi, adx, timeframe
- **⚠️ ACTION NEEDED:** Export this script from TradingView and save as `docs/pinescript/webhooks/hub_sniper_webhook.pine`

---

## Bias Factor Data Scripts (Feed Bias Engine, NOT Trade Signals)

### ⚠️ TICK Alert — NOT IN REPO
- **Status:** ACTIVE on TradingView, source not saved
- **What it does:** Sends $TICK high/low/close/avg every 15 minutes during market hours
- **Webhook route:** `/webhook/tick`
- **Bias factor:** `tick_breadth`
- **Setup reference:** Webhook payload format is documented in `tradingview.py` comments
- **⚠️ ACTION NEEDED:** Export from TradingView → `docs/pinescript/webhooks/tick_alert.pine`

### ⚠️ Breadth ($UVOL/$DVOL) Alert — NOT IN REPO
- **Status:** Set up Mar 5, expected to fire Mar 6 at 9:30 AM ET
- **What it does:** Sends NYSE up volume / down volume ratio
- **Webhook route:** `/webhook/breadth`
- **Bias factor:** `breadth_intraday`
- **⚠️ ACTION NEEDED:** Export from TradingView → `docs/pinescript/webhooks/breadth_alert.pine`

### ⚠️ McClellan ($ADVN/$DECLN) Alert — NOT IN REPO
- **Status:** Set up Mar 5, building 40-day baseline
- **What it does:** Sends daily NYSE advancing/declining issues
- **Webhook route:** `/webhook/mcclellan`
- **Bias factor:** `mcclellan_oscillator`
- **⚠️ ACTION NEEDED:** Export from TradingView → `docs/pinescript/webhooks/mcclellan_alert.pine`

### ⚠️ Circuit Breaker Alerts — NOT IN REPO AS STANDALONE
- **Status:** ACTIVE (inline PineScript in `docs/tradingview-circuit-breaker-alerts.md`)
- **What it does:** 6 triggers: SPY -1%, SPY -2%, VIX spike, VIX extreme, SPY +2% recovery, SPY recovery
- **Webhook route:** `/webhook/circuit_breaker`
- **Note:** PineScript examples exist inline in the doc. May be deployed as individual alerts or a combined script on TradingView. Should be extracted into a standalone file.
- **⚠️ ACTION NEEDED:** Confirm which version is on TradingView (individual or combined), export → `docs/pinescript/webhooks/circuit_breaker_combined.pine`

---

## Visual Overlays (Chart Aids Only — No Webhooks)

### 📊 CTA Context Indicator — `cta_context_indicator.pine`
- **What it does:** Shows CTA zones (MAX_LONG, DE_LEVERAGING, etc.) based on 20/50/120 SMA alignment
- **Use:** Visual chart reference for CTA zone awareness

### 📊 CTA Signals Indicator — `cta_signals_indicator.pine`
- **What it does:** Visual signal markers for CTA strategy setups on chart
- **Use:** Visual only — actual CTA signal generation runs server-side via `cta_scanner.py`

### 📊 Enhanced CTA VWAP Indicator — `enhanced_cta_vwap_indicator.pine`
- **What it does:** CTA framework enhanced with VWAP integration
- **Use:** Visual chart overlay

### 📊 LBR 3/10 Oscillator — `lbr_3_10_oscillator.pine`
- **What it does:** Linda Raschke 3/10 momentum oscillator (MACD variant with 3/10/16 settings)
- **Use:** Visual momentum reference. Previously evaluated for integration as either a bias factor or signal source — decision pending.

---

## Superseded / Deprecated

### 🔴 Holy Grail Pullback (Non-Webhook) — `holy_grail_pullback.pine`
- **Superseded by:** `holy_grail_webhook_v1.pine`
- **What it does:** Same logic as the webhook version but only generates visual alerts, no JSON webhook payload
- **Recommendation:** Archive or delete. The webhook version is the active one.

---

## Server-Side Scanners (No PineScript — Runs on Railway)

These are NOT PineScript indicators. They run as Python code on the Railway backend and generate signals from market data APIs (Polygon, yfinance).

| Scanner | Backend File | Signal Types | Status |
|---|---|---|---|
| CTA Scanner | `backend/scanners/cta_scanner.py` (79KB) | PULLBACK_ENTRY, RESISTANCE_REJECTION, TWO_CLOSE_VOLUME, GOLDEN_TOUCH, TRAPPED_SHORTS/LONGS, BEARISH_BREAKDOWN, DEATH_CROSS | ✅ Active — 285 trade ideas |
| Exhaustion | `backend/strategies/exhaustion.py` | EXHAUSTION_BULL, EXHAUSTION_BEAR | ✅ Active — 13 trade ideas |
| Crypto Scanner | `backend/scanners/???` | Unknown sub-types | ✅ Active — 57 trade ideas (needs Phase 2 audit) |
| Whale Hunter | `backend/scanners/hunter.py` + `backend/webhooks/whale.py` | Unknown | ❓ Handler exists, 0 trade ideas |
| Hybrid Scanner | `backend/scanners/hybrid_scanner.py` (42KB) | N/A | ❓ UI killed in Brief 09, backend status unknown |

---

## Proposed Folder Structure

Once all scripts are exported from TradingView:

```
docs/pinescript/
├── PINESCRIPT_INVENTORY.md          ← This file
├── webhooks/                        ← Scripts that send data to Railway
│   ├── holy_grail_webhook_v1.pine
│   ├── scout_sniper_webhook.pine    ← EXPORT FROM TV
│   ├── hub_sniper_webhook.pine      ← EXPORT FROM TV
│   ├── tick_alert.pine              ← EXPORT FROM TV
│   ├── breadth_alert.pine           ← EXPORT FROM TV
│   ├── mcclellan_alert.pine         ← EXPORT FROM TV
│   └── circuit_breaker_combined.pine ← EXPORT FROM TV
├── overlays/                        ← Visual chart aids only
│   ├── cta_context_indicator.pine
│   ├── cta_signals_indicator.pine
│   ├── enhanced_cta_vwap_indicator.pine
│   └── lbr_3_10_oscillator.pine
└── archive/                         ← Superseded scripts
    └── holy_grail_pullback.pine
```

---

## Export Checklist for Nick

- [ ] **Scout Sniper** — Open TradingView → Pine Editor → find the Scout indicator → Copy source → Save to repo
- [ ] **Hub Sniper / Ursa-Taurus** — Same process
- [ ] **TICK Alert** — Find the $TICK alert indicator or alert config
- [ ] **Breadth Alert** — Find the $UVOL/$DVOL alert indicator
- [ ] **McClellan Alert** — Find the $ADVN/$DECLN alert indicator
- [ ] **Circuit Breaker** — Find whichever version is actually deployed (individual or combined)
- [ ] After all exports, reorganize folder structure per the proposal above
