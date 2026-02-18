"""
Compatibility wrapper for signal outcome tracking jobs.
"""

from __future__ import annotations

from jobs.score_signals import cleanup_stale_discovery_tickers, get_hit_rates, score_pending_signals

__all__ = [
    "score_pending_signals",
    "cleanup_stale_discovery_tickers",
    "get_hit_rates",
]

