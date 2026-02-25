"""
add_cron_jobs.py — Brief 10 Task 1 + Task 2

Adds IBKR and yfinance cron jobs to the OpenClaw cron config at
/home/openclaw/.openclaw/cron/jobs.json in the exact structured format
that OpenClaw expects (UUID id, agentId, schedule, payload, delivery, state).

Run as root on the VPS:
    python3 /opt/openclaw/workspace/scripts/add_cron_jobs.py
    systemctl restart openclaw

Safe to run multiple times — checks by name before adding.
"""

import json
import pathlib
import sys
import uuid
from datetime import datetime, timezone

JOBS_PATH = pathlib.Path("/home/openclaw/.openclaw/cron/jobs.json")

NEW_JOBS = [
    {
        "name": "ibkr-position-poller",
        "description": "Poll IBKR positions and balances every 5 min during market hours (UTC). Adjust schedule to 13-20 UTC when DST starts March 9 2026.",
        "schedule_expr": "*/5 14-21 * * 1-5",
        "command": "python3 /opt/openclaw/workspace/scripts/ibkr_poller.py",
        "timeout": 60,
        "enabled": True,
    },
    {
        "name": "ibkr-quotes-poller",
        "description": "Fetch IBKR market data quotes every 1 min during market hours (UTC). Adjust schedule to 13-20 UTC when DST starts March 9 2026.",
        "schedule_expr": "*/1 14-21 * * 1-5",
        "command": "python3 /opt/openclaw/workspace/scripts/ibkr_quotes.py",
        "timeout": 30,
        "enabled": True,
    },
    {
        "name": "yfinance-price-updater",
        "description": "Fetch current prices for non-IBKR positions via yfinance every 15 min during market hours. Adjust schedule to 13-20 UTC when DST starts March 9 2026.",
        "schedule_expr": "*/15 14-21 * * 1-5",
        "command": "python3 /opt/openclaw/workspace/scripts/yfinance_price_updater.py",
        "timeout": 120,
        "enabled": True,
    },
]


def _make_job(template: dict, existing_job: dict | None = None) -> dict:
    """
    Build a job entry in OpenClaw's structured format.
    If an existing_job is provided, copies its agentId and structural fields.
    """
    # Use agentId from an existing job if possible
    agent_id = "main"
    if existing_job:
        agent_id = existing_job.get("agentId", "main")

    return {
        "id": str(uuid.uuid4()),
        "agentId": agent_id,
        "name": template["name"],
        "description": template["description"],
        "enabled": template["enabled"],
        "schedule": {
            "kind": "cron",
            "expr": template["schedule_expr"],
            "tz": "UTC",
        },
        "payload": {
            "kind": "agentTurn",
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "content": template["command"],
            "timeout": template["timeout"],
        },
        "delivery": {
            "mode": "none",
        },
        "state": {},
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def main():
    if not JOBS_PATH.exists():
        print(f"ERROR: {JOBS_PATH} does not exist. Is openclaw installed?")
        sys.exit(1)

    raw = JOBS_PATH.read_text()
    config = json.loads(raw)

    # OpenClaw config can be a list of jobs or an object with a "jobs" key
    if isinstance(config, list):
        jobs = config
        is_list = True
    elif isinstance(config, dict) and "jobs" in config:
        jobs = config["jobs"]
        is_list = False
    else:
        print(f"ERROR: Unexpected format in {JOBS_PATH}")
        print(f"  Top-level type: {type(config)}")
        print(f"  Keys: {list(config.keys()) if isinstance(config, dict) else 'N/A'}")
        sys.exit(1)

    existing_names = {j.get("name") for j in jobs}
    sample_existing = jobs[0] if jobs else None

    added = []
    skipped = []

    for template in NEW_JOBS:
        if template["name"] in existing_names:
            print(f"  [skip]  {template['name']} — already exists")
            skipped.append(template["name"])
        else:
            new_job = _make_job(template, sample_existing)
            jobs.append(new_job)
            print(f"  [add]   {template['name']} — schedule: {template['schedule_expr']}")
            added.append(template["name"])

    if not added:
        print("No new jobs to add. All jobs already present.")
        return

    # Write back
    JOBS_PATH.write_text(json.dumps(config if not is_list else jobs, indent=2))
    print(f"\nWrote {JOBS_PATH}")
    print(f"Added {len(added)} job(s): {', '.join(added)}")
    print(f"Skipped {len(skipped)} (already present): {', '.join(skipped)}")
    print("\nRestart openclaw to activate:")
    print("  systemctl restart openclaw")
    print("  sleep 3 && systemctl status openclaw")


if __name__ == "__main__":
    main()
