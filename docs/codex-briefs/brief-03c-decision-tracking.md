# Brief 03C: Decision Tracking + Pushback

## Context for Sub-Agent

You are wiring **decision tracking and re-evaluation** into the committee pipeline built by Briefs 03A (gatekeeper + pipeline) and 03B (LLM agents). The pipeline already posts committee recommendations to Discord with placeholder buttons. Your job is to make those buttons functional and build the pushback system.

**Prerequisites:**
- Brief 03A: Gatekeeper, context builder, orchestrator, JSONL logging — all working
- Brief 03B: Four LLM agents (TORO, URSA, Risk, Pivot) producing real analysis — all working
- Discord embeds posting with `CommitteeView` buttons rendered but not wired

## What You're Building

```
Discord Embed (from 03B)
  │
  ├── ✅ Take → Log decision, confirm to Nick, update JSONL
  ├── ❌ Pass → Log decision, confirm to Nick, update JSONL
  ├── 👀 Watching → Log decision, set 2-hour reminder, update JSONL
  └── 🔄 Re-evaluate → Prompt Nick for reason, re-run committee with his objection injected
```

Three systems:

1. **Button Handlers** — Wire Take/Pass/Watching/Re-evaluate to functional callbacks
2. **Decision Log** — Track what Nick actually does vs what the committee recommended
3. **Pushback (Re-evaluate)** — Nick disagrees → tells system why → committee re-runs with his objection as additional context

## What's NOT In Scope (03C)

- ❌ Outcome tracking — whether the trade actually made money (Brief 04)
- ❌ Pattern detection analytics — "Nick overrides PASS 60% of the time" (Brief 04)
- ❌ Prompt tuning based on decision data (future)
- ❌ Position sync with broker (future)
- ❌ Gatekeeper changes (03A is locked)
- ❌ Agent prompt changes (03B is locked)

---

## Section 1: Button Handler Wiring

Replace the placeholder `CommitteeView` from 03B with functional handlers. Each button callback must:
1. Identify the signal from the button's `custom_id`
2. Log the decision
3. Send ephemeral confirmation to Nick
4. Update the embed to show the decision was recorded

### Updated CommitteeView Class

