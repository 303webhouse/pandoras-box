#!/usr/bin/env python3
"""
Patch script for Brief Tiers 3+4:
  3.1 — Strip dead dirs + create README + symlink
  3.2 — File rotation script + cron
  3.3 — Caching layer for UW flow + MP levels
  3.4 — Reactivate feedback cron
  4.1 — Token budgeting (replace run cap)
  4.2 — Audit logging with content hashes
  4.3 — Pre-market briefing script

Run on VPS: python3 /tmp/patch_tier3_tier4.py
"""
import os
import re
import subprocess
import textwrap
from pathlib import Path

SCRIPTS = Path("/opt/openclaw/workspace/scripts")
DATA_DIR = Path("/opt/openclaw/workspace/data")
CONTEXT_FILE = SCRIPTS / "committee_context.py"
COMMITTEE_FILE = SCRIPTS / "pivot2_committee.py"
BRIDGE_FILE = SCRIPTS / "committee_railway_bridge.py"


# ══════════════════════════════════════════════════════════════
# TIER 3
# ══════════════════════════════════════════════════════════════

def tier_3_1_strip_dead_dirs():
    """Remove dead directories, create README, add symlink."""
    print("─── 3.1: Strip dead dirs ───")

    dead_dirs = [
        "/opt/openclaw/workspace/knowledge/books",
        "/opt/openclaw/workspace/knowledge/papers",
        "/opt/openclaw/workspace/skills/memory",
        "/opt/openclaw/workspace/skills/knowledge",
        "/opt/openclaw/workspace/.openclaw",
        "/home/openclaw/.openclaw/memory",
    ]

    for d in dead_dirs:
        p = Path(d)
        if p.exists():
            import shutil
            shutil.rmtree(p)
            print(f"  Removed: {d}")
        else:
            print(f"  Already gone: {d}")

    # Clean up empty parent dirs
    for d in ["/opt/openclaw/workspace/knowledge", "/opt/openclaw/workspace/skills"]:
        p = Path(d)
        if p.exists() and not any(p.iterdir()):
            p.rmdir()
            print(f"  Removed empty parent: {d}")

    # Create README
    readme = Path("/opt/openclaw/workspace/README.md")
    readme.write_text(textwrap.dedent("""\
    # Pivot II — Trading Committee VPS

    This is the VPS deployment of Pivot's automated trading committee.

    ## Active Components
    - `scripts/committee_railway_bridge.py` — Polls Railway every 3 min for queued signals
    - `scripts/pivot2_committee.py` — Runs the 2-call committee pipeline (combined analysts + PIVOT)
    - `scripts/committee_context.py` — Builds the user message context with trading docs
    - `scripts/committee_prompts.py` — System prompts for all agents
    - `scripts/committee_parsers.py` — Anthropic API call wrapper + response parsers
    - `scripts/sync_trading_docs.sh` — Pulls trading docs from GitHub every 5 min
    - `trading_docs/` — Synced trading context (read by committee_context)

    ## Cron Jobs
    - `*/5 * * * *` — sync_trading_docs.sh
    - `*/3 13-20 * * 1-5` — committee_railway_bridge.py (market hours UTC)
    - `0 6 * * *` — rotate_data_files.sh (daily cleanup)
    - `30 1 * * 2-6` — committee_outcomes.py (nightly feedback, 9:30 PM ET)

    ## Data Files
    - `data/twitter_signals.jsonl` — Twitter sentiment cache (rotated to 48h by cron)
    - `data/pending_signals.json` — Bridge state (truncated to 7 days by cron)
    - `data/agent_accuracy.json` — Per-agent accuracy scores
    - `data/agent_feedback.json` — Per-agent feedback directives (read by agents)
    - `data/token_usage.json` — Hourly/daily token budget tracking
    - `data/bridge_daily_count.json` — Legacy daily run counter (kept for backwards compat)

    ## Environment
    - `/etc/openclaw/openclaw.env` — All API keys and config
    """))
    print(f"  Created README at {readme}")

    # Create symlink /opt/pivot -> /opt/openclaw
    symlink = Path("/opt/pivot")
    if not symlink.exists():
        symlink.symlink_to("/opt/openclaw")
        print("  Created symlink /opt/pivot -> /opt/openclaw")
    else:
        print("  Symlink /opt/pivot already exists")


