"""
Discord webhook notifications for Pivot.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from collectors.config import (
    DISCORD_WEBHOOK_CRITICAL,
    DISCORD_WEBHOOK_SIGNALS,
    DISCORD_WEBHOOK_BRIEFS,
    DISCORD_WEBHOOK_CALENDAR,
    DISCORD_WEBHOOK_SYSTEM,
)

logger = logging.getLogger(__name__)

WEBHOOKS = {
    "critical": DISCORD_WEBHOOK_CRITICAL,
    "signals": DISCORD_WEBHOOK_SIGNALS,
    "briefs": DISCORD_WEBHOOK_BRIEFS,
    "calendar": DISCORD_WEBHOOK_CALENDAR,
    "system": DISCORD_WEBHOOK_SYSTEM,
}

COLORS = {
    "CRITICAL": 0xF44336,
    "HIGH": 0xFF9800,
    "MEDIUM": 0x4FC3F7,
    "TORO_MAJOR": 0x00E676,
    "TORO_MINOR": 0x66BB6A,
    "NEUTRAL": 0x78909C,
    "URSA_MINOR": 0xFF9800,
    "URSA_MAJOR": 0xF44336,
}


async def send_discord(
    channel: str,
    title: str,
    description: str,
    priority: str = "MEDIUM",
    content: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    webhook_url = WEBHOOKS.get(channel)
    if not webhook_url:
        logger.warning(f"Discord webhook not configured for channel={channel}")
        return

    color = COLORS.get(priority.upper(), COLORS["MEDIUM"])
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if data:
        embed["fields"] = [
            {"name": key, "value": str(value), "inline": True}
            for key, value in data.items()
        ]

    payload = {
        "username": "Pivot",
        "content": content,
        "embeds": [embed],
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code >= 400:
                logger.warning(f"Discord webhook failed: {resp.status_code} {resp.text}")
    except Exception as exc:
        logger.warning(f"Discord webhook error: {exc}")
