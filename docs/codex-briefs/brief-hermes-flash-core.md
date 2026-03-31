# BRIEF: Hermes Flash — Core Detection Layer
## Priority: P0 | System: Railway + TradingView + VPS Trigger + Agora UI
## Date: 2026-03-31

---

## CONTEXT FOR CLAUDE CODE

Nick's trading hub (Pandora's Box) missed a major market-moving catalyst today — Trump signaling willingness to end the Iran war caused SPY to rally 2%+ in minutes. The hub has no system for detecting sudden velocity moves or identifying their cause. Hermes Flash is a new real-time catalyst detection system with three layers:

1. **TradingView PineScript alerts** — monitor 10 tickers for velocity threshold breaches
2. **Railway webhook receiver** — ingests TV alerts, evaluates tier, stores events, triggers VPS
3. **VPS trigger** — pings Pivot to start a Twitter/news scrape burst (the "intelligence" layer — this is Brief 2, NOT this brief)
4. **Agora UI** — banner/notification system showing catalyst events with tier color coding

This brief covers layers 1, 2, and 4. Layer 3 (VPS scrape logic) is Brief 2.

---

## PREREQUISITE CHECK

Before building, verify these via the Railway app or Polygon docs:

- Polygon News API (`/v2/reference/news`) — confirm it's available on Stocks Starter ($29/mo) tier. If YES, add as supplementary data source in the catalyst_events enrichment step. If NO, skip it — the TV + VPS scrape path is the primary architecture and doesn't depend on this.
- Confirm the VPS at `188.245.250.2` is reachable from Railway (a simple `curl` test from the Railway shell). We need this for the trigger endpoint in Step 5.

---

## STEP 1: Database — `catalyst_events` Table

Create in Supabase:

```sql
CREATE TABLE IF NOT EXISTS catalyst_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    event_type TEXT NOT NULL DEFAULT 'velocity_breach',
    tier INTEGER NOT NULL DEFAULT 1 CHECK (tier BETWEEN 1 AND 3),
    -- Tier 1: single ticker breach (quiet notification + Pivot scrape)
    -- Tier 2: 2+ correlated tickers breach within 5 min window (loud banner + broader Pivot scrape)
    -- Tier 3: physical confirmation (Hormuz reopens, formal ceasefire, Brent < $95) — manual entry only
    trigger_ticker TEXT NOT NULL,
    trigger_move_pct NUMERIC(6,2),
    trigger_timeframe TEXT DEFAULT '30min',
    correlated_tickers JSONB DEFAULT '[]'::jsonb,
    -- e.g. [{"ticker": "XLF", "move_pct": -1.2}, {"ticker": "HYG", "move_pct": -0.6}]
    headline_summary TEXT,
    -- Populated by Pivot scrape (Brief 2) or Polygon news enrichment
    catalyst_category TEXT,
    -- Categories: geopolitical, credit_event, fed_macro, earnings, technical_flow, sector_rotation, unknown
    pivot_analysis TEXT,
    -- Full LLM analysis from Pivot (Brief 2 populates this)
    sector_velocity JSONB DEFAULT '{}'::jsonb,
    -- Snapshot of all sector moves at time of event
    trip_wire_status JSONB DEFAULT '{}'::jsonb,
    -- Which of Nick's 4 reversal trip wires are currently fired
    dismissed BOOLEAN DEFAULT FALSE,
    dismissed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_catalyst_events_created ON catalyst_events (created_at DESC);
CREATE INDEX idx_catalyst_events_tier ON catalyst_events (tier);
CREATE INDEX idx_catalyst_events_dismissed ON catalyst_events (dismissed);
```

---

## STEP 2: System Config — Hermes Watchlist & Thresholds

Add to `system_config` table (or create a new config entry):

