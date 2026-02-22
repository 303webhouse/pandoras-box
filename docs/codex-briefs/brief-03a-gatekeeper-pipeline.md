# Brief 03A: Gatekeeper + Pipeline Skeleton

## Context for Sub-Agent

You are building the **first layer** of a 4-agent AI trading committee system called "The Committee." This brief covers the **infrastructure only** — no LLM calls. Brief 03B will wire in the actual AI agents; Brief 03C adds decision tracking and pushback mechanics.

The system receives trade signals from TradingView (via webhooks to Railway), filters them through rule-based gates, assembles market context, and posts structured committee recommendations to Discord. In THIS brief, committee agent responses are **stubs** — hardcoded placeholder text proving the pipeline works end-to-end.

## System Architecture

```
TradingView Alerts
       │
       ▼
Railway API (existing) ──► POST /api/signals/webhook
       │
       ▼
VPS: Cron job polls /api/signals/pending (every 60s)
       │
       ▼
┌──────────────────────────────┐
│  GATEKEEPER (rule-based)     │
│  • Score threshold           │
│  • Dedup (ticker+direction)  │
│  • Daily cap (20 max)        │
│  • DEFCON filter             │
│  • Bias alignment check      │
│  • Alert-type routing        │
└──────────────┬───────────────┘
               │ PASS
               ▼
┌──────────────────────────────┐
│  CONTEXT BUILDER             │
│  • Bias composite from API   │
│  • VIX / DEFCON regime       │
│  • Recent Circuit Breakers   │
│  • Catalyst calendar (econ   │
│    + earnings within DTE)    │
│  • Open positions from       │
│    SESSION-STATE.md          │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  COMMITTEE ORCHESTRATOR      │
│  (stubs in 03A, LLM in 03B) │
│  1. TORO Analyst  ─┐        │
│  2. URSA Analyst   ├► Pivot  │
│  3. Risk Assessor ─┘  synth  │
│  4. Pivot/Baum → final rec   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  DISCORD OUTPUT              │
│  • Formatted recommendation  │
│  • Reply buttons: take/pass/ │
│    watching                  │
│  • JSONL log entry written   │
└──────────────────────────────┘
```

## File Locations

| File | Path | Purpose |
|------|------|---------|
| Main orchestrator | `/opt/openclaw/workspace/scripts/pivot2_committee.py` | Entry point, gatekeeper, context builder, orchestrator |
| Committee log | `/opt/openclaw/workspace/data/committee_log.jsonl` | Every recommendation logged |
| Gatekeeper log | `/opt/openclaw/workspace/data/gatekeeper_log.jsonl` | Every signal evaluated (pass or reject + reason) |
| Session state | `/opt/openclaw/workspace/data/SESSION-STATE.md` | Current open positions (already exists) |
| Old trade poller | `/opt/openclaw/workspace/scripts/pivot2_trade_poller.py` | **DISABLE** — replaced by this pipeline |
| Catalyst monitors | `/opt/pivot/monitors/economic_calendar.py`, `earnings_calendar.py` | Existing — read their output files |
| Cron entry | systemd timer or crontab | Runs orchestrator every 60s |

## What's NOT In Scope (03A)

- ❌ LLM API calls (Brief 03B)
- ❌ Decision tracking / pattern detection (Brief 03C)
- ❌ Pushback mechanics (Brief 03C)
- ❌ Position-to-UI sync (Brief 05)
- ❌ Outcome tracking / auditor (Brief 04)

## Dependencies

- Railway API running with `/api/signals/pending` and `/api/bias/composite` endpoints
- Discord bot (Pivot) running as systemd service on VPS
- Python 3.11+ on VPS with: `aiohttp`, `discord.py`, `yfinance`
- SESSION-STATE.md maintained by existing Pivot screenshot extraction flow

---

## Section 1: Gatekeeper Filter Logic

The gatekeeper is a **pure Python function** — no LLM, no API calls to external AI. It receives a signal dict from `/api/signals/pending` and returns `PASS` or `REJECT` with a reason string. Every evaluation is logged to `gatekeeper_log.jsonl`.

### Signal Input Format (from Railway API)

```python
signal = {
    "id": "sig_abc123",
    "ticker": "SPY",
    "direction": "BEARISH",       # BULLISH or BEARISH
    "score": 75,                   # 0-100, from CTA Scanner
    "alert_type": "cta_scanner",   # See alert type routing below
    "timestamp": "2026-02-22T10:30:00Z",
    "metadata": {                  # Optional, varies by alert type
        "strategy": "momentum_divergence",
        "timeframe": "15m"
    }
}
```

### Filter Chain (evaluated in order — first failure rejects)

