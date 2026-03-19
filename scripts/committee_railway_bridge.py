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
from datetime import datetime, timedelta

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
BRIDGE_COUNT_FILE = DATA_DIR / "bridge_daily_count.json"
RETRY_TRACKER_FILE = DATA_DIR / "bridge_signal_attempts.json"

RAILWAY_BASE = os.environ.get(
    "RAILWAY_API_URL",
    "https://pandoras-box-production.up.railway.app"
)

MAX_DAILY_AUTO_RUNS = 10
MAX_SIGNAL_ATTEMPTS = 3

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


# ── Per-signal retry tracking ────────────────────────────────

def load_retry_tracker() -> dict:
    try:
        if RETRY_TRACKER_FILE.exists():
            data = json.loads(RETRY_TRACKER_FILE.read_text())
            # Prune entries older than 7 days
            cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
            pruned = {
                k: v for k, v in data.items()
                if v.get("last_attempt", "") > cutoff
            }
            return pruned
    except Exception:
        pass
    return {}


def save_retry_tracker(tracker: dict) -> None:
    try:
        RETRY_TRACKER_FILE.write_text(json.dumps(tracker, indent=2))
    except Exception as e:
        log.warning("Failed to save retry tracker: %s", e)


# ── Market context cache ─────────────────────────────────────

_context_cache: dict = {"context": None, "ts": 0.0}
CONTEXT_CACHE_TTL = 900  # 15 minutes


def get_cached_context(signal, api_url, api_key, build_fn):
    """Cache build_market_context() results for 15 min between signals in same batch."""
    now = time.time()
    if _context_cache["context"] and (now - _context_cache["ts"]) < CONTEXT_CACHE_TTL:
        log.info("Using cached market context (%.0fs old)", now - _context_cache["ts"])
        return _context_cache["context"]
    ctx = build_fn(signal, api_url, api_key)
    _context_cache["context"] = ctx
    _context_cache["ts"] = now
    return ctx


# ── Railway API calls ────────────────────────────────────────

def fetch_queue(limit: int = 5, api_key: str = "") -> list:
    url = f"{RAILWAY_BASE}/api/committee/queue?limit={limit}"
    headers = {"X-API-Key": api_key} if api_key else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("queue", [])
    except Exception as e:
        log.error("Failed to fetch queue: %s", e)
        return []


def post_results(result: dict, api_key: str = "") -> dict | None:
    url = f"{RAILWAY_BASE}/api/committee/results"
    payload = json.dumps(result).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error("Failed to post results for %s: %s", result.get("signal_id"), e)
        return None


# ── Committee runner ─────────────────────────────────────────

def run_committee_on_signal(signal: dict) -> dict | str | None:
    """
    Run the existing committee pipeline on a Railway signal.
    Uses the same functions as the Discord-triggered flow.
    Returns:
        dict — result for Railway API (success)
        "CREDIT_EXHAUSTED" — credit/auth error (halt batch)
        None — other failure (skip to next signal)
    """
    from committee_parsers import CreditExhaustedError
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
    from committee_context import ensure_fresh_macro_briefing

    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)
    anthropic_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file)
    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or RAILWAY_BASE + "/api"
    polygon_key = pick_env("POLYGON_API_KEY", cfg, env_file)

    if not api_key:
        log.error("PIVOT_API_KEY not found — cannot call Railway API")
        return None

    if not anthropic_key:
        log.error("ANTHROPIC_API_KEY not found — cannot run committee LLM agents")
        return None

    start = time.time()

    try:
        # ── Macro pre-scan: verify briefing freshness before committee ──
        prescan = ensure_fresh_macro_briefing(
            api_url=api_url,
            api_key=api_key,
            anthropic_key=anthropic_key,
            polygon_key=polygon_key,
        )

        if prescan["status"] == "ASK_NICK":
            reason = prescan.get("reason", "Unknown")
            log.warning("Macro pre-scan returned ASK_NICK: %s — skipping %s",
                        reason, signal.get("ticker"))
            try:
                discord_token = load_discord_token(cfg, env_file)
                channel_id = pick_env("COMMITTEE_CHANNEL_ID", cfg, env_file) or DEFAULT_CHANNEL_ID
                _post_prescan_alert(discord_token, channel_id, signal, reason)
            except Exception as e:
                log.error("Failed to post pre-scan Discord alert: %s", e)
            return None

        context = get_cached_context(signal, api_url, api_key, build_market_context)
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

    except CreditExhaustedError as e:
        log.error("CREDIT/AUTH ERROR for %s: %s — halting batch",
                  signal.get("signal_id"), e)
        return "CREDIT_EXHAUSTED"
    except Exception as e:
        log.error("Committee run failed for %s: %s", signal.get("signal_id"), e)
        return None


