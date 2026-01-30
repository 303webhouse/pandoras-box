# TradingView Circuit Breaker Alert Setup

The Circuit Breaker System automatically adjusts bias and signal scoring during extreme market events.

## Webhook URL

```
https://your-app.railway.app/webhook/circuit_breaker
```

Replace `your-app.railway.app` with your actual Railway deployment URL.

## Circuit Breaker Triggers

### 1. SPY Down 1% (Minor Caution)

**Effect:**
- Caps bias at MINOR_TORO (prevents overly bullish stance)
- Reduces long signal scores by 10% (scoring_modifier = 0.9)

**TradingView Alert Setup:**
- **Symbol:** SPY
- **Condition:** Price drops 1.0% from prior close
- **Frequency:** Once per bar close
- **Webhook URL:** `https://your-app.railway.app/webhook/circuit_breaker`
- **Message:**

```json
{
  "trigger": "spy_down_1pct",
  "timestamp": "{{time}}"
}
```

**PineScript Example:**

```pinescript
//@version=5
indicator("Circuit Breaker - SPY -1%", overlay=true)

// Get prior close (yesterday's close)
priorClose = request.security(syminfo.tickerid, "D", close[1])

// Calculate % change from prior close
pctChange = ((close - priorClose) / priorClose) * 100

// Trigger when down 1% or more
if pctChange <= -1.0
    alert('{"trigger":"spy_down_1pct","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

// Visual indicator
bgcolor(pctChange <= -1.0 ? color.new(color.orange, 80) : na)
```

---

### 2. SPY Down 2% (Major Caution)

**Effect:**
- Caps bias at LEAN_TORO
- Forces bias floor at LEAN_URSA (minimum bearish stance)
- Reduces long signal scores by 25% (scoring_modifier = 0.75)

**TradingView Alert Setup:**
- **Symbol:** SPY
- **Condition:** Price drops 2.0% from prior close
- **Frequency:** Once per bar close
- **Webhook URL:** `https://your-app.railway.app/webhook/circuit_breaker`
- **Message:**

```json
{
  "trigger": "spy_down_2pct",
  "timestamp": "{{time}}"
}
```

**PineScript Example:**

```pinescript
//@version=5
indicator("Circuit Breaker - SPY -2%", overlay=true)

priorClose = request.security(syminfo.tickerid, "D", close[1])
pctChange = ((close - priorClose) / priorClose) * 100

if pctChange <= -2.0
    alert('{"trigger":"spy_down_2pct","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

bgcolor(pctChange <= -2.0 ? color.new(color.red, 80) : na)
```

---

### 3. VIX Spike (Volatility Warning)

**Effect:**
- Caps bias at MINOR_TORO
- Reduces long signal scores by 15% (scoring_modifier = 0.85)

**TradingView Alert Setup:**
- **Symbol:** VIX
- **Condition:** Price increases 15%+ intraday
- **Frequency:** Once per bar close
- **Webhook URL:** `https://your-app.railway.app/webhook/circuit_breaker`
- **Message:**

```json
{
  "trigger": "vix_spike",
  "timestamp": "{{time}}"
}
```

**PineScript Example:**

```pinescript
//@version=5
indicator("Circuit Breaker - VIX Spike", overlay=true)

// Calculate intraday % change
dayOpen = request.security(syminfo.tickerid, "D", open)
pctChange = ((close - dayOpen) / dayOpen) * 100

if pctChange >= 15.0
    alert('{"trigger":"vix_spike","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

bgcolor(pctChange >= 15.0 ? color.new(color.orange, 80) : na)
```

---

### 4. VIX Extreme (Fear Spike)

**Effect:**
- Caps bias at LEAN_TORO
- Forces bias floor at MINOR_URSA (stronger bearish stance)
- Reduces long signal scores by 30% (scoring_modifier = 0.7)

**TradingView Alert Setup:**
- **Symbol:** VIX
- **Condition:** Price crosses above 30
- **Frequency:** Once per bar close
- **Webhook URL:** `https://your-app.railway.app/webhook/circuit_breaker`
- **Message:**

```json
{
  "trigger": "vix_extreme",
  "timestamp": "{{time}}"
}
```

**PineScript Example:**

```pinescript
//@version=5
indicator("Circuit Breaker - VIX Extreme", overlay=true)

if close > 30
    alert('{"trigger":"vix_extreme","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

bgcolor(close > 30 ? color.new(color.red, 80) : na)
plotshape(close > 30, style=shape.xcross, location=location.abovebar, color=color.red, size=size.small)
```

---

### 5. SPY Up 2% (Recovery Signal)

**Effect:**
- Removes bias cap (allows bullish bias)
- Maintains bias floor at LEAN_URSA (still cautious)
- Boosts long signal scores by 10% (scoring_modifier = 1.1)

**TradingView Alert Setup:**
- **Symbol:** SPY
- **Condition:** Price rallies 2.0%+ from intraday low
- **Frequency:** Once per bar close
- **Webhook URL:** `https://your-app.railway.app/webhook/circuit_breaker`
- **Message:**

```json
{
  "trigger": "spy_up_2pct",
  "timestamp": "{{time}}"
}
```

**PineScript Example:**

