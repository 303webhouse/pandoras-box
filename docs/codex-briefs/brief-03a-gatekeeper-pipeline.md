# Brief 03A: Gatekeeper + Pipeline Skeleton

**Date:** February 22, 2026
**Priority:** HIGH
**Scope:** One new file + one cron job update. All work on VPS at `/opt/openclaw/workspace/`
**Estimated effort:** ~45 min agent time
**Prereqs:** None (this is the foundation for 03B and 03C)

---

## Problem

The current trade poller (`pivot2_trade_poller.py`) fetches signals from Railway, applies a score threshold, and posts raw embeds to Discord. There is no analysis — no bull/bear debate, no risk assessment, no position awareness, no catalyst checking. Nick gets a signal card and has to do all the thinking himself.

This brief builds the **pipeline skeleton** that will power the Trading Team committee system. It replaces the old trade poller with a smarter Gatekeeper that filters signals, builds rich market context, and (in this brief) posts a stub committee output to Discord. Brief 03B will plug in the actual LLM agents.

---

## Architecture Overview

```
Signal Sources                    Gatekeeper (this brief)              Committee (Brief 03B)
─────────────                    ────────────────────────             ────────────────────────
Railway API ──→ poll every 2min ─→ Score filter (≥60)     ─→ stub ─→ Discord post
TradingView ──→ signals/active  ─→ Dedup (ticker+dir+date)           (real agents in 03B)
  - Sniper                       ─→ Daily cap (≤20 runs)
  - Scout EW                     ─→ DEFCON filter
  - Exhaustion                   ─→ Bias alignment check
  - Whale Hunter ──→ UW screenshot request (separate flow)
  - Circuit Breaker ──→ context injection only (not a trade idea)
```

---

## What This Brief Creates

### New file: `/opt/openclaw/workspace/scripts/pivot2_committee.py`

Single Python script (~450 lines) that:

1. **Fetches signals** from Railway API (`/signals/active`)
2. **Runs Gatekeeper filters** (score, dedup, cap, DEFCON, bias alignment)
3. **Routes special signals** (Whale Hunter → UW request, Circuit Breaker → context only)
4. **Builds market context** (bias composite, positions, recent Circuit Breaker events, earnings calendar)
5. **Calls committee stub** (returns dummy analysis — replaced by real LLM calls in 03B)
6. **Posts recommendation to Discord** in the agreed format
7. **Logs every run** to `data/committee_log.jsonl`

### Modified: OpenClaw cron job `pivot2-trade-poller`

Swap command from `pivot2_trade_poller.py` to `pivot2_committee.py`. Same schedule (every 2 min, market hours).

---

## Gatekeeper Rules (No LLM, Pure Code)

### Signal routing by type

| Signal source | `strategy` field contains | Action |
|---|---|---|
| CTA Scanner | anything not below | → Gatekeeper filters → committee |
| TradingView Sniper | `sniper` | → Skip score threshold → committee |
| TradingView Scout EW | `scout` | → Skip score threshold → committee |
| TradingView Exhaustion | `exhaustion` | → Skip score threshold → committee |
| TradingView Whale Hunter | `whale` | → Post UW screenshot request → STOP (no committee) |
| TradingView Circuit Breaker | `circuit_breaker` | → Save to context file → STOP (no committee) |
| CTA Zone Shift | `signal_type` contains `ZONE` | → Save zone shift → STOP (same as current behavior) |

### Pass criteria (ALL must be true for committee to run)

1. **Score ≥ 60** for CTA Scanner signals. TradingView alerts (Sniper, Scout EW, Exhaustion) skip this check.
2. **Not a duplicate** — key is `{ticker}_{direction}_{YYYY-MM-DD}`. One committee run per ticker+direction per day.
3. **Daily cap not reached** — max 20 committee runs per day.
4. **DEFCON allows it:**
   - GREEN/YELLOW: pass both directions
   - ORANGE: pass only bias-aligned signals (TORO bias → BULLISH only, URSA bias → BEARISH only)
   - RED: pass only BEARISH signals regardless of bias
5. **Signal age < 30 minutes** — skip signals with timestamps older than 30 min.

### Bias alignment for CTA Scanner signals

When bias is TORO_MAJOR or TORO_MINOR: pass BULLISH freely, BEARISH only if score ≥ 80.
When bias is URSA_MAJOR or URSA_MINOR: pass BEARISH freely, BULLISH only if score ≥ 80.
When bias is NEUTRAL: pass both directions freely.

TradingView alerts are pre-qualified by PineScript and skip this check.

---

## Market Context Builder

For every signal that passes the Gatekeeper, build a context dict that will be passed to the committee agents (in 03B). For now, it's included in the Discord stub post.

### Context sources

| Data | Source | How |
|---|---|---|
| Bias composite | Railway API `/api/bias/composite` | HTTP GET |
| DEFCON status | `SESSION-STATE.md` → "DEFCON" line | File read + parse |
| Open positions | `SESSION-STATE.md` → "Active Positions" tables | File read + parse |
| Recent Circuit Breaker | `data/recent_circuit_breakers.json` | File read |
| Earnings calendar | yfinance `Ticker.calendar` for the signal ticker | Python call |
| Zone context | `data/last_zone_shift.json` (existing) | File read |
| Account summary | `SESSION-STATE.md` → "RH Account Summary" | File read + parse |

