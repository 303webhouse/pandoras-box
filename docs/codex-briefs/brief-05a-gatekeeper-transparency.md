# Brief 05A: Gatekeeper Transparency + Override Feedback Enrichment

## Context for Sub-Agent

You are adding two UX improvements to the Trading Team pipeline built by Briefs 03A-04. The pipeline is fully operational: signals arrive → gatekeeper filters → committee analyzes → Discord embed with buttons → Nick decides → outcomes tracked → weekly review. Your job is to make two things more visible that are currently hidden:

1. **Why the gatekeeper passed this signal** — Nick sees a score but not what the gatekeeper evaluated
2. **What overrides mean** — The weekly review mentions override rates but doesn't explain *what* the committee missed when Nick was right to override

**Prerequisites:**
- Briefs 03A-04: All built, deployed, and tested on VPS
- `pivot2_committee.py` — Full pipeline orchestrator at `/opt/openclaw/workspace/scripts/`
- `committee_review.py` — Weekly self-review (Saturday 9 AM MT)
- `committee_analytics.py` — Pattern analytics for review consumption
- `committee_decisions.py` — Decision logging + pending store
- `decision_log.jsonl` — Clean (test data purged 2025-02-22)
- `outcome_log.jsonl` — Will populate as real signals flow

## What You're Building

### Part 1: Gatekeeper Pass Report in Discord Embeds

Currently, the embed shows:
```
Signal: cta_scanner (score: 78)
```

After this brief, it shows a new embed field:
```
🔍 Gatekeeper Report
✅ Score: 78 (threshold: 60)
✅ Bias-aligned: BULLISH signal + TORO MINOR bias
✅ DEFCON: GREEN (all signals pass)
⚠️ Earnings: AAPL reports in 5 days
✅ Age: 12s old (max: 30min)
✅ Daily budget: 3/20 runs used
```

This gives Nick instant context on *why* this signal made it through and any yellow flags he should weigh.

### Part 2: Override Feedback Enrichment

Currently, `committee_analytics.py` computes override rates and `committee_review.py` feeds that to the LLM for weekly synthesis. But the analytics are aggregate — "Nick overrode 4 times this week, 3 were correct."

After this brief, the analytics include **per-override detail** so the weekly review LLM can explain *what* the committee keeps getting wrong:

```
Override #1: SPY BEARISH — Committee said PASS (LOW conviction), Nick took it → WIN
  Committee missed: Strong put flow on UW, gap fill setup at 580
Override #2: AAPL BULLISH — Committee said TAKE (HIGH conviction), Nick passed → Committee was right (LOSS avoided? No — AAPL rallied)
```

## What's NOT In Scope (05A)

- ❌ Dynamic gatekeeper threshold adjustments (05B — needs outcome data)
- ❌ Agent trust weighting (05B — needs outcome data)
- ❌ Gatekeeper scoring changes (thresholds stay the same)
- ❌ New signal routing logic
- ❌ Changes to LLM agent prompts (TORO/URSA/Risk/Pivot unchanged)
- ❌ Changes to button handlers or interaction handler

---

## Section 1: Gatekeeper Pass Report

### New Function: `build_gatekeeper_report()`

Add this function to `pivot2_committee.py`, after the existing `gatekeeper()` function:

