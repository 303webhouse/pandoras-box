"""Stater Swap v2 S-2 (R-1) — hot-reload loader for `crypto_gate_config`.

Loader contract (brief §5.3): read the max-id row; in-process cache with a
60s TTL; every `crypto_regime_log`/`crypto_gate_shadow` row stamps the
`config_version` it used. Hot-reload = INSERT a new row (never UPDATE in
place — prior versions are the audit trail; rollback = re-INSERT an older
payload). No write endpoint ships in S-2 — config changes are SQL-only.

Fail-open to the last-known-good cached version on a transient DB error
(this is shadow-only evidence collection, not a live gate — availability
matters more than perfect freshness here). Fails loud (raises) only on a
cold start with nothing cached yet, since serving nothing would be worse
than a visible startup error.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60
_cache: Dict[str, Any] = {"version": None, "config": None, "loaded_at": 0.0}


async def get_gate_config() -> Tuple[int, dict]:
    """Return (config_version, config_dict). Cached for up to 60s."""
    now = time.monotonic()
    if _cache["config"] is not None and (now - _cache["loaded_at"]) < _TTL_SECONDS:
        return _cache["version"], _cache["config"]

    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, config FROM crypto_gate_config ORDER BY id DESC LIMIT 1"
            )
        if row is None:
            raise RuntimeError("crypto_gate_config has no rows -- seed missing")

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
                "crypto_gate_config refresh failed, serving stale cached version %s: %s",
                _cache["version"], exc,
            )
            return _cache["version"], _cache["config"]
        logger.error("crypto_gate_config cold-start load failed, no cache to fall back to: %s", exc)
        raise