### Position parser

Parse the markdown tables in SESSION-STATE.md under `### Robinhood (Tier B)` into structured data:

```python
# Example output from position parser
[
    {
        "ticker": "TSLA",
        "type": "Put Spread",
        "strikes": "$380/$370",
        "exp": "3/20",
        "qty": 2,
        "current_value": 1.85,
        "status": "LOSING",
        "pnl": "-$40"
    },
    ...
]
```

The parser should handle the current SESSION-STATE.md format. It does NOT need to handle edge cases — if the format changes, the parser will be updated.

### Earnings check

For the signal's ticker, check if earnings are within the next 14 calendar days:

```python
import yfinance as yf

def check_earnings_proximity(ticker: str) -> dict:
    """Returns {"has_earnings": bool, "days_until": int|None, "date": str|None}"""
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is not None and not cal.empty and "Earnings Date" in cal.index:
            earn_date = cal.loc["Earnings Date"][0]
            days = (earn_date.date() - datetime.now().date()).days
            if 0 <= days <= 14:
                return {"has_earnings": True, "days_until": days, "date": str(earn_date.date())}
    except Exception:
        pass
    return {"has_earnings": False, "days_until": None, "date": None}
```

---

## Whale Hunter Flow

When a Whale Hunter signal arrives:

1. Do NOT run the committee.
2. Post to Discord:

```
🐋 **Whale Hunter detected: {TICKER} {DIRECTION}**

Absorption pattern on the tape. Need options flow confirmation before this goes to the committee.

**Nick — post a UW screenshot for {TICKER}.** I'm looking for:
• Large block/sweep activity matching {DIRECTION} direction
• Elevated OI at nearby strikes
• Dark pool prints supporting the thesis

⏰ Signal expires in 30 minutes if no confirmation.
```

3. Log the signal as `"status": "AWAITING_UW_CONFIRM"` in `committee_log.jsonl`.

**Note:** The actual screenshot → confirmation → committee flow requires Pivot's chat handler (OpenClaw) to recognize when Nick posts a screenshot in response. That integration is out of scope for this brief — it will be handled when 03B wires up the real agents. For now, the Discord message is the deliverable.

---

## Circuit Breaker Flow

When a Circuit Breaker signal arrives:

1. Do NOT run the committee.
2. Save to `data/recent_circuit_breakers.json`:

```json
[
    {
        "ticker": "SPY",
        "direction": "BEARISH",
        "timestamp": "2026-02-22T14:30:00Z",
        "entry_price": 680.50,
        "notes": "Rapid sell-off detected"
    }
]
```

Keep only events from the last 2 hours. Older entries get pruned on each write.

3. Post a brief notification to Discord:

```
⚡ **Circuit Breaker fired: {TICKER} {DIRECTION}**
This is a market stress warning, not a trade idea. The committee will factor this into its next analysis.
```

4. The context builder reads this file and includes recent CB events in the committee context payload.

---

## Discord Output Format (Stub for 03A)

Until 03B plugs in real agents, the committee stub returns placeholder text. The Discord post format is final — 03B only changes what fills the fields.

```
━━━━━━━━━━━━━━━━━━━━━━━
🎯 TRADE IDEA: {TICKER} {DIRECTION} ({STRATEGY})
━━━━━━━━━━━━━━━━━━━━━━━

**Committee:** (pending 03B — agents not yet wired)
• TORO: [stub]
• URSA: [stub]
• Risk: [stub]

**Pivot says:** Committee analysis pending — agents will be wired in Brief 03B. For now, here's the raw signal data and market context.

📊 Score: {SCORE}/100 | Bias: {BIAS_LEVEL}
📍 Entry: ${ENTRY} | Stop: ${STOP} | Target: ${TARGET}
⚠️ Earnings: {EARNINGS_NOTE}
📋 Open positions in {TICKER}: {POSITION_NOTE}
🔴 Circuit Breaker: {CB_NOTE}

Reply: **take** / **pass** / **watching**
━━━━━━━━━━━━━━━━━━━━━━━
```

Field logic:
- `EARNINGS_NOTE`: "NVDA earnings in 3 days" or "None within 14 days"
- `POSITION_NOTE`: "You have 2x TSLA $380/$370 put spreads exp 3/20" or "None"
- `CB_NOTE`: "SPY Circuit Breaker fired 25 min ago" or "None recent"

---

## Logging

Every Gatekeeper decision and committee run gets logged to `data/committee_log.jsonl` (one JSON object per line):

```json
{
    "timestamp": "2026-02-22T10:30:00Z",
    "signal_id": "SPY_SHORT_20260222_103000_123456",
    "ticker": "SPY",
    "direction": "SHORT",
    "strategy": "Sniper",
    "source": "tradingview",
    "score": 72,
    "gatekeeper_result": "PASS",
    "gatekeeper_reason": null,
    "bias_level": "URSA_MINOR",
    "defcon": "GREEN",
    "earnings_proximity": {"has_earnings": false, "days_until": null},
    "open_positions_in_ticker": [],
    "circuit_breaker_context": [],
    "committee_ran": true,
    "recommendation_id": "REC_20260222_103000",
    "nick_decision": null,
    "outcome": null
}
```