def tier_3_2_file_rotation():
    """Create rotation script and add cron."""
    print("\n─── 3.2: File rotation ───")

    script = SCRIPTS / "rotate_data_files.sh"
    script.write_text(textwrap.dedent("""\
    #!/bin/bash
    # Daily rotation of growing data files

    DATA_DIR="/opt/openclaw/workspace/data"
    LOG="/var/log/data_rotation.log"

    # 1. Truncate twitter_signals.jsonl to last 48 hours
    TWITTER_FILE="$DATA_DIR/twitter_signals.jsonl"
    if [ -f "$TWITTER_FILE" ]; then
        CUTOFF=$(date -u -d '48 hours ago' '+%Y-%m-%dT%H:%M:%S')
        python3 -c "
import json
from pathlib import Path
import datetime as dt
cutoff = dt.datetime.fromisoformat('$CUTOFF').replace(tzinfo=dt.timezone.utc)
keep = []
for line in Path('$TWITTER_FILE').read_text().splitlines():
    try:
        rec = json.loads(line)
        ts = dt.datetime.fromisoformat(rec.get('timestamp', '').replace('Z', '+00:00'))
        if ts >= cutoff:
            keep.append(line)
    except:
        pass
Path('$TWITTER_FILE').write_text(chr(10).join(keep) + chr(10))
print(f'twitter_signals.jsonl: kept {len(keep)} lines')
" >> $LOG 2>&1
    fi

    # 2. Truncate pending_signals.json to last 7 days
    PENDING_FILE="$DATA_DIR/pending_signals.json"
    if [ -f "$PENDING_FILE" ]; then
        python3 -c "
import json
from pathlib import Path
import datetime as dt
cutoff = (dt.datetime.utcnow() - dt.timedelta(days=7)).isoformat()
data = json.loads(Path('$PENDING_FILE').read_text())
if isinstance(data, dict):
    pruned = {k: v for k, v in data.items() if isinstance(v, dict) and v.get('timestamp', '') >= cutoff}
    Path('$PENDING_FILE').write_text(json.dumps(pruned, indent=2))
    print(f'pending_signals.json: kept {len(pruned)} entries')
" >> $LOG 2>&1
    fi

    # 3. Prune token_usage.json older than 7 days
    TOKEN_FILE="$DATA_DIR/token_usage.json"
    if [ -f "$TOKEN_FILE" ]; then
        python3 -c "
import json
from pathlib import Path
import datetime as dt
cutoff = (dt.datetime.utcnow() - dt.timedelta(days=7)).strftime('%Y-%m-%d')
data = json.loads(Path('$TOKEN_FILE').read_text())
pruned = {k: v for k, v in data.items() if k >= cutoff}
Path('$TOKEN_FILE').write_text(json.dumps(pruned, indent=2))
print(f'token_usage.json: kept {len(pruned)} entries')
" >> $LOG 2>&1
    fi

    echo "Rotation completed at $(date)" >> $LOG
    """))
    os.chmod(script, 0o755)
    print(f"  Created {script}")

    # Add cron (check if already exists first)
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current_cron = result.stdout if result.returncode == 0 else ""

    if "rotate_data_files" not in current_cron:
        new_cron = current_cron.rstrip("\n") + "\n0 6 * * * /opt/openclaw/workspace/scripts/rotate_data_files.sh\n"
        proc = subprocess.run(["crontab", "-"], input=new_cron, capture_output=True, text=True)
        if proc.returncode == 0:
            print("  Added rotation cron (daily 6 AM UTC)")
        else:
            print(f"  FAILED to add cron: {proc.stderr}")
    else:
        print("  Rotation cron already exists")


