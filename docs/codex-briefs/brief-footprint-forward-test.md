# Brief: Footprint Forward Test

## Purpose
Forward-test the "Volume Imbalance Pro" TradingView indicator alongside Whale Hunter for 2 weeks (Mar 14 – Mar 28, 2026). Track footprint signals (stacked imbalances + absorption) in the signals table and build a correlation dashboard to compare performance head-to-head with Whale Hunter dark pool signals.

## Three Deliverables

### Deliverable 1: Pine Script — Slim Footprint Alert Script
**Owner: Nick (manual paste into TradingView)**

Strip the Volume Imbalance Pro down to ONLY the two high-value signal types and a single `alert()` call with JSON payload. Remove all visualization, RSI, MACD, divergence detection, status table, and the 5 other alert types. The resulting script should be ~80 lines.

**Exact Pine Script to paste:**

```pinescript
//@version=6
indicator("Footprint Alert for Pandora", shorttitle="FP→Pandora", overlay=true)

// === Settings ===
ticksPerRow = input.int(10, "Ticks Per Row", minval=1, maxval=100)
vaPercent = input.float(70, "Value Area %", minval=50, maxval=95)
imbalancePct = input.float(300, "Imbalance Threshold %", minval=150, maxval=500)
minStackedRows = input.int(3, "Min Stacked Rows", minval=2, maxval=5)
webhookSecret = input.string("", "Webhook Secret", tooltip="Must match TRADINGVIEW_WEBHOOK_SECRET env var")

// === Footprint Data ===
fpData = request.footprint(ticksPerRow, vaPercent, imbalancePct)
rows = not na(fpData) ? footprint.rows(fpData) : na

// === Analyze Imbalances ===
var int maxBuyStreak = 0
var int maxSellStreak = 0
var int buyCount = 0
var int sellCount = 0

if not na(rows)
    int curBuy = 0
    int curSell = 0
    maxBuyStreak := 0
    maxSellStreak := 0
    buyCount := 0
    sellCount := 0
    
    for i = 0 to array.size(rows) - 1
        row = array.get(rows, i)
        if volume_row.has_buy_imbalance(row)
            buyCount += 1
            curBuy += 1
            curSell := 0
        else
            if curBuy > maxBuyStreak
                maxBuyStreak := curBuy
            curBuy := 0
        
        if volume_row.has_sell_imbalance(row)
            sellCount += 1
            curSell += 1
            curBuy := 0
        else
            if curSell > maxSellStreak
                maxSellStreak := curSell
            curSell := 0
    
    if curBuy > maxBuyStreak
        maxBuyStreak := curBuy
    if curSell > maxSellStreak
        maxSellStreak := curSell

// === Signal Detection ===
bool hasStackedBuy = maxBuyStreak >= minStackedRows and close > open
bool hasStackedSell = maxSellStreak >= minStackedRows and close < open
bool buyAbsorption = close < open and buyCount > 0 and (close - low) > (high - close) * 2
bool sellAbsorption = close > open and sellCount > 0 and (high - close) > (close - low) * 2

// === Determine signal type ===
string signalType = hasStackedBuy ? "stacked_buy" : hasStackedSell ? "stacked_sell" : buyAbsorption ? "buy_absorption" : sellAbsorption ? "sell_absorption" : ""
string direction = (hasStackedBuy or buyAbsorption) ? "LONG" : (hasStackedSell or sellAbsorption) ? "SHORT" : ""

bool shouldFire = barstate.isconfirmed and not na(fpData) and str.length(signalType) > 0

// === Single alert with JSON payload ===
if shouldFire
    alert('{"signal":"FOOTPRINT","ticker":"' + syminfo.ticker + '","tf":"' + timeframe.period + '","sub_type":"' + signalType + '","direction":"' + direction + '","price":' + str.tostring(close) + ',"stacked_layers":' + str.tostring(math.max(maxBuyStreak, maxSellStreak)) + ',"buy_imb_count":' + str.tostring(buyCount) + ',"sell_imb_count":' + str.tostring(sellCount) + ',"secret":"' + webhookSecret + '"}', alert.freq_once_per_bar)

// === Visual markers (minimal) ===
plotshape(hasStackedBuy, "Stacked Buy", location=location.belowbar, color=color.new(color.green, 30), style=shape.triangleup, size=size.small)
plotshape(hasStackedSell, "Stacked Sell", location=location.abovebar, color=color.new(color.red, 30), style=shape.triangledown, size=size.small)
plotshape(buyAbsorption, "Buy Absorb", location=location.belowbar, color=color.new(color.blue, 30), style=shape.diamond, size=size.tiny)
plotshape(sellAbsorption, "Sell Absorb", location=location.abovebar, color=color.new(color.orange, 30), style=shape.diamond, size=size.tiny)
```

**Nick's setup steps:**
1. Add indicator to each of the 32 Whale Hunter tickers
2. For each ticker: create ONE alert → condition = "Footprint Alert for Pandora" → "Any alert()" → Webhook URL = `https://pandoras-box-production.up.railway.app/webhook/tradingview` → Message = `{{message}}`
3. Set webhook secret in the indicator settings to match your `TRADINGVIEW_WEBHOOK_SECRET` env var

---

### Deliverable 2: Backend — Footprint Webhook Handler
**Owner: Claude Code**

