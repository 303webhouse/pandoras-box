# Brief: Auto-Prompt Trade Logging in Pivot Chat

**Priority:** HIGH — Without this, every manual trade goes untracked by the outcome system
**Target:** VPS (`/opt/openclaw/workspace/scripts/` — Pivot chat handler / OpenClaw bot)
**Estimated time:** 2-3 hours
**Source:** PLTR trade on March 6 — Nick took the trade, uploaded position screenshot to Discord, but nothing was logged to `decision_log.jsonl`. The outcome matcher will never know this trade happened.

---

## Problem

When Nick takes a trade and tells Pivot about it in Discord (by uploading a position screenshot, saying "I took the trade", "just entered PLTR short", etc.), nothing gets written to the decision tracking system. The data flows like this:

```
Nick uploads position screenshot → Pivot acknowledges it → DEAD END
                                                          ↓ (should go here)
                                                   decision_log.jsonl
                                                          ↓
                                                   outcome_matcher
                                                          ↓
                                                   weekly review
```

## Solution: Two Features

### Feature 1: Auto-Detect Trade Entry and Prompt to Log

When Pivot detects that Nick is indicating he took a trade, Pivot should:

1. **Detect trade entry signals in Nick's messages.** Look for patterns like:
   - Image uploads with captions mentioning positions/trades
   - Messages containing: "took the trade", "just entered", "I'm in", "bought", "sold", "opened", "went long", "went short", "took a position", "filled", "executed"
   - Messages referencing specific tickers + direction ("PLTR short", "long AAPL calls")

2. **Prompt Nick to confirm and log.** Reply with something like:
   ```
   📝 Looks like you entered a trade. Want me to log it for tracking?
   
   Ticker: PLTR
   Direction: SHORT
   Entry: $158.50
   Vehicle: 155p/150p spread Mar 20
   
   React ✅ to confirm, or tell me the correct details.
   ```

3. **On confirmation, write to `decision_log.jsonl`** with this schema:
   ```json
   {
     "timestamp": "2026-03-06T20:15:00+00:00",
     "signal_id": "MANUAL_PLTR_SHORT_20260306_201500",
     "ticker": "PLTR",
     "direction": "SHORT",
     "alert_type": "manual_entry",
     "score": null,
     "committee_action": "REVIEWED",
     "committee_conviction": null,
     "nick_decision": "TAKE",
     "is_override": false,
     "override_reason": null,
     "signal_timestamp": "2026-03-06T20:15:00+00:00",
     "decision_delay_seconds": 0,
     "source": "pivot_chat",
     "entry_price": 158.50,
     "stop_loss": 161.50,
     "vehicle": "155p/150p put spread Mar 20",
     "notes": "Scout Sniper fired IGNORE SHORT. Manual override after committee review + UW flow analysis."
   }
   ```

4. **Also write a corresponding entry to Railway's `signal_outcomes` table** via the Railway API so the outcome matcher can track P&L:
   ```
   POST https://pandoras-box-production.up.railway.app/webhook/outcomes/create
   {
     "signal_id": "MANUAL_PLTR_SHORT_20260306_201500",
     "symbol": "PLTR",
     "signal_type": "MANUAL_SHORT",
     "direction": "SHORT",
     "entry": 158.50,
     "stop": 161.50,
     "t1": 150.00,
     "outcome": "PENDING"
   }
   ```
   Note: This endpoint may not exist yet. If not, it needs to be built on Railway as well. Check if `POST /webhook/outcomes/create` exists.

### Feature 2: `/log-trade` Slash Command (Backup)

If the auto-detection misses a trade, Nick should be able to explicitly log it:

```
/log-trade PLTR SHORT 158.50 stop=161.50 target=150 vehicle="155p/150p Mar 20"
```

This writes the same `decision_log.jsonl` entry and Railway outcome as Feature 1.

## Implementation Notes

### Where to Add This

The trade detection logic should be added to the Pivot chat handler — the component that processes Nick's Discord messages and generates responses. This is likely in the OpenClaw bot code or `committee_interaction_handler.py`.

**Key files to check:**
- `/opt/openclaw/workspace/scripts/committee_interaction_handler.py` — handles Discord button interactions
- OpenClaw's chat handler (wherever Pivot's conversational responses are generated)
- The Discord bot's `on_message` handler

### Detection Approach

Don't try to parse screenshots — just detect the TEXT signals:

```python
TRADE_ENTRY_PATTERNS = [
    r"took the trade",
    r"just entered",
    r"i'm in",
    r"went (long|short)",
    r"(bought|sold|opened)\s+(\w+)",
    r"filled on",
    r"executed",
    r"took a position",
    r"entered (a |the )?(long|short)",
]
```

When a pattern matches, extract ticker and direction from the message context. If ambiguous, ask Nick to clarify.

### Decision Log Writer

Reuse the existing `log_decision()` function from `committee_decisions.py` if possible. It already handles the `decision_log.jsonl` schema and disk-backed storage.

```python
from committee_decisions import log_decision

log_decision(
    signal_id=f"MANUAL_{ticker}_{direction}_{timestamp}",
    ticker=ticker,
    direction=direction,
    alert_type="manual_entry",
    score=None,
    committee_action="REVIEWED" if was_committee_reviewed else "NOT_REVIEWED",
    committee_conviction=None,
    nick_decision="TAKE",
    is_override=False,
    source="pivot_chat",
)
```

## Files Changed

- VPS: Chat handler (OpenClaw bot or interaction handler) — add trade detection + logging
- VPS: Possibly `committee_decisions.py` — add `log_manual_trade()` helper
- Railway: Possibly add `POST /webhook/outcomes/create` endpoint if it doesn't exist

## Deployment

VPS: After updating, restart the relevant service(s).
Railway: If endpoint needed, push to `main` for auto-deploy.
