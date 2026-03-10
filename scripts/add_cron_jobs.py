#!/usr/bin/env python3
"""
Add cron jobs to OpenClaw's jobs.json.

Idempotent — skips jobs that already exist (matched by name).
Copies agentId and structural patterns from existing jobs.
"""
from __future__ import annotations

import json
import pathlib
import time
import uuid

JOBS_FILE = pathlib.Path("/home/openclaw/.openclaw/cron/jobs.json")

NEW_JOBS = [
    {
        "name": "ibkr-position-poller",
        "description": "IBKR position and balance sync via ibeam gateway",
        "enabled": True,
        "schedule": {
            "kind": "cron",
            "expr": "*/5 14-21 * * 1-5",
            "tz": "UTC",
            "staggerMs": 0,
        },
        "payload": {
            "kind": "agentTurn",
            "message": "Use exec once. Run exactly: python3 /opt/openclaw/workspace/scripts/ibkr_poller.py. Return only command stdout.",
            "thinking": "minimal",
            "timeoutSeconds": 120,
        },
    },
    {
        "name": "ibkr-quotes-poller",
        "description": "IBKR market data quotes for open positions",
        "enabled": True,
        "schedule": {
            "kind": "cron",
            "expr": "*/1 14-21 * * 1-5",
            "tz": "UTC",
            "staggerMs": 0,
        },
        "payload": {
            "kind": "agentTurn",
            "message": "Use exec once. Run exactly: python3 /opt/openclaw/workspace/scripts/ibkr_quotes.py. Return only command stdout.",
            "thinking": "minimal",
            "timeoutSeconds": 60,
        },
    },
    {
        "name": "yfinance-price-updater",
        "description": "Update open position prices via yfinance",
        "enabled": True,
        "schedule": {
            "kind": "cron",
            "expr": "*/15 14-21 * * 1-5",
            "tz": "UTC",
            "staggerMs": 0,
        },
        "payload": {
            "kind": "agentTurn",
            "message": "Use exec once. Run exactly: python3 /opt/openclaw/workspace/scripts/yfinance_price_updater.py. Return only command stdout.",
            "thinking": "minimal",
            "timeoutSeconds": 120,
        },
    },
]


def main() -> None:
    # Load existing jobs
    data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))

    if isinstance(data, list):
        jobs = data
        wrapper = None
    else:
        jobs = data.get("jobs", [])
        wrapper = data

    # Get agentId from first existing job (if any)
    agent_id = "main"
    for job in jobs:
        if job.get("agentId"):
            agent_id = job["agentId"]
            break

    # Get existing job names
    existing_names = {j.get("name") for j in jobs}

    now_ms = int(time.time() * 1000)

    for new_job in NEW_JOBS:
        if new_job["name"] in existing_names:
            print(f"[skip]  {new_job['name']} — already exists")
            continue

        entry = {
            "id": str(uuid.uuid4()),
            "agentId": agent_id,
            "name": new_job["name"],
            "description": new_job["description"],
            "enabled": new_job["enabled"],
            "createdAtMs": now_ms,
            "updatedAtMs": now_ms,
            "schedule": new_job["schedule"],
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": new_job["payload"],
            "delivery": {
                "mode": "none",
                "channel": "last",
            },
            "state": {},
        }

        jobs.append(entry)
        print(f"[add]   {new_job['name']} — schedule: {new_job['schedule']['expr']}")

    # Write back
    if wrapper is not None:
        wrapper["jobs"] = jobs
        output = wrapper
    else:
        output = jobs

    JOBS_FILE.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"\nDone. Total jobs: {len(jobs)}")


if __name__ == "__main__":
    main()
