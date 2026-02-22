# Brief 06 — Post-Trade Autopsy

## Overview

After the nightly outcome matcher resolves a trade, automatically generate a short narrative explaining **what happened** and **why it won or lost**. This turns raw outcome data (WIN/LOSS/EXPIRED + numbers) into plain-English stories that are useful to Nick immediately and to the Saturday weekly review later.

**Cost:** ~$0.005 per autopsy (Claude Haiku, ~300 token response). Even 20 resolved trades/week = $0.10.

## Prerequisite Fix: Missing Crons

The nightly outcome matcher (`committee_outcomes.py`) and Saturday weekly review (`committee_review.py`) have CLI entry points but **no crontab entries**. They need to be registered before Brief 06 (or anything downstream) works.

Add to `openclaw` user crontab (`crontab -u openclaw -e`):

```cron
# Nightly outcome matcher — 11 PM ET (4 AM UTC next day, or 3 AM during DST)
# Using 4 AM UTC (11 PM EST). Adjust to 3 AM UTC (11 PM EDT) in March.
0 4 * * * cd /opt/openclaw/workspace/scripts && /usr/bin/python3 committee_outcomes.py >> /var/log/pivot2_outcomes.log 2>&1

# Saturday weekly review — 9 AM MT (4 PM UTC, or 3 PM during DST)
# Using 4 PM UTC (9 AM MST). Adjust to 3 PM UTC (9 AM MDT) in March.
0 16 * * 6 cd /opt/openclaw/workspace/scripts && /usr/bin/python3 committee_review.py >> /var/log/pivot2_review.log 2>&1
```

**DST note:** Colorado goes MDT in March. These UTC offsets will be 1 hour off during summer. A proper DST-aware fix is out of scope for this brief — flag for a future Brief or use `TZ=America/Denver` prefix.

## Architecture

```
Nightly outcome matcher resolves a trade
  → write_outcome_entry() succeeds (existing 04 code)
  → NEW: call run_autopsy() for this resolved outcome
  → Haiku reads: committee agents' analysis + Nick's decision + actual outcome
  → Writes 3-5 sentence narrative to autopsy_log.jsonl
  → Posts Discord embed to committee channel
  → Saturday review picks up autopsy narratives for richer context
```

## Files

| File | Action | What changes |
|------|--------|--------------|
| `committee_autopsy.py` | **NEW** | Autopsy generator, Discord posting, JSONL logging |
| `committee_outcomes.py` | **MODIFY** | Wire autopsy call after each successful outcome match |
| `committee_review.py` | **MODIFY** | Inject autopsy summaries into weekly review context |

No schema changes. No new services. No new dependencies.

---

## File 1: `committee_autopsy.py` (NEW)

Create at `/opt/openclaw/workspace/scripts/committee_autopsy.py`

### Full file spec:

```python
"""
Post-Trade Autopsy — Generates narrative explanations of resolved trades.

Called by the nightly outcome matcher after each successful match.
Uses Claude Haiku to write a 3-5 sentence "what happened" story.

Depends on:
- committee_log.jsonl (from 03A — agent analyses)
- committee_parsers.py (call_agent from 03B)
"""

import json
import logging
import os
import pathlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("committee_autopsy")

DATA_DIR = Path("/opt/openclaw/workspace/data")
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"
AUTOPSY_LOG = DATA_DIR / "autopsy_log.jsonl"

MAX_AUTOPSY_ENTRIES = 500

OPENCLAW_CONFIG = pathlib.Path("/home/openclaw/.openclaw/openclaw.json")
OPENCLAW_ENV_FILE = pathlib.Path("/opt/openclaw/workspace/.env")

AUTOPSY_SYSTEM_PROMPT = """You are a trade post-mortem analyst. Given a trade's committee analysis, Nick's decision, and the actual outcome, write a concise 3-5 sentence autopsy explaining:
1. What the trade thesis was (bull vs bear case)
2. What actually happened
3. Why it won or lost (connect outcome to the specific risk/thesis that played out)

Be specific — reference the agents' actual arguments. Don't be generic. If the committee was wrong, say what they missed. If Nick overrode and was right/wrong, note what drove the override.

Respond with ONLY the narrative text. No headers, no formatting, no JSON. Just the plain text autopsy."""

HAIKU_MODEL = "anthropic/claude-3.5-haiku-20241022"


# ── Config helpers (same pattern as other committee files) ──

def load_openclaw_config() -> dict[str, Any]:
    try:
        return json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_env_file(path: pathlib.Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    except Exception:
        pass
    return data


def pick_env(name: str, cfg: dict[str, Any], env_file: dict[str, str]) -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    cfg_env = cfg.get("env") or {}
    if isinstance(cfg_env, dict):
        cval = str(cfg_env.get(name) or "").strip()
        if cval:
            return cval
    return str(env_file.get(name) or "").strip()


def load_discord_token(cfg: dict[str, Any], env_file: dict[str, str]) -> str:
    env_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip() or env_file.get("DISCORD_BOT_TOKEN", "").strip()
    if env_token:
        return env_token
    token = (((cfg.get("channels") or {}).get("discord") or {}).get("token") or "").strip()
    if token:
        return token
    raise RuntimeError("Discord token not found")
```