```python
import discord
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_DIR = Path("/opt/openclaw/workspace/data")
DECISION_LOG = DATA_DIR / "decision_log.jsonl"
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"

# In-memory store for pending recommendations (signal_id → recommendation dict)
# Populated when committee posts to Discord, consumed by button handlers
pending_recommendations = {}

# In-memory store for watching reminders (signal_id → asyncio.Task)
watching_reminders = {}


class CommitteeView(discord.ui.View):
    """
    Interactive buttons on committee recommendation embeds.
    
    Each button logs Nick's decision and provides confirmation.
    The Re-evaluate button triggers a pushback flow.
    
    Timeout: None (buttons persist until bot restarts).
    On restart, old buttons become non-functional — this is acceptable
    since recommendations older than a session are stale anyway.
    """
    
    def __init__(self, signal_id: str, recommendation: dict):
        super().__init__(timeout=None)
        self.signal_id = signal_id
        self.recommendation = recommendation
        self.decided = False  # Prevent double-clicks
        
        # Store recommendation for re-evaluation access
        pending_recommendations[signal_id] = recommendation
    
    async def _handle_decision(
        self, 
        interaction: discord.Interaction, 
        decision: str,
        button: discord.ui.Button
    ):
        """Common handler for Take/Pass/Watching decisions."""
        if self.decided:
            await interaction.response.send_message(
                "You already made a decision on this one.", 
                ephemeral=True
            )
            return
        
        self.decided = True
        pivot_action = self.recommendation["agents"]["pivot"]["action"]
        is_override = (decision != pivot_action)
        
        # Log the decision
        log_decision(
            signal_id=self.signal_id,
            nick_decision=decision,
            committee_action=pivot_action,
            is_override=is_override,
            override_reason=None,  # Simple decisions don't require a reason
            recommendation=self.recommendation
        )
        
        # Update committee_log.jsonl with nick_decision
        update_committee_log(self.signal_id, decision)
        
        # Disable all buttons visually
        for child in self.children:
            child.disabled = True
        
        # Highlight the chosen button
        button.style = discord.ButtonStyle.primary
        
        # Build confirmation message
        signal = self.recommendation["signal"]
        ticker = signal["ticker"]
        
        if is_override:
            override_note = (
                f"\n⚠️ **Override detected** — Committee said **{pivot_action}**, "
                f"you chose **{decision}**. Logged for pattern tracking."
            )
        else:
            override_note = ""
        
        confirm_msg = f"✅ **{decision}** recorded for {ticker}.{override_note}"
        
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(confirm_msg, ephemeral=True)
        
        # If WATCHING, set a reminder
        if decision == "WATCHING":
            await self._set_watching_reminder(interaction, ticker)
        
        # Clean up pending store
        pending_recommendations.pop(self.signal_id, None)
    
    async def _set_watching_reminder(
        self, 
        interaction: discord.Interaction, 
        ticker: str
    ):
        """Send a reminder in 2 hours to revisit a WATCHING decision."""
        async def reminder_task():
            await asyncio.sleep(7200)  # 2 hours
            try:
                await interaction.channel.send(
                    f"⏰ **Reminder:** You're watching **{ticker}** from 2 hours ago. "
                    f"Signal ID: `{self.signal_id}`. Still watching, or ready to decide?"
                )
            except Exception as e:
                logging.warning(f"Failed to send watching reminder for {self.signal_id}: {e}")
            finally:
                watching_reminders.pop(self.signal_id, None)
        
        task = asyncio.create_task(reminder_task())
        watching_reminders[self.signal_id] = task
    
    @discord.ui.button(label="✅ Take", style=discord.ButtonStyle.green, custom_id="take")
    async def take_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_decision(interaction, "TAKE", button)
    
    @discord.ui.button(label="❌ Pass", style=discord.ButtonStyle.red, custom_id="pass")
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_decision(interaction, "PASS", button)
    
    @discord.ui.button(label="👀 Watching", style=discord.ButtonStyle.grey, custom_id="watching")
    async def watching_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_decision(interaction, "WATCHING", button)
    
    @discord.ui.button(label="🔄 Re-evaluate", style=discord.ButtonStyle.blurple, custom_id="reeval")
    async def reeval_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Opens pushback modal — Nick explains why he disagrees."""
        if self.decided:
            await interaction.response.send_message(
                "You already made a decision on this one. "
                "Start a new conversation with Pivot if you want to revisit.",
                ephemeral=True
            )
            return
        
        modal = PushbackModal(
            signal_id=self.signal_id,
            recommendation=self.recommendation,
            parent_view=self
        )
        await interaction.response.send_modal(modal)
```

### Integration Point

In `pivot2_committee.py`'s `post_recommendation()` function, replace the old button setup:

**Find this block (from 03A/03B):**
```python
    view = CommitteeView(signal_id=signal["id"])
```

**Replace with:**
```python
    view = CommitteeView(
        signal_id=signal["id"],
        recommendation=recommendation
    )
```

If 03B used positional args, adjust to match. The key change: `recommendation` dict is now passed to the view so button handlers have access to committee data.

---

## Section 2: Pushback Modal + Re-evaluation

When Nick clicks "Re-evaluate", a Discord modal pops up asking him to explain his disagreement. His objection is then injected into a fresh committee run as additional context.

### PushbackModal Class