```python
def gatekeeper(signal: dict, state: dict) -> tuple[bool, str]:
    """
    state contains:
      - today_runs: int (committee runs so far today)
      - today_signals: list[dict] (ticker+direction pairs already processed)
      - bias_regime: str (TORO_MAJOR, TORO_MINOR, NEUTRAL, URSA_MINOR, URSA_MAJOR)
      - defcon: str (GREEN, YELLOW, ORANGE, RED)
    
    Returns: (passed: bool, reason: str)
    """
```

**Filter 1: Alert Type Routing**

Not all alerts use the same path. Route by `alert_type`:

| alert_type | Score Check | Enters Committee | Special Handling |
|-----------|------------|-----------------|-----------------|
| `cta_scanner` | Yes (≥60) | Yes | Standard path |
| `sniper` | **Skip** (pre-qualified by PineScript) | Yes | Respect dedup + cap only |
| `scout_early_warning` | **Skip** (pre-qualified) | Yes | Respect dedup + cap only |
| `exhaustion` | **Skip** (pre-qualified) | Yes | Respect dedup + cap only |
| `whale_hunter` | **Skip** | **No** — triggers Whale Flow | See Section 4 |
| `whale_flow_confirmed` | **Skip** (human-confirmed) | Yes | Enters committee with whale context. Respect dedup + cap only |
| `circuit_breaker` | N/A | **No** — never a trade idea | Stored as context for committee agents |

**Filter 2: Score Threshold (CTA Scanner signals only)**

```python
if signal["alert_type"] == "cta_scanner" and signal["score"] < 60:
    return (False, f"Score {signal['score']} below threshold 60")
```

**Filter 3: Signal Age**

```python
signal_age_minutes = (now - parse(signal["timestamp"])).total_seconds() / 60
if signal_age_minutes > 30:
    return (False, f"Signal age {signal_age_minutes:.0f}m exceeds 30m limit")
```

**Filter 4: Dedup (ticker + direction, per day)**

```python
key = f"{signal['ticker']}_{signal['direction']}"
if key in state["today_signals"]:
    return (False, f"Duplicate {key} already processed today")
```

**Filter 5: Daily Cap**

```python
if state["today_runs"] >= 20:
    return (False, f"Daily cap reached ({state['today_runs']}/20)")
```

**Filter 6: DEFCON Filter**

```python
defcon = state["defcon"]
direction = signal["direction"]

if defcon == "GREEN" or defcon == "YELLOW":
    pass  # Both directions allowed
elif defcon == "ORANGE":
    # Bias-aligned only
    bias = state["bias_regime"]
    if bias.startswith("URSA") and direction == "BULLISH":
        return (False, f"DEFCON ORANGE + {bias}: blocking non-aligned BULLISH")
    if bias.startswith("TORO") and direction == "BEARISH":
        return (False, f"DEFCON ORANGE + {bias}: blocking non-aligned BEARISH")
elif defcon == "RED":
    # Market stress — only short opportunities
    if direction == "BULLISH":
        return (False, "DEFCON RED: BULLISH signals blocked")
```

**Filter 7: Bias Alignment Check**

This is separate from DEFCON — it raises the bar for counter-bias trades even in normal conditions.

```python
bias = state["bias_regime"]
score = signal["score"]
direction = signal["direction"]

if bias in ("TORO_MAJOR", "TORO_MINOR"):
    if direction == "BEARISH" and score < 80:
        return (False, f"Counter-bias BEARISH in {bias} requires score ≥80, got {score}")
elif bias in ("URSA_MAJOR", "URSA_MINOR"):
    if direction == "BULLISH" and score < 80:
        return (False, f"Counter-bias BULLISH in {bias} requires score ≥80, got {score}")
# NEUTRAL: both directions pass at normal threshold
```

**Note:** For pre-qualified alert types (sniper, scout_early_warning, exhaustion, whale_flow_confirmed), Filters 2 and 7 are skipped. They still must pass Filters 3-6.

### Gatekeeper Log Entry

Every signal evaluation writes to `gatekeeper_log.jsonl`:

```json
{
    "timestamp": "2026-02-22T10:30:15Z",
    "signal_id": "sig_abc123",
    "ticker": "SPY",
    "direction": "BEARISH",
    "score": 75,
    "alert_type": "cta_scanner",
    "defcon": "YELLOW",
    "bias_regime": "URSA_MINOR",
    "passed": true,
    "reject_reason": null,
    "filter_reached": "all_passed"
}
```

---

## Section 2: Market Context Builder

When a signal passes the gatekeeper, the context builder assembles everything the committee agents need to evaluate the trade. This is a **data-fetching step** — no analysis, no LLM. It produces a structured `context` dict that gets passed to each agent in 03B.

