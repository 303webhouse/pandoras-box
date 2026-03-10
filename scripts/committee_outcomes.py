"""
Outcome Matcher — Joins committee decisions with market outcomes.

Runs nightly at 11 PM ET. Reads decision_log.jsonl for recent decisions,
queries signal_outcomes table for matching signal_ids, computes P&L
metrics, and writes results to outcome_log.jsonl.

Depends on:
- decision_log.jsonl (from 03C)
- signal_outcomes table in Railway PostgreSQL (via /webhook/outcomes/ endpoint)
- committee_log.jsonl (from 03A)
"""

import json
import logging
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

# Autopsy import — deferred to avoid circular imports
# from committee_autopsy import run_autopsy

log = logging.getLogger("committee_outcomes")

DATA_DIR = Path("/opt/openclaw/workspace/data")
DECISION_LOG = DATA_DIR / "decision_log.jsonl"
OUTCOME_LOG = DATA_DIR / "outcome_log.jsonl"
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"

DEFAULT_RAILWAY_URL = "https://pandoras-box-production.up.railway.app"

OPENCLAW_CONFIG = pathlib.Path("/home/openclaw/.openclaw/openclaw.json")
OPENCLAW_ENV_FILE = pathlib.Path("/opt/openclaw/workspace/.env")

# ── Outcome constants ──
OUTCOME_LABELS = {
    "HIT_T1": "WIN",
    "HIT_T2": "BIG_WIN",
    "STOPPED": "LOSS",
    "STOPPED_OUT": "LOSS",
    "INVALIDATED": "LOSS",
    "EXPIRED": "EXPIRED",
    "PENDING": "PENDING",
}


# ── Config helpers (same pattern as pivot2_committee.py) ──

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


# ── Decision log reader ──

