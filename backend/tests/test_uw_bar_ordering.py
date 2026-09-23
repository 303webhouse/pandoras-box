"""R-IV.487 — UW bars are newest-first, and they carry `date`, not `start_time`.

Two defects met here on 2026-09-23 and both published a wrong number as live:

  1. ORDER. UW serves /ohlc/1d newest-first. Every positional consumer in this
     repo was written for the ascending yfinance/Polygon convention, so
     `regular_bars[-1]` was the OLDEST bar. Measured on the live cache: 755 bars,
     252 regular, reg[-1] = 2025-09-23 close 663.21 and reg[-2] = 2025-09-24
     close 661.10 -> +0.32%, which is exactly what the macro strip published as
     "S&P 500" while SPY was 768.93 and -0.55% on the day.

  2. KEY NAME. A UW bar's session stamp is `date`. `_get_bars_via_uw` read only
     `start_time`, so ts_ms was always None and EVERY bar hit `continue` — the
     function returned [] for every ticker, every time. That empty list was read
     as "UW returned no regular-session bar", a vendor outage that never was.

Run:  PYTHONPATH=backend python -m pytest backend/tests/test_uw_bar_ordering.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations import uw_api


def _bar(d, close, mt="r"):
    return {"date": d, "close": close, "open": close, "high": close, "low": close,
            "market_time": mt, "total_volume": 1000, "volume": 1000}


# Newest-first, exactly as UW serves it.
DESCENDING = [
    _bar("2026-09-23", 768.925),
    _bar("2026-09-22", 773.38),
    _bar("2026-09-21", 773.50),
    _bar("2025-09-24", 661.10),
    _bar("2025-09-23", 663.21),
]


def test_a_uw_bar_has_no_start_time():
    """The assumption three call sites were built on, asserted as false."""
    assert "start_time" not in DESCENDING[0]
    assert uw_api._bar_date(DESCENDING[0]) == "2026-09-23"


def test_bar_date_ignores_neither_field():
    assert uw_api._bar_date({"start_time": "2026-09-23T20:00:00Z"}) == "2026-09-23T20:00:00Z"
    assert uw_api._bar_date({}) == ""          # sorts first, away from the [-1] slot


def test_sorting_puts_the_newest_bar_where_callers_look():
    ordered = sorted(DESCENDING, key=uw_api._bar_date)
    assert uw_api._bar_date(ordered[-1]) == "2026-09-23"
    assert uw_api._bar_date(ordered[-2]) == "2026-09-22"
    # The defect, stated: the vendor's own order put a year-old bar at [-1].
    assert uw_api._bar_date(DESCENDING[-1]) == "2025-09-23"


@pytest.mark.asyncio
async def test_regular_session_change_uses_the_two_newest_sessions(monkeypatch):
    async def fake_get_ohlc(ticker, candle_size="1d", lookback_days=30, caller="ohlc"):
        return sorted(DESCENDING, key=uw_api._bar_date)   # what get_ohlc now guarantees

    async def no_cache(*a, **k):
        return None

    monkeypatch.setattr(uw_api, "get_ohlc", fake_get_ohlc)
    monkeypatch.setattr(uw_api, "cache_get", no_cache)
    monkeypatch.setattr(uw_api, "cache_set", lambda *a, **k: _noop())

    res = await uw_api._get_regular_session_change("SPY")
    assert res is not None
    assert res["today_date"] == "2026-09-23"
    assert res["prev_date"] == "2026-09-22"
    assert res["today_close"] == 768.925
    assert res["prev_close"] == 773.38
    assert res["change_pct"] == pytest.approx(-0.576, abs=0.01)   # not +0.32
    assert res["change_pct"] < 0                                   # sign is the point


@pytest.mark.asyncio
async def test_descending_bars_are_refused_rather_than_inverted(monkeypatch):
    """Defence in depth: if ordering ever regresses, serve nothing, not a year-old change."""
    async def fake_get_ohlc(*a, **k):
        return list(DESCENDING)            # deliberately unsorted

    async def no_cache(*a, **k):
        return None

    monkeypatch.setattr(uw_api, "get_ohlc", fake_get_ohlc)
    monkeypatch.setattr(uw_api, "cache_get", no_cache)
    monkeypatch.setattr(uw_api, "cache_set", lambda *a, **k: _noop())

    assert await uw_api._get_regular_session_change("SPY") is None


async def _noop():
    return None


@pytest.mark.asyncio
async def test_bars_via_uw_keeps_every_bar_and_stamps_it_from_date(monkeypatch):
    async def fake_get_ohlc(*a, **k):
        return sorted(DESCENDING, key=uw_api._bar_date)

    monkeypatch.setattr(uw_api, "get_ohlc", fake_get_ohlc)

    out = await uw_api._get_bars_via_uw("SPY", None, None)
    assert out, "every bar was dropped — the start_time defect is back"
    assert len(out) == len(DESCENDING)          # nothing silently skipped
    assert [b["c"] for b in out][-1] == 768.925  # newest last, Polygon convention
    assert all(isinstance(b["t"], int) and b["t"] > 0 for b in out)
    assert out[0]["t"] < out[-1]["t"]            # ascending by t