### Context Assembly Function

```python
async def build_committee_context(signal: dict) -> dict:
    """
    Assembles all market context for committee evaluation.
    All data fetched in parallel where possible.
    Returns structured context dict.
    """
    context = {}
    
    # 1. Bias composite from Railway API
    context["bias"] = await fetch_bias_composite()
    # Returns: { regime, score, defcon, vix, factors: {...21 factors...} }
    
    # 2. Recent Circuit Breaker events (last 2 hours)
    context["circuit_breakers"] = await fetch_recent_circuit_breakers(hours=2)
    # Returns: list of CB events with timestamp, trigger, severity
    
    # 3. Catalyst calendar — filter to signal's ticker + macro events within DTE window
    context["catalysts"] = load_catalyst_calendar(
        ticker=signal["ticker"],
        dte_window=30  # days — covers typical options DTE
    )
    # Returns: { ticker_events: [...], macro_events: [...] }
    # ticker_events: earnings, ex-dividend, FDA dates, etc.
    # macro_events: CPI, FOMC, NFP, GDP, etc.
    
    # 4. Open positions from SESSION-STATE.md
    context["open_positions"] = parse_session_state()
    # Returns: list of position dicts (see parser below)
    
    # 5. Signal metadata passthrough
    context["signal"] = signal
    
    return context
```

### Bias Composite Fetch

```python
async def fetch_bias_composite() -> dict:
    """
    GET {RAILWAY_API_URL}/api/bias/composite
    
    Expected response shape:
    {
        "regime": "URSA_MINOR",
        "composite_score": -0.35,
        "defcon": "YELLOW",
        "vix": 18.5,
        "factors": {
            "vix_regime": {...},
            "credit_spreads": {...},
            "yield_curve": {...},
            "sector_rotation": {...},
            "factor_health": {...},
            ... (21 total factors)
        }
    }
    
    On failure: return sensible defaults (NEUTRAL regime, GREEN defcon)
    with a warning flag so committee agents know data is stale.
    """
```

### Recent Circuit Breaker Fetch

```python
async def fetch_recent_circuit_breakers(hours: int = 2) -> list:
    """
    GET {RAILWAY_API_URL}/api/circuit-breaker/recent?hours=2
    
    Returns list of recent CB events. These are NOT trade signals —
    they are injected as context into all committee agent prompts.
    
    Example: [
        {
            "timestamp": "2026-02-22T09:45:00Z",
            "trigger": "VIX spike above 25",
            "severity": "WARNING",
            "details": "VIX jumped from 19 to 26 in 15min"
        }
    ]
    
    On failure: return empty list (no CB context is acceptable).
    """
```

### Catalyst Calendar Loader

```python
def load_catalyst_calendar(ticker: str, dte_window: int = 30) -> dict:
    """
    Reads output from existing monitors at /opt/pivot/monitors/:
    - economic_calendar monitor → macro events
    - earnings_calendar monitor → ticker-specific events
    
    Implementation:
    1. Read the monitor output files (JSON format)
    2. Filter macro events to next {dte_window} days
    3. Filter ticker events for the specific ticker
    4. Return both lists
    
    This is CRITICAL for options trading. The same setup 2 days before
    earnings vs 2 weeks out is a completely different trade. Committee
    agents (especially Risk Assessor) need this to evaluate properly.
    
    On failure: return empty lists with warning flag.
    
    Expected output:
    {
        "ticker_events": [
            {"date": "2026-03-05", "event": "NVDA Earnings", "type": "earnings"}
        ],
        "macro_events": [
            {"date": "2026-02-25", "event": "Consumer Confidence", "type": "economic"},
            {"date": "2026-03-07", "event": "NFP", "type": "economic"}
        ],
        "warnings": []
    }
    """
```

---

## Section 3: SESSION-STATE.md Parser

SESSION-STATE.md is maintained by the existing Pivot bot — when Nick shares a position screenshot in Discord, Pivot extracts the data and writes it to this file. The committee pipeline needs to parse the "Active Positions" section into structured data for the Risk Assessor.

### SESSION-STATE.md Expected Format

```markdown
## Active Positions

| Ticker | Type | Strike | Exp | Qty | Avg Cost | Current | P/L |
|--------|------|--------|-----|-----|----------|---------|-----|
| SPY | PUT | 580 | 03/21 | 2 | 3.45 | 4.20 | +$150 |
| NVDA | CALL | 950 | 03/14 | 1 | 12.80 | 10.50 | -$230 |
| IBIT | PUT SPREAD | 50/45 | 03/07 | 5 | 1.20 | 0.85 | -$175 |
```

### Parser Function

