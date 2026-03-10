"""
Weekly Self-Review — Saturday cron that analyzes committee performance.

Computes analytics, feeds to Claude Sonnet for synthesis, posts Discord
embed, and distills lessons into lessons_bank.jsonl for future context.

Depends on:
- committee_analytics.py (pattern computation)
- committee_outcomes.py (outcome data)
- committee_parsers.py (call_agent from 03B)
"""

import json
import logging
import os
import pathlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("committee_review")

DATA_DIR = Path("/opt/openclaw/workspace/data")
LESSONS_BANK = DATA_DIR / "lessons_bank.jsonl"

MAX_LESSONS = 100

OPENCLAW_CONFIG = pathlib.Path("/home/openclaw/.openclaw/openclaw.json")
OPENCLAW_ENV_FILE = pathlib.Path("/opt/openclaw/workspace/.env")

REVIEW_SYSTEM_PROMPT = """You are the Trading Team's performance analyst. Your job is to review the committee's recommendations from the past week and produce actionable insights.

You are reviewing a 4-agent committee (TORO bull analyst, URSA bear analyst, TECHNICALS chart analyst, and Pivot synthesizer) that recommends options trades to Nick, who makes the final call.

KNOWN BIASES TO WATCH FOR:
- Nick tends to be bullish on AI/tech names (overrides PASS on these)
- Nick has a macro-bear bias (may PASS on good long signals due to fear)
- Fast decisions (<30s) may indicate gut-trading rather than analysis
- High conviction from committee correlates with better outcomes — track this

YOUR OUTPUT FORMAT:
You must respond with EXACTLY this structure:

## HEADLINE
One sentence summary of the week (e.g., "Committee outperformed Nick's overrides 3-to-1 this week")

## TOP 3 LESSONS
1. [Lesson with specific data — e.g., "HIGH conviction signals won 80% vs 45% for LOW — trust the committee when conviction is high"]
2. [Lesson]
3. [Lesson]

## OVERRIDE ANALYSIS
2-3 sentences on Nick's override patterns this week. Was he right to disagree? Be specific with tickers.

## MISSED PLAYS
If there were missed opportunities (Nick PASSed on winners), note the pattern. If none, say so.

## NEXT WEEK FOCUS
One concrete thing to watch for or do differently next week.

Keep it to ~300 words total. Be direct, no fluff. Use the data provided — don't speculate beyond what the numbers show. If sample size is too small (<5 resolved outcomes), say so and caveat your conclusions."""


# ── Config helpers ──

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


# ── Main entry point ──

