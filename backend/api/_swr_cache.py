"""
SWRCache — Stale-While-Revalidate cache for FastAPI route responses.

Pattern: serve recent cached data immediately; refresh asynchronously when the
cache enters the "stale-but-servable" window. Falls back to synchronous compute
on a complete miss (or when Redis is unavailable). A per-key asyncio.Lock
prevents thundering-herd refresh storms.

Built for the perf-architecture brief:
  - Phase 1c canaries this against /flow/radar (low-stakes endpoint, default_ttl=3,
    stale_ttl=10).
  - Phase 3 applies it to /v2/positions and /signals/active with user-scoped keys.

Usage:
    from api._swr_cache import SWRCache

    _swr = SWRCache(redis_client, default_ttl=3, stale_ttl=10)
    data, age = await _swr.get_or_refresh(
        "flow:radar:global",
        compute_fn=_compute_flow_radar,
    )
    return {**data, "as_of": int(time.time() - age), "cache_age_seconds": age}

Cache key namespacing:
  The caller owns the key. The wrapper prefixes "swr:" to the Redis key.
  For user-scoped data (Phase 3), include user_id in the key:
      key = f"positions:v1:{user_id}:{status}"

JSON serialization:
  compute_fn must return a JSON-serializable structure. The cache uses
  json.dumps internally to store payloads. Use sanitize_for_json from
  database.redis_client to scrub numpy types if needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Redis key prefix for all SWR entries. Keep stable across deploys — changing
# it invalidates every cache entry at once.
_SWR_PREFIX = "swr:"


class SWRCache:
    """Stale-while-revalidate wrapper over a Redis-backed cache."""

    def __init__(self, redis_client, default_ttl: int = 5, stale_ttl: int = 30):
        """
        Args:
            redis_client: async Redis client (decode_responses=True expected).
                May be None — in that case every call falls through to compute.
            default_ttl: "fresh" window in seconds. Within this age, cached
                data is served as-is with no refresh trigger.
            stale_ttl: "stale-but-servable" window in seconds, layered on top
                of default_ttl. Within (ttl, ttl+stale_ttl), cached data is
                served immediately AND a background refresh is scheduled.
                Beyond ttl+stale_ttl, the entry expires from Redis and the
                next call computes synchronously.
        """
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.stale_ttl = stale_ttl
        self._refresh_locks: Dict[str, asyncio.Lock] = {}

    async def get_or_refresh(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[Any]],
        ttl: Optional[int] = None,
        stale_ttl: Optional[int] = None,
    ) -> Tuple[Any, int]:
        """
        Returns (data, age_seconds).

        Behavior:
          - Cache fresh (age < ttl): return cached data, age >= 0.
          - Cache stale-but-servable (ttl <= age < ttl+stale_ttl): return
            cached data, schedule background refresh.
          - Cache missing or expired beyond stale window: compute synchronously,
            store, return (data, 0).
          - Redis unavailable, get error, or corrupt entry: compute synchronously,
            return (data, 0). No store attempt if Redis is None.
        """
        # SWRDBG (Phase 1c cache-hit investigation, temporary) START
        _t_entry = time.time()
        # SWRDBG END
        ttl = ttl if ttl is not None else self.default_ttl
        stale_ttl = stale_ttl if stale_ttl is not None else self.stale_ttl

        cached_raw = None
        if self.redis is not None:
            try:
                cached_raw = await self.redis.get(_SWR_PREFIX + key)
            except Exception as e:
                logger.warning("SWR get failed for %s: %s — falling through to compute", key, e)
                cached_raw = None

        # SWRDBG: report cache GET outcome
        _t_after_get = time.time()
        logger.info(
            "SWRDBG[%s] action=cache_get cached=%s elapsed_ms=%.1f",
            key, bool(cached_raw), (_t_after_get - _t_entry) * 1000.0,
        )

        if cached_raw:
            try:
                cached = json.loads(cached_raw)
                age = int(time.time() - cached["timestamp"])
                if age < ttl:
                    logger.info(
                        "SWRDBG[%s] action=return served_from=fresh_cache age=%d total_ms=%.1f",
                        key, age, (time.time() - _t_entry) * 1000.0,
                    )
                    return cached["data"], age
                if age < ttl + stale_ttl:
                    # Stale but servable; refresh in background, return cached now
                    asyncio.create_task(self._refresh(key, compute_fn, ttl, stale_ttl))
                    logger.info(
                        "SWRDBG[%s] action=return served_from=stale_cache age=%d refresh_scheduled=true total_ms=%.1f",
                        key, age, (time.time() - _t_entry) * 1000.0,
                    )
                    return cached["data"], age
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning("SWR cache for %s is corrupt: %s — recomputing", key, e)

        # SWRDBG: about to compute synchronously
        _t_before_compute = time.time()
        logger.info(
            "SWRDBG[%s] action=compute_start elapsed_ms=%.1f",
            key, (_t_before_compute - _t_entry) * 1000.0,
        )
        data = await compute_fn()
        _t_after_compute = time.time()
        await self._store(key, data, ttl, stale_ttl)
        logger.info(
            "SWRDBG[%s] action=return served_from=compute compute_ms=%.1f total_ms=%.1f",
            key, (_t_after_compute - _t_before_compute) * 1000.0,
            (time.time() - _t_entry) * 1000.0,
        )
        return data, 0

    async def _refresh(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[Any]],
        ttl: int,
        stale_ttl: int,
    ) -> None:
        """Background refresh. Skipped if another refresh for the same key is in flight."""
        lock = self._refresh_locks.setdefault(key, asyncio.Lock())
        if lock.locked():
            logger.info("SWRDBG[%s] action=refresh_skipped reason=locked", key)  # SWRDBG
            return
        async with lock:
            _t0 = time.time()  # SWRDBG
            logger.info("SWRDBG[%s] action=refresh_start", key)  # SWRDBG
            try:
                data = await compute_fn()
                await self._store(key, data, ttl, stale_ttl)
                logger.info(  # SWRDBG
                    "SWRDBG[%s] action=refresh_done elapsed_ms=%.1f",
                    key, (time.time() - _t0) * 1000.0,
                )
            except Exception as e:
                logger.error("SWR background refresh failed for %s: %s", key, e)

    async def _store(self, key: str, data: Any, ttl: int, stale_ttl: int) -> None:
        if self.redis is None:
            return
        try:
            payload = json.dumps({"timestamp": time.time(), "data": data})
            await self.redis.set(_SWR_PREFIX + key, payload, ex=ttl + stale_ttl)
        except Exception as e:
            logger.warning("SWR store failed for %s: %s", key, e)