```sql
INSERT INTO system_config (key, value) VALUES (
    'hermes_watchlist',
    '{
        "tickers": {
            "SPY":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "broad_market"},
            "QQQ":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "tech"},
            "SMH":  {"threshold_pct": 1.5, "timeframe_min": 30, "category": "semis"},
            "XLF":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "financials"},
            "HYG":  {"threshold_pct": 0.5, "timeframe_min": 30, "category": "credit"},
            "IYR":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "real_estate"},
            "TLT":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "bonds"},
            "USO":  {"threshold_pct": 2.0, "timeframe_min": 30, "category": "oil"},
            "GLD":  {"threshold_pct": 1.0, "timeframe_min": 30, "category": "safe_haven"},
            "IBIT": {"threshold_pct": 2.0, "timeframe_min": 30, "category": "crypto"}
        },
        "correlation_groups": {
            "credit_event":  ["XLF", "HYG", "IYR"],
            "risk_off":      ["SPY", "QQQ", "SMH"],
            "deescalation":  ["USO", "GLD", "TLT"],
            "full_reversal":  ["SPY", "QQQ", "SMH", "XLF", "HYG"]
        },
        "correlation_window_minutes": 5,
        "correlation_min_tickers": 2,
        "vps_trigger_url": "http://188.245.250.2:8000/api/hermes/trigger",
        "vps_api_key": "REPLACE_WITH_SHARED_SECRET",
        "cooldown_minutes": 15
    }'
) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
```

**Threshold rationale (include as comment in code):**
- HYG at 0.5% — high yield bonds barely move; 0.5% in 30 min is a screaming signal
- USO and IBIT at 2.0% — naturally volatile, tighter threshold = noise
- SMH at 1.5% — high beta to QQQ, needs wider band
- Everything else at 1.0% — standard sensitivity for liquid ETFs

---

## STEP 3: TradingView PineScript Indicators

Create ONE PineScript indicator that monitors velocity for a given ticker. Nick will add it to 10 separate TV charts (one per ticker) and configure the alert threshold per the watchlist above.

```pinescript
//@version=6
indicator("Hermes Flash Velocity", overlay=true)

// Inputs — Nick sets these per chart
lookback = input.int(30, "Lookback Period (minutes)", minval=5, maxval=120)
threshold = input.float(1.0, "Velocity Threshold (%)", minval=0.1, maxval=10.0, step=0.1)
ticker_label = input.string("SPY", "Ticker Label (for webhook payload)")

// Calculate VWAP anchor price from lookback period
// Using simple approach: price N bars ago on the current timeframe
// This indicator should be applied to 1-minute charts for accuracy
bars_back = lookback  // On 1-min chart, 30 bars = 30 minutes
anchor_price = close[bars_back]

// Calculate velocity (% move from anchor)
velocity = ((close - anchor_price) / anchor_price) * 100

// Threshold breach detection
breach_up = velocity >= threshold
breach_down = velocity <= -threshold
breach = breach_up or breach_down

// Visual
bgcolor(breach_up ? color.new(color.green, 85) : breach_down ? color.new(color.red, 85) : na)
plot(velocity, "Velocity %", color=color.white, linewidth=2)
hline(threshold, "Upper Threshold", color=color.green, linestyle=hline.style_dashed)
hline(-threshold, "Lower Threshold", color=color.red, linestyle=hline.style_dashed)
hline(0, "Zero", color=color.gray)

// Alert condition
alertcondition(breach, title="Hermes Flash Velocity Breach", message='{"ticker": "' + ticker_label + '", "velocity_pct": ' + str.tostring(velocity, "#.##") + ', "direction": "' + (breach_up ? "up" : "down") + '", "threshold": ' + str.tostring(threshold) + ', "timeframe_min": ' + str.tostring(lookback) + ', "source": "tradingview", "alert_type": "hermes_flash"}')
```

**Instructions for Nick (include in brief output or README):**
1. Add this indicator to a 1-minute chart for each of the 10 tickers
2. Set the `Ticker Label` input to match the ticker (e.g., "HYG")
3. Set the `Velocity Threshold` per the watchlist config (e.g., 0.5 for HYG, 2.0 for USO)
4. Create an alert on each chart: Condition = "Hermes Flash Velocity" → "Hermes Flash Velocity Breach"
5. Alert action = Webhook URL: `https://pandoras-box-production.up.railway.app/api/webhook/hermes`
6. Alert message: use the default (the PineScript `message` field auto-populates the JSON payload)

---

## STEP 4: Railway Webhook Receiver

