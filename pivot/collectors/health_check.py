"""
Heartbeat collector.
"""

from __future__ import annotations

import logging

from .base_collector import post_health

logger = logging.getLogger(__name__)


async def collect_and_post(factors_collected: int | None = None):
    try:
        return await post_health(status="ok", factors_collected=factors_collected)
    except Exception as exc:
        logger.warning(f"Failed to post health heartbeat: {exc}")
        return None
