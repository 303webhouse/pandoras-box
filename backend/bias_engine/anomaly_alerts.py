"""
Anomaly detection alert transport for bias-pipeline integrity events.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict

import aiohttp

logger = logging.getLogger(__name__)

ALERT_WEBHOOK = os.getenv("DISCORD_WEBHOOK_ALERTS")

_COLOR_MAP: Dict[str, int] = {
    "info": 0x3498DB,
    "warning": 0xF39C12,
    "critical": 0xE74C3C,
}


async def send_alert(title: str, description: str, severity: str = "warning") -> None:
    """
    Post a structured alert to Discord when data integrity degrades.
    """
    if not ALERT_WEBHOOK:
        logger.warning("DISCORD_WEBHOOK_ALERTS not configured; suppressed alert: %s", title)
        return

    payload = {
        "embeds": [
            {
                "title": title,
                "description": description[:3900],
                "color": _COLOR_MAP.get(severity, _COLOR_MAP["warning"]),
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]
    }

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(ALERT_WEBHOOK, json=payload) as response:
                if response.status >= 300:
                    body = await response.text()
                    logger.warning(
                        "Discord alert rejected (%s): %s",
                        response.status,
                        body[:300],
                    )
    except Exception as exc:
        logger.error("Failed to send anomaly alert '%s': %s", title, exc)
