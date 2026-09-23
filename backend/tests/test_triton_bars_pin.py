"""R-IV.489(a) — Triton's bars are pinned to yfinance for the registered window.

Until 04f6480 Triton ran on yfinance by ACCIDENT: UW yielded no usable
regular-session bar, so every row from 2026-09-14 took the R-IV.324 fallback.
04f6480 repaired the UW path for every consumer and silently un-pinned Triton —
measured 2026-09-23 19:1xZ, `triton_grader.bars` read state=primary
primary_ok=27 subs=0, back on UW with the window still open.

A population whose bar vendor changes mid-window is not one population. These
tests assert the pin holds WHATEVER UW returns, including when UW is perfectly
healthy — which is precisely the case the accident never covered.

Run:  PYTHONPATH=backend python -m pytest backend/tests/test_triton_bars_pin.py
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import triton_shadow_common as tsc

YF_BARS = [{"c": 100.0, "t": 1789084800000, "provider": "yfinance"},
           {"c": 101.0, "t": 1789171200000, "provider": "yfinance"}]
UW_BARS = [{"market_time": "r", "close": 999.0, "date": "2026-09-22"},
           {"market_time": "r", "close": 998.0, "date": "2026-09-21"}]


def test_the_window_end_is_the_registered_date():
    assert tsc.TRITON_BARS_PIN_UNTIL == date(2026, 11, 6)


@pytest.mark.parametrize("d,pinned", [
    (date(2026, 9, 23), True),    # tonight's run
    (date(2026, 11, 5), True),
    (date(2026, 11, 6), True),    # INCLUSIVE — the last session of the window
    (date(2026, 11, 7), False),   # lapses on its own, no second deploy
])
def test_the_pin_is_dated_and_inclusive(d, pinned):
    assert tsc.triton_bars_pinned(d) is pinned


@pytest.mark.asyncio
async def test_a_healthy_uw_does_not_defeat_the_pin(monkeypatch):
    """The case the accident never covered: UW returns good 'r' bars."""
    called = {"uw": 0}

    async def fake_get_ohlc(*a, **k):
        called["uw"] += 1
        return list(UW_BARS)

    async def fake_yf(ticker):
        return list(YF_BARS)

    monkeypatch.setattr("integrations.uw_api.get_ohlc", fake_get_ohlc)
    monkeypatch.setattr("integrations.uw_api.get_bars_yfinance", fake_yf)

    idx, prov = await tsc.fetch_r_close_index("SPY", 25, session_date=date(2026, 9, 23))
    assert prov == "yfinance"
    assert called["uw"] == 0, "the pin must make NO UW request at all"
    assert 999.0 not in idx.values(), "a UW close reached a pinned series"


@pytest.mark.asyncio
async def test_a_pinned_run_that_gets_nothing_does_not_fall_through_to_uw(monkeypatch):
    """Empty yfinance means SKIP. Falling back to UW would breach the window."""
    called = {"uw": 0}

    async def fake_get_ohlc(*a, **k):
        called["uw"] += 1
        return list(UW_BARS)

    async def fake_yf(ticker):
        return []

    monkeypatch.setattr("integrations.uw_api.get_ohlc", fake_get_ohlc)
    monkeypatch.setattr("integrations.uw_api.get_bars_yfinance", fake_yf)

    idx, prov = await tsc.fetch_r_close_index("SPY", 25, session_date=date(2026, 9, 23))
    assert idx == {} and prov == tsc.PROVIDER_NONE
    assert called["uw"] == 0


@pytest.mark.asyncio
async def test_after_the_window_uw_is_used_again(monkeypatch):
    """The pin is a window, not a permanent rewiring of the grader."""
    async def fake_get_ohlc(*a, **k):
        return list(UW_BARS)

    async def fake_yf(ticker):
        return list(YF_BARS)

    monkeypatch.setattr("integrations.uw_api.get_ohlc", fake_get_ohlc)
    monkeypatch.setattr("integrations.uw_api.get_bars_yfinance", fake_yf)

    idx, prov = await tsc.fetch_r_close_index("SPY", 25, session_date=date(2026, 11, 9))
    assert prov == "uw"
    assert idx[date(2026, 9, 22)] == 999.0


def test_the_default_clock_is_the_exchange_not_utc():
    """The grader runs 20:00 ET, which is already the NEXT UTC day.

    Defaulting to a UTC date would lapse the pin a day early and hand the last
    session of the registered window to UW. This asserts the module reaches for
    an ET clock, so the default cannot silently become utcnow().
    """
    import ast, inspect, textwrap
    fn = ast.parse(textwrap.dedent(inspect.getsource(tsc.triton_bars_pinned))).body[0]
    body = ast.unparse(ast.Module(body=fn.body[1:], type_ignores=[]))  # drop the docstring
    assert "ET" in body, "the default clock is not the exchange's"
    assert "utc" not in body.lower(), "a UTC clock would lapse the pin a day early"
    assert str(tsc.ET) == "America/New_York"