```python
class PushbackModal(discord.ui.Modal, title="Challenge the Committee"):
    """
    Modal that appears when Nick clicks Re-evaluate.
    Collects his objection and triggers a committee re-run.
    """
    
    objection = discord.ui.TextInput(
        label="What's the committee missing?",
        placeholder="e.g., 'You're ignoring the gap fill at 580' or 'IV is way too high for this play'",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )
    
    def __init__(self, signal_id: str, recommendation: dict, parent_view: CommitteeView):
        super().__init__()
        self.signal_id = signal_id
        self.recommendation = recommendation
        self.parent_view = parent_view
    
    async def on_submit(self, interaction: discord.Interaction):
        """Re-run committee with Nick's objection injected."""
        nick_objection = self.objection.value
        signal = self.recommendation["signal"]
        ticker = signal["ticker"]
        
        # Acknowledge immediately — re-evaluation takes 30-60 seconds
        await interaction.response.send_message(
            f"🔄 Re-evaluating **{ticker}** with your pushback. "
            f"Give me 30-60 seconds...",
            ephemeral=True
        )
        
        # Log the pushback
        log_decision(
            signal_id=self.signal_id,
            nick_decision="RE-EVALUATE",
            committee_action=self.recommendation["agents"]["pivot"]["action"],
            is_override=True,
            override_reason=nick_objection,
            recommendation=self.recommendation
        )
        
        # Mark parent view as decided to prevent further button clicks
        self.parent_view.decided = True
        for child in self.parent_view.children:
            child.disabled = True
        
        # Edit the original message to show re-evaluation in progress
        try:
            await interaction.message.edit(view=self.parent_view)
        except Exception:
            pass  # Non-critical — button state is secondary
        
        # Run re-evaluation
        try:
            new_recommendation = await run_committee_with_pushback(
                signal=signal,
                original_recommendation=self.recommendation,
                nick_objection=nick_objection
            )
            
            # Post the new recommendation as a reply to the original
            await post_recommendation(
                new_recommendation,
                channel=interaction.channel,
                reply_context=f"🔄 **Re-evaluation** (Nick's pushback: \"{nick_objection[:100]}\")"
            )
            
        except Exception as e:
            logging.error(f"Re-evaluation failed for {self.signal_id}: {e}")
            await interaction.channel.send(
                f"⚠️ Re-evaluation failed for **{ticker}**. Error: {str(e)[:200]}. "
                f"Original recommendation still stands."
            )
```

### Re-evaluation Committee Run