For filtered signals:
```json
{
    "timestamp": "2026-02-22T10:32:00Z",
    "signal_id": "AAPL_LONG_20260222_103200_789012",
    "ticker": "AAPL",
    "direction": "LONG",
    "strategy": "CTA Scanner",
    "source": "railway",
    "score": 45,
    "gatekeeper_result": "FILTERED",
    "gatekeeper_reason": "score_below_threshold",
    "committee_ran": false
}
```

Log file rotation: keep last 500 lines. Trim on each write (same pattern as `seen_signal_ids.json`).

---

## Full Script Structure

```python
#!/usr/bin/env python3
"""
Pivot II Trading Team — Gatekeeper + Pipeline
Replaces pivot2_trade_poller.py

Polls Railway API for signals, filters through Gatekeeper rules,
builds market context, runs committee (stub in 03A, real in 03B),
posts recommendations to Discord.
"""

# ── imports ──────────────────────────────────────────────────
# Standard lib: argparse, json, datetime, pathlib, re, hashlib, sys
# Third-party: yfinance (already installed on VPS)
# Internal: reuse http_json, load_openclaw_config, load_env_file,
#           pick_env, load_discord_token, now_utc, parse_iso_ts
#           from pivot2_trade_poller.py (copy the utility functions)

# ── constants ────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
SESSION_STATE_FILE = SCRIPT_DIR.parent / "SESSION-STATE.md"

DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app/api"
DEFAULT_CHANNEL_ID = "1474135100521451813"
DISCORD_API_BASE = "https://discord.com/api/v10"

MIN_SCORE_CTA = 60          # CTA Scanner minimum score
MIN_SCORE_COUNTER_BIAS = 80 # Counter-bias minimum score
MAX_DAILY_RUNS = 20         # Hard cap on committee runs per day
SIGNAL_MAX_AGE_MIN = 30     # Ignore signals older than 30 min
CB_RETENTION_HOURS = 2      # Keep Circuit Breaker events for 2 hours
LOG_MAX_LINES = 500         # committee_log.jsonl max lines

# TradingView strategy keywords for routing
TV_COMMITTEE_STRATEGIES = {"sniper", "scout", "exhaustion"}
TV_WHALE_STRATEGIES = {"whale", "whale_hunter", "whalehunter"}
TV_CIRCUIT_BREAKER_STRATEGIES = {"circuit_breaker", "circuitbreaker", "circuit"}

# ── utility functions (copied from pivot2_trade_poller.py) ───
# http_json, load_openclaw_config, load_env_file, pick_env,
# load_discord_token, now_utc, parse_iso_ts, ensure_data_dir,
# safe_float, compute_rr

# ── data files ───────────────────────────────────────────────
SEEN_FILE = DATA_DIR / "seen_signal_ids.json"        # existing
ZONE_FILE = DATA_DIR / "last_zone_shift.json"        # existing
CB_FILE = DATA_DIR / "recent_circuit_breakers.json"   # NEW
LOG_FILE = DATA_DIR / "committee_log.jsonl"           # NEW
DAILY_COUNT_FILE = DATA_DIR / "committee_daily_count.json"  # NEW

# ── Gatekeeper ───────────────────────────────────────────────

def classify_signal_source(signal: dict) -> str:
    """Determine routing: 'committee', 'whale', 'circuit_breaker', 'zone', 'skip'"""
    strategy = str(signal.get("strategy") or "").lower()
    signal_type = str(signal.get("signal_type") or "").upper()

    if "ZONE" in signal_type or "ZONE" in strategy.upper():
        return "zone"
    if any(kw in strategy for kw in TV_CIRCUIT_BREAKER_STRATEGIES):
        return "circuit_breaker"
    if any(kw in strategy for kw in TV_WHALE_STRATEGIES):
        return "whale"
    # Sniper, Scout, Exhaustion, CTA Scanner all go to committee
    return "committee"


def is_tv_prequalified(signal: dict) -> bool:
    """TradingView Sniper/Scout/Exhaustion skip score threshold."""
    strategy = str(signal.get("strategy") or "").lower()
    return any(kw in strategy for kw in TV_COMMITTEE_STRATEGIES)


def get_dedup_key(signal: dict) -> str:
    """One committee run per ticker+direction per day."""
    ticker = str(signal.get("ticker") or "UNKNOWN").upper()
    direction = str(signal.get("direction") or "UNKNOWN").upper()
    date = now_utc().strftime("%Y-%m-%d")
    return f"{ticker}_{direction}_{date}"


def load_daily_count() -> dict:
    """Load today's committee run count. Resets each day."""
    try:
        if DAILY_COUNT_FILE.exists():
            data = json.loads(DAILY_COUNT_FILE.read_text())
            if data.get("date") == now_utc().strftime("%Y-%m-%d"):
                return data
    except Exception:
        pass
    return {"date": now_utc().strftime("%Y-%m-%d"), "count": 0, "dedup_keys": []}


def save_daily_count(data: dict) -> None:
    ensure_data_dir()
    DAILY_COUNT_FILE.write_text(json.dumps(data, indent=2))


def gatekeeper(signal: dict, bias_level: str, defcon: str, daily: dict) -> tuple[bool, str|None]:
    """
    Returns (pass: bool, reject_reason: str|None).
    If pass=True, signal proceeds to committee.
    """
    score = safe_float(signal.get("score"))
    direction = str(signal.get("direction") or "").upper()
    tv_prequalified = is_tv_prequalified(signal)

    # 1. Score threshold (CTA Scanner only)
    if not tv_prequalified and score < MIN_SCORE_CTA:
        return False, "score_below_threshold"

    # 2. Signal age
    ts_raw = signal.get("timestamp")
    if ts_raw:
        sig_ts = parse_iso_ts(str(ts_raw))
        if sig_ts and (now_utc() - sig_ts).total_seconds() > SIGNAL_MAX_AGE_MIN * 60:
            return False, "signal_too_old"

    # 3. Dedup
    dedup_key = get_dedup_key(signal)
    if dedup_key in daily.get("dedup_keys", []):
        return False, "duplicate_ticker_direction_today"

    # 4. Daily cap
    if daily.get("count", 0) >= MAX_DAILY_RUNS:
        return False, "daily_cap_reached"

    # 5. DEFCON filter
    defcon_upper = defcon.upper() if defcon else "GREEN"
    if defcon_upper == "RED" and direction not in ("SHORT", "BEARISH", "SELL"):
        return False, "defcon_red_bearish_only"
    if defcon_upper == "ORANGE":
        # Only bias-aligned signals pass
        is_bullish_direction = direction in ("LONG", "BULLISH", "BUY")
        is_bearish_direction = direction in ("SHORT", "BEARISH", "SELL")
        bias_upper = bias_level.upper() if bias_level else "NEUTRAL"
        if "TORO" in bias_upper and is_bearish_direction:
            return False, "defcon_orange_counter_bias"
        if "URSA" in bias_upper and is_bullish_direction:
            return False, "defcon_orange_counter_bias"

    # 6. Bias alignment (CTA Scanner only — TV alerts skip)
    if not tv_prequalified:
        bias_upper = bias_level.upper() if bias_level else "NEUTRAL"
        is_bullish = direction in ("LONG", "BULLISH", "BUY")
        is_bearish = direction in ("SHORT", "BEARISH", "SELL")

        if "TORO" in bias_upper and is_bearish and score < MIN_SCORE_COUNTER_BIAS:
            return False, "counter_bias_score_too_low"
        if "URSA" in bias_upper and is_bullish and score < MIN_SCORE_COUNTER_BIAS:
            return False, "counter_bias_score_too_low"

    return True, None


# ── Market Context Builder ───────────────────────────────────

def parse_positions_from_session_state() -> list[dict]:
    """Parse open positions from SESSION-STATE.md markdown tables."""
    if not SESSION_STATE_FILE.exists():
        return []
    content = SESSION_STATE_FILE.read_text(encoding="utf-8")

    positions = []
    in_table = False
    header_found = False

    for line in content.split("\n"):
        stripped = line.strip()

        # Look for position table headers (starts with "| Position |")
        if stripped.startswith("| Position |"):
            in_table = True
            header_found = True
            continue

        # Skip separator line
        if in_table and stripped.startswith("|---"):
            continue

        # Parse table rows
        if in_table and stripped.startswith("|") and not stripped.startswith("| —"):
            cols = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cols) >= 6:
                # Skip rows that are sub-legs (start with "—")
                if cols[0].startswith("—") or cols[0].startswith("Greeks"):
                    continue
                positions.append({
                    "ticker": cols[0].split()[0] if cols[0] else "UNKNOWN",
                    "type": cols[1] if len(cols) > 1 else "",
                    "strikes": cols[2] if len(cols) > 2 else "",
                    "exp": cols[3] if len(cols) > 3 else "",
                    "qty": cols[4] if len(cols) > 4 else "",
                    "current_value": cols[5] if len(cols) > 5 else "",
                    "status": cols[6] if len(cols) > 6 else "",
                })

        # End of table
        if in_table and header_found and not stripped.startswith("|"):
            in_table = False

    return positions


def parse_defcon_from_session_state() -> str:
    """Extract DEFCON level from SESSION-STATE.md."""
    if not SESSION_STATE_FILE.exists():
        return "GREEN"
    content = SESSION_STATE_FILE.read_text(encoding="utf-8")
    for line in content.split("\n"):
        if "DEFCON" in line.upper() and ":" in line:
            # Match "**DEFCON:** GREEN" or "- **DEFCON:** GREEN"
            parts = line.split(":")
            if len(parts) >= 2:
                level = parts[-1].strip().upper()
                for valid in ("GREEN", "YELLOW", "ORANGE", "RED"):
                    if valid in level:
                        return valid
    return "GREEN"


def parse_account_summary_from_session_state() -> dict:
    """Extract RH buying power and cash from SESSION-STATE.md."""
    if not SESSION_STATE_FILE.exists():
        return {}
    content = SESSION_STATE_FILE.read_text(encoding="utf-8")
    summary = {}
    for line in content.split("\n"):
        if "Buying Power" in line:
            match = re.search(r"\$[\d,]+\.?\d*", line)
            if match:
                summary["buying_power"] = match.group(0)
        if "Cash:" in line and "Short Cash" not in line:
            match = re.search(r"\$[\d,]+\.?\d*", line)
            if match:
                summary["cash"] = match.group(0)
    return summary


def load_recent_circuit_breakers() -> list[dict]:
    """Load CB events from last 2 hours."""
    try:
        if CB_FILE.exists():
            events = json.loads(CB_FILE.read_text(encoding="utf-8"))
            now = now_utc()
            recent = []
            for ev in events:
                ts = parse_iso_ts(str(ev.get("timestamp") or ""))
                if ts and (now - ts).total_seconds() <= CB_RETENTION_HOURS * 3600:
                    recent.append(ev)
            return recent
    except Exception:
        pass
    return []


def save_circuit_breaker(signal: dict) -> None:
    """Append CB event, prune old entries."""
    ensure_data_dir()
    events = load_recent_circuit_breakers()  # already pruned
    events.append({
        "ticker": str(signal.get("ticker") or "SPY"),
        "direction": str(signal.get("direction") or "BEARISH"),
        "timestamp": str(signal.get("timestamp") or now_utc().isoformat()),
        "entry_price": safe_float(signal.get("entry_price")),
        "notes": str(signal.get("notes") or signal.get("signal_type") or ""),
    })
    CB_FILE.write_text(json.dumps(events, indent=2), encoding="utf-8")


def check_earnings_proximity(ticker: str) -> dict:
    """Check if ticker has earnings within 14 days."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is not None and not cal.empty and "Earnings Date" in cal.index:
            from datetime import date
            earn_date = cal.loc["Earnings Date"][0]
            if hasattr(earn_date, "date"):
                earn_date = earn_date.date()
            days = (earn_date - date.today()).days
            if 0 <= days <= 14:
                return {"has_earnings": True, "days_until": days, "date": str(earn_date)}
    except Exception:
        pass
    return {"has_earnings": False, "days_until": None, "date": None}


def build_market_context(signal: dict, api_url: str, api_key: str) -> dict:
    """Build full context dict for committee agents."""
    headers = {"Authorization": f"Bearer {api_key}"}
    base = api_url.rstrip("/")

    # 1. Bias composite
    composite = {}
    try:
        composite = http_json(url=f"{base}/bias/composite", headers=headers, timeout=30)
    except Exception:
        pass

    # 2. DEFCON
    defcon = parse_defcon_from_session_state()

    # 3. Open positions
    all_positions = parse_positions_from_session_state()
    ticker = str(signal.get("ticker") or "").upper()
    ticker_positions = [p for p in all_positions if p.get("ticker", "").upper() == ticker]

    # 4. Account summary
    account = parse_account_summary_from_session_state()

    # 5. Recent Circuit Breakers
    cb_events = load_recent_circuit_breakers()

    # 6. Earnings proximity
    earnings = check_earnings_proximity(ticker)

    # 7. Zone context
    zone = {}
    try:
        if ZONE_FILE.exists():
            zone = json.loads(ZONE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass

    return {
        "bias_composite": {
            "bias_level": composite.get("bias_level", "UNKNOWN"),
            "composite_score": composite.get("composite_score"),
            "confidence": composite.get("confidence", "UNKNOWN"),
        },
        "defcon": defcon,
        "open_positions": {
            "all": all_positions,
            "ticker_specific": ticker_positions,
            "account": account,
        },
        "circuit_breakers": cb_events,
        "earnings": earnings,
        "zone": zone,
    }


# ── Committee Stub (replaced by real LLM calls in 03B) ──────

def run_committee_stub(signal: dict, context: dict) -> dict:
    """
    Placeholder committee output. Returns the format that 03B will produce.
    This lets us test the full pipeline end-to-end without LLM costs.
    """
    return {
        "toro_summary": "[stub — TORO analyst not yet wired]",
        "ursa_summary": "[stub — URSA analyst not yet wired]",
        "risk_summary": "[stub — Risk assessor not yet wired]",
        "pivot_recommendation": (
            "Committee analysis pending — agents will be wired in Brief 03B. "
            "For now, here's the raw signal data and market context."
        ),
        "conviction": "PENDING",
        "entry": safe_float(signal.get("entry_price")),
        "stop": safe_float(signal.get("stop_loss")),
        "target": safe_float(signal.get("target_1")),
        "size_recommendation": None,
        "what_kills_it": None,
        "exit_plan": None,
    }


# ── Discord Posting ──────────────────────────────────────────

def format_recommendation_message(signal: dict, context: dict, committee: dict) -> str:
    """Format the Discord message for a committee recommendation."""
    ticker = str(signal.get("ticker") or "???")
    direction = str(signal.get("direction") or "???").upper()
    strategy = str(signal.get("strategy") or "Unknown")
    score = safe_float(signal.get("score"))
    bias = context["bias_composite"]["bias_level"]

    entry = committee["entry"]
    stop = committee["stop"]
    target = committee["target"]
    rr = compute_rr(entry, stop, target) if entry and stop and target else 0

    # Earnings note
    earn = context["earnings"]
    if earn["has_earnings"]:
        earnings_note = f"{ticker} earnings in {earn['days_until']} days ({earn['date']})"
    else:
        earnings_note = "None within 14 days"

    # Position note
    tp = context["open_positions"]["ticker_specific"]
    if tp:
        pos_parts = []
        for p in tp:
            pos_parts.append(f"{p.get('qty','')}x {p.get('ticker','')} {p.get('strikes','')} {p.get('type','')} exp {p.get('exp','')}")
        position_note = "; ".join(pos_parts)
    else:
        position_note = "None"

    # Circuit Breaker note
    cb = context["circuit_breakers"]
    if cb:
        latest = cb[-1]
        cb_ts = parse_iso_ts(str(latest.get("timestamp") or ""))
        if cb_ts:
            age_min = int((now_utc() - cb_ts).total_seconds() / 60)
            cb_note = f"{latest.get('ticker')} Circuit Breaker fired {age_min} min ago"
        else:
            cb_note = f"{latest.get('ticker')} Circuit Breaker (recent)"
    else:
        cb_note = "None recent"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 **TRADE IDEA: {ticker} {direction} ({strategy})**",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "**Committee:**",
        f"• TORO: {committee['toro_summary']}",
        f"• URSA: {committee['ursa_summary']}",
        f"• Risk: {committee['risk_summary']}",
        "",
        f"**Pivot says:** {committee['pivot_recommendation']}",
        "",
        f"📊 Score: {score:.0f}/100 | Bias: {bias} | R/R: {rr:.1f}:1",
        f"📍 Entry: ${entry:.2f} | Stop: ${stop:.2f} | Target: ${target:.2f}",
        f"⚠️ Earnings: {earnings_note}",
        f"📋 Open positions in {ticker}: {position_note}",
        f"🔴 Circuit Breaker: {cb_note}",
        "",
        "Reply: **take** / **pass** / **watching**",
        "━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_whale_message(signal: dict) -> str:
    """Format Whale Hunter UW screenshot request."""
    ticker = str(signal.get("ticker") or "???")
    direction = str(signal.get("direction") or "???").upper()
    return (
        f"🐋 **Whale Hunter detected: {ticker} {direction}**\n\n"
        f"Absorption pattern on the tape. Need options flow confirmation before "
        f"this goes to the committee.\n\n"
        f"**Nick — post a UW screenshot for {ticker}.** I'm looking for:\n"
        f"• Large block/sweep activity matching {direction} direction\n"
        f"• Elevated OI at nearby strikes\n"
        f"• Dark pool prints supporting the thesis\n\n"
        f"⏰ Signal expires in 30 minutes if no confirmation."
    )


def format_circuit_breaker_message(signal: dict) -> str:
    """Format Circuit Breaker notification."""
    ticker = str(signal.get("ticker") or "???")
    direction = str(signal.get("direction") or "???").upper()
    return (
        f"⚡ **Circuit Breaker fired: {ticker} {direction}**\n"
        f"This is a market stress warning, not a trade idea. "
        f"The committee will factor this into its next analysis."
    )


def post_discord_message(token: str, channel_id: str, content: str) -> dict:
    """Post a plain text message to Discord."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "Pivot-II/2.0",
        "Content-Type": "application/json",
    }
    # Discord limit is 2000 chars per message
    if len(content) > 1950:
        content = content[:1950] + "\n[truncated]"
    return http_json(url=url, method="POST", headers=headers, payload={"content": content}, timeout=30)


# ── Logging ──────────────────────────────────────────────────

def log_committee_event(entry: dict) -> None:
    """Append to committee_log.jsonl, trim to LOG_MAX_LINES."""
    ensure_data_dir()
    line = json.dumps(entry, default=str) + "\n"

    # Append
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

    # Trim if needed (read all, keep last N)
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) > LOG_MAX_LINES:
            LOG_FILE.write_text("\n".join(lines[-LOG_MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass


# ── Main Pipeline ────────────────────────────────────────────

def run(channel_id: str, dry_run: bool) -> dict:
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_PANDORA_API_URL
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)
    if not api_key:
        raise RuntimeError("PIVOT_API_KEY is required")

    discord_token = load_discord_token(cfg, env_file)

    # Fetch signals
    signals = fetch_signals(api_url=api_url, api_key=api_key)

    # Load state
    seen_ids = load_seen_ids()
    seen_set = set(seen_ids)
    daily = load_daily_count()

    # Get bias for Gatekeeper
    bias_level = "NEUTRAL"
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        composite = http_json(url=f"{api_url.rstrip('/')}/bias/composite", headers=headers, timeout=30)
        bias_level = composite.get("bias_level", "NEUTRAL")
    except Exception:
        pass

    defcon = parse_defcon_from_session_state()

    summary = {
        "ok": True,
        "signals_fetched": len(signals),
        "new_signals": 0,
        "committee_runs": 0,
        "filtered": 0,
        "whale_requests": 0,
        "circuit_breakers": 0,
        "zone_shifts": 0,
    }

    for signal in signals:
        signal_id = str(signal.get("signal_id") or "").strip()
        if not signal_id:
            continue
        if signal_id in seen_set:
            continue

        summary["new_signals"] += 1
        seen_ids.append(signal_id)
        seen_set.add(signal_id)

        # Route signal
        route = classify_signal_source(signal)

        if route == "zone":
            save_zone_shift(signal)
            summary["zone_shifts"] += 1
            continue

        if route == "circuit_breaker":
            save_circuit_breaker(signal)
            msg = format_circuit_breaker_message(signal)
            if not dry_run:
                post_discord_message(discord_token, channel_id, msg)
            else:
                print(f"[DRY RUN] CB: {msg[:100]}...")
            log_committee_event({
                "timestamp": now_utc().isoformat(),
                "signal_id": signal_id,
                "ticker": signal.get("ticker"),
                "route": "circuit_breaker",
                "committee_ran": False,
            })
            summary["circuit_breakers"] += 1
            continue

        if route == "whale":
            msg = format_whale_message(signal)
            if not dry_run:
                post_discord_message(discord_token, channel_id, msg)
            else:
                print(f"[DRY RUN] Whale: {msg[:100]}...")
            log_committee_event({
                "timestamp": now_utc().isoformat(),
                "signal_id": signal_id,
                "ticker": signal.get("ticker"),
                "route": "whale_hunter",
                "status": "AWAITING_UW_CONFIRM",
                "committee_ran": False,
            })
            summary["whale_requests"] += 1
            continue

        # route == "committee" — run Gatekeeper
        passed, reason = gatekeeper(signal, bias_level, defcon, daily)

        if not passed:
            log_committee_event({
                "timestamp": now_utc().isoformat(),
                "signal_id": signal_id,
                "ticker": signal.get("ticker"),
                "direction": signal.get("direction"),
                "strategy": signal.get("strategy"),
                "score": safe_float(signal.get("score")),
                "gatekeeper_result": "FILTERED",
                "gatekeeper_reason": reason,
                "committee_ran": False,
            })
            summary["filtered"] += 1
            continue

        # ── Signal passed Gatekeeper — build context + run committee ──

        context = build_market_context(signal, api_url, api_key)
        committee = run_committee_stub(signal, context)  # 03B replaces this

        # Post to Discord
        msg = format_recommendation_message(signal, context, committee)
        if not dry_run:
            post_discord_message(discord_token, channel_id, msg)
        else:
            print(f"[DRY RUN] Committee:\n{msg}\n")

        # Update daily count + dedup
        daily["count"] = daily.get("count", 0) + 1
        dedup_key = get_dedup_key(signal)
        daily.setdefault("dedup_keys", []).append(dedup_key)

        # Log
        rec_id = f"REC_{now_utc().strftime('%Y%m%d_%H%M%S')}"
        log_committee_event({
            "timestamp": now_utc().isoformat(),
            "signal_id": signal_id,
            "recommendation_id": rec_id,
            "ticker": signal.get("ticker"),
            "direction": signal.get("direction"),
            "strategy": signal.get("strategy"),
            "score": safe_float(signal.get("score")),
            "gatekeeper_result": "PASS",
            "bias_level": bias_level,
            "defcon": defcon,
            "earnings_proximity": context["earnings"],
            "open_positions_in_ticker": context["open_positions"]["ticker_specific"],
            "circuit_breaker_context": context["circuit_breakers"],
            "committee_ran": True,
            "nick_decision": None,
            "outcome": None,
        })

        summary["committee_runs"] += 1

    # Save state
    save_seen_ids(seen_ids)
    save_daily_count(daily)

    return summary


# ── CLI ──────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Pivot II Trading Team Pipeline")
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    result = run(channel_id=args.channel_id, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

**IMPORTANT:** The agent should copy utility functions (`http_json`, `load_openclaw_config`, `load_env_file`, `pick_env`, `load_discord_token`, `now_utc`, `parse_iso_ts`, `ensure_data_dir`, `safe_float`, `compute_rr`, `load_seen_ids`, `save_seen_ids`, `save_zone_shift`, `is_zone_signal`, `ZONE_RE`, `ZONE_FILE`, `OPENCLAW_ENV_FILE`) from the existing `pivot2_trade_poller.py` at `/opt/openclaw/workspace/scripts/pivot2_trade_poller.py`. Do NOT rewrite them. Do NOT import from the old file (it will be disabled). Copy them verbatim.

---

## Cron Job Update

### Disable old trade poller cron

The existing cron job `pivot2-trade-poller` (ID: `d34e2b37-ddb2-46c4-9bed-0e9ed520eb98`) needs its command updated.

**Current command in payload.message:**
```
Use exec once. Run exactly: python3 /opt/openclaw/workspace/scripts/pivot2_trade_poller.py --channel-id 1474135100521451813. Return only command stdout.
```

**New command:**
```
Use exec once. Run exactly: python3 /opt/openclaw/workspace/scripts/pivot2_committee.py --channel-id 1474135100521451813. Return only command stdout.
```

To update, edit `/home/openclaw/.openclaw/cron/jobs.json` and change the `payload.message` field for the job with `"name": "pivot2-trade-poller"`. Then restart OpenClaw:

```bash
# As root:
systemctl restart openclaw
```

**Do NOT delete the old `pivot2_trade_poller.py` file.** It stays as reference. Just swap the cron command.

---

## Testing

### Test 1: Dry run with no signals (weekend)

```bash
ssh root@188.245.250.2
su - openclaw
cd /opt/openclaw/workspace/scripts
python3 pivot2_committee.py --dry-run
```

**Pass criteria:** Exits cleanly with JSON: `{"ok": true, "signals_fetched": 0, "new_signals": 0, ...}`

### Test 2: Position parser

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from pivot2_committee import parse_positions_from_session_state, parse_defcon_from_session_state
positions = parse_positions_from_session_state()
print(f'Positions found: {len(positions)}')
for p in positions:
    print(f'  {p[\"ticker\"]} {p[\"type\"]} {p[\"strikes\"]}')
print(f'DEFCON: {parse_defcon_from_session_state()}')
"
```

