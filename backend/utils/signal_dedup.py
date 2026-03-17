"""
Signal Dedup — Redis-based atomic deduplication for webhook signals.

Prevents the same strategy from firing duplicate signals for the same
ticker+direction within a cooldown window. Uses Redis SET NX for
atomicity (no race conditions on rapid-fire webhooks).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cooldown periods by timeframe
DEDUP_COOLDOWN_INTRADAY = 7200    # 2 hours for 1M-1H signals
DEDUP_COOLDOWN_DAILY = 28800      # 8 hours for daily signals
DEDUP_COOLDOWN_DEFAULT = 7200     # 2 hours fallback


def _get_cooldown_seconds(timeframe: str) -> int:
    """Get dedup cooldown based on signal timeframe."""
    tf = (timeframe or "1H").upper()
    if tf in ("D", "1D", "DAILY", "W", "1W", "WEEKLY"):
        return DEDUP_COOLDOWN_DAILY
    return DEDUP_COOLDOWN_INTRADAY


async def is_duplicate_signal(
    ticker: str,
    strategy: str,
    direction: str,
    timeframe: str = "1H",
) -> bool:
    """
    Check if a signal is a duplicate using Redis SET NX.
    Returns True if this is a duplicate (should be skipped).
    Returns False if this is the first signal (proceed to process).

    Atomic: SET NX ensures only one signal wins even under concurrent webhooks.
    """
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()

        key = f"dedup:{ticker.upper()}:{strategy.upper()}:{direction.upper()}"
        ttl = _get_cooldown_seconds(timeframe)

        # SET NX: returns True if key was SET (first signal), False if already exists (duplicate)
        was_set = await redis.set(key, "1", ex=ttl, nx=True)

        if was_set:
            logger.debug(f"Dedup: {key} — first signal, proceeding (TTL={ttl}s)")
            return False  # Not a duplicate
        else:
            logger.info(f"Dedup: {key} — duplicate within {ttl}s cooldown, skipping")
            return True  # Is a duplicate

    except Exception as e:
        logger.warning(f"Dedup check failed (allowing signal through): {e}")
        return False  # Fail open — don't block signals if Redis is down