```python
async def run_committee_with_pushback(
    signal: dict,
    original_recommendation: dict,
    nick_objection: str
) -> dict:
    """
    Re-runs the committee with Nick's objection injected into each agent's context.
    
    The objection appears as a new section in the user message:
    - TORO sees it as a challenge to address
    - URSA sees it as potential additional risk/opportunity
    - Risk sees it as an adjustment factor
    - Pivot sees the original rec + Nick's pushback + all new analyst takes
    
    Returns a new recommendation dict with the same contract shape.
    The new recommendation has metadata indicating it's a re-evaluation.
    """
    
    # Rebuild context (market data may have changed)
    context = await build_committee_context(signal)
    
    # Create pushback injection block
    pushback_context = (
        f"\n\n## PUSHBACK FROM NICK (TRADER)\n"
        f"Nick has reviewed the committee's initial recommendation "
        f"({original_recommendation['agents']['pivot']['action']}) "
        f"and disagrees. His objection:\n\n"
        f"\"{nick_objection}\"\n\n"
        f"Address this objection specifically in your analysis. "
        f"If his point is valid, adjust your assessment. "
        f"If his point is wrong, explain why clearly.\n\n"
        f"## ORIGINAL COMMITTEE RECOMMENDATION\n"
        f"TORO said: {original_recommendation['agents']['toro']['analysis']} "
        f"(conviction: {original_recommendation['agents']['toro']['conviction']})\n"
        f"URSA said: {original_recommendation['agents']['ursa']['analysis']} "
        f"(conviction: {original_recommendation['agents']['ursa']['conviction']})\n"
        f"Risk said: Entry {original_recommendation['agents']['risk']['entry']}, "
        f"Stop {original_recommendation['agents']['risk']['stop']}, "
        f"Target {original_recommendation['agents']['risk']['target']}\n"
        f"Pivot said: {original_recommendation['agents']['pivot']['synthesis']} "
        f"(action: {original_recommendation['agents']['pivot']['action']})"
    )
    
    # Format base context with pushback appended
    base_context = format_signal_context(signal, context)
    enhanced_context = base_context + pushback_context
    
    # Run all four agents with enhanced context
    # (reuse the same call_agent, parse_* functions from 03B)
    
    # TORO
    toro_raw = await call_agent(
        system_prompt=TORO_SYSTEM_PROMPT,
        user_message=enhanced_context,
        max_tokens=500,
        temperature=0.3,
        agent_name="TORO-REEVAL"
    )
    toro_response = parse_analyst_response(toro_raw, "TORO") if toro_raw else {
        "agent": "TORO", 
        "analysis": "[ANALYSIS UNAVAILABLE — TORO agent timed out on re-eval]",
        "conviction": "MEDIUM"
    }
    
    # URSA
    ursa_raw = await call_agent(
        system_prompt=URSA_SYSTEM_PROMPT,
        user_message=enhanced_context,
        max_tokens=500,
        temperature=0.3,
        agent_name="URSA-REEVAL"
    )
    ursa_response = parse_analyst_response(ursa_raw, "URSA") if ursa_raw else {
        "agent": "URSA",
        "analysis": "[ANALYSIS UNAVAILABLE — URSA agent timed out on re-eval]",
        "conviction": "MEDIUM"
    }
    
    # Risk (gets positions too)
    positions_text = format_positions_context(context.get("open_positions", []))
    risk_context = f"{enhanced_context}\n\n{positions_text}"
    
    risk_raw = await call_agent(
        system_prompt=RISK_SYSTEM_PROMPT,
        user_message=risk_context,
        max_tokens=800,
        temperature=0.3,
        agent_name="RISK-REEVAL"
    )
    risk_response = parse_risk_response(risk_raw) if risk_raw else {
        "agent": "RISK",
        "analysis": "[ANALYSIS UNAVAILABLE]",
        "entry": "N/A", "stop": "N/A", "target": "N/A",
        "size": "1 contract (conservative default)"
    }
    
    # Pivot — gets everything including bias challenge
    bias_challenge = get_bias_challenge_context(signal, context)
    
    pivot_context = (
        f"{enhanced_context}\n\n"
        f"## TORO RE-EVALUATION\n"
        f"Analysis: {toro_response['analysis']}\n"
        f"Conviction: {toro_response['conviction']}\n\n"
        f"## URSA RE-EVALUATION\n"
        f"Analysis: {ursa_response['analysis']}\n"
        f"Conviction: {ursa_response['conviction']}\n\n"
        f"## RISK RE-EVALUATION\n"
        f"Analysis: {risk_response['analysis']}\n"
        f"Entry: {risk_response['entry']}\n"
        f"Stop: {risk_response['stop']}\n"
        f"Target: {risk_response['target']}\n"
        f"Size: {risk_response['size']}"
        f"{bias_challenge}"
    )
    
    # Enhanced Pivot prompt for re-evaluation
    reeval_pivot_prompt = (
        PIVOT_SYSTEM_PROMPT + 
        "\n\nADDITIONAL CONTEXT FOR THIS RE-EVALUATION:\n"
        "Nick pushed back on the original recommendation. "
        "You must directly address his objection. "
        "If the committee's original call was wrong, own it — "
        "'Fair point, we missed that.' "
        "If Nick's pushback is emotional or biased, call it out — "
        "'I hear you, but that's your bearish bias talking, not the chart.' "
        "Be honest. Changing your mind is fine. Caving without reason is not."
    )
    
    pivot_raw = await call_agent(
        system_prompt=reeval_pivot_prompt,
        user_message=pivot_context,
        max_tokens=1000,
        temperature=0.6,
        agent_name="PIVOT-REEVAL"
    )
    pivot_response = parse_pivot_response(pivot_raw) if pivot_raw else {
        "agent": "PIVOT",
        "synthesis": "[PIVOT UNAVAILABLE on re-eval]",
        "conviction": "LOW",
        "action": "WATCHING",
        "invalidation": "Manual review required"
    }
    
    return {
        "signal": signal,
        "agents": {
            "toro": toro_response,
            "ursa": ursa_response,
            "risk": risk_response,
            "pivot": pivot_response
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": DEFAULT_MODEL,
        "is_reeval": True,
        "pushback_reason": nick_objection,
        "original_action": original_recommendation["agents"]["pivot"]["action"],
        "raw_responses": {
            "toro": toro_raw,
            "ursa": ursa_raw,
            "risk": risk_raw,
            "pivot": pivot_raw
        }
    }
```

### Updated post_recommendation for Re-evaluations