New file: `routes/hermes.py` (or add to existing webhook handler)

```python
# === HERMES FLASH — Webhook Receiver & Correlation Engine ===

from fastapi import APIRouter, Request, HTTPException
from datetime import datetime, timedelta, timezone
import json
import httpx
import logging

logger = logging.getLogger("hermes")
router = APIRouter(prefix="/api", tags=["hermes"])

# In-memory sliding window for correlation detection
# Key: ticker, Value: {"timestamp": datetime, "velocity_pct": float, "direction": str}
recent_breaches = {}

@router.post("/webhook/hermes")
async def hermes_webhook(request: Request):
    """
    Receives TradingView velocity breach alerts.
    Evaluates tier (single vs correlated), stores event, triggers VPS if needed.
    """
    try:
        payload = await request.json()
    except Exception:
        body = await request.body()
        try:
            payload = json.loads(body.decode())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Validate required fields
    ticker = payload.get("ticker")
    velocity_pct = payload.get("velocity_pct")
    direction = payload.get("direction")
    alert_type = payload.get("alert_type")

    if not ticker or velocity_pct is None or alert_type != "hermes_flash":
        raise HTTPException(status_code=400, detail="Missing or invalid hermes_flash fields")

    logger.info(f"HERMES FLASH: {ticker} {direction} {velocity_pct}% velocity breach")

    # Load config from system_config table
    config = await get_hermes_config()  # Implement: SELECT value FROM system_config WHERE key = 'hermes_watchlist'
    cooldown_minutes = config.get("cooldown_minutes", 15)

    # Cooldown check — don't fire duplicate alerts for same ticker within cooldown window
    now = datetime.now(timezone.utc)
    last_breach = recent_breaches.get(ticker)
    if last_breach and (now - last_breach["timestamp"]) < timedelta(minutes=cooldown_minutes):
        logger.info(f"HERMES: {ticker} in cooldown, skipping")
        return {"status": "cooldown", "ticker": ticker}

    # Record this breach in sliding window
    recent_breaches[ticker] = {
        "timestamp": now,
        "velocity_pct": float(velocity_pct),
        "direction": direction
    }

    # Clean old entries (older than correlation window)
    correlation_window = config.get("correlation_window_minutes", 5)
    cutoff = now - timedelta(minutes=correlation_window)
    recent_breaches_clean = {k: v for k, v in recent_breaches.items() if v["timestamp"] >= cutoff}
    recent_breaches.clear()
    recent_breaches.update(recent_breaches_clean)

    # Correlation detection — check if 2+ tickers in same group breached within window
    correlated = []
    correlation_groups = config.get("correlation_groups", {})
    tier = 1  # Default: single ticker breach

    for group_name, group_tickers in correlation_groups.items():
        if ticker in group_tickers:
            group_breaches = [
                {"ticker": t, "move_pct": recent_breaches[t]["velocity_pct"]}
                for t in group_tickers
                if t in recent_breaches and t != ticker
            ]
            if len(group_breaches) >= (config.get("correlation_min_tickers", 2) - 1):
                tier = 2
                correlated = group_breaches
                logger.info(f"HERMES: Tier 2 CORRELATED event — {group_name}: {ticker} + {[b['ticker'] for b in group_breaches]}")
                break

    # Build sector velocity snapshot (grab current prices for all watchlist tickers)
    sector_velocity = await get_sector_velocity_snapshot(config)  # Implement: quick Polygon price check for all 10 tickers

    # Check trip wire status
    trip_wire_status = await get_trip_wire_status()  # Implement: check current trip wire conditions

    # Store catalyst event
    event_id = await store_catalyst_event(
        event_type="velocity_breach",
        tier=tier,
        trigger_ticker=ticker,
        trigger_move_pct=float(velocity_pct),
        trigger_timeframe=f"{payload.get('timeframe_min', 30)}min",
        correlated_tickers=correlated,
        sector_velocity=sector_velocity,
        trip_wire_status=trip_wire_status
    )
    # Implement: INSERT INTO catalyst_events (...) VALUES (...) RETURNING id

    # Trigger VPS scrape burst
    vps_url = config.get("vps_trigger_url")
    vps_key = config.get("vps_api_key")
    if vps_url and vps_key:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                vps_payload = {
                    "event_id": str(event_id),
                    "tier": tier,
                    "trigger_ticker": ticker,
                    "velocity_pct": float(velocity_pct),
                    "direction": direction,
                    "correlated_tickers": correlated,
                    "search_terms": build_search_terms(ticker, direction, correlated, config),
                    "scrape_interval_seconds": 120,  # Every 2 minutes
                    "scrape_duration_minutes": 15,
                    "timestamp": now.isoformat()
                }
                resp = await client.post(
                    vps_url,
                    json=vps_payload,
                    headers={"X-API-Key": vps_key}
                )
                logger.info(f"HERMES: VPS trigger sent, status {resp.status_code}")
        except Exception as e:
            logger.error(f"HERMES: VPS trigger failed: {e}")
            # Non-fatal — the alert still gets stored and shown in UI

    return {
        "status": "alert_created",
        "event_id": str(event_id),
        "tier": tier,
        "ticker": ticker,
        "correlated": [b["ticker"] for b in correlated]
    }


def build_search_terms(ticker: str, direction: str, correlated: list, config: dict) -> list:
    """
    Build dynamic search terms for Pivot's Twitter scrape based on what triggered.
    More correlated tickers = broader search terms.
    """
    # Base terms always included
    terms = ["$" + ticker, ticker]

    # Ticker-specific context terms
    context_map = {
        "SPY": ["S&P 500", "market", "stocks"],
        "QQQ": ["Nasdaq", "tech stocks"],
        "SMH": ["semiconductors", "chips", "NVDA"],
        "XLF": ["banks", "financials", "credit"],
        "HYG": ["high yield", "junk bonds", "credit spread", "default"],
        "IYR": ["real estate", "REIT", "commercial real estate"],
        "TLT": ["Treasury", "bonds", "yields", "10 year"],
        "USO": ["oil", "crude", "Hormuz", "Iran"],
        "GLD": ["gold", "safe haven"],
        "IBIT": ["Bitcoin", "crypto", "BTC"]
    }
    terms.extend(context_map.get(ticker, []))

    # If Tier 2 correlated event, add broader macro terms
    if correlated:
        correlated_tickers = [b["ticker"] for b in correlated]
        # Credit event cluster
        if any(t in correlated_tickers for t in ["XLF", "HYG", "IYR"]):
            terms.extend(["credit crisis", "bank stress", "private credit", "Apollo", "default"])
        # Broad risk-off/on cluster
        if any(t in correlated_tickers for t in ["SPY", "QQQ", "SMH"]):
            terms.extend(["risk off" if direction == "down" else "relief rally", "sell off" if direction == "down" else "buying"])
        # Geopolitical de-escalation cluster
        if any(t in correlated_tickers for t in ["USO", "GLD", "TLT"]):
            terms.extend(["ceasefire", "Iran deal", "Hormuz", "peace talks", "war end"])

    # Always include these — core thesis terms
    terms.extend(["Iran", "Hormuz", "Trump"])

    return list(set(terms))  # Deduplicate


@router.get("/hermes/alerts")
async def get_hermes_alerts(
    limit: int = 20,
    include_dismissed: bool = False,
    tier_min: int = 1
):
    """
    Returns catalyst events for the Agora frontend.
    Default: most recent 20 undismissed events, all tiers.
    """
    # Implement: SELECT * FROM catalyst_events
    # WHERE dismissed = false (unless include_dismissed)
    # AND tier >= tier_min
    # ORDER BY created_at DESC LIMIT limit
    pass  # CC implements with actual Supabase query


@router.patch("/hermes/alerts/{event_id}/dismiss")
async def dismiss_hermes_alert(event_id: str):
    """Mark a catalyst event as dismissed (Nick reviewed it)."""
    # Implement: UPDATE catalyst_events SET dismissed = true, dismissed_at = NOW() WHERE id = event_id
    pass  # CC implements


# === Helper stubs for CC to implement ===

async def get_hermes_config() -> dict:
    """Load hermes_watchlist config from system_config table."""
    # SELECT value FROM system_config WHERE key = 'hermes_watchlist'
    # Return parsed JSON
    pass

async def get_sector_velocity_snapshot(config: dict) -> dict:
    """
    Quick Polygon snapshot: for each ticker in watchlist,
    get current price vs 30-min-ago price, calculate % change.
    Returns dict like {"SPY": 1.45, "QQQ": 1.96, "HYG": -0.12, ...}
    Use Polygon /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}
    """
    pass

async def get_trip_wire_status() -> dict:
    """
    Check Nick's 4 reversal trip wires:
    1. SPX reclaims 200 DMA (~6,600) for 2 consecutive closes
    2. Brent below $95
    3. Formal ceasefire or Hormuz reopening confirmed
    4. VIX below 20 for 48 hours
    Returns: {"trip_wire_1": false, "trip_wire_2": false, ...}
    Trip wires 1, 2, 4 can be checked via Polygon data.
    Trip wire 3 is manual (check catalyst_events for Tier 3 entry).
    """
    pass

async def store_catalyst_event(**kwargs) -> str:
    """Insert into catalyst_events table, return event UUID."""
    pass
```