### `find_committee_entry(signal_id)` function:

```python
def find_committee_entry(signal_id: str) -> Optional[dict]:
    """Find the committee_log.jsonl entry for a signal to get agent analyses."""
    try:
        with open(COMMITTEE_LOG, "r") as f:
            # Read in reverse — most recent entries at end
            lines = f.readlines()
            for line in reversed(lines[-1000:]):
                try:
                    entry = json.loads(line.strip())
                    if entry.get("signal_id") == signal_id:
                        return entry
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        log.warning("committee_log.jsonl not found")
    return None
```

### `build_autopsy_prompt(decision, outcome_entry, committee_entry)` function:

```python
def build_autopsy_prompt(
    decision: dict,
    outcome_entry: dict,
    committee_entry: Optional[dict],
) -> str:
    """Build the user message for the autopsy LLM call."""
    ticker = decision.get("ticker", "?")
    direction = decision.get("direction", "?")
    score = decision.get("score", "?")

    # Outcome data
    result = outcome_entry.get("result", "?")
    mfe = outcome_entry.get("max_favorable_pct")
    mae = outcome_entry.get("max_adverse_pct")
    rr = outcome_entry.get("risk_reward_achieved")
    days = outcome_entry.get("days_held")

    # Decision data
    committee_action = decision.get("committee_action", "?")
    committee_conviction = decision.get("committee_conviction", "?")
    nick_decision = decision.get("nick_decision", "?")
    is_override = decision.get("is_override", False)
    override_reason = decision.get("override_reason")

    prompt = f"""TRADE: {ticker} {direction} (score: {score})

OUTCOME: {result}
- Max favorable move: {mfe}%
- Max adverse move: {mae}%
- Risk:Reward achieved: {rr}
- Days held: {days}

COMMITTEE RECOMMENDATION: {committee_action} ({committee_conviction} conviction)
NICK'S DECISION: {nick_decision}{"  [OVERRIDE]" if is_override else ""}"""

    if override_reason:
        prompt += f'\nOVERRIDE REASON: "{override_reason}"'

    # Add agent analyses if available
    if committee_entry:
        agents = committee_entry.get("agents", {})

        toro = agents.get("toro", {})
        if toro.get("analysis"):
            prompt += f"\n\nTORO (bull case): {toro['analysis'][:500]}"

        ursa = agents.get("ursa", {})
        if ursa.get("analysis"):
            prompt += f"\n\nURSA (bear case): {ursa['analysis'][:500]}"

        risk = agents.get("risk", {})
        risk_summary = []
        for field in ("entry", "stop", "target", "size"):
            if risk.get(field):
                risk_summary.append(f"{field}: {risk[field]}")
        if risk_summary:
            prompt += f"\n\nRISK PARAMS: {', '.join(risk_summary)}"

        pivot = agents.get("pivot", {})
        if pivot.get("synthesis"):
            prompt += f"\n\nPIVOT SYNTHESIS: {pivot['synthesis'][:500]}"

    return prompt
```

### `run_autopsy(decision, outcome_entry)` function:

```python
def run_autopsy(decision: dict, outcome_entry: dict) -> Optional[dict]:
    """
    Generate autopsy for a single resolved trade.
    Called by outcome matcher after each successful match.
    Returns autopsy dict on success, None on failure.
    """
    from committee_parsers import call_agent

    signal_id = decision.get("signal_id", "?")

    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    llm_api_key = pick_env("OPENROUTER_API_KEY", cfg, env_file) or pick_env("LLM_API_KEY", cfg, env_file)
    if not llm_api_key:
        log.error("No LLM API key — cannot run autopsy for %s", signal_id)
        return None

    # Find committee entry for agent analyses
    committee_entry = find_committee_entry(signal_id)
    if not committee_entry:
        log.warning("No committee_log entry for %s — autopsy will lack agent detail", signal_id)

    # Build prompt and call Haiku
    prompt = build_autopsy_prompt(decision, outcome_entry, committee_entry)

    narrative = call_agent(
        system_prompt=AUTOPSY_SYSTEM_PROMPT,
        user_message=prompt,
        api_key=llm_api_key,
        max_tokens=400,
        temperature=0.3,
        agent_name="AUTOPSY",
        model=HAIKU_MODEL,
    )

    if not narrative:
        log.error("Autopsy LLM call failed for %s", signal_id)
        return None

    narrative = narrative.strip()

    # Build autopsy entry
    autopsy = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal_id,
        "ticker": decision.get("ticker"),
        "direction": decision.get("direction"),
        "result": outcome_entry.get("result"),
        "committee_action": decision.get("committee_action"),
        "nick_decision": decision.get("nick_decision"),
        "is_override": decision.get("is_override", False),
        "narrative": narrative,
    }

    # Write to log
    _write_autopsy(autopsy)

    # Post to Discord
    _post_autopsy_to_discord(autopsy, outcome_entry, cfg, env_file)

    log.info("Autopsy complete for %s: %s -> %s", signal_id, decision.get("ticker"), outcome_entry.get("result"))
    return autopsy
```

### `_write_autopsy(autopsy)` function:

```python
def _write_autopsy(autopsy: dict) -> None:
    """Append autopsy to log. Rotate if over max."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(AUTOPSY_LOG, "a") as f:
        f.write(json.dumps(autopsy) + "\n")

    # Rotate
    try:
        with open(AUTOPSY_LOG, "r") as f:
            lines = f.readlines()
        if len(lines) > MAX_AUTOPSY_ENTRIES:
            keep = lines[-MAX_AUTOPSY_ENTRIES:]
            with open(AUTOPSY_LOG, "w") as f:
                f.writelines(keep)
            log.info("Rotated autopsy_log: %d -> %d", len(lines), len(keep))
    except FileNotFoundError:
        pass
```

### `_post_autopsy_to_discord(autopsy, outcome_entry, cfg, env_file)` function:

```python
def _post_autopsy_to_discord(
    autopsy: dict,
    outcome_entry: dict,
    cfg: dict,
    env_file: dict,
) -> None:
    """Post autopsy as a Discord embed."""
    try:
        discord_token = load_discord_token(cfg, env_file)
    except RuntimeError:
        log.error("No Discord token — cannot post autopsy")
        return

    channel_id = pick_env("COMMITTEE_CHANNEL_ID", cfg, env_file) or "1474135100521451813"

    result = autopsy["result"]
    ticker = autopsy.get("ticker", "?")
    direction = autopsy.get("direction", "?")

    # Color: green for WIN/BIG_WIN, red for LOSS, gray for EXPIRED
    if result in ("WIN", "BIG_WIN"):
        color = 0x2ECC71
        emoji = "✅" if result == "WIN" else "🏆"
    elif result == "LOSS":
        color = 0xE74C3C
        emoji = "❌"
    else:
        color = 0x95A5A6
        emoji = "⏱️"

    mfe = outcome_entry.get("max_favorable_pct")
    mae = outcome_entry.get("max_adverse_pct")
    rr = outcome_entry.get("risk_reward_achieved")
    days = outcome_entry.get("days_held")

    nick = autopsy.get("nick_decision", "?")
    committee = autopsy.get("committee_action", "?")
    override_tag = " ⚡ OVERRIDE" if autopsy.get("is_override") else ""

    embed = {
        "title": f"{emoji} Autopsy: {ticker} {direction} → {result}",
        "description": autopsy["narrative"][:4000],
        "color": color,
        "fields": [
            {"name": "Committee Said", "value": committee, "inline": True},
            {"name": "Nick Did", "value": f"{nick}{override_tag}", "inline": True},
            {"name": "MFE / MAE", "value": f"+{mfe}% / -{mae}%", "inline": True},
            {"name": "R:R Achieved", "value": str(rr) if rr is not None else "N/A", "inline": True},
            {"name": "Days Held", "value": str(days) if days is not None else "N/A", "inline": True},
        ],
        "footer": {
            "text": f"Signal: {autopsy['signal_id']} | Auto-generated by Pivot"
        },
    }

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bot {discord_token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                log.info("Autopsy posted for %s", ticker)
            else:
                log.warning("Discord returned %d for autopsy", resp.status)
    except Exception as e:
        log.error("Failed to post autopsy to Discord: %s", e)
```