# ── Pre-scan Discord alert ────────────────────────────────────

def _post_prescan_alert(discord_token: str, channel_id: str, signal: dict, reason: str):
    """Post a simple Discord message when macro pre-scan returns UNCERTAIN."""
    ticker = signal.get("ticker", "???")
    signal_id = signal.get("signal_id", "???")

    content = (
        f"**Macro Pre-Scan: Manual Review Needed**\n"
        f"Signal `{ticker}` (`{signal_id}`) is waiting for committee review, "
        f"but the macro briefing could not be auto-verified.\n"
        f"**Reason:** {reason}\n"
        f"Please run `/macro-update` or manually verify `macro_briefing.json`, "
        f"then the next bridge poll will pick up the signal."
    )

    payload = json.dumps({"content": content}).encode()
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization": f"Bot {discord_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info("Posted pre-scan alert to Discord for %s", ticker)
    except Exception as e:
        log.error("Failed to post pre-scan alert: %s", e)


# ── Main ─────────────────────────────────────────────────────

def main():
    # Load API key for Railway calls
    try:
        from pivot2_committee import (
            load_openclaw_config, load_env_file,
            pick_env, OPENCLAW_ENV_FILE,
        )
        _cfg = load_openclaw_config()
        _env = load_env_file(OPENCLAW_ENV_FILE)
        api_key = pick_env("PIVOT_API_KEY", _cfg, _env) or ""
    except Exception:
        api_key = os.environ.get("PIVOT_API_KEY", "")

    daily = load_daily_count()
    remaining = MAX_DAILY_AUTO_RUNS - daily["count"]

    if not check_budget(daily):
        log.info(
            "Daily cap reached (%d/%d). Manual Discord button still works.",
            daily["count"], MAX_DAILY_AUTO_RUNS,
        )
        return

    fetch_limit = min(5, remaining)
    queue = fetch_queue(limit=fetch_limit, api_key=api_key)

    if not queue:
        log.info("No signals in committee queue (%d/%d used today)",
                 daily["count"], MAX_DAILY_AUTO_RUNS)
        return

    log.info("Processing %d signal(s) — budget: %d/%d used today",
             len(queue), daily["count"], MAX_DAILY_AUTO_RUNS)

    retries = load_retry_tracker()

    for signal in queue:
        if not check_budget(daily):
            log.info("Budget exhausted mid-batch. Stopping.")
            break

        ticker = signal.get("ticker", "???")
        signal_id = signal.get("signal_id", "???")

        if signal_id in daily.get("signal_ids", []):
            log.info("Skipping %s — already processed today", signal_id)
            continue

        # Per-signal retry limit
        signal_info = retries.get(signal_id, {"attempts": 0})
        attempts = signal_info.get("attempts", 0)
        if attempts >= MAX_SIGNAL_ATTEMPTS:
            log.warning("Skipping %s (%s) — max retries (%d) exhausted. Last error: %s",
                        ticker, signal_id, MAX_SIGNAL_ATTEMPTS,
                        signal_info.get("last_error", "unknown"))
            continue

        # Count attempt BEFORE running (prevents uncapped retries)
        daily["count"] += 1
        daily["signal_ids"].append(signal_id)
        save_daily_count(daily)

        retries[signal_id] = {
            "attempts": attempts + 1,
            "last_attempt": datetime.utcnow().isoformat(),
            "last_error": None,
        }
        save_retry_tracker(retries)

        log.info("Running committee on %s (%s) [attempt %d/%d]...",
                 ticker, signal_id, attempts + 1, MAX_SIGNAL_ATTEMPTS)

        result = run_committee_on_signal(signal)

        # Circuit breaker: credit/auth error -> stop entire batch
        if result == "CREDIT_EXHAUSTED":
            retries[signal_id]["last_error"] = "credit/auth exhausted"
            save_retry_tracker(retries)
            log.error("Credit/auth exhausted — halting all processing")
            break

        if not result:
            retries[signal_id]["last_error"] = "committee run failed"
            save_retry_tracker(retries)
            log.error("Committee failed for %s", ticker)
            continue

        resp = post_results(result, api_key)
        if resp:
            log.info("Done %s: %s (%s) — %.1fs",
                     ticker, result["action"], result["conviction"],
                     result["run_duration_ms"] / 1000)
        else:
            retries[signal_id]["last_error"] = "post_results failed"
            save_retry_tracker(retries)
            log.error("Failed to post results for %s", ticker)

    log.info("Done. %d/%d auto-runs used today.", daily["count"], MAX_DAILY_AUTO_RUNS)


if __name__ == "__main__":
    main()