**Router registration — find/replace anchor in main app file:**

Find the section where other routers are registered (e.g., `app.include_router(...)`) and add:

```python
from routes.hermes import router as hermes_router
app.include_router(hermes_router)
```

---

## STEP 5: VPS Trigger Endpoint (Stub Only — Brief 2 Implements Full Logic)

On the VPS at `188.245.250.2`, create a minimal endpoint that Brief 2 will flesh out:

**File:** `/opt/openclaw/hermes_trigger.py` (or integrate into existing Pivot FastAPI app)

```python
# === HERMES TRIGGER STUB — Brief 2 will implement full scrape logic ===

from fastapi import APIRouter, Request, HTTPException
import logging

logger = logging.getLogger("hermes_trigger")
router = APIRouter()

HERMES_API_KEY = "REPLACE_WITH_SHARED_SECRET"  # Must match Railway config

@router.post("/api/hermes/trigger")
async def hermes_trigger(request: Request):
    """
    Receives trigger from Railway when a velocity breach is detected.
    Brief 2 implements: Twitter scrape burst → LLM analysis → push results back to Supabase.
    """
    # Auth check
    api_key = request.headers.get("X-API-Key")
    if api_key != HERMES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    payload = await request.json()
    logger.info(f"HERMES TRIGGER received: {payload.get('trigger_ticker')} Tier {payload.get('tier')}")

    # TODO (Brief 2): Launch scrape burst using payload["search_terms"]
    # TODO (Brief 2): Schedule scrape_interval_seconds × scrape_duration_minutes
    # TODO (Brief 2): Feed results into Haiku LLM for catalyst categorization
    # TODO (Brief 2): POST results back to Supabase catalyst_events table

    return {"status": "trigger_received", "event_id": payload.get("event_id")}
```

