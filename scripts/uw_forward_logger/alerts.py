"""
Alert dispatch — matches committee_heartbeat.py webhook pattern.
Sends to DISCORD_WEBHOOK_SIGNALS (same channel as committee alerts).

Alert conditions per brief §B.9:
1. Any data type empty for 2+ consecutive days for same ticker
2. Any 429 that caused a fully-failed fetch
3. Any unexpected 403 or 401
4. Full cron run took longer than 30 minutes
5. New response envelope key observed

DO NOT alert on:
- Expected 403s (historic_data_access_missing) — logged as WARNING only
- Weekend/holiday skips
- Retries that eventually succeeded
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_WEBHOOK_URL = (
    os.environ.get("DISCORD_WEBHOOK_SIGNALS")
    or os.environ.get("DISCORD_WEBHOOK_BRIEFS")
    or ""
)
_NICK_USER_ID = os.environ.get("NICK_DISCORD_USER_ID", "")


def _send(title: str, description: str, color: int = 0xE05A5A) -> None:
    """Post a Discord embed via webhook. Fails silently if webhook not configured."""
    if not _WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_SIGNALS not set — alert not sent: %s", title)
        return

    mention = f"<@{_NICK_USER_ID}> " if _NICK_USER_ID else ""
    payload = json.dumps({
        "content": mention,
        "embeds": [{
            "title": f"UW Forward-Logger: {title}",
            "description": description,
            "color": color,
            "footer": {"text": f"uw_forward_logger · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
        }]
    }).encode()

    req = urllib.request.Request(
        _WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                logger.warning("Discord webhook returned %d", resp.status)
    except Exception as e:
        logger.warning("Failed to send Discord alert: %s", e)


def alert_consecutive_empty(ticker: str, data_type: str, days: int = 2) -> None:
    _send(
        f"Data Gap — {ticker} {data_type}",
        f"**{ticker}** `{data_type}` has returned empty for **{days}+ consecutive days**.\n"
        f"Check UW plan status and endpoint health.",
    )


def alert_rate_limit_failure(ticker: str, data_type: str, detail: str) -> None:
    _send(
        f"Rate-Limit Failure — {ticker} {data_type}",
        f"**{ticker}** `{data_type}` failed after max retries on 429.\n"
        f"Detail: `{detail}`\n"
        f"Consider reducing logger throttle or checking committee pipeline contention.",
    )


def alert_auth_error(ticker: str, path: str, detail: str) -> None:
    _send(
        "Auth Error — UW API",
        f"**{ticker}** endpoint `{path}` returned 401/403.\n"
        f"Detail: `{detail}`\n"
        f"Check `UW_API_KEY` and UW plan status.",
        color=0xFF0000,
    )


def alert_slow_run(elapsed_minutes: float) -> None:
    _send(
        "Slow Run Warning",
        f"UW forward-logger took **{elapsed_minutes:.1f} minutes** — threshold is 30 min.\n"
        f"Check for rate-limit backoff storms or network issues.",
        color=0xF0A500,
    )


def alert_carve_out_canary(ticker: str, row_count: int) -> None:
    _send(
        f"GEX Carve-Out Canary — {ticker}",
        f"**{ticker}** `greek-exposure` returned only **{row_count} rows** "
        f"(threshold: 200).\n"
        f"UW may have tightened the no-date 1-year carve-out. "
        f"Review with ATHENA before proceeding.",
        color=0xF0A500,
    )


def alert_logger_online() -> None:
    """Send a startup notification on the first successful production run."""
    _send(
        "Logger Online",
        "UW forward-logger completed its first production run successfully. "
        "Shadow data accumulation has begun.",
        color=0x4ECDC4,
    )


def check_consecutive_empty(
    ticker: str,
    data_type: str,
    today_empty: bool,
    empty_tracker: dict,
) -> None:
    """
    Track consecutive empty days per (ticker, data_type).
    Mutates empty_tracker in place. Fires alert at 2+ consecutive days.

    empty_tracker: shared dict of {(ticker, data_type): consecutive_empty_count}
    """
    key = (ticker, data_type)
    if today_empty:
        empty_tracker[key] = empty_tracker.get(key, 0) + 1
        if empty_tracker[key] >= 2:
            alert_consecutive_empty(ticker, data_type, empty_tracker[key])
    else:
        empty_tracker[key] = 0