```python
async def post_recommendation(
    recommendation: dict, 
    channel=None, 
    reply_context: str = None
) -> None:
    """
    Posts committee recommendation to Discord.
    
    If reply_context is provided, it's prepended as a header
    (used for re-evaluations to show Nick's pushback reason).
    
    If channel is None, uses the default COMMITTEE_CHANNEL_ID.
    """
    if channel is None:
        channel = bot.get_channel(COMMITTEE_CHANNEL_ID)
    
    embed = build_committee_embed(recommendation)
    
    # Add re-evaluation indicator if applicable
    if recommendation.get("is_reeval"):
        original_action = recommendation.get("original_action", "?")
        new_action = recommendation["agents"]["pivot"]["action"]
        
        changed = original_action != new_action
        
        if changed:
            embed.set_author(
                name=f"🔄 RE-EVALUATION — Changed from {original_action} to {new_action}"
            )
        else:
            embed.set_author(
                name=f"🔄 RE-EVALUATION — Committee stands by {original_action}"
            )
    
    signal_id = recommendation["signal"]["id"]
    
    # Re-evaluations get new buttons too
    view = CommitteeView(
        signal_id=f"{signal_id}_reeval" if recommendation.get("is_reeval") else signal_id,
        recommendation=recommendation
    )
    
    content = reply_context if reply_context else None
    await channel.send(content=content, embed=embed, view=view)
    
    # Log committee run
    log_committee(
        recommendation["signal"],
        await build_committee_context(recommendation["signal"]),
        recommendation
    )
```

---

## Section 3: Decision Logging

All decisions — Take, Pass, Watching, Re-evaluate — are logged to a dedicated JSONL file for future pattern analysis (Brief 04).

### Decision Log Writer

```python
def log_decision(
    signal_id: str,
    nick_decision: str,
    committee_action: str,
    is_override: bool,
    override_reason: str = None,
    recommendation: dict = None
) -> None:
    """
    Write Nick's decision to decision_log.jsonl.
    
    This is the primary data source for Brief 04's pattern analytics.
    """
    signal = recommendation["signal"] if recommendation else {}
    pivot = recommendation["agents"]["pivot"] if recommendation else {}
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal_id,
        "ticker": signal.get("ticker"),
        "direction": signal.get("direction"),
        "alert_type": signal.get("alert_type"),
        "score": signal.get("score"),
        
        # Committee recommendation
        "committee_action": committee_action,
        "committee_conviction": pivot.get("conviction"),
        
        # Nick's decision
        "nick_decision": nick_decision,
        "is_override": is_override,
        "override_reason": override_reason,
        
        # Timing
        "signal_timestamp": signal.get("timestamp"),
        "decision_delay_seconds": None  # calculated below
    }
    
    # Calculate decision delay (how long Nick took to decide)
    try:
        signal_ts = datetime.fromisoformat(
            recommendation.get("timestamp", "").replace("Z", "+00:00")
        )
        delay = (datetime.now(timezone.utc) - signal_ts).total_seconds()
        entry["decision_delay_seconds"] = round(delay, 1)
    except (ValueError, TypeError):
        pass
    
    with open(DECISION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    logging.info(
        f"[DECISION] {signal_id}: Nick={nick_decision} "
        f"Committee={committee_action} Override={is_override}"
    )


def update_committee_log(signal_id: str, nick_decision: str) -> None:
    """
    Backfill nick_decision into the matching committee_log.jsonl entry.
    
    Reads the file, finds the matching signal_id, updates the field,
    rewrites the file. This is safe because committee_log entries are
    small and the file is append-only during normal operation.
    
    If the file is large (>1000 entries), only scan the last 100 lines
    for performance.
    """
    try:
        lines = []
        with open(COMMITTEE_LOG, "r") as f:
            lines = f.readlines()
        
        # Scan from the end (most recent entries)
        scan_range = min(len(lines), 100)
        updated = False
        
        for i in range(len(lines) - 1, max(len(lines) - scan_range - 1, -1), -1):
            try:
                entry = json.loads(lines[i])
                if entry.get("signal_id") == signal_id and entry.get("nick_decision") is None:
                    entry["nick_decision"] = nick_decision
                    lines[i] = json.dumps(entry) + "\n"
                    updated = True
                    break
            except json.JSONDecodeError:
                continue
        
        if updated:
            with open(COMMITTEE_LOG, "w") as f:
                f.writelines(lines)
            logging.info(f"Updated committee_log for {signal_id}: nick_decision={nick_decision}")
        else:
            logging.warning(f"Could not find {signal_id} in committee_log to update")
    
    except Exception as e:
        logging.error(f"Failed to update committee_log for {signal_id}: {e}")
```

---

## Section 4: Expiration + Cleanup

### Unanswered Recommendation Expiration

If Nick doesn't click any button within 4 hours, the recommendation expires. This prevents stale signals from cluttering the decision pipeline.

