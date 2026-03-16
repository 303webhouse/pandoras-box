# Brief 4E — Committee Pipeline: Runaway Loop Fix + Streamlining

**Target:** Claude Code (VSCode) for Railway changes + manual VPS deploy for committee scripts
**Estimated scope:** Medium — VPS script changes + Railway endpoint tweak
**Priority:** HIGH — the bridge is currently burning API credits on stuck signals

---

## Background

The committee pipeline runs on VPS via cron (`committee_railway_bridge.py`) every 3 minutes during market hours. It polls Railway for signals in `COMMITTEE_REVIEW` status, runs 4 LLM agents (TORO, URSA, TECHNICALS, PIVOT) via Anthropic API, posts results to Discord, then POSTs results back to Railway.

Three compounding bugs caused a runaway loop that made **2,376 LLM API calls** and **584 duplicate Discord embeds** over 5 days:

1. **Infinite retry on failed result POST** — When `post_results()` back to Railway fails, the signal stays in `COMMITTEE_REVIEW`. The bridge picks it up again next poll (3 min) and runs the full 4-agent committee again. Three signals (XLU, ECL, D) were stuck since March 11.

2. **Daily cap only counts successes** — `daily["count"]` only increments after a successful `post_results()`. Failed runs don't count, so the 10/day cap never triggered even with hundreds of runs.

3. **No circuit breaker on API errors** — When Anthropic returns "credit balance too low," the bridge still calls all 4 agents with 2 retries each = 8 failed API calls per signal per poll.

The stuck signals have been manually dismissed. This brief fixes the pipeline to prevent recurrence and streamlines the LLM calls.

## Fix 1: Bridge Retry Logic (VPS)

**File:** `/opt/openclaw/workspace/scripts/committee_railway_bridge.py`

### 1A: Count ALL runs toward daily cap, not just successes

Currently `daily["count"]` increments only after successful `post_results()`. Move the increment to BEFORE `run_committee_on_signal()` so every attempt counts.

**Find** in `main()` (around the per-signal loop):
```python
        resp = post_results(result)
        if resp:
            log.info("✅ %s: %s (%s) — %.1fs",
                     ticker, result["action"], result["conviction"],
                     result["run_duration_ms"] / 1000)
            daily["count"] += 1
            daily["signal_ids"].append(signal_id)
            save_daily_count(daily)
```

**Replace** with:
```python
        # Count the attempt BEFORE running (prevents uncapped retries)
        daily["count"] += 1
        daily["signal_ids"].append(signal_id)
        save_daily_count(daily)

        resp = post_results(result)
        if resp:
            log.info("✅ %s: %s (%s) — %.1fs",
                     ticker, result["action"], result["conviction"],
                     result["run_duration_ms"] / 1000)
```

### 1B: Add per-signal retry limit (max 3 attempts ever)

Track signal IDs that have been attempted. If a signal has been tried 3+ times across any number of days, skip it and log a warning.

**Add** a new tracking file: `/opt/openclaw/workspace/data/bridge_signal_attempts.json`

Structure:
```json
{
  "signal_id_1": {"attempts": 2, "last_attempt": "2026-03-14T...", "last_error": "post_results failed"},
  "signal_id_2": {"attempts": 3, "last_attempt": "2026-03-14T...", "last_error": "credit balance too low"}
}
```

In the main loop, before running committee:
```python
MAX_SIGNAL_ATTEMPTS = 3
attempts = load_signal_attempts()
signal_attempts = attempts.get(signal_id, {}).get("attempts", 0)
if signal_attempts >= MAX_SIGNAL_ATTEMPTS:
    log.warning("Skipping %s — already attempted %d times (max %d). Last error: %s",
                ticker, signal_attempts, MAX_SIGNAL_ATTEMPTS,
                attempts.get(signal_id, {}).get("last_error", "unknown"))
    continue
```

After each attempt (success or failure), increment the counter:
```python
attempts[signal_id] = {
    "attempts": signal_attempts + 1,
    "last_attempt": datetime.utcnow().isoformat(),
    "last_error": None if resp else "post_results failed"
}
save_signal_attempts(attempts)
```

Clean up entries older than 7 days on each run.

### 1C: Circuit breaker on credit/auth errors

If ANY agent call returns a 400/401/403 with "credit balance" or "authentication" in the error, abort the entire bridge run immediately — don't try remaining agents or remaining signals.

**In `run_committee_on_signal()`**, the `call_agent()` function returns `None` on failure. But we need to distinguish "timeout" from "credit exhausted." 

