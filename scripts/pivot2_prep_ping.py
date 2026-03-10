#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.request

DISCORD_API_BASE = "https://discord.com/api/v10"
DEFAULT_CHANNEL_ID = "1474135100521451813"


MORNING_MESSAGE = (
    "Morning brief in 30 minutes. Drop any of these in this channel and I will include them in the analysis:\n\n"
    "- UW Market Tide screenshot\n"
    "- UW Dark Pool levels\n"
    "- Any notable overnight flow or unusual activity\n\n"
    "No screenshots is fine. I will generate the brief with available data at 9:45 AM ET."
)

EOD_MESSAGE = (
    "EOD brief in 15 minutes. If you have these, drop them here:\n\n"
    "- UW Market Tide (end of day)\n"
    "- UW Dark Pool levels (closing)\n"
    "- GEX levels if notable\n"
    "- Any flow that stood out today\n\n"
    "Brief fires at 4:30 PM ET regardless."
)


def load_discord_token() -> str:
    env_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if env_token:
        return env_token

    state_dir = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
    cfg_path = state_dir / "openclaw.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        token = (((cfg.get("channels") or {}).get("discord") or {}).get("token") or "").strip()
        if token:
            return token
    except Exception:
        pass

    raise RuntimeError("Discord token not found. Set DISCORD_BOT_TOKEN or channels.discord.token in openclaw.json")


def discord_post(token: str, channel_id: str, content: str) -> dict:
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    payload = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "Pivot-II/1.0",
        },
        data=payload,
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Pivot II prep ping")
    parser.add_argument("--mode", choices=["morning", "eod"], required=True)
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID)
    args = parser.parse_args()

    content = MORNING_MESSAGE if args.mode == "morning" else EOD_MESSAGE

    token = load_discord_token()
    sent = discord_post(token, args.channel_id, content)
    print(
        json.dumps(
            {
                "ok": True,
                "mode": args.mode,
                "channel_id": args.channel_id,
                "message_id": sent.get("id"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise
