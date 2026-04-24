"""
Tests for sector_rotation_3_10.py — sector ETF lookup and INDEX sentinel.

Day-0 calibration brief (docs/codex-briefs/brief-raschke-day0-calibration.md):
  - Mapped tickers return the correct sector ETF's cached reading.
  - INDEX sentinel (SPY, QQQ, etc.) returns None — sector-agnostic.
  - Unmapped tickers return None — not an error condition.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import indicators.sector_rotation_3_10 as sr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_XLK_READING = {"sector_etf": "XLK", "osc_fast": 0.12, "osc_slow": 0.08, "osc_cross": 0}
_FAKE_XLF_READING = {"sector_etf": "XLF", "osc_fast": -0.05, "osc_slow": -0.02, "osc_cross": -1}


def _run(coro):
    """Run a coroutine synchronously for sync-style test assertions."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _patch_cache(cache_state: dict):
    """Return a context manager that stubs the sector cache and skips refresh."""
    return patch.multiple(
        "indicators.sector_rotation_3_10",
        _sector_cache=cache_state,
        _refresh_if_stale=AsyncMock(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_nvda_maps_to_xlk():
    """NVDA should resolve to the XLK cache reading."""
    cache = {"XLK": _FAKE_XLK_READING, "XLF": _FAKE_XLF_READING}
    with _patch_cache(cache):
        result = _run(sr.get_sector_3_10_for_ticker("NVDA"))
    assert result is not None
    assert result["sector_etf"] == "XLK"


def test_jpm_maps_to_xlf():
    """JPM should resolve to the XLF cache reading."""
    cache = {"XLK": _FAKE_XLK_READING, "XLF": _FAKE_XLF_READING}
    with _patch_cache(cache):
        result = _run(sr.get_sector_3_10_for_ticker("JPM"))
    assert result is not None
    assert result["sector_etf"] == "XLF"


def test_spy_returns_none_index_sentinel():
    """SPY maps to INDEX sentinel — get_sector_3_10_for_ticker must return None."""
    cache = {"XLK": _FAKE_XLK_READING}
    with _patch_cache(cache):
        result = _run(sr.get_sector_3_10_for_ticker("SPY"))
    assert result is None


def test_unknown_ticker_returns_none():
    """Unmapped ticker returns None — not an error, just no sector context."""
    cache = {"XLK": _FAKE_XLK_READING}
    with _patch_cache(cache):
        # Patch sector_rs import so it doesn't interfere
        with patch.dict("sys.modules", {"scanners.sector_rs": None}):
            result = _run(sr.get_sector_3_10_for_ticker("UNKNOWN_TICKER_XYZ"))
    assert result is None