---

## STEP 6: Agora Frontend — Hermes Flash Banner

Add to `app.js` — the Hermes Flash alert banner that appears at the top of the Agora dashboard.

**Find the main dashboard container** (the element that holds the Bloomberg-style ticker strip, trip wire monitor, etc.) and add the Hermes Flash banner ABOVE it.

### HTML Structure (add to dashboard area):

```html
<!-- Hermes Flash Alert Banner — sits above ticker strip -->
<div id="hermes-flash-container" class="hermes-flash-container" style="display: none;">
    <div id="hermes-flash-banner" class="hermes-flash-banner">
        <div class="hermes-flash-tier-badge" id="hermes-tier-badge">T1</div>
        <div class="hermes-flash-content">
            <span class="hermes-flash-ticker" id="hermes-trigger-ticker">SPY</span>
            <span class="hermes-flash-move" id="hermes-trigger-move">+1.45%</span>
            <span class="hermes-flash-timeframe">in 22min</span>
            <span class="hermes-flash-separator">|</span>
            <span class="hermes-flash-correlated" id="hermes-correlated" style="display: none;">
                Correlated: <span id="hermes-correlated-list"></span>
                <span class="hermes-flash-separator">|</span>
            </span>
            <span class="hermes-flash-intel" id="hermes-intel">Pivot analyzing...</span>
            <span class="hermes-flash-separator">|</span>
            <span class="hermes-flash-tripwires" id="hermes-tripwires">Trip Wires: 0/4 fired</span>
        </div>
        <div class="hermes-flash-actions">
            <button class="hermes-flash-expand-btn" onclick="toggleHermesDetail()" title="Expand details">▼</button>
            <button class="hermes-flash-dismiss-btn" onclick="dismissHermesAlert()" title="Dismiss">✕</button>
        </div>
    </div>
    <!-- Expandable detail panel -->
    <div id="hermes-detail-panel" class="hermes-detail-panel" style="display: none;">
        <div class="hermes-sector-velocity" id="hermes-sector-grid">
            <!-- Dynamically populated: 10 ticker boxes showing current velocity -->
        </div>
        <div class="hermes-pivot-analysis" id="hermes-pivot-analysis">
            Waiting for Pivot intelligence...
        </div>
    </div>
</div>

<!-- Hermes notification counter (for Tier 1 quiet alerts when banner is dismissed) -->
<div id="hermes-notification-badge" class="hermes-notification-badge" style="display: none;" onclick="showHermesHistory()">
    <span id="hermes-unread-count">0</span>
</div>
```