```python
def parse_session_state(path: str = "/opt/openclaw/workspace/data/SESSION-STATE.md") -> list:
    """
    Parses the Active Positions table from SESSION-STATE.md.
    
    Returns list of position dicts:
    [
        {
            "ticker": "SPY",
            "type": "PUT",
            "strike": "580",
            "expiration": "03/21",
            "quantity": 2,
            "avg_cost": 3.45,
            "current_price": 4.20,
            "pnl": "+$150",
            "sector": "SPY"  # enriched via yfinance for non-ETF tickers
        }
    ]
    
    Edge cases to handle:
    - File doesn't exist → return empty list, log warning
    - No "Active Positions" section → return empty list
    - Malformed rows → skip with warning, don't crash
    - Spread notation (50/45) → keep as string, don't parse strikes
    
    The Risk Assessor uses this to check:
    - Sector correlation with new recommendation
    - Ticker overlap (already have NVDA exposure?)
    - Total account exposure
    - Expiration clustering (too many positions expiring same week?)
    """
```

### Sector Enrichment

```python
def get_sector(ticker: str) -> str:
    """
    Returns sector for a ticker using yfinance.
    Cache results in memory dict to avoid repeated API calls.
    
    Known ETF mappings (no yfinance needed):
    SPY → "S&P 500 ETF"
    QQQ → "Nasdaq ETF"
    IBIT → "Bitcoin ETF"
    IWM → "Russell 2000 ETF"
    XLF → "Financials ETF"
    XLE → "Energy ETF"
    ... (extend as needed)
    
    For individual stocks: yfinance.Ticker(ticker).info["sector"]
    On failure: return "Unknown"
    """
```

---

## Section 4: Whale Hunter Flow

Whale Hunter alerts are **NOT standalone trade signals**. They detect unusual options flow (dark pool / large block trades) but require human confirmation via an Unusual Whales screenshot before entering the committee.

### Flow Diagram

```
Whale Hunter alert arrives
       │
       ▼
Gatekeeper: alert_type == "whale_hunter"
       │
       ▼  (does NOT enter committee)
Discord prompt posted to Nick:
  "🐋 Whale Hunter flagged {TICKER} {DIRECTION}
   
   Flow detected: {metadata.description}
   
   To confirm, reply with a screenshot of the UW flow showing:
   • Size relative to OI (>5% is meaningful)
   • Expiration clustering (are whales targeting same date?)
   • Sweep vs block (sweeps = more urgency)
   • Premium spent ($1M+ is significant)
   
   Reply with screenshot to send to committee, 
   or 'skip' to dismiss."
       │
       ├── Nick replies with screenshot
       │         │
       │         ▼
       │   Signal re-enters pipeline as:
       │   alert_type = "whale_flow_confirmed"
       │   (skips score check, enters committee with
       │    whale context + screenshot description)
       │
       └── Nick replies "skip" or no reply within 30min
                 │
                 ▼
              Signal expires, logged as "whale_expired"
```

### Implementation Notes

```python
async def handle_whale_hunter(signal: dict, discord_channel):
    """
    Posts the UW screenshot request to Discord.
    
    The actual reply handling is done by the Discord bot's 
    existing message listener. When Nick replies with an image:
    1. Bot detects it's a reply to a whale prompt
    2. Extracts/describes the screenshot (existing Pivot capability)  
    3. Creates new signal with alert_type="whale_flow_confirmed"
    4. Injects into pipeline (bypasses Railway, goes direct to gatekeeper)
    
    Store pending whale signals in memory dict with message_id as key.
    TTL: 30 minutes. After expiry, log as whale_expired.
    
    The whale prompt message_id must be tracked so the bot knows
    which replies are whale confirmations vs normal conversation.
    """
```

### Whale-Confirmed Signal Format

When Nick confirms with a screenshot, the signal that enters the committee:

```python
confirmed_signal = {
    "id": f"whale_{original_signal['id']}",
    "ticker": original_signal["ticker"],
    "direction": original_signal["direction"],
    "score": None,  # N/A for whale signals
    "alert_type": "whale_flow_confirmed",
    "timestamp": datetime.utcnow().isoformat(),
    "metadata": {
        "original_whale_alert": original_signal["metadata"],
        "uw_screenshot_description": extracted_description,  # from Pivot's image extraction
        "confirmation_delay_seconds": delay  # how long Nick took to confirm
    }
}
```

---

## Section 5: Orchestrator Skeleton + Stub Agents

The orchestrator is the main script that ties everything together. In 03A, the four committee agents are **stubs** returning hardcoded text. Brief 03B replaces stubs with real LLM calls.

### Main Orchestrator: `pivot2_committee.py`

