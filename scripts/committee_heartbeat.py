"""
Committee Heartbeat — Alerts to Discord if the committee pipeline goes silent.

Runs every 30 minutes via cron during market hours.
Checks when the last committee_log.jsonl entry was written.
>2h stale = WARNING, >4h stale = CRITICAL.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("/opt/openclaw/workspace/data")
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"

# Reuse signals webhook or set a dedicated monitoring webhook
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_HEARTBEAT_WEBHOOK") or os.environ.get("DISCORD_WEBHOOK_SIGNALS") or ""


def get_last_committee_time():
    """Read last line of committee_log.jsonl, parse timestamp."""
    if not COMMITTEE_LOG.exists():
        return None
    try:
        with open(COMMITTEE_LOG, "rb") as f:
            f.seek(0, 2)
            pos = f.tell()
            if pos == 0:
                return None
            while pos > 0:
                pos -= 1
                f.seek(pos)
                if f.read(1) == b"\n" and pos < f.tell() - 1:
                    break
            last_line = f.readline().decode("utf-8").strip()
        if not last_line:
            return None
        entry = json.loads(last_line)
        ts = entry.get("timestamp", "")
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def is_market_hours():
    """Check if current time is within US market hours (9:30 AM - 4:00 PM ET)."""
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


def send_discord_alert(level, message):
    """Post heartbeat alert to Discord via webhook."""
    if not DISCORD_WEBHOOK_URL:
        print(f"[HEARTBEAT] No webhook configured. {level}: {message}")
        return
    color = 0xFF0000 if level == "CRITICAL" else 0xFFAA00
    emoji = "\U0001f534" if level == "CRITICAL" else "\U0001f7e1"
    payload = json.dumps({
        "embeds": [{
            "title": f"{emoji} Committee Heartbeat \u2014 {level}",
            "description": message,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }).encode("utf-8")
    req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Pivot-II/2.0")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                print(f"[HEARTBEAT] Discord returned {resp.status}")
    except Exception as e:
        print(f"[HEARTBEAT] Discord post failed: {e}")


def main():
    if not is_market_hours():
        return

    last_run = get_last_committee_time()
    if last_run is None:
        send_discord_alert("CRITICAL", "No committee_log.jsonl found or file is empty. Committee may have never run.")
        return

    now = datetime.now(timezone.utc)
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    gap_hours = (now - last_run).total_seconds() / 3600

    if gap_hours > 4:
        send_discord_alert(
            "CRITICAL",
            f"No committee run in {gap_hours:.1f} hours.\n"
            f"Last run: {last_run.isoformat()}\n"
            f"Check `systemctl status openclaw` and `journalctl -u openclaw -n 50`.",
        )
    elif gap_hours > 2:
        send_discord_alert(
            "WARNING",
            f"No committee run in {gap_hours:.1f} hours.\n"
            f"Last run: {last_run.isoformat()}\n"
            f"Pipeline may be stalled \u2014 no signals reaching Discord.",
        )


if __name__ == "__main__":
    main()