**Pass criteria:** Prints positions matching SESSION-STATE.md. DEFCON prints GREEN.

### Test 3: Gatekeeper logic

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from pivot2_committee import gatekeeper, safe_float, now_utc, load_daily_count

# Should pass: high score, neutral bias
sig = {'score': 75, 'direction': 'LONG', 'timestamp': now_utc().isoformat()}
print('High score LONG:', gatekeeper(sig, 'NEUTRAL', 'GREEN', load_daily_count()))

# Should fail: low score
sig = {'score': 40, 'direction': 'LONG', 'timestamp': now_utc().isoformat()}
print('Low score:', gatekeeper(sig, 'NEUTRAL', 'GREEN', load_daily_count()))

# Should fail: counter-bias + not high enough
sig = {'score': 65, 'direction': 'LONG', 'timestamp': now_utc().isoformat()}
print('Counter-bias:', gatekeeper(sig, 'URSA_MINOR', 'GREEN', load_daily_count()))

# Should pass: counter-bias but score >= 80
sig = {'score': 82, 'direction': 'LONG', 'timestamp': now_utc().isoformat()}
print('Counter-bias high:', gatekeeper(sig, 'URSA_MINOR', 'GREEN', load_daily_count()))

# Should fail: DEFCON RED + bullish
sig = {'score': 90, 'direction': 'LONG', 'timestamp': now_utc().isoformat()}
print('DEFCON RED LONG:', gatekeeper(sig, 'NEUTRAL', 'RED', load_daily_count()))

