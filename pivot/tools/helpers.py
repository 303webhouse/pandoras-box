"""
Shared helpers for market data tools.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _error_response(ticker: str, error: str) -> dict:
    """Standard error response dict."""
    return {
        "status": "error",
        "ticker": ticker,
        "error": str(error),
        "timestamp": _now_iso(),
    }