### CSS (add to stylesheet):

```css
/* === HERMES FLASH === */
.hermes-flash-container {
    position: relative;
    z-index: 100;
    margin-bottom: 4px;
}

.hermes-flash-banner {
    display: flex;
    align-items: center;
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 13px;
    font-family: 'IBM Plex Mono', monospace;
    gap: 8px;
    animation: hermes-pulse 2s ease-in-out 3;
}

/* Tier color coding */
.hermes-flash-banner.tier-1 {
    background: rgba(255, 193, 7, 0.12);
    border: 1px solid rgba(255, 193, 7, 0.3);
    color: #ffc107;
}
.hermes-flash-banner.tier-2 {
    background: rgba(255, 152, 0, 0.15);
    border: 1px solid rgba(255, 152, 0, 0.4);
    color: #ff9800;
}
.hermes-flash-banner.tier-3 {
    background: rgba(244, 67, 54, 0.15);
    border: 1px solid rgba(244, 67, 54, 0.4);
    color: #f44336;
}

.hermes-flash-tier-badge {
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: 700;
    font-size: 11px;
    min-width: 24px;
    text-align: center;
}
.tier-1 .hermes-flash-tier-badge { background: rgba(255, 193, 7, 0.3); }
.tier-2 .hermes-flash-tier-badge { background: rgba(255, 152, 0, 0.4); }
.tier-3 .hermes-flash-tier-badge { background: rgba(244, 67, 54, 0.4); }

.hermes-flash-ticker { font-weight: 700; }
.hermes-flash-move { font-weight: 700; }
.hermes-flash-separator { opacity: 0.4; margin: 0 4px; }
.hermes-flash-intel { font-style: italic; opacity: 0.85; }

.hermes-flash-actions {
    margin-left: auto;
    display: flex;
    gap: 4px;
}
.hermes-flash-actions button {
    background: none;
    border: 1px solid rgba(255,255,255,0.15);
    color: inherit;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 11px;
}
.hermes-flash-actions button:hover { background: rgba(255,255,255,0.1); }

@keyframes hermes-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

/* Detail panel */
.hermes-detail-panel {
    padding: 10px 12px;
    background: rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.08);
    border-top: none;
    border-radius: 0 0 4px 4px;
    font-size: 12px;
}

.hermes-sector-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 6px;
    margin-bottom: 8px;
}

.hermes-sector-box {
    padding: 4px 6px;
    border-radius: 3px;
    text-align: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
}
.hermes-sector-box.positive { background: rgba(76, 175, 80, 0.15); color: #4caf50; }
.hermes-sector-box.negative { background: rgba(244, 67, 54, 0.15); color: #f44336; }
.hermes-sector-box.neutral { background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.5); }

/* Notification badge for dismissed/quiet alerts */
.hermes-notification-badge {
    position: fixed;
    top: 10px;
    right: 10px;
    background: rgba(255, 152, 0, 0.8);
    color: #000;
    border-radius: 50%;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    z-index: 200;
    animation: hermes-badge-pulse 1.5s ease-in-out infinite;
}
@keyframes hermes-badge-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
}
```

