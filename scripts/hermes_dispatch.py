"""
Hermes Dispatch — Weekly AI Performance Report.

Extends committee_review.py with Oracle-powered metrics, multi-section
Discord embeds, and PostgreSQL storage for Chronicle tab.

Saturday 9 AM MT cron (VPS):
    0 16 * * 6 cd /opt/openclaw/workspace/scripts && python3 hermes_dispatch.py

Depends on: Brief 3A (Ariadne outcomes), 3B (Oracle), committee_review.py
"""

import json
import logging
import os
import pathlib
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("hermes_dispatch")

DATA_DIR = Path("/opt/openclaw/workspace/data")
LESSONS_BANK = DATA_DIR / "lessons_bank.jsonl"
MAX_LESSONS = 100

OPENCLAW_CONFIG = pathlib.Path("/home/openclaw/.openclaw/openclaw.json")
OPENCLAW_ENV_FILE = pathlib.Path("/opt/openclaw/workspace/.env")

HERMES_SYSTEM_PROMPT = """You are Hermes, the messenger of the trading gods. You deliver the weekly
performance dispatch for Nick's trading system.

Your report must be:
- Brutally honest: if something is failing, say so
- Specific: use exact numbers, ticker names, dollar amounts
- Actionable: every lesson should have a concrete next step
- Brief: no filler, no encouragement fluff, just facts and insights

Nick has ADHD — keep sections punchy, use the structured format provided.
Don't soften bad news. A losing week should feel like a losing week.

You will receive structured metrics. Generate:
1. Three distilled lessons from the week's data (SOPHIA'S SCROLL)
2. A forward-looking outlook based on current regime and performance trends
3. One specific recommendation for next week

Respond with this EXACT structure:

## LESSONS
1. [Lesson with specific data]
2. [Lesson]
3. [Lesson]

## OUTLOOK
[2-3 sentences on what to focus on next week based on regime + trends]

## RECOMMENDATION
[One concrete, specific action item]
"""


# ── Config helpers (shared with committee_review.py) ──

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


# ── Data fetching ──

def _fetch_railway_json(path: str, api_url: str) -> dict:
    """Fetch JSON from Railway API."""
    url = f"{api_url.rstrip('/')}{path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "Hermes-Dispatch/1.0")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("Railway fetch failed for %s: %s", path, e)
        return {}


def fetch_oracle_data(api_url: str) -> dict:
    """Fetch Oracle payload for the last 7 days."""
    return _fetch_railway_json("/api/analytics/oracle?days=7", api_url)


def fetch_risk_budget(api_url: str) -> dict:
    """Fetch current risk budget."""
    return _fetch_railway_json("/api/analytics/risk-budget", api_url)


def fetch_bias_composite(api_url: str) -> dict:
    """Fetch current bias regime."""
    return _fetch_railway_json("/api/bias/composite", api_url)


# ── Report building ──

def build_report(oracle: dict, risk: dict, bias: dict) -> dict:
    """Build the structured report payload."""
    h = oracle.get("system_health") or {}
    scorecards = oracle.get("strategy_scorecards") or []
    dq = oracle.get("decision_quality") or {}
    opts = oracle.get("options_analytics") or {}

    week_of = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    return {
        "week_of": week_of,
        "performance": {
            "total_pnl": h.get("pnl_total", 0),
            "pnl_equity": h.get("pnl_equity", 0),
            "pnl_crypto": h.get("pnl_crypto", 0),
            "total_trades": h.get("total_trades", 0),
            "win_rate": h.get("win_rate", 0),
            "expectancy": h.get("expectancy", 0),
            "max_drawdown_pct": h.get("max_drawdown_pct", 0),
            "current_streak": h.get("current_streak"),
            "trajectory": h.get("trajectory"),
        },
        "strategy_rankings": sorted(
            scorecards,
            key=lambda s: s.get("total_pnl", 0),
            reverse=True,
        ),
        "decision_quality": dq,
        "options_analytics": opts,
        "risk_budget": risk,
        "bias_regime": bias.get("composite", {}).get("level", "UNKNOWN"),
    }