def tier_3_3_caching():
    """Add in-memory cache with TTL for UW flow and MP levels."""
    print("\n─── 3.3: Caching layer ───")

    content = CONTEXT_FILE.read_text()

    if "_api_cache" in content:
        print("  Cache already exists, skipping")
        return

    # Find the import section and add cache infrastructure after it
    cache_code = '''
# ── API Response Cache (TTL-based) ────────────────────────────
import time as _time_mod

_api_cache: dict = {}
_API_CACHE_TTL = 300  # 5 minutes

def _cache_get(key: str):
    entry = _api_cache.get(key)
    if entry and (_time_mod.time() - entry["ts"]) < _API_CACHE_TTL:
        return entry["value"]
    return None

def _cache_set(key: str, value):
    _api_cache[key] = {"value": value, "ts": _time_mod.time()}
'''

    # Insert after the _log line
    marker = '_log = logging.getLogger("committee_context")'
    if marker in content:
        content = content.replace(marker, marker + cache_code)
        print("  Added cache infrastructure")
    else:
        print("  WARNING: Could not find logger line, appending cache code")
        content = cache_code + content

    # Wrap build_uw_flow_context with cache
    old_uw = 'def build_uw_flow_context(ticker: str, api_url: str, api_key: str) -> str:'
    new_uw = '''def build_uw_flow_context(ticker: str, api_url: str, api_key: str) -> str:
    cache_key = f"uw_flow_{ticker.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        _log.debug("UW flow cache hit for %s", ticker)
        return cached'''
    if old_uw in content:
        content = content.replace(old_uw, new_uw, 1)
        # Add cache_set before the return in build_uw_flow_context
        # Find the return statement at the end of the function
        # We need to cache the result - add it before "return" at the function end
        old_uw_return = '    return "\\n".join(parts)'
        # There might be multiple such returns, we need the one in build_uw_flow_context
        # Find the position of the new function start
        func_start = content.find(new_uw)
        # Find the next def after this function
        next_def = content.find("\ndef ", func_start + len(new_uw))
        # Find the last return before next_def
        func_body = content[func_start:next_def]
        # Replace the final return
        if old_uw_return in func_body:
            new_return = '    result = "\\n".join(parts)\n    _cache_set(cache_key, result)\n    return result'
            # Do the replacement only within this function's scope
            new_body = func_body[:func_body.rfind(old_uw_return)] + new_return + func_body[func_body.rfind(old_uw_return) + len(old_uw_return):]
            content = content[:func_start] + new_body + content[next_def:]
            print("  Wrapped build_uw_flow_context with cache")
        else:
            print("  WARNING: Could not find UW flow return to cache-wrap")
    else:
        print("  WARNING: build_uw_flow_context signature not found")

    # Wrap build_mp_levels_context with cache
    old_mp = 'def build_mp_levels_context(ticker: str, api_url: str, api_key: str) -> str:'
    new_mp = '''def build_mp_levels_context(ticker: str, api_url: str, api_key: str) -> str:
    cache_key = f"mp_levels_{ticker.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        _log.debug("MP levels cache hit for %s", ticker)
        return cached'''
    if old_mp in content:
        content = content.replace(old_mp, new_mp, 1)
        print("  Wrapped build_mp_levels_context with cache check")
        # Find end of mp function and add cache_set before final return
        func_start = content.find(new_mp)
        next_def = content.find("\ndef ", func_start + len(new_mp))
        if next_def == -1:
            next_def = len(content)
        func_body = content[func_start:next_def]
        # The mp function has 'return "\\n".join(lines)' at the end
        mp_return = '    return "\\n".join(lines)'
        if mp_return in func_body:
            new_mp_return = '    result = "\\n".join(lines)\n    _cache_set(cache_key, result)\n    return result'
            pos = func_body.rfind(mp_return)
            new_body = func_body[:pos] + new_mp_return + func_body[pos + len(mp_return):]
            content = content[:func_start] + new_body + content[next_def:]
            print("  Added cache_set to build_mp_levels_context")
        # Also need to handle the early return ""
        # Those don't need caching (empty result)
    else:
        print("  WARNING: build_mp_levels_context signature not found")

    CONTEXT_FILE.write_text(content)


