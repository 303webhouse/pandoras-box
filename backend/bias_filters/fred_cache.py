"""
Redis helpers for last-known-good FRED snapshots.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from database.redis_client import get_redis_client, sanitize_for_json

logger = logging.getLogger(__name__)

FRED_CACHE_TTL_SECONDS = int(os.getenv("FRED_CACHE_TTL_SECONDS", "172800"))


async def cache_fred_snapshot(cache_key: str, payload: Dict[str, Any]) -> None:
    """
    Persist a successful FRED fetch payload for fallback use.
    """
    try:
        client = await get_redis_client()
        if not client:
            return
        snapshot = {
            **payload,
            "fetched_at": payload.get("fetched_at") or datetime.utcnow().isoformat(),
        }
        await client.setex(
            cache_key,
            FRED_CACHE_TTL_SECONDS,
            json.dumps(sanitize_for_json(snapshot)),
        )
    except Exception as exc:
        logger.warning("FRED cache write failed for %s: %s", cache_key, exc)


async def load_fred_snapshot(cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Load the latest cached FRED payload if available.
    """
    try:
        client = await get_redis_client()
        if not client:
            return None
        raw = await client.get(cache_key)
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("FRED cache read failed for %s: %s", cache_key, exc)
        return None
