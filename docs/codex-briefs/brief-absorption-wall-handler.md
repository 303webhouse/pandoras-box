# Brief: Wire Absorption Wall Detector to Trade Ideas Pipeline

**Priority:** HIGH — Adds the only ORDER FLOW lens to the confluence pool.
**Target:** Two changes: TradingView PineScript (alert format) + Railway backend (handler)
**Estimated time:** 1-2 days

---

## Problem

The Absorption Wall Detector v1.5 is running on TradingView with alerts configured and firing. But:
1. The alert payload uses **pipe-delimited format** (not JSON)
2. There is **no Railway handler** to receive the data

Result: signals fire into the void. This is the only strategy that detects order flow balance (buy/sell delta at high volume levels), making it a unique and valuable lens for the confluence engine.

## Solution: Two-Part Fix

### Part 1: Rewrite PineScript Alert Payload to JSON

The current PineScript (`docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine`) sends pipe-delimited alerts:
```
type=absorption_wall|symbol=NASDAQ:AAPL|tf=15|time=...|price=...
```

**Find the alert section at the bottom of the file (around line 215-230).** Replace the three `alertcondition()` calls with a single `alert()` call that sends JSON, matching the pattern used by all other webhook scripts.

**Find this block:**
```pine
alertcondition(wall, title="Absorption Wall (Any)",
     message="type=absorption_wall|symbol={{exchange}}:{{ticker}}|tf={{interval}}|time={{time}}|price={{close}}|vol={{volume}}|deltaRatio={{plot_0}}|buyPct={{plot_1}}|buyVol={{plot_2}}|sellVol={{plot_3}}|totVol={{plot_4}}|minDist={{plot_5}}")

alertcondition(bullWall, title="Bullish Absorption Wall",
     message="type=absorption_wall_bull|symbol={{exchange}}:{{ticker}}|tf={{interval}}|time={{time}}|price={{close}}|vol={{volume}}|deltaRatio={{plot_0}}|buyPct={{plot_1}}|buyVol={{plot_2}}|sellVol={{plot_3}}|totVol={{plot_4}}|minDist={{plot_5}}")

alertcondition(bearWall, title="Bearish Absorption Wall",
     message="type=absorption_wall_bear|symbol={{exchange}}:{{ticker}}|tf={{interval}}|time={{time}}|price={{close}}|vol={{volume}}|deltaRatio={{plot_0}}|buyPct={{plot_1}}|buyVol={{plot_2}}|sellVol={{plot_3}}|totVol={{plot_4}}|minDist={{plot_5}}")
```

**Replace with this JSON alert block (add AFTER the existing alertconditions, don't remove them):**
```pine
// JSON webhook alert for Trading Hub pipeline
if wall and barstate.isconfirmed and (bullWall or bearWall)
    string direction = bullWall ? "LONG" : "SHORT"
    string wallType = bullWall ? "BULL_WALL" : "BEAR_WALL"
    
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

**Nick must then update the TradingView alert** to point to:
```
https://pandoras-box-production.up.railway.app/webhook/tradingview
```

The `strategy: "AbsorptionWall"` field will route through the existing `process_generic_signal()` handler in `tradingview.py`, which produces `BULLISH_TRADE` or `BEAR_CALL` signal types based on direction.

### Part 2: Update the PineScript File in Repo

Update `docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine` with the new JSON alert block added after the existing alertconditions.

## Alternative: Dedicated Handler (Optional, Not Required)

The generic handler works fine. But if we want to preserve the rich order flow data (delta_ratio, buy_pct, buy_vol, sell_vol), we could add a dedicated route:

**In `backend/webhooks/tradingview.py`, add before the generic handler:**
```python
elif "absorption" in strategy_lower or "wall" in strategy_lower:
    return await process_absorption_signal(alert, start_time)
```

And add the handler:
```python
async def process_absorption_signal(alert: TradingViewAlert, start_time: datetime):
    """Process Absorption Wall signals with order flow context."""
    signal_id = f"WALL_{alert.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    direction = (alert.direction or "").upper()
    signal_type = "BULL_WALL" if direction in ["LONG", "BUY"] else "BEAR_WALL"
    
    signal_data = {
        "signal_id": signal_id,
        "timestamp": alert.timestamp or datetime.now().isoformat(),
        "ticker": alert.ticker,
        "strategy": "AbsorptionWall",
        "direction": alert.direction,
        "signal_type": signal_type,
        "entry_price": alert.entry_price,
        "timeframe": alert.timeframe,
        "trade_type": "ORDER_FLOW",
        "asset_class": "CRYPTO" if is_crypto_ticker(alert.ticker) else "EQUITY",
        "status": "ACTIVE",
    }
    
    asyncio.ensure_future(process_signal_unified(signal_data, source="tradingview"))
    
    logger.info(f"🧱 Absorption Wall accepted: {alert.ticker} {signal_type}")
    return {"status": "accepted", "signal_id": signal_id, "signal_type": signal_type}
```

This is optional — the generic handler already works. The dedicated handler just gives cleaner logging and preserves the `ORDER_FLOW` trade type.

## Confluence Integration

Once wired, Absorption Wall signals are automatically categorized as `ORDER_FLOW_BALANCE` lens by the confluence engine (already configured in `backend/confluence/lenses.py` with the mapping `"AbsorptionWall": "ORDER_FLOW_BALANCE"`).

## Files Changed

- `docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine` — Add JSON alert block
- `backend/webhooks/tradingview.py` — Optionally add dedicated handler route

## Deployment

1. Push PineScript update to repo
2. Push handler update to repo → Railway auto-deploy
3. **Nick manually:** Update the PineScript on TradingView (copy new alert block into Pine Editor)
4. **Nick manually:** Update TradingView alert webhook URL to point to `/webhook/tradingview`

## Validation

After Nick updates the TV alert:
1. Wait for next Absorption Wall signal to fire on TradingView
2. Check Railway logs for `Absorption Wall accepted:` or `Generic signal accepted:`
3. Check Trade Ideas for a new signal with strategy `AbsorptionWall`
4. Check confluence engine for `ORDER_FLOW_BALANCE` lens appearing in groupings