```python
"""
pivot2_committee.py — Main entry point for the Committee pipeline.

Usage: Called by cron/systemd every 60 seconds.
  python3 /opt/openclaw/workspace/scripts/pivot2_committee.py

Flow:
  1. Fetch pending signals from Railway API
  2. For each signal, run through gatekeeper
  3. If PASS: build context, run committee, post to Discord, log
  4. If REJECT: log rejection reason
  5. Mark signal as processed on Railway API
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# Configuration
RAILWAY_API_URL = "https://your-railway-url.up.railway.app"  # from env var
DISCORD_CHANNEL_ID = 123456789  # committee output channel
DATA_DIR = Path("/opt/openclaw/workspace/data")
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"
GATEKEEPER_LOG = DATA_DIR / "gatekeeper_log.jsonl"

# Daily state (resets at midnight UTC)
daily_state = {
    "today_runs": 0,
    "today_signals": [],  # list of "TICKER_DIRECTION" strings
    "date": None  # tracks current date for reset
}


async def main():
    """Main loop — fetch pending signals, process each."""
    reset_daily_state_if_needed()
    
    signals = await fetch_pending_signals()
    if not signals:
        return  # Nothing to process
    
    for signal in signals:
        await process_signal(signal)


async def process_signal(signal: dict):
    """Process a single signal through the full pipeline."""
    
    # Route whale hunters separately
    if signal.get("alert_type") == "whale_hunter":
        await handle_whale_hunter(signal)
        return
    
    # Store circuit breaker events as context (not trade signals)
    if signal.get("alert_type") == "circuit_breaker":
        store_circuit_breaker(signal)
        await mark_signal_processed(signal["id"])
        return
    
    # Run gatekeeper
    state = await get_current_state()
    passed, reason = gatekeeper(signal, state)
    
    # Log gatekeeper decision
    log_gatekeeper(signal, state, passed, reason)
    
    if not passed:
        await mark_signal_processed(signal["id"])
        return
    
    # Build context
    context = await build_committee_context(signal)
    
    # Run committee (STUBS in 03A)
    recommendation = await run_committee(signal, context)
    
    # Post to Discord
    await post_recommendation(recommendation)
    
    # Log committee run
    log_committee(signal, context, recommendation)
    
    # Update daily state
    daily_state["today_runs"] += 1
    daily_state["today_signals"].append(
        f"{signal['ticker']}_{signal['direction']}"
    )
    
    # Mark processed on Railway
    await mark_signal_processed(signal["id"])


async def run_committee(signal: dict, context: dict) -> dict:
    """
    Run all four committee agents and produce recommendation.
    
    IN 03A: Returns stub responses.
    IN 03B: This function gets replaced with real LLM calls.
    """
    
    # ---- STUB AGENTS (replaced in Brief 03B) ----
    
    toro_response = {
        "agent": "TORO",
        "analysis": f"[STUB] Bull case for {signal['ticker']} {signal['direction']}: "
                     f"Momentum aligns with signal. Score: {signal.get('score', 'N/A')}.",
        "conviction": "MEDIUM"
    }
    
    ursa_response = {
        "agent": "URSA",
        "analysis": f"[STUB] Bear case for {signal['ticker']} {signal['direction']}: "
                     f"Overhead resistance and elevated VIX ({context['bias'].get('vix', '?')}) "
                     f"suggest caution.",
        "conviction": "LOW"
    }
    
    risk_response = {
        "agent": "RISK",
        "analysis": f"[STUB] Risk assessment: "
                     f"Open positions: {len(context['open_positions'])}. "
                     f"DEFCON: {context['bias'].get('defcon', '?')}. "
                     f"Upcoming catalysts: {len(context['catalysts'].get('macro_events', []))} macro, "
                     f"{len(context['catalysts'].get('ticker_events', []))} ticker-specific.",
        "entry": "N/A",
        "stop": "N/A",
        "target": "N/A",
        "size": "1 contract (stub)"
    }
    
    pivot_synthesis = {
        "agent": "PIVOT",
        "synthesis": f"[STUB] Pivot synthesis for {signal['ticker']}: "
                      f"Committee reviewed. This is a stub response — "
                      f"real analysis comes in Brief 03B.",
        "conviction": "MEDIUM",
        "action": "TAKE",  # TAKE, PASS, or WATCHING
        "invalidation": "Stub — no real invalidation scenario"
    }
    
    # ---- END STUBS ----
    
    return {
        "signal": signal,
        "agents": {
            "toro": toro_response,
            "ursa": ursa_response,
            "risk": risk_response,
            "pivot": pivot_synthesis
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
```

### Stub Agent Response Contract

Each agent MUST return a dict matching this shape. Brief 03B's LLM responses must conform to the same contract so the orchestrator doesn't change.