# Should pass: DEFCON RED + bearish
sig = {'score': 65, 'direction': 'SHORT', 'timestamp': now_utc().isoformat()}
print('DEFCON RED SHORT:', gatekeeper(sig, 'NEUTRAL', 'RED', load_daily_count()))
"
```

**Pass criteria:** Output matches expected behavior for each case.

### Test 4: Earnings check

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from pivot2_committee import check_earnings_proximity
print('NVDA:', check_earnings_proximity('NVDA'))
print('SPY:', check_earnings_proximity('SPY'))
"
```

**Pass criteria:** Returns dict with `has_earnings` bool. SPY should return `False` (ETFs don't have earnings).

### Test 5: Live post (after cron swap)

Wait for a signal during market hours, or manually inject a test signal via the Railway API test endpoint. Verify the Discord post appears in #pivot-ii with the correct format.

---

## Definition of Done

- [ ] `/opt/openclaw/workspace/scripts/pivot2_committee.py` exists and runs without errors
- [ ] Utility functions copied verbatim from `pivot2_trade_poller.py`
- [ ] Gatekeeper filters work correctly (all 6 test cases pass)
- [ ] Position parser extracts positions from current SESSION-STATE.md
- [ ] DEFCON parser reads current level correctly
- [ ] Earnings proximity check works for individual tickers
- [ ] Circuit Breaker events saved/loaded/pruned correctly
- [ ] Whale Hunter posts UW screenshot request message
- [ ] Discord recommendation format matches spec (with stub committee text)
- [ ] `committee_log.jsonl` gets written with correct schema
- [ ] `committee_daily_count.json` tracks daily runs and dedup keys
- [ ] Cron job updated to call `pivot2_committee.py` instead of `pivot2_trade_poller.py`
- [ ] `--dry-run` flag works for testing without Discord posts
- [ ] Old `pivot2_trade_poller.py` is NOT deleted

---

## Scope Boundaries

- **Only new file:** `pivot2_committee.py` (plus data files it creates)
- **Only modified file:** `/home/openclaw/.openclaw/cron/jobs.json` (one command swap)
- **No Railway backend changes.** No new API endpoints. No database changes.
- **No LLM calls.** Committee agents are stubs returning placeholder text.
- **No changes to existing scripts.** `pivot2_brief.py`, `pivot2_twitter.py`, `pivot2_prep_ping.py` untouched.
- **No changes to AGENTS.md, IDENTITY.md, SOUL.md.** Those will be updated in Brief 03B.
- **No decision tracking or pushback logic.** That's Brief 03C.

---

## What Comes Next

- **Brief 03B:** Wire real LLM agents (TORO, URSA, Risk, Pivot/Mark Baum) into `run_committee_stub()`. Add catalyst injection to agent prompts. Update AGENTS.md/SOUL.md with Mark Baum persona.
- **Brief 03C:** Decision tracking (take/pass/watching), pattern detection, pushback mechanic. Wire into Discord reply handler.
