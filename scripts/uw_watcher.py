#!/usr/bin/env python3
"""
UW Watcher Bot — Parses Unusual Whales ticker updates from Discord.

Persistent Discord bot (discord.py) that watches #uw-flow-alerts for messages
from the UW Bot, parses structured text content into JSON, and POSTs to the
Pandora API for Redis caching and committee context consumption.

Uses Haiku vision for image parsing (~$0.01/image), pure text parsing for text messages.

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

import base64

import discord
import httpx
import requests

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

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


# ── Image Parsing (Haiku Vision) ──────────────────────────────

async def parse_uw_image(image_url: str, anthropic_key: str) -> list[dict] | None:
    """
    Download a UW image/chart and send to Haiku for structured data extraction.
    Returns list of parsed ticker dicts or None if parsing fails.
    Cost: ~$0.01-0.02 per image (Haiku vision).
    """
    if not anthropic_key:
        logger.warning("No ANTHROPIC_API_KEY — cannot parse UW images")
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            img_resp = await client.get(image_url)
            if img_resp.status_code != 200:
                logger.warning("Failed to download UW image: HTTP %s", img_resp.status_code)
                return None

            image_bytes = img_resp.content
            content_type = img_resp.headers.get("content-type", "image/png")
            if "jpeg" in content_type or "jpg" in content_type:
                media_type = "image/jpeg"
            elif "gif" in content_type:
                media_type = "image/gif"
            elif "webp" in content_type:
                media_type = "image/webp"
            else:
                media_type = "image/png"

            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        async with httpx.AsyncClient(timeout=30.0) as client:
            haiku_resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_b64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": (
                                        "Extract all options flow data from this Unusual Whales chart/table. "
                                        "Return ONLY a JSON array (no markdown, no backticks) where each element has: "
                                        '{"ticker": "AAPL", "volume": 50000, "premium": 12000000, '
                                        '"direction": "BULLISH" or "BEARISH" or "NEUTRAL", '
                                        '"contract_type": "CALL" or "PUT" or "MIXED", '
                                        '"strike": 150.0 or null, "expiry": "2026-04-17" or null, '
                                        '"notes": "brief description of the flow"}. '
                                        "If the image is not an options flow chart, return an empty array []."
                                    ),
                                },
                            ],
                        }
                    ],
                },
            )

            if haiku_resp.status_code != 200:
                logger.warning("Haiku API error: %s %s", haiku_resp.status_code, haiku_resp.text[:200])
                return None

            haiku_data = haiku_resp.json()
            text = ""
            for block in haiku_data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            parsed = json.loads(text)
            if isinstance(parsed, list) and len(parsed) > 0:
                logger.info("Haiku parsed %d entries from UW image", len(parsed))
                return parsed
            return None

    except json.JSONDecodeError as e:
        logger.warning("Haiku returned non-JSON: %s", e)
        return None
    except Exception as e:
        logger.error("UW image parsing failed: %s", e)
        return None


# ── Discord Bot ──────────────────────────────────────────────

def create_bot(api_url: str, api_key: str, anthropic_key: str = "") -> discord.Client:
    """Create the Discord bot with message content intent."""
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    client._anthropic_key = anthropic_key

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

        # Parse image messages via Haiku (attachments = charts, embeds = sweep alerts)
        if not message.content:
            image_url = None

            if message.attachments:
                for att in message.attachments:
                    if att.content_type and att.content_type.startswith("image/"):
                        image_url = att.url
                        break

            if not image_url and message.embeds:
                for embed in message.embeds:
                    if embed.image and embed.image.url:
                        image_url = embed.image.url
                        break
                    if embed.thumbnail and embed.thumbnail.url:
                        image_url = embed.thumbnail.url
                        break

            if not image_url:
                logger.info("UW message with no parseable content or images")
                return

            logger.info("Parsing UW image via Haiku: %s", image_url[:80])
            parsed_entries = await parse_uw_image(image_url, client._anthropic_key)

            if not parsed_entries:
                logger.info("No flow data extracted from UW image")
                return

            haiku_tickers = []
            for entry in parsed_entries:
                ticker = (entry.get("ticker") or "").upper()
                if not ticker or len(ticker) > 5:
                    continue

                direction = (entry.get("direction") or "NEUTRAL").upper()
                premium = entry.get("premium") or 0

                haiku_tickers.append({
                    "ticker": ticker,
                    "price": None,
                    "change_pct": None,
                    "volume": entry.get("volume") or 0,
                    "pc_ratio": None,
                    "put_volume": None,
                    "call_volume": None,
                    "total_premium": premium if isinstance(premium, int) else 0,
                    "flow_sentiment": direction if direction in ("BULLISH", "BEARISH") else None,
                    "flow_premium": None,
                    "flow_pct": None,
                })

            if haiku_tickers:
                payload = {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "source": "uw_image_haiku",
                    "tickers": haiku_tickers,
                }
                try:
                    resp = requests.post(
                        f"{api_url}/api/uw/ticker-updates",
                        json=payload,
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=10,
                    )
                    logger.info(
                        "Posted %d Haiku-parsed tickers from UW image (status=%s)",
                        len(haiku_tickers), resp.status_code,
                    )
                except Exception as e:
                    logger.error("Failed to POST Haiku-parsed UW data: %s", e)

            return

        # Parse Ticker Updates from message content
        lines = message.content.strip().split("\n")
        parsed_tickers = []
        for line in lines:
            line = line.strip()
            if line.startswith("<t:"):
                continue
            line = line.replace("**", "")
            result = parse_ticker_update(line)
            if result:
                parsed_tickers.append(result)

        if not parsed_tickers:
            logger.info(f"No parseable tickers in UW message ({len(lines)} lines)")
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
    anthropic_key = pick_env("ANTHROPIC_API_KEY", cfg, env_file)
    if not anthropic_key:
        logger.warning("ANTHROPIC_API_KEY not set — UW image parsing will be disabled")
    bot = create_bot(api_url, api_key, anthropic_key)
    bot.run(discord_token, log_handler=None)


if __name__ == "__main__":
    main()