def run_weekly_review() -> dict:
    """
    Main entry point for Saturday cron.

    1. Compute analytics
    2. Feed to Claude Sonnet for synthesis
    3. Post Discord embed
    4. Distill lessons to bank
    """
    from committee_analytics import compute_weekly_analytics, format_analytics_for_llm, compute_agent_accuracy
    from committee_parsers import call_agent

    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    llm_api_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file) or pick_env("LLM_API_KEY", cfg, env_file)
    if not llm_api_key:
        log.error("No LLM API key found — cannot run weekly review")
        return {"status": "error", "reason": "no API key"}

    discord_token = load_discord_token(cfg, env_file)
    channel_id = pick_env("COMMITTEE_CHANNEL_ID", cfg, env_file) or "1474135100521451813"

    # Step 1: Compute analytics
    analytics = compute_weekly_analytics(days=7)
    analytics_text = format_analytics_for_llm(analytics)

    overview = analytics["overview"]

    if overview["total_signals_reviewed"] == 0:
        log.info("Weekly review: no signals reviewed this week, skipping")
        return {"status": "skipped", "reason": "no signals"}

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
                result_emoji = "\u2705" if a.get("result") in ("WIN", "BIG_WIN") else "\u274c" if a.get("result") == "LOSS" else "\u23f1\ufe0f"
                autopsy_lines.append(
                    f"- {result_emoji} {a.get('ticker', '?')} {a.get('direction', '?')}: {a.get('narrative', 'No narrative')[:200]}"
                )
            autopsy_context = (
                "\n\n## TRADE AUTOPSIES THIS WEEK:\n"
                + "\n".join(autopsy_lines)
            )
    except Exception as e:
        log.warning("Could not load autopsies for review: %s", e)

    # Step 2: Call Sonnet for synthesis (default model is Sonnet 4.6)
    review_raw = call_agent(
        system_prompt=REVIEW_SYSTEM_PROMPT,
        user_message=analytics_text + lessons_context + autopsy_context,
        api_key=llm_api_key,
        max_tokens=1000,
        temperature=0.5,
        agent_name="WEEKLY-REVIEW",
    )

    if not review_raw:
        log.error("Weekly review: Sonnet call failed")
        return {"status": "error", "reason": "LLM call failed"}

    review_text = review_raw.strip()

    # Step 3: Post to Discord
    _post_review_to_discord(discord_token, channel_id, review_text, analytics)

    # Step 4: Distill lessons
    lessons = _extract_lessons(review_text, analytics)
    _save_lessons(lessons)

    # Step 5: Compute per-agent accuracy and generate agent feedback
    agent_accuracy = compute_agent_accuracy(days=28)  # 4-week lookback
    agent_feedback = _generate_agent_feedback(agent_accuracy, analytics, llm_api_key)

    log.info("Weekly review complete: %d lessons distilled, agent feedback generated", len(lessons))

    return {
        "status": "posted",
        "signals_reviewed": overview["total_signals_reviewed"],
        "outcomes_resolved": overview["outcomes_resolved"],
        "lessons_saved": len(lessons),
        "agent_feedback_generated": bool(agent_feedback),
    }


def _post_review_to_discord(token: str, channel_id: str, review_text: str, analytics: dict) -> None:
    """Post weekly review as a Discord embed via bot token."""
    overview = analytics["overview"]
    outcomes = analytics["outcome_stats"]
    overrides = analytics["override_stats"]

    embed = {
        "title": "Weekly Committee Review",
        "description": review_text[:4000],
        "color": 0x5865F2,
        "fields": [
            {"name": "Signals Reviewed", "value": str(overview["total_signals_reviewed"]), "inline": True},
            {"name": "Outcomes Resolved", "value": str(overview["outcomes_resolved"]), "inline": True},
            {"name": "Committee Accuracy", "value": f"{outcomes['committee_accuracy_pct']}%", "inline": True},
            {"name": "Nick's Accuracy", "value": f"{outcomes['nick_accuracy_pct']}%", "inline": True},
            {"name": "Override Rate", "value": f"{overrides['override_rate_pct']}%", "inline": True},
            {"name": "Override Accuracy", "value": f"{overrides['override_accuracy_pct']}%", "inline": True},
        ],
        "footer": {
            "text": f"Week of {datetime.now(timezone.utc).strftime('%b %d, %Y')} | Auto-generated by Pivot"
        },
    }

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bot {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Pivot-II/2.0")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                log.info("Weekly review posted to Discord")
            else:
                log.warning("Discord returned %d", resp.status)
    except Exception as e:
        log.error("Failed to post review to Discord: %s", e)


def _extract_lessons(review_text: str, analytics: dict) -> list[dict]:
    """Extract structured lessons from the LLM review text."""
    lessons = []
    in_lessons_section = False

    for line in review_text.split("\n"):
        line = line.strip()

        if "TOP 3 LESSONS" in line.upper() or "TOP LESSONS" in line.upper():
            in_lessons_section = True
            continue

        if in_lessons_section and line.startswith("##"):
            break

        if in_lessons_section and line and line[0].isdigit() and "." in line[:3]:
            lesson_text = line.split(".", 1)[1].strip().strip('"').strip()
            if lesson_text:
                lessons.append({
                    "lesson": lesson_text,
                    "week_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "total_signals": analytics["overview"]["total_signals_reviewed"],
                    "outcomes_resolved": analytics["overview"]["outcomes_resolved"],
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                })

    return lessons[:5]


def _save_lessons(lessons: list[dict]) -> None:
    """Append lessons to bank. Rotate if over MAX_LESSONS."""
    if not lessons:
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LESSONS_BANK, "a") as f:
        for lesson in lessons:
            f.write(json.dumps(lesson) + "\n")

    try:
        with open(LESSONS_BANK, "r") as f:
            lines = f.readlines()
        if len(lines) > MAX_LESSONS:
            keep = lines[-MAX_LESSONS:]
            with open(LESSONS_BANK, "w") as f:
                f.writelines(keep)
            log.info("Rotated lessons_bank: %d -> %d", len(lines), len(keep))
    except FileNotFoundError:
        pass


