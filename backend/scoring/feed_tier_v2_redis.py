"""
Redis helpers for feed-tier v2 shadow mode.

  pythia_tiebreaker_check() — bounded 2/ticker/day Redis counter
  path_b_stack_check()      — multi-scanner window dedup
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Pythia tiebreaker ─────────────────────────────────────────────────────────
# Redis key: pythia_tiebreaker:{ticker}:{utc_date}  (expires at midnight + buffer)
PYTHIA_TIEBREAKER_MAX_PER_DAY = 2
_TIEBREAKER_TTL = 90000  # 25h — outlasts one UTC day with buffer

# ── Path B — multi-scanner stack ──────────────────────────────────────────────
# Redis key: signal_stack:{ticker}:{timeframe_class}
# Value: JSON list of {scanner, signal_id, ts_ms} entries
# TTL = window length (intraday: 7200s = 2h, daily: 28800s = 8h trading session)
PATH_B_INTRADAY_WINDOW_SEC = 7200   # 2 hours
PATH_B_DAILY_WINDOW_SEC    = 28800  # 1 trading session (~8h)
PATH_B_RACE_THRESHOLD_MS   = 100    # log race events when two scanners fire within 100ms


def _utc_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _timeframe_class(signal_data: Dict[str, Any]) -> str:
    """Classify signal timeframe as 'intraday' or 'daily'."""
    tf = (signal_data.get("timeframe") or "").lower()
    if any(x in tf for x in ("1d", "daily", "swing", "d1")):
        return "daily"
    return "intraday"


async def pythia_tiebreaker_check(
    ticker: str,
    consume: bool = True,
) -> Tuple[bool, int]:
    """
    Check whether the Pythia tiebreaker quota allows a promotion for this ticker today.

    Args:
        ticker:  signal ticker symbol
        consume: if True and quota allows, increment the counter (default True)

    Returns:
        (allowed, current_count_after)
        allowed = True if count after increment would be <= PYTHIA_TIEBREAKER_MAX_PER_DAY
    """
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        key = f"pythia_tiebreaker:{ticker}:{_utc_date_str()}"

        current = await client.get(key)
        current_count = int(current) if current else 0

        if current_count >= PYTHIA_TIEBREAKER_MAX_PER_DAY:
            logger.debug(
                "Pythia tiebreaker rejected for %s — count=%d (max %d/day)",
                ticker, current_count, PYTHIA_TIEBREAKER_MAX_PER_DAY,
            )
            return False, current_count

        if consume:
            new_count = await client.incr(key)
            await client.expire(key, _TIEBREAKER_TTL)
            logger.debug(
                "Pythia tiebreaker approved for %s — count now %d/%d",
                ticker, new_count, PYTHIA_TIEBREAKER_MAX_PER_DAY,
            )
            return True, new_count

        return True, current_count

    except Exception as exc:
        logger.warning("Pythia tiebreaker Redis check failed: %s — allowing by default", exc)
        return True, 0  # fail-open: don't block tiebreaker on Redis errors


async def path_b_stack_check(
    signal_data: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Push this signal onto the multi-scanner stack for its ticker+timeframe,
    then check whether ≥2 distinct scanners have fired within the window.

    Returns:
        (qualifies_path_b, race_note)
        qualifies_path_b — True if stack now has ≥2 distinct scanners
        race_note        — non-None string if two scanners fired within 100ms (log only)
    """
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()

        ticker    = (signal_data.get("ticker") or "UNKNOWN").upper()
        scanner   = (signal_data.get("strategy") or signal_data.get("signal_type") or "unknown")
        signal_id = signal_data.get("signal_id") or ""
        tf_class  = _timeframe_class(signal_data)
        window    = PATH_B_INTRADAY_WINDOW_SEC if tf_class == "intraday" else PATH_B_DAILY_WINDOW_SEC
        now_ms    = int(time.monotonic() * 1000)

        key = f"signal_stack:{ticker}:{tf_class}"

        # Push new entry
        entry = json.dumps({"scanner": scanner, "signal_id": signal_id, "ts_ms": now_ms})
        await client.lpush(key, entry)
        await client.expire(key, window)

        # Trim to last 20 entries (safety cap)
        await client.ltrim(key, 0, 19)

        # Fetch all entries in the list
        raw_entries = await client.lrange(key, 0, -1)
        cutoff_ms   = now_ms - (window * 1000)

        scanners_in_window = set()
        race_note = None
        prev_ts_ms = None

        for raw in raw_entries:
            try:
                e = json.loads(raw)
                ts = e.get("ts_ms", 0)
                if ts >= cutoff_ms:
                    scanners_in_window.add(e.get("scanner", ""))
                    # Race detection
                    if prev_ts_ms is not None and abs(ts - prev_ts_ms) <= PATH_B_RACE_THRESHOLD_MS:
                        race_note = (
                            f"Path B race: {ticker} two scanners within "
                            f"{abs(ts - prev_ts_ms)}ms"
                        )
                    prev_ts_ms = ts
            except (json.JSONDecodeError, KeyError):
                continue

        qualifies = len(scanners_in_window) >= 2

        if race_note:
            logger.info(race_note)

        if qualifies:
            logger.debug(
                "Path B qualified: %s %s — %d distinct scanners in %ds window: %s",
                ticker, tf_class, len(scanners_in_window), window, scanners_in_window,
            )

        return qualifies, race_note

    except Exception as exc:
        logger.warning("Path B stack check failed: %s — skipping Path B", exc)
        return False, None