```python
async def expire_stale_recommendations():
    """
    Called periodically (e.g., every 30 minutes via cron or asyncio loop).
    Checks pending_recommendations for entries older than 4 hours.
    Logs them as EXPIRED decisions.
    """
    now = datetime.now(timezone.utc)
    expired_ids = []
    
    for signal_id, rec in pending_recommendations.items():
        try:
            rec_time = datetime.fromisoformat(
                rec["timestamp"].replace("Z", "+00:00")
            )
            age_hours = (now - rec_time).total_seconds() / 3600
            
            if age_hours > 4:
                expired_ids.append(signal_id)
                
                log_decision(
                    signal_id=signal_id,
                    nick_decision="EXPIRED",
                    committee_action=rec["agents"]["pivot"]["action"],
                    is_override=False,
                    override_reason=f"No decision within 4 hours",
                    recommendation=rec
                )
                
                logging.info(f"Recommendation {signal_id} expired after {age_hours:.1f} hours")
        
        except (ValueError, KeyError) as e:
            logging.warning(f"Could not check expiry for {signal_id}: {e}")
    
    for sid in expired_ids:
        pending_recommendations.pop(sid, None)
        # Cancel any watching reminders for expired signals
        task = watching_reminders.pop(sid, None)
        if task:
            task.cancel()
```

### Log Rotation

Both `decision_log.jsonl` and `committee_log.jsonl` need rotation to prevent unbounded growth.

```python
def rotate_log_if_needed(log_path: Path, max_lines: int = 5000) -> None:
    """
    If log file exceeds max_lines, keep only the most recent half.
    Called at the start of each orchestrator run.
    
    5000 lines ≈ 50-100 committee runs per day × 50-100 days of history.
    Plenty for Brief 04's pattern analysis.
    """
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        
        if len(lines) > max_lines:
            keep = lines[len(lines) - (max_lines // 2):]
            with open(log_path, "w") as f:
                f.writelines(keep)
            logging.info(
                f"Rotated {log_path.name}: {len(lines)} → {len(keep)} lines"
            )
    except FileNotFoundError:
        pass  # File doesn't exist yet — fine
```

### Startup Recovery

On bot restart, pending_recommendations is lost (in-memory). Old buttons become non-functional. This is acceptable — stale recommendations shouldn't be acted on after a restart.

Add to bot startup:

```python
@bot.event
async def on_ready():
    """Register persistent view for button handling after restart."""
    # Note: We do NOT re-register old views.
    # Old buttons will show "This interaction failed" — intentional.
    # Recommendations from before restart are stale.
    logging.info("Committee decision tracking ready. Old buttons will not function.")
```

---

## Section 5: Orchestrator Integration Points

### Changes to `pivot2_committee.py`

These are the specific modifications to the existing orchestrator from 03A/03B:

**1. Import the new modules:**

```python
from committee_decisions import (
    CommitteeView, 
    log_decision,
    expire_stale_recommendations,
    rotate_log_if_needed,
    DECISION_LOG, 
    COMMITTEE_LOG
)
```

**2. In `main()`, add cleanup at start:**

```python
async def main():
    reset_daily_state_if_needed()
    
    # Rotate logs if needed
    rotate_log_if_needed(DECISION_LOG)
    rotate_log_if_needed(COMMITTEE_LOG)
    
    # Expire stale recommendations
    await expire_stale_recommendations()
    
    signals = await fetch_pending_signals()
    # ... rest unchanged
```

**3. In `post_recommendation()`, pass recommendation to view:**

Already covered in Section 1's integration point. The key change is `CommitteeView` now receives the full `recommendation` dict.

---

## Section 6: Testing Checklist

### Button Handler Tests

- [ ] **Click Take** → decision_log.jsonl gets TAKE entry, ephemeral confirm sent
- [ ] **Click Pass** → decision_log.jsonl gets PASS entry, ephemeral confirm sent
- [ ] **Click Watching** → decision_log.jsonl gets WATCHING entry, reminder task created
- [ ] **Watching reminder fires** after 2 hours with correct ticker + signal_id
- [ ] **Double-click prevention** → second click on any button says "already decided"
- [ ] **Buttons disabled after decision** → all 4 buttons greyed out
- [ ] **Chosen button highlighted** → changes to primary (blue) style
- [ ] **Override detection** → Take when committee said PASS logs is_override=true
- [ ] **Non-override** → Take when committee said TAKE logs is_override=false

### Decision Log Tests