def tier_3_4_feedback_cron():
    """Schedule committee_outcomes.py nightly."""
    print("\n─── 3.4: Feedback loop cron ───")

    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current_cron = result.stdout if result.returncode == 0 else ""

    if "committee_outcomes" not in current_cron:
        new_cron = current_cron.rstrip("\n") + "\n30 1 * * 2-6 cd /opt/openclaw/workspace/scripts && source /etc/openclaw/openclaw.env && python3 committee_outcomes.py >> /var/log/committee_outcomes.log 2>&1\n"
        proc = subprocess.run(["crontab", "-"], input=new_cron, capture_output=True, text=True)
        if proc.returncode == 0:
            print("  Added outcomes cron (1:30 AM UTC = 9:30 PM ET, Tue-Sat)")
        else:
            print(f"  FAILED to add cron: {proc.stderr}")
    else:
        print("  Outcomes cron already exists")


# ══════════════════════════════════════════════════════════════
# TIER 4
# ══════════════════════════════════════════════════════════════

def tier_4_1_token_budgeting():
    """Replace daily run cap with token budgeting."""
    print("\n─── 4.1: Token budgeting ───")

    content = BRIDGE_FILE.read_text()

    if "TOKEN_BUDGET_HOURLY" in content:
        print("  Token budgeting already present, skipping")
        return

    # Add token budget constants after the existing constants
    old_consts = "MAX_SIGNAL_ATTEMPTS = 3"
    new_consts = """MAX_SIGNAL_ATTEMPTS = 3

# ── Token budgeting (supplements daily run cap) ──────────────
TOKEN_BUDGET_HOURLY = 50000   # input tokens per hour
TOKEN_BUDGET_DAILY = 200000   # input tokens per day
TOKEN_USAGE_FILE = DATA_DIR / "token_usage.json"


def estimate_tokens(text: str) -> int:
    \"\"\"Rough estimate: 1 token ~ 4 chars for English.\"\"\"
    return len(text) // 4


def check_token_budget(estimated_input_tokens: int) -> bool:
    \"\"\"Returns True if we have token budget remaining.\"\"\"
    now = datetime.utcnow()
    try:
        usage = json.loads(TOKEN_USAGE_FILE.read_text()) if TOKEN_USAGE_FILE.exists() else {}
    except Exception:
        usage = {}

    hour_key = now.strftime("%Y-%m-%dT%H")
    day_key = now.strftime("%Y-%m-%d")

    hour_usage = usage.get(hour_key, 0)
    day_usage = sum(v for k, v in usage.items() if k.startswith(day_key))

    if hour_usage + estimated_input_tokens > TOKEN_BUDGET_HOURLY:
        log.warning("Hourly token budget exceeded: %d/%d", hour_usage, TOKEN_BUDGET_HOURLY)
        return False
    if day_usage + estimated_input_tokens > TOKEN_BUDGET_DAILY:
        log.warning("Daily token budget exceeded: %d/%d", day_usage, TOKEN_BUDGET_DAILY)
        return False
    return True


def record_token_usage(input_tokens: int):
    \"\"\"Record token usage for the current hour.\"\"\"
    now = datetime.utcnow()
    hour_key = now.strftime("%Y-%m-%dT%H")
    try:
        usage = json.loads(TOKEN_USAGE_FILE.read_text()) if TOKEN_USAGE_FILE.exists() else {}
    except Exception:
        usage = {}
    usage[hour_key] = usage.get(hour_key, 0) + input_tokens
    # Prune entries older than 7 days
    cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    usage = {k: v for k, v in usage.items() if k >= cutoff}
    try:
        TOKEN_USAGE_FILE.write_text(json.dumps(usage, indent=2))
    except Exception as e:
        log.warning("Failed to save token usage: %s", e)"""

    if old_consts in content:
        content = content.replace(old_consts, new_consts)
        print("  Added token budget functions")
    else:
        print("  ERROR: Could not find MAX_SIGNAL_ATTEMPTS constant")
        return

    # Add token budget check in main() before processing each signal
    # Find the line where we run committee and add token estimation + check
    old_run = '        log.info("Running committee on %s (%s) [attempt %d/%d]...",'
    new_run = '''        # Token budget check (estimated ~15K input tokens per committee run)
        est_tokens = 15000
        if not check_token_budget(est_tokens):
            log.warning("Token budget exceeded — stopping batch")
            break

        log.info("Running committee on %s (%s) [attempt %d/%d]...",'''
    if old_run in content:
        content = content.replace(old_run, new_run, 1)
        print("  Added token budget check before each committee run")
    else:
        print("  WARNING: Could not find committee run log line")

    # Add token usage recording after successful result
    old_done = '        resp = post_results(result, api_key)'
    new_done = '''        # Record estimated token usage
        record_token_usage(est_tokens)

        resp = post_results(result, api_key)'''
    if old_done in content:
        content = content.replace(old_done, new_done, 1)
        print("  Added token usage recording after successful run")
    else:
        print("  WARNING: Could not find post_results call")

    BRIDGE_FILE.write_text(content)