def read_recent_decisions(hours: int = 0) -> list[dict]:
    """
    Read decision_log.jsonl entries from the last N hours.

    Uses 48h window (not 24h) to catch signals that were decided
    yesterday but didn't have outcomes resolved yet at last run.
    Skips EXPIRED and RE-EVALUATE entries (not actionable decisions).
    """
    decisions = []

    try:
        with open(DECISION_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("nick_decision") in ("EXPIRED", "RE-EVALUATE"):
                        continue
                    decisions.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except FileNotFoundError:
        log.warning("decision_log.jsonl not found — no decisions to match")

    return decisions


# ── Railway API fetcher ──

def fetch_signal_outcome(signal_id: str, api_url: str, api_key: str) -> Optional[dict]:
    """
    Query Railway backend for a signal's outcome from signal_outcomes table.
    Uses /webhook/outcomes/{signal_id} endpoint.
    Returns dict on success, None on 404 or error.
    """
    url = f"{api_url.rstrip('/').removesuffix('/api')}/webhook/outcomes/{urllib.parse.quote(signal_id)}"

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Content-Type", "application/json")
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        log.warning("Failed to fetch outcome for %s: HTTP %d", signal_id, e.code)
    except Exception as e:
        log.warning("Failed to fetch outcome for %s: %s", signal_id, e)

    return None


# ── Outcome classification ──

def classify_outcome(outcome_row: dict) -> dict:
    """Turn a signal_outcomes row into a P&L classification."""
    outcome = outcome_row.get("outcome", "PENDING")
    entry = outcome_row.get("entry")
    stop = outcome_row.get("stop")
    t1 = outcome_row.get("t1")
    outcome_price = outcome_row.get("outcome_price")
    max_favorable = outcome_row.get("max_favorable")
    max_adverse = outcome_row.get("max_adverse")
    direction = (outcome_row.get("direction") or "").upper()
    days = outcome_row.get("days_to_outcome")

    result = OUTCOME_LABELS.get(outcome, "UNKNOWN")

    mfe_pct = None
    mae_pct = None
    rr_achieved = None

    if entry and entry > 0:
        if max_favorable is not None:
            if direction in ("LONG", "BUY", "BULLISH"):
                mfe_pct = round((max_favorable - entry) / entry * 100, 2)
            else:
                mfe_pct = round((entry - max_favorable) / entry * 100, 2)

        if max_adverse is not None:
            if direction in ("LONG", "BUY", "BULLISH"):
                mae_pct = round((entry - max_adverse) / entry * 100, 2)
            else:
                mae_pct = round((max_adverse - entry) / entry * 100, 2)

        if stop and outcome_price:
            risk = abs(entry - stop)
            if risk > 0:
                if direction in ("LONG", "BUY", "BULLISH"):
                    reward = outcome_price - entry
                else:
                    reward = entry - outcome_price
                rr_achieved = round(reward / risk, 2)

    return {
        "result": result,
        "pnl_category": outcome,
        "max_favorable_pct": mfe_pct,
        "max_adverse_pct": mae_pct,
        "risk_reward_achieved": rr_achieved,
        "days_held": days,
    }


# ── Outcome log writer ──

def write_outcome_entry(decision: dict, outcome_row: dict, classification: dict) -> None:
    """Write a matched decision+outcome entry to outcome_log.jsonl."""
    entry = {
        "matched_at": datetime.now(timezone.utc).isoformat(),
        "signal_id": decision["signal_id"],
        "ticker": decision.get("ticker"),
        "direction": decision.get("direction"),
        "alert_type": decision.get("alert_type"),
        "score": decision.get("score"),
        "committee_action": decision.get("committee_action"),
        "committee_conviction": decision.get("committee_conviction"),
        "nick_decision": decision.get("nick_decision"),
        "is_override": decision.get("is_override"),
        "decision_delay_seconds": decision.get("decision_delay_seconds"),
        "result": classification["result"],
        "pnl_category": classification["pnl_category"],
        "max_favorable_pct": classification["max_favorable_pct"],
        "max_adverse_pct": classification["max_adverse_pct"],
        "risk_reward_achieved": classification["risk_reward_achieved"],
        "days_held": classification["days_held"],
        "committee_was_right": _committee_was_right(
            decision.get("committee_action"), classification["result"],
        ),
        "nick_was_right": _nick_was_right(
            decision.get("nick_decision"), classification["result"],
        ),
        "override_correct": _override_correct(decision, classification),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTCOME_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _committee_was_right(committee_action: str, result: str) -> Optional[bool]:
    if result in ("PENDING", "EXPIRED", "UNKNOWN"):
        return None
    if committee_action == "TAKE":
        return result in ("WIN", "BIG_WIN")
    elif committee_action == "PASS":
        return result in ("LOSS", "EXPIRED")
    return None


def _nick_was_right(nick_decision: str, result: str) -> Optional[bool]:
    if result in ("PENDING", "EXPIRED", "UNKNOWN"):
        return None
    if nick_decision == "TAKE":
        return result in ("WIN", "BIG_WIN")
    elif nick_decision == "PASS":
        return result in ("LOSS", "EXPIRED")
    return None


def _override_correct(decision: dict, classification: dict) -> Optional[bool]:
    if not decision.get("is_override"):
        return None
    return _nick_was_right(decision.get("nick_decision"), classification["result"])


# ── Dedup check ──

def _already_matched(signal_id: str) -> bool:
    """Check if signal_id already exists in outcome_log.jsonl."""
    try:
        with open(OUTCOME_LOG, "r") as f:
            lines = f.readlines()
            for line in lines[-500:]:
                try:
                    if json.loads(line).get("signal_id") == signal_id:
                        return True
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return False


# ── Log rotation ──

def rotate_log_if_needed(log_path: Path, max_lines: int = 5000) -> None:
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            keep = lines[len(lines) - (max_lines // 2):]
            with open(log_path, "w") as f:
                f.writelines(keep)
            log.info("Rotated %s: %d -> %d lines", log_path.name, len(lines), len(keep))
    except FileNotFoundError:
        pass


# ── Main entry point ──

def run_outcome_matcher() -> dict:
    """
    Main entry point. Called by cron at 11 PM ET nightly.
    Returns summary dict for logging.
    """
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_RAILWAY_URL
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)

    decisions = read_recent_decisions()
    log.info("Outcome matcher: %d recent decisions to check", len(decisions))

    stats = {"checked": 0, "matched": 0, "pending": 0, "errors": 0}

    for decision in decisions:
        signal_id = decision.get("signal_id")
        if not signal_id:
            continue

        if _already_matched(signal_id):
            continue

        stats["checked"] += 1

        outcome_row = fetch_signal_outcome(signal_id, api_url, api_key)
        if outcome_row is None:
            stats["pending"] += 1
            continue

        classification = classify_outcome(outcome_row)

        if classification["result"] == "PENDING":
            stats["pending"] += 1
            continue

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

    rotate_log_if_needed(OUTCOME_LOG, max_lines=5000)
    log.info("Outcome matcher complete: %s", stats)
    return stats


# ── CLI ──

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    result = run_outcome_matcher()
    print(json.dumps(result, indent=2))
