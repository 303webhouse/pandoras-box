# Dollar Smile TradingView Webhook Setup

## Overview

The Dollar Smile indicator uses TradingView webhooks to automatically update the macro bias in Pandora's Box. This requires two alerts: one for DXY and one for VIX.

## Webhook URL

```
https://pandoras-box-production.up.railway.app/api/dollar-smile/webhook
```

---

## Alert 1: DXY (US Dollar Index)

### Step 1: Open DXY Chart
1. Go to TradingView
2. Search for `DXY` or `TVC:DXY`
3. Set timeframe to **Daily**

### Step 2: Add the Alert Condition
1. Click "Alerts" (clock icon) → "Create Alert"
2. Condition: `DXY` → `Crossing` → (any value, we just want daily updates)
   
   **OR better:** Use a simple condition that fires daily:
   - Condition: `Time` → `Every day at` → `16:00` (market close)

### Step 3: Configure the Webhook
1. In the alert dialog, check "Webhook URL"
2. Paste: `https://pandoras-box-production.up.railway.app/api/dollar-smile/webhook`

### Step 4: Set the Message (JSON payload)
```json
{
  "indicator": "dxy",
  "value": {{close}},
  "value_5d_ago": {{close[5]}}
}
```

**Note:** TradingView placeholders:
- `{{close}}` = Current close price
- `{{close[5]}}` = Close price 5 bars ago (5 days on daily chart)

### Step 5: Save Alert
- Name: "Dollar Smile - DXY Update"
- Set expiration or make it recurring

---

## Alert 2: VIX (Volatility Index)

### Step 1: Open VIX Chart
1. Go to TradingView
2. Search for `VIX` or `TVC:VIX`
3. Set timeframe to **Daily**

### Step 2: Create Alert
1. Click "Alerts" → "Create Alert"
2. Condition: Daily close update (same as DXY)

### Step 3: Configure Webhook
1. Check "Webhook URL"
2. Paste: `https://pandoras-box-production.up.railway.app/api/dollar-smile/webhook`

### Step 4: Set the Message
```json
{
  "indicator": "vix",
  "value": {{close}}
}
```

### Step 5: Save Alert
- Name: "Dollar Smile - VIX Update"

---

## Alternative: Combined Alert (Advanced)

If you want a single alert that sends both DXY and VIX, you can create a custom indicator in Pine Script:

```pinescript
//@version=5
indicator("Dollar Smile Data", overlay=false)

// Get DXY data
dxy = request.security("TVC:DXY", "D", close)
dxy_5d = request.security("TVC:DXY", "D", close[5])

// Get VIX data  
vix = request.security("TVC:VIX", "D", close)

// Plot for alert trigger
plot(dxy, title="DXY")

// Alert message (use in alert dialog)
alertcondition(true, "Dollar Smile Update", 
  '{"indicator": "dollar_smile", "dxy_current": ' + str.tostring(dxy) + 
  ', "dxy_5d_ago": ' + str.tostring(dxy_5d) + 
  ', "vix_current": ' + str.tostring(vix) + '}')
```

Then create an alert on this indicator and use the webhook URL.

---

## Testing the Webhook

### Manual Test via cURL:
```bash
curl -X POST "https://pandoras-box-production.up.railway.app/api/dollar-smile/webhook" \
  -H "Content-Type: application/json" \
  -d '{"indicator": "dollar_smile", "dxy_current": 104.50, "dxy_5d_ago": 102.00, "vix_current": 18.5}'
```

### Manual Test via Hub:
Use the manual bias endpoint:
```
POST /api/dollar-smile/manual
{
  "bias": "TORO_MINOR",
  "dxy_current": 104.50,
  "vix_current": 18.5,
  "notes": "Testing Dollar Smile"
}
```

---

## Bias Logic Reference

| DXY Change (5d) | VIX Level | Smile Position | Bias |
|-----------------|-----------|----------------|------|
| >+2% | >20 | Left (Fear) | URSA_MAJOR |
| >+2% | <20 | Right (Growth) | TORO_MAJOR |
| Flat/Down | <20 | Bottom (Stagnation) | NEUTRAL |
| Down | Rising | Transition | URSA_MINOR |

---

## Troubleshooting

1. **Webhook not firing:** Check TradingView alert history
2. **Data not updating:** Check Railway logs for errors
3. **Wrong bias:** Verify DXY and VIX values are correct

---

## Check Current Status

```
GET https://pandoras-box-production.up.railway.app/api/dollar-smile/status
```