def format_performance_text(report: dict) -> str:
    """Format structured report into readable text for LLM."""
    p = report["performance"]
    lines = [
        f"PERFORMANCE SUMMARY (past 7 days):",
        f"  Total P&L: ${p['total_pnl']:+.0f} (Equity: ${p['pnl_equity']:+.0f}, Crypto: ${p['pnl_crypto']:+.0f})",
        f"  Trades: {p['total_trades']} ({(p['win_rate'] * 100):.1f}% win rate)",
        f"  Expectancy: ${p['expectancy']:.2f}/trade",
        f"  Max Drawdown: {p['max_drawdown_pct']:.1f}%",
        f"  Trajectory: {p['trajectory'] or 'UNKNOWN'}",
        "",
        "STRATEGY RANKINGS:",
    ]

    for i, s in enumerate(report["strategy_rankings"][:6], 1):
        name = s.get("display_name") or s.get("strategy", "?")
        grade = s.get("grade", "?")
        wins = s.get("wins", 0)
        losses = s.get("losses", 0)
        pnl = s.get("total_pnl", 0)
        lines.append(f"  {i}. {name}: {grade} grade ({wins}W/{losses}L, ${pnl:+.0f})")

    dq = report.get("decision_quality") or {}
    if dq:
        lines.extend([
            "",
            "DECISION QUALITY:",
            f"  Committee agreement: {(dq.get('committee_agreement_rate', 0) * 100):.0f}%",
            f"  Overrides: {dq.get('overrides', 0)} (WR: {(dq.get('override_win_rate', 0) * 100):.0f}%)",
            f"  Override net P&L: ${dq.get('override_net_pnl', 0):+.0f}",
            f"  Passed-would-have-won: {dq.get('passed_would_have_won', 0)}",
            f"  Passed-would-have-lost: {dq.get('passed_would_have_lost', 0)}",
        ])

    opts = report.get("options_analytics") or {}
    if opts.get("total_options_trades"):
        lines.extend([
            "",
            "OPTIONS INTELLIGENCE:",
            f"  Total options trades: {opts['total_options_trades']}",
            f"  Best structure: {opts.get('best_structure', 'N/A')}",
            f"  Avg DTE at entry: {opts.get('avg_dte_at_entry', 'N/A')}",
            f"  Avg DTE at exit: {opts.get('avg_dte_at_exit', 'N/A')}",
        ])

    lines.extend([
        "",
        f"CURRENT REGIME: {report.get('bias_regime', 'UNKNOWN')}",
    ])

    return "\n".join(lines)


# ── Discord posting (multi-embed) ──

