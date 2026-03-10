"""
Polygon.io Health Tracker — monitors API error rates.

Tracks success/failure counts in a rolling window. When error rate exceeds
threshold, logs a warning and optionally alerts Discord. Exposed via the
monitoring API for dashboard visibility.

Usage from Polygon integration files:
    from monitoring.polygon_health import record_polygon_call
    record_polygon_call(success=True)   # after successful API call
    record_polygon_call(success=False)  # after failed API call
"""

import logging
import time
from collections import deque
from typing import Dict

logger = logging.getLogger(__name__)

# Rolling window: keep last 100 calls with timestamps
_call_log: deque = deque(maxlen=100)

# Alert threshold: if >50% of last 10+ calls failed, Polygon is degraded
ERROR_RATE_THRESHOLD = 0.50
MIN_CALLS_FOR_ALERT = 10

# Cooldown: don't alert more than once per 30 min
_last_alert_time: float = 0
ALERT_COOLDOWN = 1800


def record_polygon_call(success: bool, endpoint: str = "") -> None:
    """Record a Polygon API call result."""
    _call_log.append({
        "time": time.time(),
        "success": success,
        "endpoint": endpoint,
    })


def get_polygon_health() -> Dict:
    """Get current Polygon health status from rolling window."""
    if not _call_log:
        return {
            "status": "no_data",
            "total_calls": 0,
            "error_rate": 0.0,
            "recent_errors": 0,
            "recent_successes": 0,
        }

    # Only consider calls from last 30 min
    cutoff = time.time() - 1800
    recent = [c for c in _call_log if c["time"] > cutoff]

    if not recent:
        return {
            "status": "idle",
            "total_calls": len(_call_log),
            "error_rate": 0.0,
            "recent_errors": 0,
            "recent_successes": 0,
        }

    successes = sum(1 for c in recent if c["success"])
    errors = len(recent) - successes
    error_rate = errors / len(recent) if recent else 0.0

    if len(recent) >= MIN_CALLS_FOR_ALERT and error_rate > ERROR_RATE_THRESHOLD:
        status = "degraded"
    elif errors > 0:
        status = "partial_errors"
    else:
        status = "healthy"

    return {
        "status": status,
        "total_calls": len(_call_log),
        "error_rate": round(error_rate, 3),
        "recent_errors": errors,
        "recent_successes": successes,
        "window_minutes": 30,
    }


def check_and_alert() -> bool:
    """Check if Polygon is degraded and should alert. Returns True if degraded."""
    global _last_alert_time
    health = get_polygon_health()

    if health["status"] == "degraded":
        now = time.time()
        if now - _last_alert_time > ALERT_COOLDOWN:
            _last_alert_time = now
            logger.warning(
                "Polygon.io DEGRADED: %d errors / %d calls (%.0f%%) in last 30 min",
                health["recent_errors"],
                health["recent_errors"] + health["recent_successes"],
                health["error_rate"] * 100,
            )
            return True
    return False
