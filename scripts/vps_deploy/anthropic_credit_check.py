#!/usr/bin/env python3
"""
Anthropic credit balance health check.
Called from premarket_briefing.py to append credit status to the briefing.

NOTE: Anthropic does not expose a public credit-balance API endpoint as of 2026-04.
      This module uses a probe approach: make a minimal /v1/messages call and parse
      the error body. This detects CRITICAL (exhausted) vs OK, but cannot distinguish
      "balance $5" from "balance $500" — the LOW ($25) threshold is therefore not
      implemented until Anthropic adds a balance endpoint.
"""
import json
import logging
import os
import pathlib
import urllib.error
import urllib.request
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

AUDIT_LOG = pathlib.Path("/var/log/committee_audit.log")

# Cost estimate per committee run (5 agents × ~Haiku 4.5 input+output)
COST_PER_RUN_USD = 0.15

# Critical alert config — set via env so Nick can configure without code changes
# DISCORD_WEBHOOK_OPS: dedicated ops channel webhook (optional).
#   Falls back to DISCORD_WEBHOOK_BRIEFS (same channel as morning briefing).
# NICK_DISCORD_USER_ID: set in /etc/openclaw/openclaw.env → 339527833674317824
DISCORD_WEBHOOK_OPS = (
    os.environ.get("DISCORD_WEBHOOK_OPS", "").strip()
    or os.environ.get("DISCORD_WEBHOOK_BRIEFS", "").strip()
)
NICK_DISCORD_USER_ID = os.environ.get("NICK_DISCORD_USER_ID", "").strip()


def fetch_credit_status() -> str:
    """
    Probe the Anthropic API with a minimal request.

    Returns:
        "ok"       — API accepted the request (credits available)
        "critical" — 400/402 with "credit balance is too low" in body
        "unknown"  — unexpected error (fail-open: treat as ok)
    """
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — skipping credit probe")
        return "unknown"

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ping"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
            return "ok"
    except urllib.error.HTTPError as e:
        try:
            body = e.read(500).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        if "credit" in body.lower() or "balance" in body.lower():
            log.error("Anthropic credit exhausted: %s", body[:200])
            return "critical"
        log.warning("Anthropic probe HTTP %s (non-credit): %s", e.code, body[:200])
        return "unknown"
    except Exception as exc:
        log.error("Anthropic credit probe error: %s", exc)
        return "unknown"


def estimate_daily_burn() -> float:
    """
    Read last 7 days of committee_audit.log to estimate $/day.
    Falls back to COST_PER_RUN_USD * 10 runs/day if log is absent or empty.
    """
    if not AUDIT_LOG.exists():
        return COST_PER_RUN_USD * 10  # conservative default: 10 runs/day

    cutoff = datetime.utcnow() - timedelta(days=7)
    runs_by_day: dict[str, int] = {}
    try:
        with AUDIT_LOG.open() as f:
            for line in f:
                if "committee_run" not in line and "run_committee" not in line:
                    continue
                try:
                    parts = line.split()
                    ts = datetime.fromisoformat(
                        (parts[0] + " " + parts[1]).replace(",", ".")
                    )
                    if ts > cutoff:
                        day = ts.strftime("%Y-%m-%d")
                        runs_by_day[day] = runs_by_day.get(day, 0) + 1
                except Exception:
                    continue
    except Exception as exc:
        log.warning("Could not parse audit log for burn estimate: %s", exc)
        return COST_PER_RUN_USD * 10

    if not runs_by_day:
        return 0.0
    avg_runs = sum(runs_by_day.values()) / max(len(runs_by_day), 1)
    return avg_runs * COST_PER_RUN_USD


def post_critical_alert(message: str) -> None:
    """
    Post a separate urgent Discord message (to DISCORD_WEBHOOK_OPS, or skip if not set).
    Pings Nick by user ID if NICK_DISCORD_USER_ID is set.
    """
    webhook = DISCORD_WEBHOOK_OPS
    if not webhook:
        log.warning("DISCORD_WEBHOOK_OPS not set — critical credit alert not sent as separate ping")
        return

    ping = f"<@{NICK_DISCORD_USER_ID}> " if NICK_DISCORD_USER_ID else ""
    payload = json.dumps({
        "content": f"{ping}**CRITICAL: Anthropic API credits exhausted.** "
                   f"Committee bridge is failing on every run. "
                   f"Top up at console.anthropic.com/settings/billing.",
        "username": "Pivot Ops Alert",
    }).encode()
    try:
        req = urllib.request.Request(
            webhook, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        log.info("Critical credit alert posted to ops channel")
    except Exception as exc:
        log.error("Failed to post critical credit alert: %s", exc)


def build_status_block() -> tuple[str, bool]:
    """
    Returns (markdown_string, is_critical).

    markdown_string: text to append to the briefing; empty string = silent
    is_critical:     True → caller should also send a separate urgent ping
    """
    burn = estimate_daily_burn()
    status = fetch_credit_status()

    if status == "critical":
        burn_line = f" (est. ${burn:.2f}/day burn)" if burn > 0 else ""
        msg = (
            f"**CRITICAL: Anthropic API credits exhausted.**{burn_line} "
            f"Committee bridge will fail on every run. "
            f"Top up NOW → console.anthropic.com/settings/billing"
        )
        return msg, True

    if status == "unknown":
        # Fail-open: transient probe errors don't add noise
        return "", False

    # "ok" — credits available. Show burn rate as light context.
    if burn > 0:
        return f"Anthropic API: OK (est. ${burn:.2f}/day committee burn)", False
    return "", False


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    block, critical = build_status_block()
    print(block or "(no credit issue detected)")
    if critical:
        post_critical_alert(block)
        sys.exit(2)
