# Brief: PYTHIA Level Sheet — Market Profile Indicator + Webhook Pipeline

## Summary

Build a TradingView Pine Script indicator that computes the prior session's Value Area (VAH, VAL, POC) from volume-at-price data, draws them on the chart, and fires webhooks to Pandora's Box. Then build the backend webhook handler that stores these levels and makes them available to the committee pipeline.

This is Phase 1 of PYTHIA's automation roadmap (see `skills/pythia-market-profile/SKILL.md`).

**Priority:** HIGH — this is the single highest-impact data integration for the committee
**Complexity:** Medium — Pine Script + simple webhook handler + context injection

## Part 1: Pine Script Indicator

### What It Does

1. At the start of each new session, compute the prior session's volume profile:
   - Divide the prior session's price range into 50 equal-width bins
   - For each bar in the prior session, distribute its volume across the bins the bar's range covers (proportional distribution)
   - POC = bin with the highest accumulated volume (use the bin's midpoint price)
   - Value Area = expand outward from POC bin, alternating up/down, adding the higher-volume side first, until 70% of total session volume is captured
   - VAH = upper boundary of value area
   - VAL = lower boundary of value area

2. Draw three horizontal lines on the current session:
   - POC: solid line, bright yellow, labeled "POC $XXX.XX"
   - VAH: dashed line, red/coral, labeled "VAH $XXX.XX"
   - VAL: dashed line, green/teal, labeled "VAL $XXX.XX"
   - Lines extend from session start to current bar
   - Optional: shade the value area between VAH and VAL with a semi-transparent fill

3. Also compute and display the **Initial Balance** (first 60 minutes of RTH):
   - IB High and IB Low as dotted lines (lighter color)
   - Label showing IB width in points/dollars
   - Compare to 20-period average IB width
   - If IB width < 75% of average, display "NARROW IB" label (orange) — breakout likely
   - If IB width > 125% of average, display "WIDE IB" label (blue) — range likely set

4. Fire webhook alerts on two conditions:
   - **Session open:** Send prior day's VAH, VAL, POC levels
   - **80% Rule trigger:** If price opens outside prior VA then re-enters it, fire alert

### Session Definitions

**For equities (SPY, QQQ, IWM, SMH, GLD, XLE, IGV, GOOGL, TSLA, PLTR, CRWV):**
- Regular Trading Hours: 9:30 AM - 4:00 PM ET
- Use `session.regular` in Pine Script
- IB = 9:30 AM - 10:30 AM ET

**For BTC:**
- Use midnight-to-midnight UTC as the session boundary
- OR better: use three sub-sessions that produce cleaner profiles:
  - Asia: 8:00 PM - 4:00 AM ET
  - London: 3:00 AM - 12:00 PM ET  
  - NY: 8:00 AM - 5:00 PM ET
- Start with single 24H session, add sub-sessions later
- IB = first 60 minutes of NY session (8:00 AM - 9:00 AM ET) for crypto

### Webhook Payload

```json
{
  "type": "mp_levels",
  "ticker": "{{ticker}}",
  "timeframe": "{{interval}}",
  "session_date": "2026-04-01",
  "vah": 523.50,
  "val": 518.20,
  "poc": 520.85,
  "ib_high": 522.10,
  "ib_low": 519.40,
  "ib_width": 2.70,
  "ib_avg_width": 3.50,
  "ib_classification": "NARROW",
  "va_migration": "HIGHER",
  "prior_vah": 521.00,
  "prior_val": 516.50,
  "prior_poc": 518.75,
  "alert_type": "session_levels",
  "timestamp": "{{time}}"
}
```

For 80% rule alerts:
```json
{
  "type": "mp_alert",
  "ticker": "{{ticker}}",
  "alert_type": "80pct_rule",
  "direction": "BEARISH",
  "detail": "Price opened above VAH, re-entered value area. 80% probability of travel to VAL.",
  "vah": 523.50,
  "val": 518.20,
  "poc": 520.85,
  "price": 523.10,
  "timestamp": "{{time}}"
}
```

### Webhook URL

Same pattern as existing TradingView webhooks:
`https://pandoras-box-production.up.railway.app/webhook/mp_levels`

### Pine Script Settings (User Inputs)

- `num_bins` (default 50): Number of price bins for volume distribution
- `va_pct` (default 70): Percentage of volume for value area calculation  
- `ib_minutes` (default 60): Duration of initial balance period
- `ib_lookback` (default 20): Number of sessions for average IB width
- `show_ib` (default true): Toggle IB lines on/off
- `show_va_fill` (default true): Toggle value area shading
- `webhook_url` (default ""): Webhook endpoint (alerts configured separately in TradingView UI)

### Chart Timeframe

Designed for 15-minute or 30-minute charts. The indicator uses `request.security` or intrabar data to build the volume profile from lower timeframe bars. Use 5-minute source bars for profile computation on a 15-min chart.

### Tickers to Apply To

**Core (apply immediately):**
- SPY, QQQ, IWM, BTC/BTCUSD

**Sector barometers:**
- SMH, GLD, XLE, IGV

**Bellwether canaries:**
- GOOGL, TSLA, PLTR, CRWV

Each ticker gets its own chart tab in TradingView with the indicator applied.

## Part 2: Backend Webhook Handler

### New File: `backend/webhooks/mp_levels.py`

Receive the webhook, validate, store in Redis with TTL.

```python
# Key pattern: mp_levels:{ticker}
# Value: JSON with VAH, VAL, POC, IB data, timestamp
# TTL: 24 hours (levels are session-specific)

async def handle_mp_levels(payload: dict):
    ticker = payload.get("ticker", "").upper()
    if not ticker:
        return {"error": "missing ticker"}
    
    key = f"mp_levels:{ticker}"
    await redis.set(key, json.dumps(payload), ex=86400)
    
    # If 80% rule alert, also forward to Discord
    if payload.get("alert_type") == "80pct_rule":
        await notify_discord_mp_alert(payload)
    
    return {"status": "ok", "ticker": ticker}
```

### New Route in FastAPI

```python
@app.post("/webhook/mp_levels")
async def mp_levels_webhook(request: Request):
    payload = await request.json()
    result = await handle_mp_levels(payload)
    return result
```

### Discord Notification for 80% Rule

Post to the signals channel when an 80% rule triggers:

```
🔮 PYTHIA: 80% Rule — SPY
Price opened above VAH ($523.50), re-entered value area
Expect travel to VAL ($518.20) | POC at $520.85
```

## Part 3: Committee Context Injection

### Update `scripts/committee_context.py`

Add a new function that pulls MP levels from Redis and formats them for committee context:

```python
def build_mp_levels_context(ticker: str, api_url: str, api_key: str) -> str:
    """Fetch cached MP levels for a ticker from the Pandora API."""
    # GET /api/mp/levels/{ticker}
    # Returns the stored webhook data
    # Format as:
    # ## MARKET PROFILE LEVELS (SPY)
    # Prior Session: VAH $523.50 | POC $520.85 | VAL $518.20
    # Value Area Migration: HIGHER (prior POC was $518.75)
    # Initial Balance: $519.40 - $522.10 (width: $2.70, NARROW vs $3.50 avg)
    # 80% Rule: Not triggered
```

### Update `run_committee()` in `pivot2_committee.py`

After the existing context injections, add:

```python
# Inject Market Profile levels if available
try:
    from committee_context import build_mp_levels_context
    ticker = signal.get("ticker", "")
    if ticker:
        mp_block = build_mp_levels_context(ticker, api_url, api_key_val)
        if mp_block:
            base_context = base_context + "\n\n" + mp_block
    # Also inject SPY MP levels for macro context (unless ticker is already SPY)
    if ticker.upper() != "SPY":
        spy_mp = build_mp_levels_context("SPY", api_url, api_key_val)
        if spy_mp:
            base_context = base_context + "\n\n" + spy_mp
except Exception as e:
    log.warning("Failed to inject MP levels: %s", e)
```

### New API Endpoint

```python
@app.get("/api/mp/levels/{ticker}")
async def get_mp_levels(ticker: str):
    key = f"mp_levels:{ticker.upper()}"
    data = await redis.get(key)
    if data:
        return {"available": True, "levels": json.loads(data)}
    return {"available": False, "levels": None}

@app.get("/api/mp/levels")
async def get_all_mp_levels():
    """Return MP levels for all tickers that have them cached."""
    keys = await redis.keys("mp_levels:*")
    result = {}
    for key in keys:
        ticker = key.split(":")[1]
        data = await redis.get(key)
        if data:
            result[ticker] = json.loads(data)
    return {"available": bool(result), "levels": result}
```

## Part 4: Value Area Migration Detection

The Pine Script should compare current session's developing VA to prior session's VA and classify:

- **HIGHER:** Today's VAL > yesterday's VAL (value shifting up)
- **LOWER:** Today's VAH < yesterday's VAH (value shifting down)
- **OVERLAPPING:** Significant overlap between today's and yesterday's VA (balance)
- **NON-OVERLAPPING:** Gap between VAs (strong directional move)

Include this classification in the webhook payload. This is the trending-vs-bracketing signal PYTHIA needs most.

## Part 5: Poor High / Poor Low Detection (Stretch Goal)

At session close, evaluate the profile extremes:
- If the session high has 2+ TPO periods (letters) touching it → **excess** (healthy rejection, less likely to be revisited)
- If the session high has only 1 TPO period → **poor high** (unfinished auction, likely to be revisited)
- Same logic for session low

This is harder to compute in Pine Script because true TPO requires 30-minute period tracking. A reasonable proxy: if the high was only touched during 1 bar on a 30-min chart, it's a poor high. If touched during 2+ bars, it has excess.

Include in webhook:
```json
"high_quality": "POOR",
"low_quality": "EXCESS",
"poor_high_price": 524.20,
"poor_low_price": null
```

## Verification

1. Apply indicator to SPY 15-min chart — verify VAH/VAL/POC lines appear correctly
2. Compare computed levels to TradingView's built-in Volume Profile indicator visually — they should be close (won't be exact due to computation differences)
3. Set up a test alert, verify webhook fires and payload arrives at Railway
4. Check Redis for stored levels via `/api/mp/levels/SPY`
5. Trigger a committee run and verify MP levels appear in PYTHIA's context
6. Manually verify 80% rule detection on a historical day where it clearly triggered

## File Locations

| File | Purpose |
|------|--------|
| `docs/pinescript/webhooks/mp_level_sheet.pine` | The Pine Script indicator |
| `backend/webhooks/mp_levels.py` | Webhook handler |
| `backend/api/mp.py` or add to existing routes | API endpoints |
| `scripts/committee_context.py` | Context injection function (modify existing) |
| `scripts/pivot2_committee.py` | Wire MP context into pipeline (modify existing) |

## Cost Impact

TradingView alerts: Uses ~14 of Nick's 400 available alerts (one per ticker for session levels). Minimal.
Redis storage: ~14 keys, each <1KB, 24hr TTL. Negligible.
No additional API costs — this is all webhook-driven.
