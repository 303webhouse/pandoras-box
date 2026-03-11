# Brief: Pivot Macro Pre-Scan Before Committee Runs

## Summary

Before the 4-agent committee runs, Pivot should verify the macro backdrop is current. If the macro briefing file is stale (>48h) or missing, Pivot scans available data sources (Polygon news, Twitter signals, bias macro prices) and either confirms existing conditions, writes a fresh briefing, or flags uncertainty and asks Nick before proceeding.

## Problem

`macro_briefing.json` is a persistent file with no auto-refresh. When it goes stale (e.g., crisis data from March 9 still injected into committee runs on March 11), all 4 agents get a distorted macro picture. The old 7-day staleness threshold is far too generous.

## Architecture

### Staleness tiers (in `_get_macro_briefing_context` in `committee_context.py`)

| Age | Behavior |
|-----|----------|
| <24h | Use as-is, no warning |
| 24-48h | Use as-is, prepend warning: `"⚠️ Macro briefing is {age} hours old — may not reflect current conditions"` |
| >48h OR missing | **Trigger Pivot macro pre-scan** before committee runs |

### Pre-scan flow (new function in `committee_context.py`)

New function: `ensure_fresh_macro_briefing(api_url, api_key, anthropic_key, polygon_key) -> dict`

Returns `{"status": "READY", "briefing": ...}` or `{"status": "ASK_NICK", "reason": "..."}`.

**Step 1 — Gather current data:**
- Polygon market news (use existing `fetch_news_context()` from `committee_news.py` — forces fresh fetch by deleting cache file first)
- Twitter sentiment (use existing `_get_twitter_sentiment_context()` from `committee_context.py`)
- Macro prices from bias composite (use existing `_get_macro_prices_context()` — call Railway `/api/bias/composite` to get VIX, DXY, yields, SPY levels, oil, gold)

**Step 2 — Call Pivot (Sonnet) with a macro scan prompt:**

System prompt (new constant `PIVOT_MACRO_SCAN_PROMPT` in `committee_prompts.py`):
```
You are Pivot, the lead synthesizer for a trading committee. Your job right now is to assess the current macro landscape before the committee evaluates a trade signal.

You will receive:
1. The PREVIOUS macro briefing (if one exists) — it may be outdated
2. CURRENT market news headlines from Polygon
3. CURRENT Twitter sentiment from financial accounts
4. CURRENT macro price levels (VIX, DXY, yields, SPY, oil, gold)

Your task: Determine whether the previous macro briefing still accurately describes current conditions, or whether it needs to be updated.

Respond in EXACTLY this JSON format (no markdown, no backticks):
{
  "decision": "CONFIRM" | "UPDATE" | "UNCERTAIN",
  "regime": "short regime label, e.g. RISK-OFF / ROTATION / CRISIS / RECOVERY / NEUTRAL",
  "narrative": "2-4 sentence summary of current macro conditions",
  "key_facts": ["fact 1", "fact 2", ...],
  "sectors_to_watch": {
    "bullish": ["sector (ticker)"],
    "bearish": ["sector (ticker)"],
    "neutral": ["sector (ticker)"]
  },
  "reason": "Why you chose CONFIRM/UPDATE/UNCERTAIN — 1 sentence"
}

Rules:
- CONFIRM = previous briefing is still materially accurate (conditions haven't changed meaningfully)
- UPDATE = conditions have changed enough that the briefing needs rewriting (you provide the new one)
- UNCERTAIN = conflicting signals, major gaps in data, or can't determine current state — ask Nick
- Be concrete: cite specific price levels, percentages, and events
- Do NOT hallucinate data — only reference what's in the provided context
```

User message: formatted block containing old briefing (if any) + the three current data sources.

**Step 3 — Handle Pivot's response:**

- Parse JSON response (with fallback for malformed responses → treat as UNCERTAIN)
- `CONFIRM`: Touch `updated_at` on existing briefing to reset the clock. Log: "Pivot confirmed macro briefing still current"
- `UPDATE`: Write new `macro_briefing.json` with Pivot's response fields + `updated_at` = now + `updated_by` = "pivot_macro_scan". Log: "Pivot updated macro briefing: {regime}"
- `UNCERTAIN`: Return `{"status": "ASK_NICK", "reason": pivot_response["reason"]}`. Do NOT write briefing.

### Integration point (in `committee_railway_bridge.py`)

In `run_committee_on_signal()`, BEFORE calling `build_market_context()`:

```python
# Check if macro briefing needs refresh
from committee_context import ensure_fresh_macro_briefing
macro_result = ensure_fresh_macro_briefing(api_url, api_key, anthropic_key, polygon_key)

if macro_result["status"] == "ASK_NICK":
    # Post to Discord asking Nick to clarify macro conditions
    msg = f"⚠️ **Macro Context Unclear** — Pivot couldn't determine the current macro landscape.\n"
    msg += f"Reason: {macro_result['reason']}\n\n"
    msg += f"Committee run for **{ticker}** is paused. Please update macro context via `/macro-update` or reply with current conditions."
    post_discord_message(discord_token, channel_id, msg)
    log.warning("Macro pre-scan uncertain for %s — asking Nick", ticker)
    return None  # Skip this signal, it stays in COMMITTEE_REVIEW queue for next poll
```

### File paths

| File | Change |
|------|--------|
| `/opt/openclaw/workspace/scripts/committee_context.py` | Modify `_get_macro_briefing_context()` staleness tiers, add `ensure_fresh_macro_briefing()` |
| `/opt/openclaw/workspace/scripts/committee_prompts.py` | Add `PIVOT_MACRO_SCAN_PROMPT` constant |
| `/opt/openclaw/workspace/scripts/committee_railway_bridge.py` | Add pre-scan call before `build_market_context()` |
| `/opt/openclaw/workspace/data/macro_briefing.json` | Written/updated by pre-scan (same schema as today) |

### Key constraints

- Pivot macro scan uses **Sonnet** (same as Pivot in committee). Cost: ~$0.01 per scan.
- Only fires when briefing is >48h old or missing — NOT on every committee run.
- The scan adds ~10-15 seconds to committee startup (one LLM call).
- If Polygon key is missing, skip news and use whatever Twitter + macro prices are available.
- `UNCERTAIN` does NOT fail permanently — signal stays in `COMMITTEE_REVIEW` and gets retried next 3-min poll cycle. If Nick updates macro context in the meantime, next poll succeeds.
- The existing `_get_macro_briefing_context()` function still reads from `macro_briefing.json` — the pre-scan just ensures it's fresh before the committee reads it.

### Environment variable for Polygon key

The Polygon API key is already available on VPS. Check these sources (same `pick_env` pattern used elsewhere):
- OpenClaw config: `POLYGON_API_KEY`
- Env file: `POLYGON_API_KEY`

### Testing

1. Delete `macro_briefing.json` → run bridge → Pivot should scan and write a new one
2. Set `updated_at` to 3 days ago → run bridge → Pivot should scan and either CONFIRM or UPDATE
3. Set `updated_at` to 12 hours ago → run bridge → should use as-is, no scan
4. Set `updated_at` to 30 hours ago → run bridge → should use with warning, no scan

### Definition of done

- [ ] `ensure_fresh_macro_briefing()` function in `committee_context.py`
- [ ] `PIVOT_MACRO_SCAN_PROMPT` in `committee_prompts.py`
- [ ] Bridge calls pre-scan before `build_market_context()`
- [ ] UNCERTAIN posts Discord message and skips signal (stays in queue)
- [ ] Staleness tiers: <24h clean, 24-48h warning, >48h scan
- [ ] Existing committee flow unchanged when briefing is fresh
