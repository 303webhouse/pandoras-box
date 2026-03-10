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

HAIKU_MODEL = "claude-haiku-4-5-20251001"


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


# ── Committee log lookup ──

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


# ── Prompt builder ──

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


# ── Main autopsy runner ──

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

    llm_api_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file)
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


# ── Log writer ──

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


# ── Discord posting ──

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
        emoji = "\u2705" if result == "WIN" else "\U0001f3c6"
    elif result == "LOSS":
        color = 0xE74C3C
        emoji = "\u274c"
    else:
        color = 0x95A5A6
        emoji = "\u23f1\ufe0f"

    mfe = outcome_entry.get("max_favorable_pct")
    mae = outcome_entry.get("max_adverse_pct")
    rr = outcome_entry.get("risk_reward_achieved")
    days = outcome_entry.get("days_held")

    nick = autopsy.get("nick_decision", "?")
    committee = autopsy.get("committee_action", "?")
    override_tag = " \u26a1 OVERRIDE" if autopsy.get("is_override") else ""

    embed = {
        "title": f"{emoji} Autopsy: {ticker} {direction} \u2192 {result}",
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
    req.add_header("User-Agent", "Pivot-II/2.0")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                log.info("Autopsy posted for %s", ticker)
            else:
                log.warning("Discord returned %d for autopsy", resp.status)
    except Exception as e:
        log.error("Failed to post autopsy to Discord: %s", e)


# ── Export for weekly review ──

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
