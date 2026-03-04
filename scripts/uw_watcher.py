#!/usr/bin/env python3
"""
UW Watcher Bot — Parses Unusual Whales ticker updates from Discord.

Persistent Discord bot (discord.py) that watches #uw-flow-alerts for messages
from the UW Bot, parses structured text content into JSON, and POSTs to the
Pandora API for Redis caching and committee context consumption.

No LLM. Pure text parsing. $0/run.

Deploy: SCP to /opt/openclaw/workspace/scripts/uw_watcher.py
Service: systemd uw-watcher.service
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import sys
from datetime import datetime, timezone

import discord
import requests

# ── Config ───────────────────────────────────────────────────

UW_FLOW_CHANNEL_ID = 1463692055694807201   # #uw-flow-alerts
UW_NEWS_CHANNEL_ID = 1478626930805702756   # #uw-economic-news (future use)
UW_BOT_USER_ID = 1100705854271008798       # UW Bot's Discord user ID

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
OPENCLAW_STATE_DIR = pathlib.Path(os.environ.get("OPENCLAW_STATE_DIR", "/home/openclaw/.openclaw"))
OPENCLAW_CONFIG = OPENCLAW_STATE_DIR / "openclaw.json"
OPENCLAW_ENV_FILE = pathlib.Path("/etc/openclaw/openclaw.env")

DEFAULT_PANDORA_API_URL = "https://pandoras-box-production.up.railway.app"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("uw_watcher")


# ── Config Loading (same pattern as signal_notifier.py) ──────

def load_openclaw_config() -> dict:
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


def pick_env(name: str, cfg: dict, env_file: dict[str, str]) -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    cfg_env = cfg.get("env") or {}
    if isinstance(cfg_env, dict):
        cval = str(cfg_env.get(name) or "").strip()
        if cval:
            return cval
    return str(env_file.get(name) or "").strip()


# ── Volume / Premium Parsing ─────────────────────────────────

def parse_volume_str(s: str) -> int | None:
    """Parse volume strings like '7.36M', '743K', '58,910', '1.05B'."""
    if not s:
        return None
    s = s.strip().replace(",", "").replace("$", "")

    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    upper = s.upper()
    for suffix, mult in multipliers.items():
        if upper.endswith(suffix):
            try:
                return int(float(upper[:-1]) * mult)
            except (ValueError, TypeError):
                return None

    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


# ── Ticker Update Parser ─────────────────────────────────────

# Pattern: TICKER: $PRICE (CHANGE%) | Volume: X | P/C: X.XX | P: X/C: X | Premium: $X
TICKER_PATTERN = re.compile(
    r"^(?P<ticker>[A-Z]{1,5}):\s*"               # TICKER:
    r"\$(?P<price>[\d,.]+)\s*"                     # $681.90
    r"\((?P<change>-?[\d.]+)%\)\s*"                # (0.23%)
    r"\|\s*Volume:\s*(?P<volume>[\d.,]+[KMB]?)\s*" # Volume: 7.36M
    r"\|\s*P/C:\s*(?P<pc_ratio>[\d.]+)\s*"         # P/C: 1.07
    r"\|\s*P:\s*(?P<puts>[\d.,]+[KMB]?)"           # P: 743K
    r"/C:\s*(?P<calls>[\d.,]+[KMB]?)\s*"           # /C: 698K
    r"\|\s*Premium:\s*\$(?P<premium>[\d.,]+[KMB]?)" # Premium: $320M
    r"(?:\s*\|\s*(?P<emoji>[🐻🐂])\s*Premium:\s*\$(?P<flow_premium>[\d.,]+[KMB]?)"  # optional flow
    r"\s*\((?P<flow_pct>[\d.]+)%\))?"              # (67.8%)
)


def parse_ticker_update(line: str) -> dict | None:
    """
    Parse a single Ticker Update line into structured data.

    Returns dict with keys:
        ticker, price, change_pct, volume, pc_ratio,
        put_volume, call_volume, total_premium,
        flow_sentiment, flow_premium, flow_pct

    Returns None if line doesn't match expected format.
    """
    line = line.strip()
    if not line:
        return None

    m = TICKER_PATTERN.match(line)
    if not m:
        return None

    try:
        result = {
            "ticker": m.group("ticker"),
            "price": float(m.group("price").replace(",", "")),
            "change_pct": float(m.group("change")),
            "volume": parse_volume_str(m.group("volume")) or 0,
            "pc_ratio": float(m.group("pc_ratio")),
            "put_volume": parse_volume_str(m.group("puts")) or 0,
            "call_volume": parse_volume_str(m.group("calls")) or 0,
            "total_premium": parse_volume_str(m.group("premium")) or 0,
            "flow_sentiment": None,
            "flow_premium": None,
            "flow_pct": None,
        }

        # Parse optional flow sentiment suffix
        emoji = m.group("emoji")
        if emoji:
            result["flow_sentiment"] = "BEARISH" if emoji == "\U0001f43b" else "BULLISH"
            result["flow_premium"] = parse_volume_str(m.group("flow_premium"))
            flow_pct = m.group("flow_pct")
            if flow_pct:
                result["flow_pct"] = float(flow_pct)

        return result
    except (ValueError, TypeError) as e:
        logger.debug(f"Failed to parse ticker line: {line!r} — {e}")
        return None


# ── Discord Bot ──────────────────────────────────────────────

def create_bot(api_url: str, api_key: str) -> discord.Client:
    """Create the Discord bot with message content intent."""
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info(f"UW Watcher logged in as {client.user} (ID: {client.user.id})")
        logger.info(f"Watching channel {UW_FLOW_CHANNEL_ID} for UW Bot (ID: {UW_BOT_USER_ID})")

    @client.event
    async def on_message(message: discord.Message):
        # Only watch the designated UW flow channel
        if message.channel.id != UW_FLOW_CHANNEL_ID:
            return

        # Only parse messages from the UW Bot
        if message.author.id != UW_BOT_USER_ID:
            return

        # Skip messages that are just images (Highest Volume Contracts chart)
        if not message.content and message.attachments:
            logger.info("Skipping image-only UW message (Highest Volume Contracts chart)")
            return

        # Skip embed-only messages (Highest Volume Contracts header)
        if not message.content and message.embeds:
            logger.info("Skipping embed-only UW message")
            return

        if not message.content:
            return

        # Parse Ticker Updates from message content
        lines = message.content.strip().split("\n")
        parsed_tickers = []
        for line in lines:
            result = parse_ticker_update(line.strip())
            if result:
                parsed_tickers.append(result)

        if not parsed_tickers:
            logger.debug(f"No parseable tickers in UW message ({len(lines)} lines)")
            return

        # POST to Pandora API
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "source": "uw_ticker_updates",
            "tickers": parsed_tickers,
        }

        try:
            resp = requests.post(
                f"{api_url}/api/uw/ticker-updates",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            logger.info(
                f"Posted {len(parsed_tickers)} tickers to Pandora API "
                f"(status={resp.status_code})"
            )
            if resp.status_code != 200:
                logger.warning(f"Unexpected status: {resp.text[:200]}")
        except requests.exceptions.Timeout:
            logger.error("Timeout posting UW data to Pandora API")
        except Exception as e:
            logger.error(f"Failed to POST UW data: {e}")

    return client


# ── Main ─────────────────────────────────────────────────────

def main():
    cfg = load_openclaw_config()
    env_file = load_env_file(OPENCLAW_ENV_FILE)

    api_url = pick_env("PANDORA_API_URL", cfg, env_file) or DEFAULT_PANDORA_API_URL
    api_key = pick_env("PIVOT_API_KEY", cfg, env_file)

    # Discord token: env var first, then openclaw.json channels.discord.token
    discord_token = pick_env("DISCORD_BOT_TOKEN", cfg, env_file)
    if not discord_token:
        discord_token = (
            ((cfg.get("channels") or {}).get("discord") or {}).get("token") or ""
        ).strip()

    if not api_key:
        logger.error("PIVOT_API_KEY is required")
        sys.exit(1)
    if not discord_token:
        logger.error("DISCORD_BOT_TOKEN not found in env, openclaw.json, or env file")
        sys.exit(1)

    logger.info(f"Starting UW Watcher Bot — API: {api_url}")
    bot = create_bot(api_url, api_key)
    bot.run(discord_token, log_handler=None)


if __name__ == "__main__":
    main()