### JavaScript Logic (add to `app.js`):

```javascript
// === HERMES FLASH — Frontend Logic ===

let hermesCurrentEvent = null;
let hermesUnreadCount = 0;
let hermesPollingInterval = null;

function initHermesFlash() {
    // Poll for new alerts every 10 seconds
    hermesPollingInterval = setInterval(fetchHermesAlerts, 10000);
    fetchHermesAlerts(); // Initial fetch
}

async function fetchHermesAlerts() {
    try {
        const resp = await fetch('/api/hermes/alerts?limit=1&include_dismissed=false&tier_min=1', {
            headers: { 'X-API-Key': API_KEY }
        });
        if (!resp.ok) return;
        const data = await resp.json();

        if (data.alerts && data.alerts.length > 0) {
            const latest = data.alerts[0];
            // Only show if newer than current
            if (!hermesCurrentEvent || latest.id !== hermesCurrentEvent.id) {
                showHermesAlert(latest);
            }
            // Check if Pivot analysis has been updated (Brief 2 populates this)
            if (hermesCurrentEvent && latest.id === hermesCurrentEvent.id && latest.pivot_analysis && !hermesCurrentEvent.pivot_analysis) {
                updateHermesPivotAnalysis(latest.pivot_analysis, latest.catalyst_category);
            }
        }
    } catch (err) {
        console.error('Hermes polling error:', err);
    }
}

function showHermesAlert(event) {
    hermesCurrentEvent = event;
    const container = document.getElementById('hermes-flash-container');
    const banner = document.getElementById('hermes-flash-banner');
    const tierBadge = document.getElementById('hermes-tier-badge');
    const triggerTicker = document.getElementById('hermes-trigger-ticker');
    const triggerMove = document.getElementById('hermes-trigger-move');
    const correlatedEl = document.getElementById('hermes-correlated');
    const correlatedList = document.getElementById('hermes-correlated-list');
    const intelEl = document.getElementById('hermes-intel');
    const tripwiresEl = document.getElementById('hermes-tripwires');

    // Set tier
    banner.className = `hermes-flash-banner tier-${event.tier}`;
    tierBadge.textContent = `T${event.tier}`;

    // Set trigger info
    triggerTicker.textContent = event.trigger_ticker;
    const sign = event.trigger_move_pct >= 0 ? '+' : '';
    triggerMove.textContent = `${sign}${event.trigger_move_pct}%`;
    triggerMove.style.color = event.trigger_move_pct >= 0 ? '#4caf50' : '#f44336';

    // Correlated tickers
    if (event.correlated_tickers && event.correlated_tickers.length > 0) {
        correlatedEl.style.display = 'inline';
        correlatedList.textContent = event.correlated_tickers.map(c => `${c.ticker} ${c.move_pct >= 0 ? '+' : ''}${c.move_pct}%`).join(', ');
    } else {
        correlatedEl.style.display = 'none';
    }

    // Intel (Pivot analysis or placeholder)
    if (event.pivot_analysis) {
        intelEl.textContent = event.pivot_analysis;
        intelEl.style.fontStyle = 'normal';
    } else {
        intelEl.textContent = 'Pivot analyzing...';
        intelEl.style.fontStyle = 'italic';
    }

    // Trip wire status
    if (event.trip_wire_status) {
        const fired = Object.values(event.trip_wire_status).filter(v => v === true).length;
        tripwiresEl.textContent = `Trip Wires: ${fired}/4 fired`;
        if (fired >= 2) {
            tripwiresEl.style.color = '#f44336';
            tripwiresEl.style.fontWeight = '700';
        }
    }

    // Build sector velocity grid
    if (event.sector_velocity) {
        buildSectorGrid(event.sector_velocity);
    }

    // Show banner — Tier 2+ gets full banner, Tier 1 gets badge + quiet banner
    container.style.display = 'block';

    // Play notification sound for Tier 2+
    if (event.tier >= 2) {
        playHermesChime();
    }
}

function buildSectorGrid(velocities) {
    const grid = document.getElementById('hermes-sector-grid');
    grid.innerHTML = '';
    const tickers = ['SPY', 'QQQ', 'SMH', 'XLF', 'HYG', 'IYR', 'TLT', 'USO', 'GLD', 'IBIT'];
    tickers.forEach(ticker => {
        const pct = velocities[ticker] || 0;
        const div = document.createElement('div');
        div.className = `hermes-sector-box ${pct > 0.1 ? 'positive' : pct < -0.1 ? 'negative' : 'neutral'}`;
        const sign = pct >= 0 ? '+' : '';
        div.innerHTML = `<div style="font-weight:700">${ticker}</div><div>${sign}${pct.toFixed(2)}%</div>`;
        grid.appendChild(div);
    });
}

function updateHermesPivotAnalysis(analysis, category) {
    const intelEl = document.getElementById('hermes-intel');
    intelEl.textContent = analysis;
    intelEl.style.fontStyle = 'normal';

    const pivotPanel = document.getElementById('hermes-pivot-analysis');
    const categoryLabel = category ? ` [${category.toUpperCase()}]` : '';
    pivotPanel.textContent = `${categoryLabel} ${analysis}`;
}

function toggleHermesDetail() {
    const panel = document.getElementById('hermes-detail-panel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

async function dismissHermesAlert() {
    if (!hermesCurrentEvent) return;
    try {
        await fetch(`/api/hermes/alerts/${hermesCurrentEvent.id}/dismiss`, {
            method: 'PATCH',
            headers: { 'X-API-Key': API_KEY }
        });
    } catch (err) {
        console.error('Dismiss error:', err);
    }
    document.getElementById('hermes-flash-container').style.display = 'none';
    hermesCurrentEvent = null;
}

function playHermesChime() {
    // Simple audio notification — use Web Audio API for a short chime
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = 880; // A5 note
        osc.type = 'sine';
        gain.gain.value = 0.1;
        osc.start();
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
        osc.stop(ctx.currentTime + 0.3);
    } catch (e) { /* Audio not available, silent fallback */ }
}

// Initialize when dashboard loads — add this call to your existing init function
// initHermesFlash();
```