```python
# TORO / URSA agents
{
    "agent": "TORO" | "URSA",
    "analysis": str,          # 1-3 sentence analysis
    "conviction": str         # HIGH, MEDIUM, LOW
}

# Risk Assessor
{
    "agent": "RISK",
    "analysis": str,          # Risk assessment paragraph
    "entry": str,             # Suggested entry price/level
    "stop": str,              # Stop loss level
    "target": str,            # Profit target
    "size": str               # Position size recommendation
}

# Pivot/Baum Synthesizer
{
    "agent": "PIVOT",
    "synthesis": str,          # Mark Baum-voiced synthesis
    "conviction": str,         # HIGH, MEDIUM, LOW
    "action": str,             # TAKE, PASS, WATCHING
    "invalidation": str        # "What kills this trade"
}
```

---

## Section 6: Infrastructure Setup

### Data Directory Setup

```bash
# Ensure data directory exists
mkdir -p /opt/openclaw/workspace/data

# Initialize empty log files if they don't exist
touch /opt/openclaw/workspace/data/committee_log.jsonl
touch /opt/openclaw/workspace/data/gatekeeper_log.jsonl
```

### Disable Old Trade Poller

The old `pivot2_trade_poller.py` is being replaced by this pipeline. **Do not delete it** — disable it.

```bash
# If running as cron job:
# Comment out the line in crontab that runs pivot2_trade_poller.py

# If running as systemd service:
sudo systemctl stop pivot2-trade-poller.service
sudo systemctl disable pivot2-trade-poller.service

# Add a comment at the top of the old file:
# DEPRECATED: Replaced by pivot2_committee.py (Brief 03A) — do not re-enable
```

### Cron / Systemd Timer Setup

The orchestrator runs every 60 seconds during market hours (9:30 AM - 4:00 PM ET, weekdays).

**Option A: Crontab (simpler)**
```bash
# Run every minute during market hours (ET = UTC-5 in winter, UTC-4 in summer)
# Using UTC times for winter (adjust for DST):
# 14:30-21:00 UTC = 9:30 AM - 4:00 PM ET
* 14-20 * * 1-5 /usr/bin/python3 /opt/openclaw/workspace/scripts/pivot2_committee.py >> /var/log/committee.log 2>&1
```

**Option B: Systemd timer (preferred — better logging, restart on failure)**
```ini
# /etc/systemd/system/pivot2-committee.service
[Unit]
Description=Pandora's Box Committee Pipeline
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/openclaw/workspace/scripts/pivot2_committee.py
WorkingDirectory=/opt/openclaw/workspace
Environment=RAILWAY_API_URL=https://your-url.up.railway.app
Environment=DISCORD_BOT_TOKEN=your-token
StandardOutput=append:/var/log/committee.log
StandardError=append:/var/log/committee-error.log

# /etc/systemd/system/pivot2-committee.timer
[Unit]
Description=Run Committee Pipeline every 60s

[Timer]
OnBootSec=60s
OnUnitActiveSec=60s

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable pivot2-committee.timer
sudo systemctl start pivot2-committee.timer
```

**Important:** The script must be **idempotent** — if it runs and finds no pending signals, it exits cleanly in <1 second. No long-running process, no polling loop inside the script.

### Railway API Endpoints Used