**New file: `backend/webhooks/footprint.py`**

Pattern: Clone `backend/webhooks/whale.py` structure exactly. Key differences:

- Pydantic model `FootprintSignal` with fields: `signal`, `ticker`, `tf`, `sub_type`, `direction`, `price`, `stacked_layers`, `buy_imb_count`, `sell_imb_count`, `secret`
- Route: `POST /footprint`
- Signal category: `FOOTPRINT` (not `DARK_POOL`)
- Strategy name: `Footprint_Imbalance`
- Signal type: `FOOTPRINT_{direction}` (e.g. `FOOTPRINT_LONG`)
- Signal ID format: `FP_{ticker}_{timestamp}_{hash}`
- Dedup window: 300s (footprint signals can recur faster than whale prints)
- Redis cache key: `footprint:recent:{TICKER}` with 30 min TTL
- Discord embed: use 🔬 emoji, title "FOOTPRINT ALERT", show sub_type, stacked layers, imbalance counts
- Pipeline integration: call `process_signal_unified()` with base_score=40 (same as UW Flow)
- Metadata dict should include: `sub_type`, `stacked_layers`, `buy_imb_count`, `sell_imb_count`

**Mount the router in `backend/main.py`:**

Find this line pattern in main.py (near other webhook imports):
```python
from webhooks.whale import router as whale_router
```
Add below it:
```python
from webhooks.footprint import router as footprint_router
```

Find where whale_router is included (pattern: `app.include_router(whale_router`):
Add below it:
```python
app.include_router(footprint_router, prefix="/webhook", tags=["webhooks"])
```

**Also modify `backend/webhooks/tradingview.py`** to route FOOTPRINT signals:

In the main tradingview webhook handler, find where it dispatches based on `signal` field. Add a check:
```python
if payload.get("signal") == "FOOTPRINT":
    # Forward to footprint handler
    from webhooks.footprint import footprint_webhook, FootprintSignal
    fp_data = FootprintSignal(**payload)
    return await footprint_webhook(fp_data)
```

This way the single TV webhook URL handles both WHALE and FOOTPRINT payloads automatically.

---

### Deliverable 3: Correlation Engine + Dashboard Tab
**Owner: Claude Code**

**New file: `backend/api/footprint_correlation.py`**

API endpoint: `GET /api/analytics/footprint-correlation`

Query params: `days` (default 14), `window_minutes` (default 30)

Logic:
1. Fetch all signals where `signal_category IN ('DARK_POOL', 'FOOTPRINT')` from the last N days
2. Group by ticker + time window: signals within `window_minutes` of each other on the same ticker = "coincident"
3. Classify each signal into buckets:
   - `whale_solo` — DARK_POOL signal with no FOOTPRINT within window
   - `footprint_solo` — FOOTPRINT signal with no DARK_POOL within window  
   - `confluence` — both fired within window on same ticker
4. For each bucket, compute: count, win_rate (from signal_outcomes if available), avg days to resolution
5. Return JSON:
```json
{
  "period_days": 14,
  "window_minutes": 30,
  "buckets": {
    "whale_solo": {"count": 0, "wins": 0, "losses": 0, "pending": 0, "win_rate": null},
    "footprint_solo": {"count": 0, "wins": 0, "losses": 0, "pending": 0, "win_rate": null},
    "confluence": {"count": 0, "wins": 0, "losses": 0, "pending": 0, "win_rate": null}
  },
  "signals": [
    {"signal_id": "...", "ticker": "...", "category": "...", "bucket": "...", "created_at": "...", "outcome": null}
  ]
}
```

**Frontend: Add "Footprint Test" tab to Abacus section of the hub**

Simple table view showing:
- Summary cards at top: Whale Solo (count/win%), Footprint Solo (count/win%), Confluence (count/win%)
- Below: chronological signal list with columns: Time, Ticker, Source (Whale/Footprint/Both), Direction, Outcome, Days Held
- Auto-refresh every 60s
- Evaluation countdown: "X days remaining" until Mar 28

---

## Verification Checklist

After deploy:
- [ ] `curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview -H 'Content-Type: application/json' -d '{"signal":"FOOTPRINT","ticker":"SPY","tf":"5","sub_type":"stacked_buy","direction":"LONG","price":560.50,"stacked_layers":4,"buy_imb_count":6,"sell_imb_count":1,"secret":"YOUR_SECRET"}'` returns `{"status": "received"}`
- [ ] Signal appears in signals table with `signal_category=FOOTPRINT`
- [ ] Discord gets footprint embed in #📊-signals
- [ ] `/api/analytics/footprint-correlation` returns valid JSON
- [ ] Hub Abacus section shows new Footprint Test tab
- [ ] Dedup works: same signal within 300s returns `{"status": "duplicate"}`

## Test Plan
- Unit tests for FootprintSignal model validation
- Unit test for correlation bucketing logic (mock signals at various time offsets)
- Integration test: POST footprint webhook → verify signal in DB

## Out of Scope
- Modifying Whale Hunter Pine Script (separate indicator)
- Modifying existing signal scoring (footprint gets base_score=40, same as UW Flow)
- Committee pipeline integration (footprint signals enter the same pipeline as everything else — committee will pick them up automatically if they pass gatekeeper)