### `load_recent_autopsies(count)` function (export for weekly review):

```python
def load_recent_autopsies(count: int = 20) -> list[dict]:
    """Load the N most recent autopsies for weekly review injection."""
    try:
        with open(AUTOPSY_LOG, "r") as f:
            lines = f.readlines()
        autopsies = []
        for line in lines[-count:]:
            try:
                autopsies.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
        return autopsies
    except FileNotFoundError:
        return []
```

---

## File 2: `committee_outcomes.py` (MODIFY)

### Change 1: Add import at top

**Find (line ~17, after existing imports):**
```python
from typing import Any, Optional
```

**Replace with:**
```python
from typing import Any, Optional

# Autopsy import — deferred to avoid circular imports
# from committee_autopsy import run_autopsy
```

### Change 2: Wire autopsy call after successful match

**Find (inside `run_outcome_matcher()`, the try block that writes outcomes — around line 335):**
```python
        try:
            write_outcome_entry(decision, outcome_row, classification)
            stats["matched"] += 1
            log.info(
                "Matched %s: %s -> %s (committee said %s)",
                signal_id, decision.get("nick_decision"),
                classification["result"], decision.get("committee_action"),
            )
        except Exception as e:
            stats["errors"] += 1
            log.error("Failed to write outcome for %s: %s", signal_id, e)
```

**Replace with:**
```python
        try:
            write_outcome_entry(decision, outcome_row, classification)
            stats["matched"] += 1
            log.info(
                "Matched %s: %s -> %s (committee said %s)",
                signal_id, decision.get("nick_decision"),
                classification["result"], decision.get("committee_action"),
            )

            # Generate post-trade autopsy
            try:
                from committee_autopsy import run_autopsy
                outcome_entry = {
                    "result": classification["result"],
                    "max_favorable_pct": classification["max_favorable_pct"],
                    "max_adverse_pct": classification["max_adverse_pct"],
                    "risk_reward_achieved": classification["risk_reward_achieved"],
                    "days_held": classification["days_held"],
                }
                run_autopsy(decision, outcome_entry)
            except Exception as ae:
                log.warning("Autopsy failed for %s (non-fatal): %s", signal_id, ae)

        except Exception as e:
            stats["errors"] += 1
            log.error("Failed to write outcome for %s: %s", signal_id, e)
```

**Key design choice:** Autopsy failure is non-fatal (warning, not error). The outcome match is already written before autopsy runs. If Haiku is down or rate-limited, we don't lose the outcome data.

### Change 3: Add autopsy count to stats

**Find (after the for loop, around line 347):**
```python
    rotate_log_if_needed(OUTCOME_LOG, max_lines=5000)
    log.info("Outcome matcher complete: %s", stats)
    return stats
```

**Replace with:**
```python
    rotate_log_if_needed(OUTCOME_LOG, max_lines=5000)
    log.info("Outcome matcher complete: %s", stats)
    return stats
```

No change needed — the stats dict doesn't need an autopsy counter since autopsy failures are logged individually and don't affect the matcher's return value.

---

## File 3: `committee_review.py` (MODIFY)

### Change: Inject autopsy summaries into weekly review context

**Find (inside `run_weekly_review()`, after lessons context is built, around line 141):**
```python
    # Load recent lessons to avoid repetition
    recent_lessons = _load_recent_lessons(count=5)
    lessons_context = ""
    if recent_lessons:
        lessons_context = (
            "\n\n## PREVIOUS LESSONS (avoid repeating these):\n"
            + "\n".join(f"- {l['lesson']}" for l in recent_lessons)
        )
```