```python
def build_gatekeeper_report(
    signal: dict,
    bias_level: str,
    defcon: str,
    daily: dict,
    context: dict,
) -> str:
    """
    Build a human-readable breakdown of what the gatekeeper evaluated.
    Called AFTER gatekeeper() returns True (signal passed).
    Returns a multi-line string for the Discord embed field.
    
    Format: emoji + label + value, one per line.
    ✅ = passed cleanly
    ⚠️ = passed but flagged (earnings, high daily usage, counter-bias)
    """
    lines = []
    score = safe_float(signal.get("score"))
    direction = str(signal.get("direction") or "").upper()
    tv_prequalified = is_tv_prequalified(signal)
    bias_upper = bias_level.upper() if bias_level else "NEUTRAL"
    
    # 1. Score
    if tv_prequalified:
        strategy = str(signal.get("strategy") or "").lower()
        lines.append(f"✅ TradingView pre-qualified ({strategy}) — score threshold skipped")
    else:
        threshold = MIN_SCORE_CTA
        # Check if counter-bias threshold applied
        is_bullish = direction in ("LONG", "BULLISH", "BUY")
        is_bearish = direction in ("SHORT", "BEARISH", "SELL")
        counter_bias = False
        if "TORO" in bias_upper and is_bearish:
            threshold = MIN_SCORE_COUNTER_BIAS
            counter_bias = True
        elif "URSA" in bias_upper and is_bullish:
            threshold = MIN_SCORE_COUNTER_BIAS
            counter_bias = True
        
        if counter_bias:
            lines.append(f"⚠️ Score: {int(score)} (counter-bias threshold: {threshold})")
        else:
            lines.append(f"✅ Score: {int(score)} (threshold: {threshold})")
    
    # 2. Bias alignment
    if "TORO" in bias_upper:
        bias_display = "TORO"
    elif "URSA" in bias_upper:
        bias_display = "URSA"
    else:
        bias_display = "NEUTRAL"
    
    direction_display = "BULLISH" if direction in ("LONG", "BULLISH", "BUY") else "BEARISH" if direction in ("SHORT", "BEARISH", "SELL") else direction
    
    is_aligned = (
        ("TORO" in bias_upper and direction_display == "BULLISH") or
        ("URSA" in bias_upper and direction_display == "BEARISH") or
        "NEUTRAL" == bias_display
    )
    
    if is_aligned:
        lines.append(f"✅ Bias-aligned: {direction_display} signal + {bias_level} bias")
    else:
        lines.append(f"⚠️ Counter-bias: {direction_display} signal vs {bias_level} bias")
    
    # 3. DEFCON
    defcon_upper = defcon.upper() if defcon else "GREEN"
    defcon_emoji = {"GREEN": "✅", "YELLOW": "⚠️", "ORANGE": "⚠️", "RED": "🔴"}
    if defcon_upper == "GREEN":
        lines.append(f"{defcon_emoji.get(defcon_upper, '✅')} DEFCON: {defcon_upper}")
    else:
        lines.append(f"{defcon_emoji.get(defcon_upper, '⚠️')} DEFCON: {defcon_upper} (filtering active)")
    
    # 4. Earnings proximity
    earnings = context.get("earnings") or {}
    if earnings.get("has_earnings"):
        days = earnings["days_until"]
        if days <= 3:
            lines.append(f"🔴 Earnings: {signal.get('ticker')} reports in {days} day(s)!")
        else:
            lines.append(f"⚠️ Earnings: {signal.get('ticker')} reports in {days} days")
    else:
        lines.append(f"✅ No earnings within 14 days")
    
    # 5. Signal age
    ts_raw = signal.get("timestamp")
    if ts_raw:
        sig_ts = parse_iso_ts(str(ts_raw))
        if sig_ts:
            age_secs = (now_utc() - sig_ts).total_seconds()
            if age_secs < 60:
                lines.append(f"✅ Age: {int(age_secs)}s old (max: {SIGNAL_MAX_AGE_MIN}min)")
            else:
                lines.append(f"✅ Age: {int(age_secs / 60)}min old (max: {SIGNAL_MAX_AGE_MIN}min)")
    
    # 6. Daily budget
    count = daily.get("count", 0)
    remaining = MAX_DAILY_RUNS - count
    if remaining <= 5:
        lines.append(f"⚠️ Daily budget: {count}/{MAX_DAILY_RUNS} runs used ({remaining} remaining)")
    else:
        lines.append(f"✅ Daily budget: {count}/{MAX_DAILY_RUNS} runs used")
    
    return "\n".join(lines)
```

