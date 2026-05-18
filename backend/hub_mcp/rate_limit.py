"""Per-token rate limiting for the MCP server.

Two windows are checked per call:
  - 60 requests/minute  (rolling 60-second window)
  - 5,000 requests/day  (rolling 24-hour window)

Either being exceeded triggers a rate-limit response.

`mcp_ping` is exempt — Olympus calls it once per pass and Nick's expectation
is that the health check never consumes the data quota.

Implementation: in-process token-bucket per token-hash. For v1, in-process
is acceptable — Railway runs a single web dyno. v2 should move to Redis
if we ever scale horizontally.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

LIMITS_PER_MINUTE = 60
LIMITS_PER_DAY = 5_000

EXEMPT_TOOLS = frozenset({"mcp_ping"})


def _token_key(token: str) -> str:
    """SHA-256 truncated to 16 hex chars — enough to disambiguate, never the full token."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


class _RollingCounter:
    """Rolling time-window counter. Thread-safe via Lock."""

    __slots__ = ("window_seconds", "events", "_lock")

    def __init__(self, window_seconds: int):
        self.window_seconds = window_seconds
        self.events: Deque[float] = deque()
        self._lock = threading.Lock()

    def record_and_count(self, now: float) -> int:
        """Append `now`, evict old entries, return count inside window."""
        cutoff = now - self.window_seconds
        with self._lock:
            while self.events and self.events[0] < cutoff:
                self.events.popleft()
            self.events.append(now)
            return len(self.events)


class RateLimiter:
    """Per-token rate limiter with the two configured windows."""

    def __init__(self):
        self._per_token: Dict[str, Tuple[_RollingCounter, _RollingCounter]] = {}
        self._lock = threading.Lock()

    def _get_or_create(
        self, key: str
    ) -> Tuple[_RollingCounter, _RollingCounter]:
        with self._lock:
            counters = self._per_token.get(key)
            if counters is None:
                counters = (_RollingCounter(60), _RollingCounter(86_400))
                self._per_token[key] = counters
            return counters

    def check(self, token: str, tool_name: str) -> Optional[str]:
        """Record this call. Returns None if allowed, else a rate-limit error message."""
        if tool_name in EXEMPT_TOOLS:
            return None

        key = _token_key(token)
        minute_counter, day_counter = self._get_or_create(key)
        now = time.time()

        minute_count = minute_counter.record_and_count(now)
        day_count = day_counter.record_and_count(now)

        if minute_count > LIMITS_PER_MINUTE:
            return (
                f"Rate limit exceeded: {LIMITS_PER_MINUTE} requests/minute. "
                f"Retry in <60s."
            )
        if day_count > LIMITS_PER_DAY:
            return (
                f"Rate limit exceeded: {LIMITS_PER_DAY} requests/day. "
                f"Retry tomorrow."
            )
        return None


# Module-level singleton — single Railway dyno per the v1 scaling assumption.
limiter = RateLimiter()