def post_to_discord(token: str, channel_id: str, report: dict, narrative: str) -> None:
    """Post Hermes Dispatch as multi-embed Discord message."""
    p = report["performance"]
    week_of = report["week_of"]

    # Embed 1: Performance + Strategy Rankings
    strategy_lines = []
    for s in report["strategy_rankings"][:6]:
        name = s.get("display_name") or s.get("strategy", "?")
        grade = s.get("grade", "?")
        wins = s.get("wins", 0)
        losses = s.get("losses", 0)
        pnl = s.get("total_pnl", 0)
        strategy_lines.append(f"**[{grade}]** {name}: {wins}W/{losses}L ${pnl:+.0f}")

    embed1 = {
        "title": f"HERMES DISPATCH — Week of {week_of}",
        "color": 0x14b8a6,
        "fields": [
            {"name": "Total P&L", "value": f"${p['total_pnl']:+.0f}", "inline": True},
            {"name": "Win Rate", "value": f"{(p['win_rate'] * 100):.1f}%", "inline": True},
            {"name": "Trades", "value": str(p["total_trades"]), "inline": True},
            {"name": "Expectancy", "value": f"${p['expectancy']:.2f}/trade", "inline": True},
            {"name": "Trajectory", "value": p.get("trajectory") or "—", "inline": True},
            {"name": "Strategy Rankings", "value": "\n".join(strategy_lines) or "No data", "inline": False},
        ],
    }

    # Embed 2: Decision Quality + Options
    dq = report.get("decision_quality") or {}
    dq_text = (
        f"Agreement: {(dq.get('committee_agreement_rate', 0) * 100):.0f}%\n"
        f"Overrides: {dq.get('overrides', 0)} (WR: {(dq.get('override_win_rate', 0) * 100):.0f}%)\n"
        f"Override P&L: ${dq.get('override_net_pnl', 0):+.0f}"
    )

    opts = report.get("options_analytics") or {}
    opts_text = "No options data"
    if opts.get("total_options_trades"):
        opts_text = (
            f"Trades: {opts['total_options_trades']}\n"
            f"Best structure: {opts.get('best_structure', 'N/A')}\n"
            f"Avg DTE entry/exit: {opts.get('avg_dte_at_entry', '?')}/{opts.get('avg_dte_at_exit', '?')}"
        )

    embed2 = {
        "title": "Decision Quality + Options Intel",
        "color": 0x5865F2,
        "fields": [
            {"name": "Prometheus Report", "value": dq_text, "inline": False},
            {"name": "Options Intelligence", "value": opts_text, "inline": False},
        ],
    }

    # Embed 3: Cassandra + Lessons + Outlook
    passed_won = dq.get("passed_would_have_won", 0)
    passed_lost = dq.get("passed_would_have_lost", 0)
    cassandra_text = f"Would-have-won: {passed_won}\nWould-have-lost: {passed_lost}"
    if passed_won + passed_lost > 0:
        cassandra_text += f"\nPass accuracy: {(passed_lost / (passed_won + passed_lost) * 100):.0f}%"

    embed3 = {
        "title": "Cassandra's Mirror + Sophia's Scroll",
        "color": 0xf59e0b,
        "description": narrative[:3900] if narrative else "No narrative generated.",
        "fields": [
            {"name": "Counterfactuals", "value": cassandra_text, "inline": False},
        ],
        "footer": {"text": f"Hermes Dispatch | Auto-generated by Pivot | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"},
    }

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = json.dumps({"embeds": [embed1, embed2, embed3]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bot {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Pivot-II/2.0")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                log.info("Hermes Dispatch posted to Discord")
            else:
                log.warning("Discord returned %d", resp.status)
    except Exception as e:
        log.error("Failed to post Hermes Dispatch to Discord: %s", e)


# ── PostgreSQL storage ──

def save_to_postgres(api_url: str, api_key: str, report: dict, narrative: str, lessons: list) -> None:
    """Save weekly report to Railway PostgreSQL via API."""
    p = report["performance"]
    payload = {
        "week_of": report["week_of"],
        "report_json": report,
        "narrative": narrative,
        "lessons": lessons,
        "total_pnl": p.get("total_pnl", 0),
        "total_trades": p.get("total_trades", 0),
        "win_rate": p.get("win_rate", 0),
    }

    url = f"{api_url.rstrip('/')}/api/analytics/weekly-reports"
    data = json.dumps(payload, default=str).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", api_key)
    req.add_header("User-Agent", "Hermes-Dispatch/1.0")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                log.info("Weekly report saved to PostgreSQL")
            else:
                log.warning("PostgreSQL save returned %d", resp.status)
    except Exception as e:
        log.error("Failed to save weekly report to PostgreSQL: %s", e)


# ── Lesson extraction + JSONL ──

def extract_lessons(narrative: str, report: dict) -> list[dict]:
    """Extract structured lessons from Hermes narrative."""
    lessons = []
    in_lessons = False

    for line in narrative.split("\n"):
        line = line.strip()
        if "LESSONS" in line.upper():
            in_lessons = True
            continue
        if in_lessons and line.startswith("##"):
            break
        if in_lessons and line and line[0].isdigit() and "." in line[:3]:
            text = line.split(".", 1)[1].strip().strip('"').strip()
            if text:
                lessons.append({
                    "lesson": text,
                    "week_of": report["week_of"],
                    "total_trades": report["performance"].get("total_trades", 0),
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                })

    return lessons[:5]


def save_lessons_jsonl(lessons: list[dict]) -> None:
    """Append lessons to lessons_bank.jsonl on VPS."""
    if not lessons:
        return
    try:
        from safe_jsonl import safe_append, safe_trim_jsonl
        for lesson in lessons:
            safe_append(LESSONS_BANK, lesson)
        safe_trim_jsonl(LESSONS_BANK, MAX_LESSONS)
        log.info("Saved %d lessons to %s", len(lessons), LESSONS_BANK)
    except Exception as e:
        log.warning("Failed to save lessons: %s", e)


# ── Main entry point ──

def run_hermes_dispatch() -> dict:
    """
    Main entry point for Saturday cron.

    1. Fetch Oracle + risk budget + bias from Railway
    2. Build structured report
    3. Call Sonnet for synthesis
    4. Post to Discord (multi-embed)
    5. Save to PostgreSQL
    6. Write lessons to JSONL
    """
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    llm_api_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file)
    if not llm_api_key:
        log.error("No ANTHROPIC_API_KEY found")
        return {"status": "error", "reason": "no API key"}

    discord_token = load_discord_token(cfg, env_file)
    channel_id = pick_env("COMMITTEE_CHANNEL_ID", cfg, env_file) or "1474135100521451813"
    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or "https://pandoras-box-production.up.railway.app"
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)

    # Step 1: Fetch data from Railway
    oracle = fetch_oracle_data(api_url)
    risk = fetch_risk_budget(api_url)
    bias = fetch_bias_composite(api_url)

    if not oracle.get("system_health"):
        log.warning("Oracle data empty — trying committee_review fallback")
        # Fall back to existing committee_review if Oracle isn't populated
        try:
            from committee_review import run_weekly_review
            return run_weekly_review()
        except Exception as e:
            log.error("Fallback to committee_review failed: %s", e)
            return {"status": "error", "reason": "no Oracle data and fallback failed"}

    # Step 2: Build structured report
    report = build_report(oracle, risk, bias)
    perf_text = format_performance_text(report)

    if report["performance"]["total_trades"] == 0:
        log.info("Hermes Dispatch: no trades this week, skipping")
        return {"status": "skipped", "reason": "no trades"}

    # Load recent lessons to avoid repetition
    recent = []
    try:
        with open(LESSONS_BANK) as f:
            for line in f.readlines()[-5:]:
                try:
                    recent.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass

    avoid_text = ""
    if recent:
        avoid_text = "\n\nPREVIOUS LESSONS (avoid repeating):\n" + "\n".join(
            f"- {l['lesson']}" for l in recent
        )

    # Step 3: Call Sonnet for synthesis
    from committee_parsers import call_agent
    narrative = call_agent(
        system_prompt=HERMES_SYSTEM_PROMPT,
        user_message=perf_text + avoid_text,
        api_key=llm_api_key,
        max_tokens=800,
        temperature=0.5,
        agent_name="HERMES",
    )

    if not narrative:
        log.error("Hermes LLM call failed")
        narrative = "Oracle data available but narrative generation failed."

    narrative = narrative.strip()

    # Step 4: Post to Discord
    post_to_discord(discord_token, channel_id, report, narrative)

    # Step 5: Extract and save lessons
    lessons = extract_lessons(narrative, report)
    save_lessons_jsonl(lessons)

    # Step 6: Save to PostgreSQL (via API)
    if api_key:
        save_to_postgres(api_url, api_key, report, narrative, lessons)
    else:
        log.warning("No PIVOT_API_KEY — skipping PostgreSQL save")

    # Also run existing committee review for backward compat
    try:
        from committee_review import run_weekly_review
        committee_result = run_weekly_review()
        log.info("Committee review also ran: %s", committee_result.get("status"))
    except Exception as e:
        log.warning("Committee review fallback error: %s", e)

    log.info(
        "Hermes Dispatch complete: %d trades, $%.0f P&L, %d lessons",
        report["performance"]["total_trades"],
        report["performance"]["total_pnl"],
        len(lessons),
    )

    return {
        "status": "posted",
        "total_trades": report["performance"]["total_trades"],
        "total_pnl": report["performance"]["total_pnl"],
        "lessons_saved": len(lessons),
    }


# ── CLI ──

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    result = run_hermes_dispatch()
    print(json.dumps(result, indent=2))