**Modify `call_agent()` in `committee_parsers.py`** to raise a specific exception on credit/auth errors:

```python
class CreditExhaustedError(Exception):
    """Raised when Anthropic API returns credit balance too low."""
    pass

def call_agent(...):
    # ... existing code ...
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")[:500]
        except Exception:
            pass
        
        # CIRCUIT BREAKER: Don't retry credit/auth errors
        if e.code in (400, 401, 403) and ("credit balance" in err_body.lower() or "authentication" in err_body.lower()):
            log.error("[%s] CREDIT/AUTH ERROR — aborting: %s", agent_name, err_body[:200])
            raise CreditExhaustedError(err_body[:200])
        
        log.warning("[%s] API error %d: %s (attempt %d/%d)", ...)
```

Then in `run_committee_on_signal()`, catch `CreditExhaustedError` and return a sentinel:
```python
try:
    toro_raw = call_agent(...)
except CreditExhaustedError:
    log.error("Credit exhausted during TORO — aborting entire committee run")
    return None  # Caller should stop processing all signals
```

And in `main()`, if `run_committee_on_signal()` returns `None` AND the signal_attempts log shows a credit error, break the entire loop.

## Fix 2: Consolidate 4 LLM Calls → 2 (VPS)

**Files:**
- `/opt/openclaw/workspace/scripts/pivot2_committee.py` — `run_committee()` function
- `/opt/openclaw/workspace/scripts/committee_prompts.py` — new combined prompt
- `/opt/openclaw/workspace/scripts/committee_parsers.py` — new combined parser

### Current: 4 serial LLM calls
```
TORO    → call_agent(TORO_SYSTEM_PROMPT, context, max_tokens=500)     # ~3-5s
URSA    → call_agent(URSA_SYSTEM_PROMPT, context, max_tokens=500)     # ~3-5s  
TECH    → call_agent(TECHNICALS_SYSTEM_PROMPT, context, max_tokens=750)  # ~3-5s
PIVOT   → call_agent(PIVOT_SYSTEM_PROMPT, all_above + context, max_tokens=1500)  # ~5-8s
```
Total: ~4 API calls, ~15-23 seconds, ~$0.08-0.15 per signal

### New: 2 serial LLM calls
```
ANALYSIS → call_agent(COMBINED_ANALYST_PROMPT, context, max_tokens=1500)  # ~5-8s
PIVOT    → call_agent(PIVOT_SYSTEM_PROMPT, analysis + context, max_tokens=1500)  # ~5-8s
```
Total: ~2 API calls, ~10-16 seconds, ~$0.04-0.08 per signal (50% cost reduction)

### New Combined Analyst Prompt

Create `COMBINED_ANALYST_SYSTEM_PROMPT` in `committee_prompts.py` that asks the model to role-play all three analysts in structured output:

```
You are a trading committee with three analysts evaluating a trade setup.
Provide analysis from each perspective in the exact format below.

## TORO (Bull Analyst)
Find the strongest reasons to TAKE this trade.
Analysis: <1-3 sentences>
Conviction: HIGH|MEDIUM|LOW

## URSA (Bear Analyst)  
Find the strongest reasons to PASS on this trade.
Analysis: <1-3 sentences>
Conviction: HIGH|MEDIUM|LOW

## TECHNICALS (Risk/Structure Analyst)
Evaluate entry, stop, target levels and position sizing.
Analysis: <1-3 sentences with specific levels>
Conviction: HIGH|MEDIUM|LOW
```

### New Combined Parser

Add `parse_combined_analyst_response(raw: str) -> dict` to `committee_parsers.py` that splits the response into three analyst dicts by parsing the `## TORO`, `## URSA`, `## TECHNICALS` sections.

### Updated run_committee()