### Embed Integration

In the `build_committee_embed()` function, add the gatekeeper report as a new field. The function signature needs to accept the report string.

**Find this in `pivot2_committee.py`, in `build_committee_embed()`:**

```python
def build_committee_embed(recommendation: dict, context: dict) -> dict:
```

**Replace with:**

```python
def build_committee_embed(recommendation: dict, context: dict, gatekeeper_report: str = None) -> dict:
```

**Find this block (the fields list, after the Direction field):**

```python
        {
            "name": "Signal",
            "value": truncate(
                f"{signal.get('alert_type', signal.get('signal_type', signal.get('strategy', '?')))} "
                f"(score: {signal.get('score', 'N/A')})",
                256,
            ),
            "inline": True,
        },
```

**Replace with:**

```python
        {
            "name": "Signal",
            "value": truncate(
                f"{signal.get('alert_type', signal.get('signal_type', signal.get('strategy', '?')))} "
                f"(score: {signal.get('score', 'N/A')})",
                256,
            ),
            "inline": True,
        },
    ]
    
    # Gatekeeper report (after the inline row, before trade params)
    if gatekeeper_report:
        fields.append({
            "name": "🔍 Gatekeeper Report",
            "value": truncate(gatekeeper_report, 1024),
            "inline": False,
        })
    
    fields += [
```

**Important:** This splits the `fields` list. The existing code has all fields in one list literal. After this change, `fields` is built in two parts: the first 3 inline fields, then the gatekeeper report, then the remaining fields. Make sure the list continues correctly — the next field should be the Trade Parameters field:

```python
    fields += [
        {
            "name": "📊 Trade Parameters",
            ...
```

### Pipeline Integration

In the `run()` function, build the gatekeeper report after context building and pass it through to the embed.

**Find this block in `run()` (the committee run section):**

```python
        context = build_market_context(signal, api_url, api_key)

        # Run real committee if LLM key available, else fallback
        if llm_api_key:
```

**Replace with:**

```python
        context = build_market_context(signal, api_url, api_key)
        
        # Build gatekeeper transparency report
        gatekeeper_report = build_gatekeeper_report(signal, bias_level, defcon, daily, context)

        # Run real committee if LLM key available, else fallback
        if llm_api_key:
```

**Find all calls to `build_committee_embed(recommendation, context)` in `run()` and add the `gatekeeper_report` parameter:**

```python
            embed = build_committee_embed(recommendation, context, gatekeeper_report)
```

There are **two** calls — one in the `if llm_api_key:` block and one in the `else:` fallback block. Update both.

---

## Section 2: Override Feedback Enrichment

### Changes to `committee_analytics.py`

Currently `compute_weekly_analytics()` returns an `overrides` section with aggregate stats. We need to add per-override detail.

**Add this new function to `committee_analytics.py`:**

