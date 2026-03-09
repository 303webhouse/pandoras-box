#!/usr/bin/env python3
"""
Committee Railway Bridge

Polls Railway API every 3 minutes for signals awaiting committee review.
Runs existing committee pipeline on each signal, then POSTs results back.

Daily cap: 10 auto-runs per day. Manual Discord button bypasses this cap
entirely (it doesn't use this script at all).

Cron: */3 8-16 * * 1-5  (every 3 min during market hours ET, weekdays)
"""

import json
import logging
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
BRIDGE_COUNT_FILE = DATA_DIR / "bridge_daily_count.json"

RAILWAY_BASE = os.environ.get(
    "RAILWAY_API_URL",
    "https://pandoras-box-production.up.railway.app"
)

MAX_DAILY_AUTO_RUNS = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [bridge] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("committee_bridge")


# ── Daily cap tracking ───────────────────────────────────────

def load_daily_count() -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        if BRIDGE_COUNT_FILE.exists():
            data = json.loads(BRIDGE_COUNT_FILE.read_text())
            if data.get("date") == today:
                return data
    except Exception:
        pass
    return {"date": today, "count": 0, "signal_ids": []}


def save_daily_count(data: dict) -> None:
    try:
        BRIDGE_COUNT_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        log.warning("Failed to save daily count: %s", e)


def check_budget(daily: dict) -> bool:
    """Returns True if we have budget remaining."""
    return daily["count"] < MAX_DAILY_AUTO_RUNS


# ── Railway API calls ────────────────────────────────────────

def fetch_queue(limit: int = 5) -> list:
    url = f"{RAILWAY_BASE}/api/committee/queue?limit={limit}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("queue", [])
    except Exception as e:
        log.error("Failed to fetch queue: %s", e)
        return []


def post_results(result: dict) -> dict | None:
    url = f"{RAILWAY_BASE}/api/committee/results"
    payload = json.dumps(result).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error("Failed to post results for %s: %s", result.get("signal_id"), e)
        return None


# ── Committee runner ─────────────────────────────────────────

def run_committee_on_signal(signal: dict) -> dict | None:
    """
    Run the existing committee pipeline on a Railway signal.
    Uses the same functions as the Discord-triggered flow.
    Returns result dict for Railway API AND posts Discord embed.
    """
    from pivot2_committee import (
        run_committee,
        build_market_context,
        build_committee_embed,
        post_discord_embed,
        load_openclaw_config,
        load_discord_token,
        load_env_file,
        pick_env,
        OPENCLAW_CONFIG,
        OPENCLAW_ENV_FILE,
        DEFAULT_CHANNEL_ID,
    )
    from committee_decisions import build_button_components, save_pending

    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)
    anthropic_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file)
    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or RAILWAY_BASE + "/api"

    if not api_key:
        log.error("PIVOT_API_KEY not found — cannot call Railway API")
        return None

    if not anthropic_key:
        log.error("ANTHROPIC_API_KEY not found — cannot run committee LLM agents")
        return None

    start = time.time()

    try:
        context = build_market_context(signal, api_url, api_key)
        recommendation = run_committee(signal, context, anthropic_key)
        elapsed_ms = (time.time() - start) * 1000

        pivot = recommendation.get("agents", {}).get("pivot", {})
        toro = recommendation.get("agents", {}).get("toro", {})
        ursa = recommendation.get("agents", {}).get("ursa", {})
        technicals = recommendation.get("agents", {}).get("technicals", {})

        # Post committee embed to Discord
        try:
            discord_token = load_discord_token(cfg, env_file)
            channel_id = pick_env("COMMITTEE_CHANNEL_ID", cfg, env_file) or DEFAULT_CHANNEL_ID
            embed = build_committee_embed(recommendation, context)
            signal_id = signal.get("signal_id", "")
            buttons = build_button_components(signal_id)
            save_pending(signal_id, recommendation)
            post_discord_embed(discord_token, channel_id, embed, components=buttons)
            log.info("Posted committee embed to Discord for %s", signal.get("ticker"))
        except Exception as e:
            log.error("Failed to post Discord embed for %s: %s", signal.get("ticker"), e)

        return {
            "signal_id": signal["signal_id"],
            "committee_run_id": f"bridge_{signal['signal_id']}_{int(time.time())}",
            "action": pivot.get("action", "WATCHING"),
            "conviction": pivot.get("conviction", "LOW"),
            "toro_analysis": toro.get("analysis"),
            "ursa_analysis": ursa.get("analysis"),
            "risk_params": {"analysis": technicals.get("analysis")},
            "pivot_synthesis": pivot.get("synthesis"),
            "run_duration_ms": round(elapsed_ms, 1),
        }

    except Exception as e:
        log.error("Committee run failed for %s: %s", signal.get("signal_id"), e)
        return None


# ── Main ─────────────────────────────────────────────────────

def main():
    daily = load_daily_count()
    remaining = MAX_DAILY_AUTO_RUNS - daily["count"]

    if not check_budget(daily):
        log.info(
            "Daily cap reached (%d/%d). Manual Discord button still works.",
            daily["count"], MAX_DAILY_AUTO_RUNS,
        )
        return

    fetch_limit = min(5, remaining)
    queue = fetch_queue(limit=fetch_limit)

    if not queue:
        log.info("No signals in committee queue (%d/%d used today)",
                 daily["count"], MAX_DAILY_AUTO_RUNS)
        return

    log.info("Processing %d signal(s) — budget: %d/%d used today",
             len(queue), daily["count"], MAX_DAILY_AUTO_RUNS)

    for signal in queue:
        if not check_budget(daily):
            log.info("Budget exhausted mid-batch. Stopping.")
            break

        ticker = signal.get("ticker", "???")
        signal_id = signal.get("signal_id", "???")

        if signal_id in daily.get("signal_ids", []):
            log.info("Skipping %s — already processed today", signal_id)
            continue

        log.info("🧠 Running committee on %s (%s)...", ticker, signal_id)

        result = run_committee_on_signal(signal)
        if not result:
            log.error("❌ Committee failed for %s", ticker)
            continue

        resp = post_results(result)
        if resp:
            log.info("✅ %s: %s (%s) — %.1fs",
                     ticker, result["action"], result["conviction"],
                     result["run_duration_ms"] / 1000)
            daily["count"] += 1
            daily["signal_ids"].append(signal_id)
            save_daily_count(daily)
        else:
            log.error("❌ Failed to post results for %s", ticker)

    log.info("Done. %d/%d auto-runs used today.", daily["count"], MAX_DAILY_AUTO_RUNS)


if __name__ == "__main__":
    main()