```pinescript
//@version=5
indicator("Circuit Breaker - SPY +2% Recovery", overlay=true)

// Get intraday low
dayLow = request.security(syminfo.tickerid, "D", low)

// Calculate % change from low
pctFromLow = ((close - dayLow) / dayLow) * 100

if pctFromLow >= 2.0
    alert('{"trigger":"spy_up_2pct","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

bgcolor(pctFromLow >= 2.0 ? color.new(color.green, 80) : na)
```

---

### 6. SPY Recovery (All Clear)

**Effect:**
- Resets circuit breaker completely
- Removes all bias caps and floors
- Returns scoring to normal (scoring_modifier = 1.0)

**TradingView Alert Setup:**
- **Symbol:** SPY
- **Condition:** Price closes above prior session close
- **Frequency:** Once per bar close
- **Webhook URL:** `https://your-app.railway.app/webhook/circuit_breaker`
- **Message:**

```json
{
  "trigger": "spy_recovery",
  "timestamp": "{{time}}"
}
```

**PineScript Example:**

```pinescript
//@version=5
indicator("Circuit Breaker - SPY Recovery", overlay=true)

priorClose = request.security(syminfo.tickerid, "D", close[1])

if close > priorClose
    alert('{"trigger":"spy_recovery","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

bgcolor(close > priorClose ? color.new(color.green, 80) : na)
plotshape(close > priorClose, style=shape.circle, location=location.belowbar, color=color.green, size=size.tiny)
```

---

## Combined Circuit Breaker Strategy

You can combine all triggers into a single Pine Script strategy:

```pinescript
//@version=5
indicator("Circuit Breaker - All Triggers", overlay=true)

// SPY triggers
if syminfo.ticker == "SPY"
    priorClose = request.security(syminfo.tickerid, "D", close[1])
    pctChange = ((close - priorClose) / priorClose) * 100
    dayLow = request.security(syminfo.tickerid, "D", low)
    pctFromLow = ((close - dayLow) / dayLow) * 100

    // Down 1%
    if pctChange <= -1.0 and pctChange > -2.0
        alert('{"trigger":"spy_down_1pct","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

    // Down 2%
    if pctChange <= -2.0
        alert('{"trigger":"spy_down_2pct","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

    // Up 2% from low
    if pctFromLow >= 2.0
        alert('{"trigger":"spy_up_2pct","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

    // Recovery (back above prior close)
    if close > priorClose and close[1] <= priorClose
        alert('{"trigger":"spy_recovery","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

// VIX triggers
if syminfo.ticker == "VIX"
    dayOpen = request.security(syminfo.tickerid, "D", open)
    pctChange = ((close - dayOpen) / dayOpen) * 100

    // VIX Extreme (>30)
    if close > 30
        alert('{"trigger":"vix_extreme","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

    // VIX Spike (+15%)
    else if pctChange >= 15.0
        alert('{"trigger":"vix_spike","timestamp":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)
```

---

## Testing Circuit Breaker

You can test the circuit breaker without TradingView alerts:

```bash
# Test SPY -1%
curl -X POST https://your-app.railway.app/webhook/circuit_breaker/test/spy_down_1pct

# Test SPY -2%
curl -X POST https://your-app.railway.app/webhook/circuit_breaker/test/spy_down_2pct

# Test VIX spike
curl -X POST https://your-app.railway.app/webhook/circuit_breaker/test/vix_spike

# Test VIX extreme
curl -X POST https://your-app.railway.app/webhook/circuit_breaker/test/vix_extreme

# Test SPY recovery
curl -X POST https://your-app.railway.app/webhook/circuit_breaker/test/spy_up_2pct

# Test all-clear
curl -X POST https://your-app.railway.app/webhook/circuit_breaker/test/spy_recovery
```

## Check Circuit Breaker Status

```bash
curl https://your-app.railway.app/webhook/circuit_breaker/status
```

## Manual Reset

```bash
curl -X POST https://your-app.railway.app/webhook/circuit_breaker/reset
```

---

## How It Works

1. **TradingView alerts trigger the webhook** when market conditions meet thresholds
2. **Circuit breaker state is updated** with bias caps/floors and scoring modifiers
3. **Bias refresh is triggered** immediately to apply new constraints
4. **Signal scoring is modified** to penalize/boost trades based on market regime
5. **WebSocket broadcast** notifies all connected clients of circuit breaker status
6. **Auto-reset at 9:30 AM ET** each trading day (or manual reset via API)

## Signal Scoring Impact

### Bearish Circuit Breaker (SPY down, VIX spike)

- **LONG signals:** Penalized by scoring_modifier (0.7-0.9x)
- **SHORT signals:** Boosted by 1.3x
- **SHORT exhaustion/reversal signals:** Boosted by 1.56x (1.3 × 1.2)

### Bullish Circuit Breaker (SPY recovery)

- **SHORT signals:** Penalized by scoring_modifier (0.9-1.0x)
- **LONG signals:** Boosted by 1.3x
- **LONG exhaustion/reversal signals:** Boosted by 1.56x (1.3 × 1.2)

---

## Bias Level Reference

From most bearish to most bullish:
1. **MAJOR_URSA** (6 = most bearish)
2. **MINOR_URSA** (5)
3. **LEAN_URSA** (4)
4. **LEAN_TORO** (3)
5. **MINOR_TORO** (2)
6. **MAJOR_TORO** (1 = most bullish)

Circuit breaker caps/floors use these levels to constrain bias calculations.