- [ ] **Log entry shape** → all fields present (timestamp, signal_id, ticker, direction, nick_decision, committee_action, is_override, decision_delay_seconds)
- [ ] **Decision delay calculated** → reasonable number of seconds (not negative, not >86400)
- [ ] **committee_log.jsonl updated** → nick_decision backfilled for matching signal_id
- [ ] **Committee log scan** → only scans last 100 lines (performance)
- [ ] **Missing committee entry** → warning logged, doesn't crash

### Re-evaluation (Pushback) Tests

- [ ] **Click Re-evaluate** → modal pops up with text input
- [ ] **Submit objection** → ephemeral "re-evaluating" message, then new embed posted
- [ ] **New embed shows re-evaluation header** → "Changed from X to Y" or "stands by X"
- [ ] **New embed has functional buttons** → can Take/Pass/Watch the re-evaluation
- [ ] **Original buttons disabled** after re-eval triggered
- [ ] **Pushback logged** → decision_log shows RE-EVALUATE with override_reason
- [ ] **Agents address objection** → LLM responses reference Nick's pushback text
- [ ] **Pivot's re-eval prompt** → includes "address his objection" instruction
- [ ] **Failed re-evaluation** → error message posted, original rec still stands
- [ ] **Empty objection** → modal validation prevents submit (required=True)
- [ ] **Long objection** → capped at 500 chars by modal max_length

### Expiration Tests

- [ ] **Recommendation >4 hours old** → logged as EXPIRED, removed from pending
- [ ] **Recommendation <4 hours old** → not expired
- [ ] **Expired watching reminder cancelled** → asyncio task cancelled
- [ ] **Expire function handles empty pending_recommendations** → no crash

### Log Rotation Tests

- [ ] **Log under 5000 lines** → no rotation
- [ ] **Log over 5000 lines** → trimmed to 2500 most recent
- [ ] **Missing log file** → no crash (FileNotFoundError caught)
- [ ] **Rotation preserves valid JSONL** → all remaining lines parse as JSON

### Integration Smoke Test

1. Trigger a committee run (send test signal via Railway API)
2. Verify embed posts with all 4 buttons functional
3. Click **Take** → verify decision logged, buttons disabled, confirmation shown
4. Trigger another committee run
5. Click **Re-evaluate** → type objection → verify new embed posts
6. Verify new embed references Nick's pushback
7. Click **Pass** on re-evaluation embed → verify second decision logged
8. Check decision_log.jsonl → should show TAKE (first), RE-EVALUATE (second), PASS (third)
9. Check committee_log.jsonl → nick_decision backfilled for first signal
10. Wait 4+ hours with an unanswered recommendation → verify EXPIRED logged
11. Restart bot → verify old buttons say "interaction failed" (expected)

### Implementation Order

1. **Create `committee_decisions.py`** — CommitteeView, PushbackModal, log functions
2. **Wire log_decision + update_committee_log** — test with manual JSONL entries
3. **Wire button handlers (Take/Pass/Watching)** — test with live Discord embed
4. **Build PushbackModal** — test modal popup and text capture
5. **Build run_committee_with_pushback()** — test re-evaluation LLM calls
6. **Wire Re-evaluate button → modal → re-run → post** — full pushback flow
7. **Add expire_stale_recommendations()** — test with aged entries
8. **Add log rotation** — test with oversized log files
9. **Update orchestrator imports + main()** — integration
10. **Full integration smoke test** (steps 1-11 above)
11. **Monitor first 5 live decisions** — verify logging accuracy

---

## File Summary

| File | Action |
|------|--------|
| `/opt/openclaw/workspace/scripts/committee_decisions.py` | **CREATE** — CommitteeView, PushbackModal, decision logging, expiration, rotation |
| `/opt/openclaw/workspace/scripts/pivot2_committee.py` | **MODIFY** — import new module, pass recommendation to CommitteeView, add cleanup to main() |
| `/opt/openclaw/workspace/data/decision_log.jsonl` | **CREATE** — auto-created on first decision |

All other files from 03A and 03B remain unchanged. Agent prompts, gatekeeper logic, context builder, parsers — all untouched.

---

*End of Brief 03C. Next: Brief 04 (Outcome Tracking + Performance Analytics) — tracks whether committee recommendations actually made money and detects Nick's decision patterns.*