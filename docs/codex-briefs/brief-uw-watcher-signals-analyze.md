# Codex Brief: UW Watcher Bot + Signals Channel with Analyze Button

**Date:** March 4, 2026
**Priority:** HIGH
**Scope:** Two new VPS components + one Railway endpoint update + committee portfolio fix
**Estimated effort:** ~2-3 hours agent time
**Deploy target:** VPS (manual) + Railway (auto-deploy on push to main)

---

## Context

The Unusual Whales (UW) free-tier Discord bot is now auto-posting **Ticker Updates** and **Highest Volume Contracts** to `#uw-flow-alerts` in Nick's Discord server. This data includes per-ticker price, volume, put/call ratio, put/call counts, and total premium — exactly what the bias engine and committee context builder need.

Currently this data sits in Discord unread by any system. This brief builds three things:

1. **UW Watcher Bot** — Lightweight Discord bot that parses UW auto-posts into structured data and forwards to the Pandora API
2. **Signals Channel** — All trade signals that enter the trading hub appear in `#📊-signals` with an **Analyze** button that triggers a full committee review on demand
3. **Portfolio Fix** — Remove hardcoded account balances from committee prompts, use live data with staleness warnings

### What This Does NOT Include

- No UW Premium server subscription features (locked behind $104/mo)
- No slash command automation (can't be done — Discord API limitation)
- No image/chart OCR parsing (Highest Volume Contracts image is skipped; text data sufficient)
- No changes to existing bias factor calculation logic

---

## Architecture Overview

```
UW Bot auto-posts to #uw-flow-alerts
  → UW Watcher Bot sees message (discord.py on_message)
  → Parses Ticker Updates text into structured JSON
  → POSTs to Railway API: POST /webhook/uw/ticker-updates
  → Railway stores in Redis + updates bias factors
  → Committee context builder reads UW data on next run

TradingView webhook fires
  → Railway pipeline scores + persists signal
  → Flags for committee if score ≥ 75
  → POSTs signal summary to #📊-signals via Discord REST API
  → Embed includes signal info + "🔬 Analyze" button
  → Nick clicks Analyze
  → Interaction handler triggers committee pipeline for that signal
  → Committee result appears as follow-up embed in #📊-signals
  → Follow-up has Take / Pass / Watching buttons (existing flow)
```

---

## Part 1: UW Watcher Bot

### File: `/opt/openclaw/workspace/scripts/uw_watcher.py`

**What it does:** A persistent Discord bot (discord.py) that watches `#uw-flow-alerts` for messages from the UW Bot, parses the structured text content, and POSTs it to the Pandora API.

**Runtime:** Runs as its own systemd service `uw-watcher.service` on VPS.

**No LLM.** Pure text parsing. $0/run.

### Discord Channel & Bot IDs

The watcher needs to know:
- **Channel to watch:** `#uw-flow-alerts` — get the channel ID from Discord (right-click channel → Copy Channel ID, with Developer Mode enabled in Discord settings)
- **UW Bot user ID:** The UW Bot's Discord user ID — get from right-clicking the UW Bot in the member list → Copy User ID
- **Bot token:** Use the existing Pivot II (OpenClaw) bot token from `/home/openclaw/.openclaw/openclaw.json` — the watcher just needs to READ messages, it doesn't post anything to Discord. Alternatively, use a dedicated bot token if available.

Store these in environment variables or a config dict at the top of the script.

### Parsing Logic: Ticker Updates

The UW Bot posts Ticker Updates as plain text messages (NOT embeds). Each line follows this exact format:

```
TICKER: $PRICE (CHANGE%) | Volume: X | P/C: X.XX | P: X/C: X | Premium: $X
```

Real examples from today:
```
SPY: $681.90 (0.23%) | Volume: 7.36M | P/C: 1.07 | P: 743K/C: 698K | Premium: $320M
NVDA: $181.24 (0.66%) | Volume: 27.44M | P/C: 0.53 | P: 162K/C: 305K | Premium: $115M
TSLA: $398.82 (1.63%) | Volume: 9.92M | P/C: 0.56 | P: 169K/C: 303K | Premium: $242M
PLTR: $151.94 (3.20%) | Volume: 10.8M | P/C: 0.43 | P: 58,910/C: 138K | Premium: $80.38M
```

Some tickers also have an emoji+premium suffix for notable flow:
```
NEM: $120.50 (1.67%) | Volume: 913K | P/C: 0.22 | P: 576/C: 2,628 | Premium: $1.77M | 🐻 Premium: $1.2M (67.8%)
TOST: $29.20 (0.33%) | Volume: 1.05M | P/C: 0.41 | P: 394/C: 972 | Premium: $229K | 🐻 Premium: $143K (62.41%)
```

The 🐻/🐂 emoji suffix indicates bearish/bullish premium dominance with percentage.

**Parser function signature:**

```python
def parse_ticker_update(line: str) -> dict | None:
    """
    Parse a single Ticker Update line into structured data.
    
    Returns dict with keys:
        ticker: str          — "SPY", "NVDA", etc.
        price: float         — 681.90
        change_pct: float    — 0.23
        volume: int          — 7360000 (parsed from "7.36M")
        pc_ratio: float      — 1.07
        put_volume: int      — 743000 (parsed from "743K")
        call_volume: int     — 698000
        total_premium: float — 320000000 (parsed from "$320M")
        flow_sentiment: str | None  — "BEARISH" or "BULLISH" (from emoji suffix)
        flow_premium: float | None  — 1200000 (from emoji suffix)
        flow_pct: float | None      — 67.8 (from emoji suffix)
    
    Returns None if line doesn't match expected format.
    """
```

Volume/premium values use suffixes: `K` = thousands, `M` = millions, `B` = billions. Handle all three. Also handle comma-separated numbers like `58,910`.

### Parsing Logic: Highest Volume Contracts

The Highest Volume Contracts post contains an **image** (the cyan table chart). The watcher bot should **skip image-only messages** — we don't need OCR since Ticker Updates already gives us the core flow data.

However, the Highest Volume Contracts post also includes a text header/embed with the title "Highest Volume Contracts / No Index/ETFs". If the bot detects this, it should log it but not attempt to parse the image.

### Railway Endpoint: `POST /webhook/uw/ticker-updates`

**File to create/modify:** `backend/webhooks/uw_webhook.py` (new file)
**Register in:** `backend/main.py` (add router)

```python
@router.post("/webhook/uw/ticker-updates")
async def receive_uw_ticker_updates(payload: dict):
    """
    Receives parsed UW Ticker Update data from the VPS watcher bot.
    Stores in Redis for bias engine and committee context consumption.
    """
```

**Payload schema (sent by watcher bot):**

```json
{
    "timestamp": "2026-03-04T14:30:00Z",
    "source": "uw_ticker_updates",
    "tickers": [
        {
            "ticker": "SPY",
            "price": 681.90,
            "change_pct": 0.23,
            "volume": 7360000,
            "pc_ratio": 1.07,
            "put_volume": 743000,
            "call_volume": 698000,
            "total_premium": 320000000,
            "flow_sentiment": null,
            "flow_premium": null,
            "flow_pct": null
        }
    ]
}
```

**Redis storage:**

```python
# Per-ticker latest data (committee context builder reads these)
redis.setex(f"uw:ticker:{ticker}", 3600, json.dumps(ticker_data))

# Aggregate market flow snapshot (bias engine reads this)
redis.setex("uw:market_flow:latest", 3600, json.dumps({
    "timestamp": payload["timestamp"],
    "spy_pc_ratio": spy_data["pc_ratio"],  # if SPY in tickers
    "qqq_pc_ratio": qqq_data["pc_ratio"],  # if QQQ in tickers
    "total_premium_all": sum of all ticker premiums,
    "bearish_flow_count": count of tickers with flow_sentiment == "BEARISH",
    "bullish_flow_count": count of tickers with flow_sentiment == "BULLISH",
    "ticker_count": len(tickers)
}))
```

**Auth:** Validate `X-API-Key` header matches `PIVOT_API_KEY` env var (same pattern as other webhook endpoints).

### Railway Endpoint: `GET /webhook/uw/recent/{ticker}`

Committee context builder calls this to get UW flow data for a specific ticker during committee runs.

```python
@router.get("/webhook/uw/recent/{ticker}")
async def get_uw_recent(ticker: str):
    """Returns latest UW Ticker Update data for a specific ticker, or 404."""
    data = redis.get(f"uw:ticker:{ticker.upper()}")
    if not data:
        raise HTTPException(404, "No recent UW data for ticker")
    return json.loads(data)
```

### VPS Watcher Bot: Event Handler

```python
@client.event
async def on_message(message):
    # Only watch the designated UW flow channel
    if message.channel.id != UW_FLOW_CHANNEL_ID:
        return
    
    # Only parse messages from the UW Bot
    if message.author.id != UW_BOT_USER_ID:
        return
    
    # Skip messages that are just images (Highest Volume Contracts chart)
    if not message.content and message.attachments:
        logger.info("Skipping image-only UW message (Highest Volume Contracts chart)")
        return
    
    # Parse Ticker Updates from message content
    lines = message.content.strip().split("\n")
    parsed_tickers = []
    for line in lines:
        result = parse_ticker_update(line.strip())
        if result:
            parsed_tickers.append(result)
    
    if not parsed_tickers:
        return
    
    # POST to Pandora API
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "uw_ticker_updates",
        "tickers": parsed_tickers
    }
    
    try:
        resp = requests.post(
            f"{PANDORA_API_URL}/webhook/uw/ticker-updates",
            json=payload,
            headers={"X-API-Key": PIVOT_API_KEY},
            timeout=10
        )
        logger.info(f"Posted {len(parsed_tickers)} tickers to Pandora API (status={resp.status_code})")
    except Exception as e:
        logger.error(f"Failed to POST UW data: {e}")
```

### Systemd Service: `uw-watcher.service`

```ini
[Unit]
Description=UW Discord Watcher Bot
After=network.target

[Service]
Type=simple
User=openclaw
Group=openclaw
WorkingDirectory=/opt/openclaw/workspace/scripts
ExecStart=/usr/bin/python3 /opt/openclaw/workspace/scripts/uw_watcher.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**Dependencies:** `pip install discord.py requests` (should already be installed on VPS from existing bots).

**Important:** The watcher bot needs the `MESSAGE_CONTENT` privileged intent enabled on whatever Discord bot token it uses. If sharing the OpenClaw bot token, this should already be enabled. If using a new token, enable it in Discord Developer Portal → Bot → Privileged Gateway Intents.

---

## Part 2: Signals Channel with Analyze Button

### Concept

Currently, signals that pass the gatekeeper score threshold (≥75) are automatically sent to the committee pipeline. Nick never sees the signal until after the committee has already run and spent LLM tokens.

**New flow:** ALL signals that enter the trading hub (score ≥ 75, or any threshold Nick sets) are posted to `#📊-signals` as a lightweight info embed with an **Analyze** button. The committee does NOT run automatically. When Nick clicks Analyze, THEN the committee runs and the result appears as a follow-up in the same channel.

This gives Nick:
- Visibility into ALL signals hitting the system (not just committee-reviewed ones)
- Control over which signals get the (cost-bearing) committee analysis
- A single channel to monitor for incoming trade ideas

### Discord Channel

**`#📊-signals`** — This channel already exists in Nick's server (visible in the screenshot as `📊-signals` under `pivot-ii`). Use its channel ID.

### Signal Embed Format

When a signal passes the score threshold, post this embed to `#📊-signals`:

```
━━━━━━━━━━━━━━━━━━━━━
📡 NEW SIGNAL: {TICKER} {DIRECTION}
━━━━━━━━━━━━━━━━━━━━━

Strategy: {strategy_name}
Score: {score}/100 ({score_tier})
Bias: {bias_level}
Timeframe: {timeframe}

Entry: ${entry} | Stop: ${stop} | Target: ${target}
R:R: {risk_reward}:1

Source: {source} | {timestamp}
━━━━━━━━━━━━━━━━━━━━━

[🔬 Analyze]  [❌ Dismiss]
```

- **🔬 Analyze** button — triggers full committee review for this signal
- **❌ Dismiss** button — marks signal as dismissed (no committee run, logged as DISMISSED)

The embed should use color coding: green for LONG/BUY, red for SHORT/SELL.

### Implementation: Signal Posting

**Modify:** `backend/signals/pipeline.py` — the `_maybe_flag_for_committee()` function

Currently this function sets `status=COMMITTEE_REVIEW` in the database. Change it to:

1. Set `status=PENDING_REVIEW` (new status — signal is waiting for Nick's decision)
2. POST a Discord embed to `#📊-signals` with the signal summary + Analyze/Dismiss buttons
3. Store the signal_id ↔ Discord message_id mapping (for button callback resolution)

The Discord POST uses the bot token + REST API (same pattern as `committee_decisions.py` `build_buttons()`).

**New file on VPS:** `/opt/openclaw/workspace/scripts/signal_poster.py`

This script is called by the Railway backend (via a new endpoint) or by the trade poller when a committee-eligible signal is detected. It:
1. Receives signal data
2. Formats the embed
3. Posts to `#📊-signals` with buttons
4. Stores pending signal in `data/pending_signals.json` (disk-backed, same pattern as `pending_recommendations.json`)

**Alternative approach (simpler):** Modify `pivot2_trade_poller.py` to post ALL polled signals to `#📊-signals` with buttons, instead of silently forwarding to the committee. The trade poller already runs every 15 minutes and fetches signals from Railway. Add the embed posting + button building logic there.

### Implementation: Analyze Button Handler

**Modify:** `/opt/openclaw/workspace/scripts/committee_interaction_handler.py`

This bot already handles Take/Pass/Watching button clicks. Add a new handler for the Analyze button:

```python
# In the interaction handler's on_interaction callback:

if custom_id.startswith("analyze_"):
    signal_id = custom_id.replace("analyze_", "")
    
    # 1. Acknowledge the interaction (defer with "thinking" state)
    await interaction.response.defer(ephemeral=False)
    
    # 2. Update the original embed to show "⏳ Committee analyzing..."
    # (disable buttons to prevent double-clicks)
    
    # 3. Fetch full signal data from Railway API
    signal_data = fetch_signal(signal_id)  # GET /api/signals/{signal_id}
    
    # 4. Run the committee pipeline
    # Import and call the existing orchestrator from pivot2_committee.py
    from pivot2_committee import run_committee_pipeline
    result = run_committee_pipeline(signal_data)
    
    # 5. Post committee result as a follow-up embed in the SAME channel
    # This embed has the existing Take/Pass/Watching buttons
    # (reuse existing build_committee_embed() from committee parsers)
    
    # 6. Update the original signal embed to show "✅ Committee reviewed"

elif custom_id.startswith("dismiss_"):
    signal_id = custom_id.replace("dismiss_", "")
    
    # 1. Log dismissal to decision_log.jsonl
    # 2. Update original embed to show "❌ Dismissed"
    # 3. Remove buttons
```

### Button Custom IDs

Follow the existing pattern from committee_decisions.py:

```python
# Signal embed buttons
f"analyze_{signal_id}"   # Triggers committee review
f"dismiss_{signal_id}"   # Dismisses signal

# Committee result buttons (already exist)
f"take_{signal_id}"      # Nick takes the trade
f"pass_{signal_id}"      # Nick passes
f"watching_{signal_id}"  # Nick is watching
f"reeval_{signal_id}"    # Re-evaluate with pushback
```

### Railway Endpoint Update

**Modify:** `backend/signals/pipeline.py`

In `_maybe_flag_for_committee()`, change the behavior:

```python
async def _maybe_flag_for_committee(signal_data: Dict[str, Any]) -> None:
    """
    Flag signal for display in #📊-signals with Analyze button.
    Committee does NOT run automatically — waits for Nick's click.
    """
    # ... existing skip logic (scouts, manual, already has committee data) ...
    
    score = signal_data.get("score_v2") or signal_data.get("score") or 0
    if score < COMMITTEE_SCORE_THRESHOLD:
        return
    
    signal_id = signal_data.get("signal_id")
    if not signal_id:
        return
    
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE signals
                SET status = 'PENDING_REVIEW',
                    committee_requested_at = NOW()
                WHERE signal_id = $1
                AND status = 'ACTIVE'
                """,
                signal_id,
            )
        signal_data["status"] = "PENDING_REVIEW"
        logger.info(f"📡 Posted to signals channel: {signal_data.get('ticker')} (score={score})")
    except Exception as e:
        logger.warning(f"Failed to flag {signal_id}: {e}")
```

The trade poller on VPS (`pivot2_trade_poller.py`) should then pick up `PENDING_REVIEW` signals and post them to `#📊-signals` with buttons.

### Wire UW Data into Committee Context

**Modify:** `/opt/openclaw/workspace/scripts/committee_context.py`

In the context builder (the function that assembles market data for the committee), add a section that fetches UW data:

```python
def build_uw_flow_context(ticker: str) -> str:
    """Fetch UW flow data for a ticker from Pandora API."""
    try:
        resp = requests.get(
            f"{PANDORA_API_URL}/webhook/uw/recent/{ticker}",
            headers={"X-API-Key": PIVOT_API_KEY},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            return (
                f"📊 UW Flow Data ({ticker}):\n"
                f"  P/C Ratio: {data['pc_ratio']}\n"
                f"  Put Volume: {data['put_volume']:,} | Call Volume: {data['call_volume']:,}\n"
                f"  Total Premium: ${data['total_premium']:,.0f}\n"
                f"  Flow Sentiment: {data.get('flow_sentiment', 'N/A')}\n"
            )
        return ""  # No UW data available
    except Exception:
        return ""  # Silently skip if unavailable
```

Add this to the context string that gets passed to all 4 committee agents. Place it after the bias snapshot section and before the open positions section.

Also fetch the aggregate market flow snapshot for SPY/QQQ context:

```python
def build_market_flow_context() -> str:
    """Fetch aggregate UW market flow snapshot."""
    try:
        resp = requests.get(
            f"{PANDORA_API_URL}/webhook/uw/market-flow",
            headers={"X-API-Key": PIVOT_API_KEY},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            return (
                f"📊 UW Market Flow Snapshot:\n"
                f"  SPY P/C: {data.get('spy_pc_ratio', 'N/A')} | "
                f"QQQ P/C: {data.get('qqq_pc_ratio', 'N/A')}\n"
                f"  Bearish Flow Tickers: {data.get('bearish_flow_count', 0)} | "
                f"Bullish: {data.get('bullish_flow_count', 0)}\n"
            )
        return ""
    except Exception:
        return ""
```

**Add endpoint:** `GET /webhook/uw/market-flow` on Railway that returns the `uw:market_flow:latest` Redis key.

---

## Part 3: Fix Stale Portfolio Data in Committee

### Problem

The committee cites stale portfolio data for two reasons:

1. **Hardcoded account limits in prompts.** `committee_prompts.py` line 187 has:
   ```
   R.02: Account limits — 401k: ~$81 max risk, Robinhood: ~$235 max, Prop: ~$620 daily max
   ```
   These are baked into the TECHNICALS system prompt. Even though the orchestrator fetches live balance data, TECHNICALS and PIVOT reference these stale dollar amounts for sizing.

2. **Portfolio positions not synced.** `GET /api/portfolio/positions` returns only 1 position (XLF put spread from March 2). Nick's actual holdings aren't reflected, so URSA can't assess correlation risk and TECHNICALS can't check exposure limits.

### Fix 1: Dynamic Account Limits in Context (not prompts)

**Modify:** `/opt/openclaw/workspace/scripts/committee_prompts.py`

Remove the hardcoded R.02 dollar amounts from the TECHNICALS and PIVOT system prompts. Replace with a generic reference:

```python
# OLD (line 187):
"- R.02: Account limits — 401k: ~$81 max risk, Robinhood: ~$235 max, Prop: ~$620 daily max"

# NEW:
"- R.02: Account limits — see PORTFOLIO CONTEXT section for current balances. Max risk = 5% of account balance per trade (Robinhood), 1% (401k), 5% daily (Prop)."
```

Also update the TECHNICALS example output (line 229) and PIVOT example output (line 316) to remove hardcoded dollar amounts:

```python
# OLD:
"SIZE: HIGH conviction, 2 contracts (~$180 risk, ~3.8% of Robinhood account per R.02)"

# NEW:
"SIZE: HIGH conviction — calculate from PORTFOLIO CONTEXT balance × 5% max risk per R.02"
```

### Fix 2: Enhanced Portfolio Context Block

**Modify:** `/opt/openclaw/workspace/scripts/committee_context.py` — `format_portfolio_context()`

Enhance the portfolio context block to include pre-calculated risk limits so agents don't need to do math:

```python
def format_portfolio_context(portfolio: dict) -> str:
    # ... existing balance/position rendering ...
    
    # Add pre-calculated risk limits
    if account_balance:
        max_risk_rh = round(account_balance * 0.05, 2)  # 5% rule
        lines.append(f"Max risk per trade (5% rule): ${max_risk_rh:,.0f}")
        lines.append(f"Max correlated exposure (2 positions): ${max_risk_rh * 2:,.0f}")
```

### Fix 3: Position & Balance Freshness Warnings

Since there's no automated position sync (IBKR not funded, no RH API), the committee should at least KNOW when data is stale.

**Modify:** `format_portfolio_context()` to add staleness warnings:

```python
# Check position freshness
if positions:
    from datetime import datetime, timezone, timedelta
    newest = max(
        datetime.fromisoformat(p["last_updated"].replace("Z", "+00:00"))
        for p in positions if p.get("last_updated")
    )
    age_hours = (datetime.now(timezone.utc) - newest).total_seconds() / 3600
    if age_hours > 4:
        lines.append(f"⚠️ POSITION DATA IS {age_hours:.0f} HOURS OLD — may not reflect current holdings")
else:
    lines.append("⚠️ NO POSITIONS RECORDED — Nick may have open trades not reflected here. Size conservatively.")

# Check balance freshness
if rh:
    updated_at = rh.get("updated_at", "")
    if updated_at:
        from datetime import datetime, timezone
        bal_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        bal_age_hours = (datetime.now(timezone.utc) - bal_time).total_seconds() / 3600
        if bal_age_hours > 24:
            lines.append(f"⚠️ BALANCE LAST UPDATED {bal_age_hours:.0f}h AGO — may be stale")
```

---

## File Summary

### New Files

| File | Location | Purpose |
|------|----------|---------|
| `uw_watcher.py` | VPS `/opt/openclaw/workspace/scripts/` | UW Discord watcher bot |
| `signal_poster.py` | VPS `/opt/openclaw/workspace/scripts/` | Posts signals to #📊-signals with buttons |
| `uw_webhook.py` | Railway `backend/webhooks/` | Endpoints for UW data ingestion + retrieval |
| `uw-watcher.service` | VPS `/etc/systemd/system/` | Systemd service for watcher bot |

### Modified Files

| File | Location | Change |
|------|----------|--------|
| `pipeline.py` | Railway `backend/signals/` | Change `_maybe_flag_for_committee()` to set `PENDING_REVIEW` status |
| `main.py` | Railway `backend/` | Register `uw_webhook` router |
| `pivot2_trade_poller.py` | VPS scripts | Post signals to #📊-signals with Analyze/Dismiss buttons |
| `committee_interaction_handler.py` | VPS scripts | Handle Analyze/Dismiss button clicks |
| `committee_context.py` | VPS scripts | Add UW flow data to committee context + pre-calculated risk limits + staleness warnings |
| `committee_prompts.py` | VPS scripts | Remove hardcoded R.02 dollar amounts, reference PORTFOLIO CONTEXT |

### No Changes To

- `committee_parsers.py` — LLM call/parse logic unchanged
- `committee_decisions.py` — Decision logging unchanged
- `committee_outcomes.py` — Outcome tracking unchanged
- `committee_review.py` — Weekly review unchanged
- `pivot2_brief.py` — Morning/EOD briefs unchanged (could add UW context later)

---

## Environment Variables

The watcher bot needs these (same as other VPS scripts):

```bash
PANDORA_API_URL=https://pandoras-box-production.up.railway.app
PIVOT_API_KEY=<existing key from /opt/openclaw scripts>
DISCORD_BOT_TOKEN=<existing OpenClaw bot token or dedicated token>
UW_FLOW_CHANNEL_ID=<channel ID for #uw-flow-alerts>
UW_BOT_USER_ID=<UW Bot's Discord user ID>
SIGNALS_CHANNEL_ID=<channel ID for #📊-signals>
```

---

## Verification Steps

### Part 1: UW Watcher

1. Start `uw-watcher.service` on VPS
2. Check logs: `journalctl -u uw-watcher -f`
3. Wait for next UW Ticker Updates post during market hours
4. Verify watcher parses the text and POSTs to Railway
5. Verify Redis keys: `redis-cli GET uw:ticker:SPY` should return JSON
6. Verify API: `curl .../webhook/uw/recent/SPY` should return data
7. Verify `uw:market_flow:latest` key populated

### Part 2: Signals Channel

1. Trigger a test signal (use TradingView alert or manual POST to `/webhook/tradingview`)
2. Verify signal appears in `#📊-signals` with Analyze and Dismiss buttons
3. Click **Analyze** — verify committee runs and result appears as follow-up
4. Verify follow-up has Take/Pass/Watching buttons
5. Click **Take** — verify decision logged to `decision_log.jsonl`
6. Click **Dismiss** on a different signal — verify it's logged and buttons removed
7. Verify committee context includes UW flow data (check `committee_log.jsonl` for UW section)

### Part 3: Portfolio Fix

1. Verify `committee_prompts.py` no longer contains hardcoded dollar amounts like `~$235 max` or `~$81 max`
2. Trigger a committee run and check the committee_log.jsonl — verify PORTFOLIO CONTEXT section shows live balance + calculated risk limits
3. Verify staleness warning appears when positions are >4 hours old
4. Verify "NO POSITIONS RECORDED" warning when positions list is empty

### Edge Cases

- UW Bot posts mid-sentence or multi-message: watcher should handle partial lines gracefully (skip unparseable lines)
- Signal arrives outside market hours: still post to #📊-signals, but note market is closed
- Analyze clicked twice: first click disables button, second click should be no-op
- Railway down when watcher POSTs: log error, retry on next message (don't crash)
- No UW data for a ticker: committee context builder returns empty string, agents proceed without it

---

## Definition of Done

- [ ] UW Watcher Bot running as systemd service, parsing Ticker Updates, POSTing to Railway
- [ ] Railway stores UW data in Redis with 1-hour TTL
- [ ] `GET /webhook/uw/recent/{ticker}` returns latest UW data
- [ ] ALL committee-eligible signals appear in `#📊-signals` with Analyze + Dismiss buttons
- [ ] Clicking Analyze triggers committee review; result appears in same channel
- [ ] Committee result has Take/Pass/Watching buttons (existing flow)
- [ ] Clicking Dismiss logs and removes buttons
- [ ] Committee context includes UW flow data when available
- [ ] Committee prompts no longer contain hardcoded account dollar amounts
- [ ] Portfolio context block includes pre-calculated risk limits from live balances
- [ ] Stale/missing position data triggers warning in committee context
- [ ] No regressions to existing committee, decision tracking, or outcome matching

---

## Channel IDs Needed From Nick

Before Claude Code can build this, Nick needs to provide:

1. **`#uw-flow-alerts` channel ID** — right-click → Copy Channel ID (enable Developer Mode in Discord Settings → Advanced first)
2. **`#📊-signals` channel ID** — same
3. **UW Bot user ID** — right-click UW Bot in member list → Copy User ID
4. **Confirm bot token** — Is Claude Code using the OpenClaw bot token, or does Nick want a separate token for the watcher?
