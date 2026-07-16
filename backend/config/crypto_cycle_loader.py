"""S-3 Phase 2 — hot-reload loader for `crypto_cycle_config`.

Mirrors crypto_gate_loader.py exactly — same 60s TTL, same fail-open-to-stale
behavior, same append-only pattern. Config changes are SQL-only (INSERT a new row);
rollback = re-INSERT an older payload. No write endpoint ships in S-3.

gating_enabled stays False for the dial (shadow observation only).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60
_cache: Dict[str, Any] = {"version": None, "config": None, "loaded_at": 0.0}


async def get_cycle_config() -> Tuple[int, dict]:
    """Return (config_version, config_dict). Cached for up to 60s."""
    now = time.monotonic()
    if _cache["config"] is not None and (now - _cache["loaded_at"]) < _TTL_SECONDS:
        return _cache["version"], _cache["config"]

    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, config FROM crypto_cycle_config ORDER BY id DESC LIMIT 1"
            )
        if row is None:
            raise RuntimeError("crypto_cycle_config has no rows -- seed missing")

        config = row["config"]
        if isinstance(config, str):
            config = json.loads(config)

        _cache["version"] = row["id"]
        _cache["config"] = config
        _cache["loaded_at"] = now
        return row["id"], config
    except Exception as exc:
        if _cache["config"] is not None:
            logger.warning(
                "crypto_cycle_config refresh failed, serving stale cached version %s: %s",
                _cache["version"], exc,
            )
            return _cache["version"], _cache["config"]
        logger.error("crypto_cycle_config cold-start load failed, no cache to fall back to: %s", exc)
        raise