**Find/replace anchor to add initialization:**
Find the existing dashboard initialization function (wherever `initDashboard()` or similar is called) and add `initHermesFlash();` to it.

---

## STEP 7: Nick's Setup Checklist (Post-Deploy)

After CC deploys this code:

1. **Generate a shared secret** for VPS auth — run `python -c "import secrets; print(secrets.token_urlsafe(32))"` and set it in both Railway's `system_config` and the VPS endpoint
2. **Add the PineScript indicator** to 10 TradingView 1-minute charts (SPY, QQQ, SMH, XLF, HYG, IYR, TLT, USO, GLD, IBIT)
3. **Configure alerts** on each chart with the webhook URL and appropriate threshold per the watchlist config
4. **Test the chain** — manually trigger a TV alert and confirm:
   - Railway receives the webhook ✓
   - catalyst_events row is created in Supabase ✓
   - VPS receives the trigger ping ✓ (will return stub response until Brief 2)
   - Agora banner shows the alert ✓

---

## NOTES FOR CC

- This brief is self-contained. Brief 2 (Pivot intelligence layer) and Brief 3 (Hydra squeeze scanner) follow separately.
- The `build_search_terms()` function is critical — it's what makes the Pivot scrape targeted rather than generic. Adjust the `context_map` if Nick's thesis evolves.
- The correlation group definitions in `system_config` are editable without code changes. Nick can add/remove tickers or groups from the Supabase dashboard directly.
- The frontend polls every 10 seconds. This is intentional — we don't need WebSocket complexity for this. The TV webhook → Railway → Supabase path means data is available within 2-5 seconds; the 10-second poll adds at most 10 seconds of UI delay, which is fine for a human reviewing an alert.
- Trip wire checking (Step 4 helper) should reuse any existing trip wire logic in the codebase. If none exists yet, implement a basic version using Polygon data for trip wires 1, 2, and 4. Trip wire 3 is always manual.