```python
def compute_override_details(days: int = 7) -> list[dict]:
    """
    Build per-override narratives for the weekly review LLM.
    
    Reads decision_log.jsonl for overrides, cross-references outcome_log.jsonl
    for results when available. Returns a list of dicts describing each override.
    
    This gives the review LLM specific context about WHAT the committee missed,
    not just aggregate override rates.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Load decisions
    decisions = []
    try:
        with open(DECISION_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if ts >= cutoff and entry.get("is_override"):
                        decisions.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except FileNotFoundError:
        return []
    
    if not decisions:
        return []
    
    # Load outcomes for cross-reference
    outcomes = {}
    try:
        with open(OUTCOME_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    outcomes[entry["signal_id"]] = entry
                except (json.JSONDecodeError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    
    # Build per-override details
    details = []
    for dec in decisions:
        signal_id = dec.get("signal_id", "?")
        ticker = dec.get("ticker", "?")
        direction = dec.get("direction", "?")
        committee_action = dec.get("committee_action", "?")
        committee_conviction = dec.get("committee_conviction", "?")
        nick_decision = dec.get("nick_decision", "?")
        override_reason = dec.get("override_reason")
        
        # Check outcome if available
        outcome = outcomes.get(signal_id, {})
        result = outcome.get("result", "PENDING")
        committee_was_right = outcome.get("committee_was_right")
        nick_was_right = outcome.get("nick_was_right")
        
        detail = {
            "ticker": ticker,
            "direction": direction,
            "committee_said": f"{committee_action} ({committee_conviction} conviction)",
            "nick_did": nick_decision,
            "override_reason": override_reason,
            "outcome": result,
            "committee_was_right": committee_was_right,
            "nick_was_right": nick_was_right,
        }
        
        # Build narrative string for LLM consumption
        if result != "PENDING":
            if nick_was_right and not committee_was_right:
                detail["narrative"] = (
                    f"{ticker} {direction} — Committee said {committee_action} ({committee_conviction}), "
                    f"Nick overrode to {nick_decision} → {result}. "
                    f"Nick was right. What did the committee miss?"
                )
            elif committee_was_right and not nick_was_right:
                detail["narrative"] = (
                    f"{ticker} {direction} — Committee said {committee_action} ({committee_conviction}), "
                    f"Nick overrode to {nick_decision} → {result}. "
                    f"Committee was right. Nick's override was costly."
                )
            else:
                detail["narrative"] = (
                    f"{ticker} {direction} — Committee said {committee_action} ({committee_conviction}), "
                    f"Nick overrode to {nick_decision} → {result}."
                )
        else:
            detail["narrative"] = (
                f"{ticker} {direction} — Committee said {committee_action} ({committee_conviction}), "
                f"Nick overrode to {nick_decision}. Outcome pending."
            )
            if override_reason:
                detail["narrative"] += f" Nick's reason: \"{override_reason}\""
        
        details.append(detail)
    
    return details
```

**Modify `format_analytics_for_llm()` in `committee_analytics.py` to include override details.**

**Find the return statement or the section that formats the override analytics. Add this block after the existing override stats:**

```python
    # Per-override detail (for 05A enrichment)
    override_details = compute_override_details(days=days)
    if override_details:
        sections.append("## OVERRIDE DETAILS (this week)")
        for i, detail in enumerate(override_details, 1):
            sections.append(f"  Override #{i}: {detail['narrative']}")
    else:
        sections.append("## OVERRIDE DETAILS: No overrides this week.")
```

**Note:** The exact insertion point depends on how CC built `format_analytics_for_llm()`. The key contract: the function returns a string with sections separated by newlines. Append the override details section to whatever sections list or string is being built. If the function uses a list called `sections`, append to it. If it builds a string, concatenate.

### New Import in `committee_analytics.py`

Add at the top of the file, with the other path constants:

```python
OUTCOME_LOG = DATA_DIR / "outcome_log.jsonl"
```

If `DATA_DIR` isn't already defined, it should be:
```python
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
```

### No Changes Needed to `committee_review.py`

The weekly review already calls `format_analytics_for_llm()` and feeds it to Sonnet. By enriching the analytics output, the review LLM automatically gets the override details — no prompt changes required.

---

## Section 3: Testing Checklist

### Gatekeeper Report Tests

- [ ] **CTA Scanner signal passes** → Report shows score with threshold 60
- [ ] **TV-prequalified signal (sniper/scout)** → Report says "pre-qualified, threshold skipped"
- [ ] **Counter-bias signal** → Report shows ⚠️ and threshold 80
- [ ] **Bias-aligned signal** → Report shows ✅ with bias level
- [ ] **DEFCON GREEN** → Report shows ✅
- [ ] **DEFCON ORANGE** → Report shows ⚠️ with "filtering active"
- [ ] **Earnings within 3 days** → Report shows 🔴
- [ ] **Earnings within 14 days** → Report shows ⚠️
- [ ] **No earnings** → Report shows ✅
- [ ] **Daily budget > 15/20** → Report shows ⚠️
- [ ] **Signal age shown in seconds** (for fresh signals) or minutes
- [ ] **Embed field renders correctly** in Discord (no truncation issues)
- [ ] **Existing embed fields unchanged** — conviction, direction, trade params, TORO/URSA all still render
- [ ] **Fallback (no LLM key) path** also includes gatekeeper report