def tier_4_2_audit_logging():
    """Add audit logging with content hashes."""
    print("\n─── 4.2: Audit logging ───")

    content = COMMITTEE_FILE.read_text()

    if "_audit_log" in content:
        print("  Audit logging already present, skipping")
        return

    # Add audit log function after imports
    audit_code = '''
# ── Audit Logging ─────────────────────────────────────────────
import hashlib as _hashlib

AUDIT_LOG = Path("/var/log/committee_audit.log")

def _audit_log(signal_id: str, agent: str, system_prompt: str, user_message: str):
    sys_hash = _hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
    user_hash = _hashlib.sha256(user_message.encode()).hexdigest()[:12]
    line = f"{now_utc().isoformat()} | {signal_id} | {agent} | sys={sys_hash} | user={user_hash} | sys_chars={len(system_prompt)} | user_chars={len(user_message)}\\n"
    try:
        with open(AUDIT_LOG, "a") as f:
            f.write(line)
    except Exception:
        pass

'''

    # Insert before the run_committee function
    marker = "def run_committee(signal: dict, context: dict, api_key: str"
    if marker in content:
        content = content.replace(marker, audit_code + marker)
        print("  Added _audit_log function")
    else:
        print("  ERROR: Could not find run_committee function")
        return

    # Add audit calls before combined analyst call and pivot call
    old_combined = '    combined_raw = call_agent(\n        system_prompt=COMBINED_ANALYST_SYSTEM_PROMPT,'
    new_combined = '''    _audit_log(signal.get("signal_id", "?"), "ANALYSTS", COMBINED_ANALYST_SYSTEM_PROMPT, _agent_context("ANALYSTS"))
    combined_raw = call_agent(
        system_prompt=COMBINED_ANALYST_SYSTEM_PROMPT,'''
    if old_combined in content:
        content = content.replace(old_combined, new_combined, 1)
        print("  Added audit log before combined analyst call")

    old_pivot_call = '    pivot_raw = call_agent(\n        system_prompt=PIVOT_SYSTEM_PROMPT,'
    new_pivot_call = '''    _audit_log(signal.get("signal_id", "?"), "PIVOT", PIVOT_SYSTEM_PROMPT, pivot_context)
    pivot_raw = call_agent(
        system_prompt=PIVOT_SYSTEM_PROMPT,'''
    if old_pivot_call in content:
        content = content.replace(old_pivot_call, new_pivot_call, 1)
        print("  Added audit log before PIVOT call")

    COMMITTEE_FILE.write_text(content)


