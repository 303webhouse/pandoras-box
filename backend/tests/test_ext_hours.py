"""Overnight futures + extended-hours ETFs (stable_engine/ext_hours.py).

The load-bearing assertions:
  * every percent is measured from the price AT 16:00 ET of the right session
    (Tue night -> Tue; Mon pre-market -> Fri; the day after a holiday skips it);
  * the futures base is the bar that ENDS at 16:00 (stamped 15:55), and a base
    from an hour earlier is refused rather than used;
  * a delayed feed that has not reached the close yet waits, it does not serve an
    afternoon move under an overnight label;
  * ETFs use the official daily close, read by DATE (not shifted through UTC);
  * the loop and the flatline check are quiet exactly when futures are shut.
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stable_engine import ext_hours as eh  # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def _frame(series: dict) -> pd.DataFrame:
    """A yfinance-shaped (ticker, field) frame from {symbol: {ET datetime: close}}."""
    cols = {}
    for sym, pts in series.items():
        idx = pd.DatetimeIndex([pd.Timestamp(t).tz_convert("UTC") for t in pts])
        cols[(sym, "Close")] = pd.Series(list(pts.values()), index=idx)
    df = pd.DataFrame(cols)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def _daily(closes: dict) -> pd.DataFrame:
    """{symbol: {date: close}} with a naive date index, as Yahoo serves /1d."""
    cols = {}
    for sym, pts in closes.items():
        idx = pd.DatetimeIndex([pd.Timestamp(d) for d in pts])
        cols[(sym, "Close")] = pd.Series(list(pts.values()), index=idx)
    df = pd.DataFrame(cols)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


# ── base_session ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("now,expected", [
    (_et(2026, 9, 29, 22, 0), date(2026, 9, 29)),   # Tue night -> Tue close
    (_et(2026, 9, 29, 16, 0), date(2026, 9, 29)),   # 16:00:00 is after the close
    (_et(2026, 9, 29, 15, 59), date(2026, 9, 28)),  # still in session -> Mon
    (_et(2026, 9, 28, 7, 0), date(2026, 9, 25)),    # Mon pre-market -> Fri
    (_et(2026, 9, 27, 19, 0), date(2026, 9, 25)),   # Sunday evening -> Fri
    (_et(2026, 9, 8, 7, 0), date(2026, 9, 4)),      # day after Labor Day -> Fri
    (_et(2026, 9, 7, 20, 0), date(2026, 9, 4)),     # on the holiday itself -> Fri
])
def test_base_session(now, expected):
    assert eh.base_session(now) == expected


def test_base_session_refuses_naive():
    with pytest.raises(ValueError):
        eh.base_session(datetime(2026, 9, 29, 22, 0))


# ── windows ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("now,fetch,futures", [
    (_et(2026, 9, 29, 22, 0), True, True),     # Tue night
    (_et(2026, 9, 29, 17, 30), True, False),   # daily futures halt; ETF after-hours still on
    (_et(2026, 10, 2, 18, 0), True, False),    # Fri after 17:00: futures shut, ETFs trade to 20:00
    (_et(2026, 10, 2, 20, 30), False, False),  # Fri night
    (_et(2026, 10, 3, 12, 0), False, False),   # Saturday
    (_et(2026, 10, 4, 17, 0), False, False),   # Sunday before the open
    (_et(2026, 10, 4, 18, 5), True, True),     # Sunday open
])
def test_windows(now, fetch, futures):
    assert eh.window_open(now) is fetch
    assert eh.futures_open(now) is futures


# ── compute_rows ──────────────────────────────────────────────────────────────
def _tuesday_frame(es_1555=7732.5, include_1555=True, last=(22, 0, 7742.5)):
    es = {_et(2026, 9, 29, 15, 50): 7735.0}
    if include_1555:
        es[_et(2026, 9, 29, 15, 55)] = es_1555
    es[_et(2026, 9, 29, 16, 0)] = 7736.25
    es[_et(2026, 9, 29, last[0], last[1])] = last[2]
    spy = {_et(2026, 9, 29, 15, 55): 764.29, _et(2026, 9, 29, 19, 55): 766.07}
    return _frame({"ES=F": es, "SPY": spy})


def _row(out, sym):
    return next(r for r in out["rows"] if r["symbol"] == sym)


def test_futures_measured_from_the_bar_ending_at_4pm():
    out = eh.compute_rows(_tuesday_frame(), None, _et(2026, 9, 29, 22, 10))
    es = _row(out, "ES=F")
    assert es["base"] == 7732.5            # the 15:55 bar's close, NOT the 16:00 bar's
    assert es["pct"] == round((7742.5 / 7732.5 - 1) * 100, 3)
    assert es["bar_ts"] == _et(2026, 9, 29, 22, 0).astimezone(timezone.utc)
    assert es["leads"] == "SPY" and es["reason"] is None
    assert es["spark"] and es["spark"][-1] == es["pct"]


def test_futures_base_falls_back_only_within_the_last_quarter_hour():
    out = eh.compute_rows(_tuesday_frame(include_1555=False), None, _et(2026, 9, 29, 22, 10))
    assert _row(out, "ES=F")["base"] == 7735.0   # the 15:50 bar

    early = _frame({"ES=F": {_et(2026, 9, 29, 15, 0): 7700.0, _et(2026, 9, 29, 22, 0): 7742.5}})
    es = _row(eh.compute_rows(early, None, _et(2026, 9, 29, 22, 10)), "ES=F")
    assert es["pct"] is None and "4 PM" in es["reason"]


def test_delayed_feed_waits_for_the_close():
    frame = _frame({"ES=F": {_et(2026, 9, 29, 15, 45): 7735.0, _et(2026, 9, 29, 15, 50): 7734.0}})
    es = _row(eh.compute_rows(frame, None, _et(2026, 9, 29, 16, 3)), "ES=F")
    assert es["pct"] is None and es["reason"].startswith(eh.WAITING)


def test_etf_uses_official_close_by_date():
    daily = _daily({"SPY": {date(2026, 9, 28): 760.0, date(2026, 9, 29): 764.2}})
    spy = _row(eh.compute_rows(_tuesday_frame(), daily, _et(2026, 9, 29, 22, 10)), "SPY")
    assert spy["base"] == 764.2                  # not 760.0 (a UTC-shifted date) nor 764.29
    assert spy["ext_session"] == "after_hours"
    assert spy["pct"] == round((766.07 / 764.2 - 1) * 100, 3)


def test_etf_falls_back_to_4pm_bar_and_labels_pre_market():
    frame = _frame({"SPY": {_et(2026, 9, 25, 15, 55): 700.0, _et(2026, 9, 28, 7, 0): 707.0}})
    spy = _row(eh.compute_rows(frame, None, _et(2026, 9, 28, 7, 5)), "SPY")
    assert spy["base"] == 700.0 and spy["ext_session"] == "pre_market" and spy["pct"] == 1.0


def test_no_bars_is_a_reason_never_a_zero():
    out = eh.compute_rows(_frame({"ES=F": {_et(2026, 9, 29, 15, 55): 7732.5}}), None,
                          _et(2026, 9, 29, 22, 0))
    for sym in ("NQ=F", "QQQ"):
        r = _row(out, sym)
        assert r["pct"] is None and r["reason"]


# ── flatline ──────────────────────────────────────────────────────────────────
def test_off_hours_flatline_quiet_in_session_and_weekend(monkeypatch):
    from stable_engine import job_status as js

    class _Fixed(datetime):
        now_value = None

        @classmethod
        def now(cls, tz=None):
            return cls.now_value.astimezone(tz) if tz else cls.now_value

    monkeypatch.setattr(js, "datetime", _Fixed)
    _Fixed.now_value = _et(2026, 9, 29, 11, 0)             # regular session
    assert js.feed_flatline("ext_hours", 99999) is False
    _Fixed.now_value = _et(2026, 10, 3, 12, 0)             # Saturday
    assert js.feed_flatline("ext_hours", 99999) is False
    _Fixed.now_value = _et(2026, 9, 29, 16, 10)            # 10 min after the close
    assert js.feed_flatline("ext_hours", 99999) is False
    _Fixed.now_value = _et(2026, 9, 29, 23, 0)             # overnight, quiet 1h
    assert js.feed_flatline("ext_hours", 3600) is True
    assert js.feed_flatline("ext_hours", 300) is False


# ─────────── the bar-order assumption, made explicit (CC-BUILD, R-IV.615)

def test_the_close_series_is_sorted_so_iloc_minus_one_is_the_newest_bar():
    """`_series` never sorted, and every `iloc[-1]` below it means "the newest bar" — which is
    only true of an ascending index.

    yfinance returns ascending today, so this changed no behaviour. It is here because this repo
    has already shipped exactly this assumption and been wrong: `fetch_crypto_ohlc` returns
    vendor-order bars (UW and OKX descending, Binance ascending) and positional slices read the
    oldest bar as the newest. Unsorted here would take an overnight percent from a bar hours old
    and report it as current, with nothing raising.
    """
    import pandas as pd

    from stable_engine import ext_hours

    ts = pd.to_datetime(["2026-09-30 19:55", "2026-09-30 20:25", "2026-09-30 20:10"],
                        utc=True)
    frame = pd.DataFrame({"Close": [100.0, 103.0, 101.0]}, index=ts)
    out = ext_hours._series(frame, "ES=F", single=True)

    assert list(out.index) == sorted(out.index), "the series came back unsorted"
    assert float(out.iloc[-1]) == 103.0, "iloc[-1] did not return the newest bar"
    # POSITIVE CONTROL: the shuffled input really was out of order, so a pass here is the sort
    # working rather than the fixture already being sorted.
    assert list(ts) != sorted(ts)