```python
def run_committee(signal, context, api_key, technical_data=None):
    base_context = format_signal_context(signal, context)
    # ... existing context enrichment (economic cal, UW flow, portfolio, P&L) ...
    
    # ── CALL 1: Combined Analyst (TORO + URSA + TECHNICALS) ──
    log.info("Calling combined analyst (TORO/URSA/TECHNICALS)...")
    combined_raw = call_agent(
        system_prompt=COMBINED_ANALYST_SYSTEM_PROMPT,
        user_message=base_context,
        api_key=api_key,
        max_tokens=1500,
        temperature=0.3,
        agent_name="ANALYSTS",
        model=COMMITTEE_MODEL,
    )
    if combined_raw:
        analysts = parse_combined_analyst_response(combined_raw)
        toro_response = analysts["toro"]
        ursa_response = analysts["ursa"]
        technicals_response = analysts["technicals"]
    else:
        # Fallback defaults (same as current)
        ...
    
    # ── CALL 2: PIVOT Synthesis (same as current) ──
    log.info("Calling PIVOT agent...")
    pivot_context = (
        f"{base_context}\n\n"
        f"## TORO ANALYST REPORT\n..."
        f"## URSA ANALYST REPORT\n..."
        f"## TECHNICALS ANALYST REPORT\n..."
        f"{bias_challenge}{pivot_feedback}"
    )
    pivot_raw = call_agent(
        system_prompt=PIVOT_SYSTEM_PROMPT,
        user_message=pivot_context,
        api_key=api_key,
        max_tokens=1500,
        temperature=0.6,
        agent_name="PIVOT",
        model=COMMITTEE_MODEL,
    )
    # ... same pivot parsing as current ...
```

## Fix 3: Update Model (VPS)

**File:** `/opt/openclaw/workspace/scripts/pivot2_committee.py`

**Find:**
```python
COMMITTEE_MODEL = "claude-sonnet-4-5-20250929"
```

**Replace:**
```python
COMMITTEE_MODEL = "claude-sonnet-4-6"
```

Also update `DEFAULT_MODEL` in `committee_parsers.py` if it references the old model.

## Fix 4: Cache Market Context (VPS)

**File:** `/opt/openclaw/workspace/scripts/committee_railway_bridge.py`

Currently `build_market_context()` is called fresh for every signal. When Nick triggers 3 analyses in the same session, it makes 3× redundant API calls for bias, news, sector data, portfolio, etc.

**Add** a simple in-memory cache in the bridge's `main()` function:

```python
_context_cache = {"data": None, "timestamp": 0}
CONTEXT_CACHE_TTL = 900  # 15 minutes

def get_cached_context(signal, api_url, api_key):
    now = time.time()
    if _context_cache["data"] and (now - _context_cache["timestamp"]) < CONTEXT_CACHE_TTL:
        log.info("Using cached market context (%.0fs old)", now - _context_cache["timestamp"])
        # Update signal-specific fields (ticker, signal data) while keeping market context
        ctx = _context_cache["data"].copy()
        ctx["signal"] = signal  # Signal-specific
        return ctx
    
    ctx = build_market_context(signal, api_url, api_key)
    _context_cache["data"] = ctx
    _context_cache["timestamp"] = now
    return ctx
```

The macro briefing, bias data, portfolio context, and news are all market-wide and don't change between signals in the same session.

## Deployment

All changes are VPS-only (no Railway changes needed):

```bash
ssh root@188.245.250.2
# Edit the 3 files:
#   /opt/openclaw/workspace/scripts/committee_railway_bridge.py
#   /opt/openclaw/workspace/scripts/committee_parsers.py  
#   /opt/openclaw/workspace/scripts/pivot2_committee.py
#   /opt/openclaw/workspace/scripts/committee_prompts.py
# Then restart:
systemctl restart openclaw
journalctl -u openclaw -f
```

No Railway auto-deploy needed — committee scripts live on VPS only.

## Verification

1. **Runaway loop fixed:** Run 1 manual committee analysis. Check `/var/log/committee_bridge.log` — should see exactly 2 LLM calls (ANALYSTS + PIVOT), not 4. Signal should clear from queue after 1 successful run.
2. **Daily cap works:** `cat /opt/openclaw/workspace/data/bridge_daily_count.json` should show count incrementing on every attempt, not just successes.
3. **Credit error stops immediately:** Temporarily set a bad API key, trigger an analysis. Bridge log should show 1 failed call then abort — not 8+ failed calls.
4. **Context caching:** Trigger 2 analyses within 5 minutes. Second one should log "Using cached market context" instead of re-fetching everything.
5. **Model updated:** Bridge log should show `claude-sonnet-4-6` not `claude-sonnet-4-5`.

## Cost Impact

| Metric | Before (broken) | Before (working) | After |
|--------|-----------------|-------------------|-------|
| LLM calls per signal | 4 + 8 retries on failure | 4 | 2 |
| Cost per signal | ~$0.08-0.15 | ~$0.08-0.15 | ~$0.04-0.08 |
| Stuck signal cost | Unlimited (1,017 runs × 4 agents) | N/A | Max 3 attempts then skip |
| Context fetches per batch | 1 per signal | 1 per signal | 1 per batch (cached 15 min) |