### Override Feedback Tests

- [ ] **Override with resolved outcome** → Narrative says who was right
- [ ] **Override with pending outcome** → Narrative says "outcome pending"
- [ ] **Override with reason (from re-evaluate)** → Reason included in narrative
- [ ] **Override without reason (Take vs PASS)** → No reason field, still works
- [ ] **No overrides this week** → Section says "No overrides this week"
- [ ] **Multiple overrides** → Each numbered and distinct
- [ ] **format_analytics_for_llm() output** includes override details section
- [ ] **Weekly review still works** → Override details don't break Sonnet's synthesis

### Integration Smoke Test

1. Trigger a test signal via Railway API (or wait for a real one)
2. Verify embed has new "🔍 Gatekeeper Report" field between Signal and Trade Parameters
3. Verify all existing fields still render correctly
4. Verify report content matches actual gatekeeper evaluation
5. Check `build_committee_embed()` backward compatibility — re-evaluation embeds (from 03C) should work with `gatekeeper_report=None`
6. Manually add test entries to `decision_log.jsonl` with `is_override: true` and various outcomes
7. Run `format_analytics_for_llm(days=7)` and verify override details appear
8. Run a local test of `committee_review.py` logic to verify LLM gets enhanced analytics

### Implementation Order

1. **Add `build_gatekeeper_report()`** to `pivot2_committee.py`
2. **Update `build_committee_embed()` signature** — add `gatekeeper_report` param with default `None`
3. **Insert gatekeeper report field** into embed fields list
4. **Wire `build_gatekeeper_report()` into `run()`** — call after `build_market_context()`, pass to embed builder
5. **Test gatekeeper report** — trigger signals, verify Discord output
6. **Add `compute_override_details()`** to `committee_analytics.py`
7. **Wire into `format_analytics_for_llm()`** — append override details section
8. **Test override feedback** — add test decision entries, run analytics, verify output
9. **Full integration smoke test** (steps 1-8 above)

---

## File Summary

| File | Action | Scope |
|------|--------|-------|
| `/opt/openclaw/workspace/scripts/pivot2_committee.py` | **MODIFY** | Add `build_gatekeeper_report()`, update `build_committee_embed()` signature, wire report into `run()` |
| `/opt/openclaw/workspace/scripts/committee_analytics.py` | **MODIFY** | Add `compute_override_details()`, append override details to `format_analytics_for_llm()` |

**Only two files modified. No new files created. No schema changes. No new dependencies.**

All other files from 03A-04 remain unchanged: committee_prompts.py, committee_parsers.py, committee_context.py, committee_decisions.py, committee_interaction_handler.py, committee_outcomes.py, committee_review.py.

---

## Backward Compatibility Notes

- `build_committee_embed(recommendation, context)` still works — `gatekeeper_report` defaults to `None` and the field is simply omitted
- Re-evaluation embeds (from 03C's `run_committee_with_pushback`) don't pass a gatekeeper report — this is correct, re-evals shouldn't show gatekeeper info since they're re-runs of already-gated signals
- `format_analytics_for_llm()` output is a string consumed by `committee_review.py` — adding more sections doesn't break the consumer since the LLM synthesizes the full text
- `compute_override_details()` gracefully handles missing outcome data (returns "PENDING")

---

*End of Brief 05A. Next: Brief 05B (Adaptive Calibration — dynamic gatekeeper thresholds + agent trust weighting) — requires 2-3 weeks of outcome data before implementation.*