def tier_4_3_premarket_briefing():
    """Create pre-market briefing script."""
    print("\n─── 4.3: Pre-market briefing ───")

    script = SCRIPTS / "premarket_briefing.py"
    script.write_text(textwrap.dedent('''\
    #!/usr/bin/env python3
    """
    Pre-Market Briefing — runs at 7:30 AM ET (11:30 UTC) weekdays.

    Pulls top signals from last 24h, open positions, macro context,
    and runs a PIVOT-only synthesis on the day's setup.
    Posts to Discord and the committee history endpoint.
    """
    import json
    import logging
    import os
    import sys
    import time
    import urllib.error
    import urllib.request
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    SCRIPT_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(SCRIPT_DIR))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [premarket] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("premarket")


    def load_env():
        env = {}
        env_file = Path("/etc/openclaw/openclaw.env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
                    os.environ.setdefault(k.strip(), v.strip())
        return env


    def fetch_recent_signals(api_url: str, api_key: str, limit: int = 5) -> list:
        """Fetch top scored signals from the last 24 hours."""
        url = f"{api_url}/api/signals?limit={limit}&sort=score_v2_desc&hours=24"
        try:
            req = urllib.request.Request(url, headers={"X-API-Key": api_key})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                return data.get("signals", [])
        except Exception as e:
            log.warning("Failed to fetch signals: %s", e)
            return []


    def load_trading_docs() -> str:
        parts = []
        docs_dir = Path("/opt/openclaw/workspace/trading_docs")
        for fn in ["trading-memory.md", "open-positions.md", "macro-economic-data.md"]:
            try:
                parts.append((docs_dir / fn).read_text())
            except Exception:
                pass
        return "\\n---\\n".join(parts) if parts else ""


    def build_premarket_context(signals: list, trading_docs: str) -> str:
        lines = ["## PRE-MARKET BRIEFING CONTEXT"]
        lines.append(f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} (pre-market)")
        lines.append(f"Signals reviewed: {len(signals)}")
        lines.append("")

        if signals:
            lines.append("## TOP SIGNALS (last 24h)")
            for s in signals:
                ticker = s.get("ticker", "?")
                direction = s.get("direction", "?")
                score = s.get("score_v2") or s.get("score") or "?"
                strategy = s.get("strategy", "?")
                lines.append(f"  - {ticker} {direction} (score={score}, strategy={strategy})")
            lines.append("")

        if trading_docs:
            lines.append(trading_docs)

        return "\\n".join(lines)


    def run_premarket(anthropic_key: str, context: str) -> dict:
        """Run a single PIVOT-only synthesis."""
        from committee_parsers import call_agent
        from committee_prompts import PIVOT_SYSTEM_PROMPT

        system = PIVOT_SYSTEM_PROMPT + """\\n\\n## SPECIAL MODE: PRE-MARKET BRIEFING
    You are running in pre-market mode. There is no specific signal to evaluate.
    Instead, synthesize the day's setup:
    1. What are the top opportunities from overnight/yesterday's signals?
    2. What macro risks should Nick watch today?
    3. Any position management needed on open positions?
    4. One-sentence market bias for the day.

    Use the same voice (brash New Yorker) but adapted for a morning briefing.

    ## OUTPUT FORMAT
    SYNTHESIS: <your 4-6 sentence pre-market briefing>
    CONVICTION: <HIGH|MEDIUM|LOW> (confidence in the day's setup quality)
    ACTION: WATCHING
    INVALIDATION: <what would change this morning's read>
    STRUCTURE: N/A
    LEVELS: N/A
    SIZE: N/A"""

        raw = call_agent(
            system_prompt=system,
            user_message=context,
            api_key=anthropic_key,
            max_tokens=1500,
            temperature=0.6,
            agent_name="PREMARKET",
            model="claude-sonnet-4-6",
        )
        if raw:
            from committee_parsers import parse_pivot_response
            return parse_pivot_response(raw)
        return {"synthesis": "[Pre-market briefing unavailable]", "conviction": "LOW", "action": "WATCHING"}


    def post_to_discord(webhook_url: str, briefing: dict):
        """Post briefing to Discord via webhook."""
        synthesis = briefing.get("synthesis", "N/A")
        conviction = briefing.get("conviction", "?")
        invalidation = briefing.get("invalidation", "N/A")

        embed = {
            "title": f"Pre-Market Briefing — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "description": synthesis[:2000],
            "color": 3066993,
            "fields": [
                {"name": "Conviction", "value": conviction, "inline": True},
                {"name": "Invalidation", "value": invalidation[:200], "inline": False},
            ],
        }
        payload = json.dumps({
            "username": "Pivot Pre-Market",
            "embeds": [embed],
        }).encode()

        try:
            req = urllib.request.Request(
                webhook_url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                log.info("Posted pre-market briefing to Discord")
        except Exception as e:
            log.error("Failed to post to Discord: %s", e)


    def main():
        env = load_env()
        api_url = env.get("PANDORA_API_URL", "https://pandoras-box-production.up.railway.app/api")
        api_key = env.get("PIVOT_API_KEY", "")
        anthropic_key = env.get("ANTHROPIC_API_KEY", "")
        webhook = env.get("COWORK_DISCORD_WEBHOOK", "")

        if not anthropic_key:
            log.error("ANTHROPIC_API_KEY not set")
            return

        log.info("Starting pre-market briefing...")

        # Sync trading docs first
        try:
            import subprocess
            subprocess.run(["/opt/openclaw/workspace/scripts/sync_trading_docs.sh"],
                          timeout=30, capture_output=True)
        except Exception:
            pass

        signals = fetch_recent_signals(api_url, api_key, limit=5)
        trading_docs = load_trading_docs()
        context = build_premarket_context(signals, trading_docs)

        briefing = run_premarket(anthropic_key, context)

        log.info("Briefing: %s (conviction=%s)", briefing.get("synthesis", "")[:100], briefing.get("conviction"))

        if webhook:
            post_to_discord(webhook, briefing)

        log.info("Pre-market briefing complete")


    if __name__ == "__main__":
        main()
    '''))
    os.chmod(script, 0o755)
    print(f"  Created {script}")

    # Add cron
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current_cron = result.stdout if result.returncode == 0 else ""

    if "premarket_briefing" not in current_cron:
        new_cron = current_cron.rstrip("\n") + "\n30 11 * * 1-5 cd /opt/openclaw/workspace/scripts && source /etc/openclaw/openclaw.env && python3 premarket_briefing.py >> /var/log/premarket_briefing.log 2>&1\n"
        proc = subprocess.run(["crontab", "-"], input=new_cron, capture_output=True, text=True)
        if proc.returncode == 0:
            print("  Added premarket cron (11:30 UTC = 7:30 AM ET, weekdays)")
        else:
            print(f"  FAILED to add cron: {proc.stderr}")
    else:
        print("  Premarket cron already exists")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Brief Tiers 3 + 4: Cleanup + Enhancements")
    print("=" * 60)

    # Tier 3
    tier_3_1_strip_dead_dirs()
    tier_3_2_file_rotation()
    tier_3_3_caching()
    tier_3_4_feedback_cron()

    # Tier 4
    tier_4_1_token_budgeting()
    tier_4_2_audit_logging()
    tier_4_3_premarket_briefing()

    # Verify syntax
    print("\n" + "=" * 60)
    print("  Syntax Verification")
    print("=" * 60)
    import py_compile
    for f in ["committee_context.py", "pivot2_committee.py", "committee_railway_bridge.py", "premarket_briefing.py"]:
        try:
            py_compile.compile(str(SCRIPTS / f), doraise=True)
            print(f"  {f}: OK")
        except py_compile.PyCompileError as e:
            print(f"  {f}: FAILED — {e}")

    # Show cron
    print("\n" + "=" * 60)
    print("  Current Crontab")
    print("=" * 60)
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    print(result.stdout)

    print("\n=== All done ===")