**Replace with:**
```python
    # Load recent lessons to avoid repetition
    recent_lessons = _load_recent_lessons(count=5)
    lessons_context = ""
    if recent_lessons:
        lessons_context = (
            "\n\n## PREVIOUS LESSONS (avoid repeating these):\n"
            + "\n".join(f"- {l['lesson']}" for l in recent_lessons)
        )

    # Load autopsy narratives for richer context
    autopsy_context = ""
    try:
        from committee_autopsy import load_recent_autopsies
        autopsies = load_recent_autopsies(count=20)
        if autopsies:
            autopsy_lines = []
            for a in autopsies:
                result_emoji = "✅" if a.get("result") in ("WIN", "BIG_WIN") else "❌" if a.get("result") == "LOSS" else "⏱️"
                autopsy_lines.append(
                    f"- {result_emoji} {a.get('ticker', '?')} {a.get('direction', '?')}: {a.get('narrative', 'No narrative')[:200]}"
                )
            autopsy_context = (
                "\n\n## TRADE AUTOPSIES THIS WEEK:\n"
                + "\n".join(autopsy_lines)
            )
    except Exception as e:
        log.warning("Could not load autopsies for review: %s", e)
```

**Then update the LLM call to include autopsy context.**

**Find (the call_agent call, around line 148):**
```python
    # Step 2: Call Sonnet for synthesis (default model is Sonnet 4.6)
    review_raw = call_agent(
        system_prompt=REVIEW_SYSTEM_PROMPT,
        user_message=analytics_text + lessons_context,
        api_key=llm_api_key,
        max_tokens=1000,
        temperature=0.5,
        agent_name="WEEKLY-REVIEW",
    )
```

**Replace with:**
```python
    # Step 2: Call Sonnet for synthesis (default model is Sonnet 4.6)
    review_raw = call_agent(
        system_prompt=REVIEW_SYSTEM_PROMPT,
        user_message=analytics_text + lessons_context + autopsy_context,
        api_key=llm_api_key,
        max_tokens=1000,
        temperature=0.5,
        agent_name="WEEKLY-REVIEW",
    )
```

---

## Schemas

### autopsy_log.jsonl (NEW)

```json
{
  "timestamp": "ISO8601",
  "signal_id": "sig_abc123",
  "ticker": "SPY",
  "direction": "BEARISH",
  "result": "WIN",
  "committee_action": "TAKE",
  "nick_decision": "TAKE",
  "is_override": false,
  "narrative": "TORO argued for a bearish entry on weakening breadth, while URSA flagged strong support at 585. The trade worked as TORO predicted — breadth continued deteriorating and SPY broke through support on day 2, hitting T1 with a 2.3% favorable move. The committee's HIGH conviction call was well-calibrated here."
}
```

---

## Integration Contracts

### 06 exports (used by weekly review):
- `load_recent_autopsies(count) → list[dict]` — for weekly review context injection
- `autopsy_log.jsonl` — flat file with narrative entries

### 06 consumes (from existing briefs):
- `committee_log.jsonl` — reads agent analyses (03A)
- `call_agent()` — from committee_parsers.py (03B)
- Called by `committee_outcomes.py` after each successful match (04)

---

## Verification

After deployment, test with:

```bash
# Manually run outcome matcher (if there are any pending decisions)
cd /opt/openclaw/workspace/scripts && python3 committee_outcomes.py

# Or test autopsy directly
python3 -c "
from committee_autopsy import run_autopsy
# Create mock data
decision = {'signal_id': 'test_autopsy_001', 'ticker': 'SPY', 'direction': 'BEARISH', 'score': 78, 'committee_action': 'TAKE', 'committee_conviction': 'HIGH', 'nick_decision': 'TAKE', 'is_override': False}
outcome = {'result': 'WIN', 'max_favorable_pct': 2.3, 'max_adverse_pct': 0.8, 'risk_reward_achieved': 1.85, 'days_held': 3}
result = run_autopsy(decision, outcome)
print(result)
"

# Check output
tail -5 /opt/openclaw/workspace/data/autopsy_log.jsonl
```

**Clean up test data after verification** — delete any `test_autopsy_*` entries from autopsy_log.jsonl.

---

## Cron Registration (prerequisite)

Before this brief works in production, the crons must be added. CC should run:

```bash
# Add to openclaw user crontab
(crontab -u openclaw -l 2>/dev/null; echo ""; echo "# Nightly outcome matcher — 11 PM ET (4 AM UTC)"; echo "0 4 * * * cd /opt/openclaw/workspace/scripts && /usr/bin/python3 committee_outcomes.py >> /var/log/pivot2_outcomes.log 2>&1"; echo ""; echo "# Saturday weekly review — 9 AM MT (4 PM UTC)"; echo "0 16 * * 6 cd /opt/openclaw/workspace/scripts && /usr/bin/python3 committee_review.py >> /var/log/pivot2_review.log 2>&1") | crontab -u openclaw -
```

Verify with `crontab -u openclaw -l`.