Verify these exist and return expected shapes before testing:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/signals/pending` | GET | Fetch unprocessed signals |
| `/api/signals/{id}/processed` | POST | Mark signal as processed |
| `/api/bias/composite` | GET | Current bias regime + factors |
| `/api/circuit-breaker/recent?hours=2` | GET | Recent CB events |

### Discord Output Format

The recommendation posts to a designated Discord channel. In 03A with stubs, the format is established even though content is placeholder.

```python
async def post_recommendation(recommendation: dict) -> None:
    """
    Posts formatted committee recommendation to Discord.
    
    Uses discord.py's existing bot instance.
    Message includes reply buttons for Nick's decision (Brief 03C
    will wire up the button handlers for decision tracking).
    """
    
    signal = recommendation["signal"]
    agents = recommendation["agents"]
    pivot = agents["pivot"]
    risk = agents["risk"]
    
    # Build the message
    embed = discord.Embed(
        title=f"{'🟢' if signal['direction'] == 'BULLISH' else '🔴'} "
              f"{signal['ticker']} — {signal['direction']}",
        color=0x00ff00 if signal['direction'] == 'BULLISH' else 0xff0000,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Committee deliberation
    embed.add_field(
        name="📊 Committee",
        value=(
            f"**TORO:** {agents['toro']['analysis']}\n"
            f"**URSA:** {agents['ursa']['analysis']}\n"
            f"**RISK:** {agents['risk']['analysis']}"
        ),
        inline=False
    )
    
    # Pivot's synthesis (Mark Baum voice in 03B)
    embed.add_field(
        name="🎯 Pivot's Take",
        value=pivot["synthesis"],
        inline=False
    )
    
    # Trade parameters
    embed.add_field(
        name="📋 Setup",
        value=(
            f"**Entry:** {risk['entry']}\n"
            f"**Stop:** {risk['stop']}\n"
            f"**Target:** {risk['target']}\n"
            f"**Size:** {risk['size']}"
        ),
        inline=True
    )
    
    # Meta
    embed.add_field(
        name="📈 Meta",
        value=(
            f"**Conviction:** {pivot['conviction']}\n"
            f"**Signal:** {signal['alert_type']}\n"
            f"**Score:** {signal.get('score', 'N/A')}"
        ),
        inline=True
    )
    
    # What kills it
    embed.add_field(
        name="💀 Invalidation",
        value=pivot["invalidation"],
        inline=False
    )
    
    embed.set_footer(text=f"Signal ID: {signal['id']} | Recommendation: {pivot['action']}")
    
    # Reply buttons (visual only in 03A — wired in 03C)
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="✅ Take", style=discord.ButtonStyle.success, custom_id=f"take_{signal['id']}"
    ))
    view.add_item(discord.ui.Button(
        label="❌ Pass", style=discord.ButtonStyle.danger, custom_id=f"pass_{signal['id']}"
    ))
    view.add_item(discord.ui.Button(
        label="👀 Watching", style=discord.ButtonStyle.secondary, custom_id=f"watch_{signal['id']}"
    ))
    
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    await channel.send(embed=embed, view=view)
```

### JSONL Logging

```python
def log_committee(signal: dict, context: dict, recommendation: dict) -> None:
    """Append committee run to committee_log.jsonl"""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal["id"],
        "ticker": signal["ticker"],
        "direction": signal["direction"],
        "score": signal.get("score"),
        "alert_type": signal["alert_type"],
        "bias_regime": context["bias"].get("regime"),
        "defcon": context["bias"].get("defcon"),
        "vix": context["bias"].get("vix"),
        "open_positions_count": len(context["open_positions"]),
        "catalysts_macro": len(context["catalysts"].get("macro_events", [])),
        "catalysts_ticker": len(context["catalysts"].get("ticker_events", [])),
        "conviction": recommendation["agents"]["pivot"]["conviction"],
        "action": recommendation["agents"]["pivot"]["action"],
        "sector": get_sector(signal["ticker"]),
        # Decision fields populated by Brief 03C:
        "nick_decision": None,
        "outcome": None  # Populated by Brief 04 Auditor
    }
    
    with open(COMMITTEE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def log_gatekeeper(signal: dict, state: dict, passed: bool, reason: str) -> None:
    """Append gatekeeper evaluation to gatekeeper_log.jsonl"""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal["id"],
        "ticker": signal["ticker"],
        "direction": signal["direction"],
        "score": signal.get("score"),
        "alert_type": signal["alert_type"],
        "defcon": state.get("defcon"),
        "bias_regime": state.get("bias_regime"),
        "passed": passed,
        "reject_reason": reason if not passed else None
    }
    
    with open(GATEKEEPER_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
```

---

## Section 7: Testing Checklist

Every item must pass before Brief 03A is considered complete. Test with stub agents — no LLM calls.

### Gatekeeper Tests

- [ ] **CTA Scanner signal, score 75, no blockers** → PASS
- [ ] **CTA Scanner signal, score 45** → REJECT "Score 45 below threshold 60"
- [ ] **Signal older than 30 minutes** → REJECT with age reason
- [ ] **Duplicate ticker+direction same day** → REJECT "Duplicate SPY_BEARISH already processed"
- [ ] **21st signal of the day** → REJECT "Daily cap reached (20/20)"
- [ ] **DEFCON RED + BULLISH signal** → REJECT "DEFCON RED: BULLISH signals blocked"
- [ ] **DEFCON RED + BEARISH signal** → PASS
- [ ] **DEFCON ORANGE + URSA_MINOR + BULLISH signal** → REJECT "blocking non-aligned BULLISH"
- [ ] **DEFCON ORANGE + URSA_MINOR + BEARISH signal** → PASS
- [ ] **TORO_MAJOR bias + BEARISH score 65** → REJECT "Counter-bias BEARISH requires score ≥80"
- [ ] **TORO_MAJOR bias + BEARISH score 85** → PASS
- [ ] **Sniper alert, score 40** → PASS (score check skipped for pre-qualified)
- [ ] **Scout alert** → PASS (score check skipped)
- [ ] **Exhaustion alert** → PASS (score check skipped)
- [ ] **Whale Hunter alert** → Does NOT enter committee, triggers Discord prompt
- [ ] **Circuit Breaker alert** → Stored as context, does NOT enter committee
- [ ] **Every evaluation writes to gatekeeper_log.jsonl** — pass AND reject
- [ ] **NEUTRAL bias** → Both BULLISH and BEARISH pass at normal threshold

### Context Builder Tests

- [ ] **Bias composite fetched** → Returns regime, defcon, VIX, factors
- [ ] **Bias composite API down** → Returns defaults (NEUTRAL, GREEN) with warning
- [ ] **Circuit breaker fetch** → Returns recent CB events list
- [ ] **Circuit breaker API down** → Returns empty list (non-fatal)
- [ ] **Catalyst calendar loads** → Returns macro + ticker events
- [ ] **Catalyst calendar for unknown ticker** → Returns empty ticker_events, still has macro
- [ ] **SESSION-STATE.md exists with positions** → Parses into structured list
- [ ] **SESSION-STATE.md missing** → Returns empty list, logs warning
- [ ] **SESSION-STATE.md malformed row** → Skips bad row, parses rest

### Orchestrator Tests

- [ ] **No pending signals** → Script exits cleanly in <1 second
- [ ] **One valid signal** → Gatekeeper PASS → context built → stub committee runs → Discord post → JSONL log
- [ ] **Multiple signals in one run** → Each processed independently
- [ ] **Daily state resets at midnight** → today_runs and today_signals clear

### Discord Output Tests

- [ ] **Embed posts to correct channel** with all fields populated
- [ ] **BULLISH signal** → Green embed, green circle emoji
- [ ] **BEARISH signal** → Red embed, red circle emoji
- [ ] **Three buttons appear** → Take / Pass / Watching (visual only, no handlers yet)
- [ ] **Signal ID in footer** → Traceable back to logs

### Whale Hunter Tests

- [ ] **Whale alert posts UW screenshot request** to Discord with guidance text
- [ ] **Nick replies with image** → Creates whale_flow_confirmed signal → enters pipeline
- [ ] **Nick replies "skip"** → Signal logged as whale_expired
- [ ] **No reply within 30 min** → Signal expires, logged
- [ ] **Whale-confirmed signal** → Passes gatekeeper (skips score), runs through committee

### Infrastructure Tests

- [ ] **Data directory exists** with proper permissions
- [ ] **Old trade poller disabled** — not running, not in cron
- [ ] **Systemd timer fires every 60s** during market hours
- [ ] **Script is idempotent** — running twice with no new signals causes no side effects
- [ ] **JSONL files are valid** — each line parseable as JSON
- [ ] **Log rotation considered** — files don't grow unbounded (suggest logrotate config)

### Integration Smoke Test

Run this sequence manually:

1. Inject a test signal into Railway API with score 75, ticker TEST, direction BULLISH
2. Wait for cron to pick it up (or run script manually)
3. Verify: gatekeeper_log.jsonl shows PASS
4. Verify: committee_log.jsonl shows stub recommendation
5. Verify: Discord channel receives formatted embed with buttons
6. Inject same signal again → verify dedup rejects it
7. Inject a whale_hunter signal → verify Discord prompt appears (not committee)
8. Reply to whale prompt with "skip" → verify whale_expired logged

---

## Implementation Order

Build in this exact sequence to allow incremental testing:

1. **Data directory setup + JSONL helpers** — Can test file writes immediately
2. **Gatekeeper function** — Unit testable with mock state dicts
3. **SESSION-STATE.md parser** — Unit testable with sample file
4. **Bias composite + CB fetcher** — Requires Railway API running
5. **Catalyst calendar loader** — Requires monitor output files
6. **Context builder (assembles above)** — Integration point
7. **Stub committee + recommendation builder** — Produces output dict
8. **Discord embed formatter + posting** — Requires bot running
9. **Main orchestrator (wires everything)** — Full pipeline
10. **Whale Hunter flow** — Requires Discord message listener
11. **Cron/systemd setup** — Final step, only after manual runs work
12. **Disable old trade poller** — Only after new pipeline confirmed working

---

## Environment Variables Required

```bash
RAILWAY_API_URL=https://your-app.up.railway.app
DISCORD_BOT_TOKEN=your-discord-bot-token
COMMITTEE_CHANNEL_ID=123456789
```

These should be set in the systemd service file or sourced from an env file that the Pivot bot already uses.

---

*End of Brief 03A. Next: Brief 03B (Committee Prompts + LLM Integration) — assumes this pipeline is running with stubs.*