def _load_recent_lessons(count: int = 5) -> list[dict]:
    """Load the N most recent lessons from the bank."""
    try:
        with open(LESSONS_BANK, "r") as f:
            lines = f.readlines()
        lessons = []
        for line in lines[-count:]:
            try:
                lessons.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
        return lessons
    except FileNotFoundError:
        return []


AGENT_FEEDBACK_FILE = DATA_DIR / "agent_feedback.json"

AGENT_FEEDBACK_PROMPT = """You are generating performance feedback for individual AI trading committee agents. Based on the accuracy data and weekly analytics below, provide concise, actionable feedback for each agent.

For each agent, provide:
1. accuracy_summary: One sentence with their conviction accuracy stats (e.g., "6 HIGH conviction calls, 4 correct (67%)")
2. strengths: One sentence on what they're doing well
3. weaknesses: One sentence on what they need to improve
4. directive: One specific, actionable instruction for next week

Be direct. Use the actual numbers. Don't be generic.

## AGENT ACCURACY (last 4 weeks)
{accuracy_data}

## WEEKLY ANALYTICS SUMMARY
{analytics_summary}

Respond in this EXACT JSON format (no markdown, no backticks, just raw JSON):
{{
  "toro": {{"accuracy_summary": "...", "strengths": "...", "weaknesses": "...", "directive": "..."}},
  "ursa": {{"accuracy_summary": "...", "strengths": "...", "weaknesses": "...", "directive": "..."}},
  "technicals": {{"accuracy_summary": "...", "strengths": "...", "weaknesses": "...", "directive": "..."}},
  "pivot": {{"accuracy_summary": "...", "strengths": "...", "weaknesses": "...", "directive": "..."}}
}}"""


def _generate_agent_feedback(agent_accuracy: dict, analytics: dict, api_key: str) -> dict:
    """Generate per-agent feedback via LLM and save to agent_feedback.json."""
    from committee_parsers import call_agent

    accuracy_text = json.dumps(agent_accuracy, indent=2)
    analytics_summary = json.dumps({
        "overview": analytics.get("overview"),
        "conviction_stats": analytics.get("conviction_stats"),
        "agent_agreement": analytics.get("agent_agreement"),
        "outcome_stats": analytics.get("outcome_stats"),
    }, indent=2)

    prompt = AGENT_FEEDBACK_PROMPT.format(
        accuracy_data=accuracy_text,
        analytics_summary=analytics_summary,
    )

    raw = call_agent(
        system_prompt="You are a trading performance analyst. Respond only with valid JSON.",
        user_message=prompt,
        api_key=api_key,
        max_tokens=800,
        temperature=0.3,
        agent_name="AGENT-FEEDBACK",
    )

    if not raw:
        log.warning("Agent feedback LLM call failed")
        return {}

    # Parse JSON from response
    try:
        # Strip any markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        feedback = json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning("Failed to parse agent feedback JSON: %s", raw[:200])
        return {}

    # Add metadata
    feedback["generated_at"] = datetime.now(timezone.utc).isoformat()

    # Save to file
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        AGENT_FEEDBACK_FILE.write_text(json.dumps(feedback, indent=2), encoding="utf-8")
        log.info("Agent feedback saved to %s", AGENT_FEEDBACK_FILE)
    except Exception as e:
        log.warning("Failed to save agent feedback: %s", e)

    return feedback


# ── CLI ──

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    result = run_weekly_review()
    print(json.dumps(result, indent=2))
