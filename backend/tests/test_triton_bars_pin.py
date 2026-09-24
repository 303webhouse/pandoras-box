"""R-IV.497(d) — Triton's bar vendor is a property of the ROW, not of the run.

The first pin keyed on the RUN date. QUERY found the hole: a grader run after the
window closed would revert to UW and re-grade in-window rows on a vendor the
registration does not name. A row's vendor is decided by its own `fired_at`
session, so it holds whenever that row is graded — today, next month, or in a
backfill years from now.

Window of record (R-IV.485(b)): cohorts W1 (Tue 2026-09-15, T_clock) through W7
(ends Fri 2026-10-30) — 34 sessions. The seven Friday READS run to 2026-11-06,
one week behind their cohort (R-IV.485(a)). **The last read date is not the last
session**, and keying on it is exactly the earlier error.

Run:  PYTHONPATH=backend python -m pytest backend/tests/test_triton_bars_pin.py
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import triton_shadow_common as tsc

YF_BARS = [{"c": 100.0, "t": 1789084800000, "provider": "yfinance"},
           {"c": 101.0, "t": 1789171200000, "provider": "yfinance"}]
UW_BARS = [{"market_time": "r", "close": 999.0, "date": "2026-09-22"},
           {"market_time": "r", "close": 998.0, "date": "2026-09-21"}]


def test_the_window_is_the_registration_s_not_the_reader_s():
    assert tsc.TRITON_WINDOW_FIRST_SESSION == date(2026, 9, 15)   # T_clock
    assert tsc.TRITON_WINDOW_LAST_SESSION == date(2026, 10, 30)   # W7's last session


@pytest.mark.parametrize("session,pinned", [
    (date(2026, 9, 14), False),   # the day before T_clock
    (date(2026, 9, 15), True),    # T_clock — inclusive
    (date(2026, 9, 23), True),
    (date(2026, 10, 30), True),   # W7's last session — inclusive
    (date(2026, 10, 31), False),  # the day after
    (date(2026, 11, 6), False),   # the last READ date is NOT a cohort session
])
def test_the_pin_is_keyed_to_the_row_s_session(session, pinned):
    assert tsc.triton_row_pinned(session) is pinned


def test_a_datetime_is_accepted_as_well_as_a_date():
    """fired_at arrives as a timestamptz; it must not have to be converted first."""
    assert tsc.triton_row_pinned(datetime(2026, 9, 23, 13, 31, tzinfo=timezone.utc)) is True
    assert tsc.triton_row_pinned(datetime(2026, 11, 3, 13, 31, tzinfo=timezone.utc)) is False


def test_a_row_with_no_session_is_not_pinned():
    assert tsc.triton_row_pinned(None) is False


def test_the_pin_reads_no_clock():
    """THE REGRESSION QUERY FOUND. The old form keyed on the run date, so a run
    after the window reverted an in-window row to UW. Nothing here may consult
    the current time — if it did, the answer for a fixed row would change."""
    import ast, inspect, textwrap
    fn = ast.parse(textwrap.dedent(inspect.getsource(tsc.triton_row_pinned))).body[0]
    body = ast.unparse(ast.Module(body=fn.body[1:], type_ignores=[]))
    for forbidden in ("now", "today", "utcnow", "time"):
        assert forbidden not in body.lower(), (
            f"triton_row_pinned consults the clock ({forbidden!r}) — the pin must "
            "depend only on the row's own session")


@pytest.mark.asyncio
async def test_a_healthy_uw_does_not_defeat_the_pin(monkeypatch):
    """The case the original accident never exercised: UW returns good 'r' bars."""
    called = {"uw": 0}

    async def fake_get_ohlc(*a, **k):
        called["uw"] += 1
        return list(UW_BARS)

    async def fake_yf(ticker):
        return list(YF_BARS)

    monkeypatch.setattr("integrations.uw_api.get_ohlc", fake_get_ohlc)
    monkeypatch.setattr("integrations.uw_api.get_bars_yfinance", fake_yf)

    idx, prov = await tsc.fetch_r_close_index("SPY", 25, pinned=True)
    assert prov == "yfinance"
    assert called["uw"] == 0, "the pin made a UW request"
    assert 999.0 not in idx.values(), "a UW close reached a pinned series"


@pytest.mark.asyncio
async def test_a_pinned_fetch_that_gets_nothing_does_not_fall_through_to_uw(monkeypatch):
    called = {"uw": 0}

    async def fake_get_ohlc(*a, **k):
        called["uw"] += 1
        return list(UW_BARS)

    async def fake_yf(ticker):
        return []

    monkeypatch.setattr("integrations.uw_api.get_ohlc", fake_get_ohlc)
    monkeypatch.setattr("integrations.uw_api.get_bars_yfinance", fake_yf)

    idx, prov = await tsc.fetch_r_close_index("SPY", 25, pinned=True)
    assert idx == {} and prov == tsc.PROVIDER_NONE
    assert called["uw"] == 0


@pytest.mark.asyncio
async def test_an_unpinned_fetch_still_prefers_uw(monkeypatch):
    async def fake_get_ohlc(*a, **k):
        return list(UW_BARS)

    async def fake_yf(ticker):
        return list(YF_BARS)

    monkeypatch.setattr("integrations.uw_api.get_ohlc", fake_get_ohlc)
    monkeypatch.setattr("integrations.uw_api.get_bars_yfinance", fake_yf)

    idx, prov = await tsc.fetch_r_close_index("SPY", 25, pinned=False)
    assert prov == "uw"
    assert idx[date(2026, 9, 22)] == 999.0


def test_pinned_is_required_and_keyword_only():
    """No default. A default is how the run-date form answered for rows it had
    never looked at."""
    import inspect
    sig = inspect.signature(tsc.fetch_r_close_index)
    p = sig.parameters["pinned"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default is inspect.Parameter.empty
