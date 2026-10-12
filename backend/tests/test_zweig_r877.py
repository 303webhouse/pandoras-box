"""Zweig indicators, display-only (R-IV.877(b)): the published rules on synthetic paths, and one
real incremental update with only the database and the vendor stubbed."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from stable_engine import zweig as z


def _days(n, start=date(2024, 1, 1)):
    return [start + timedelta(days=i) for i in range(n)]


def test_advance_counts_skip_unchanged_and_missing():
    closes = pd.DataFrame({"A": [10, 11, 11], "B": [10, 9, np.nan], "C": [10, 10, 12]},
                          index=_days(3))
    c = z.advance_counts(closes)
    assert list(c.advancers) == [1, 1] and list(c.decliners) == [1, 0]
    assert c.adv_share.iloc[0] == 0.5 and c.adv_share.iloc[1] == 1.0


def test_a_thrust_fires_when_the_ema_crosses_040_to_0615_within_10_sessions():
    share = pd.Series([0.30] * 15 + [0.95] * 10, index=_days(25))
    bt = z.breadth_thrust(share)
    fired = list(bt.index[bt.bt_thrust])
    assert len(fired) == 1
    i = list(bt.index).index(fired[0])
    assert bt.bt_ema10.iloc[i] > 0.615 >= bt.bt_ema10.iloc[i - 1]
    lows = [j for j in range(i) if bt.bt_ema10.iloc[j] < 0.40]
    assert i - lows[-1] <= 10                                   # within the window
    assert bt.bt_state.iloc[i] == "THRUST"


def test_a_slow_climb_is_not_a_thrust():
    share = pd.Series([0.30] * 15 + list(np.linspace(0.40, 0.70, 60)), index=_days(75))
    assert not z.breadth_thrust(share).bt_thrust.any()


def _weekly(closes, start=date(2024, 1, 5)):            # a Friday
    return pd.Series(closes, index=[start + timedelta(weeks=i) for i in range(len(closes))])


def test_four_percent_buys_after_a_4pct_rise_and_sells_after_a_4pct_fall():
    fp = z.four_percent(_weekly([100, 98, 96, 100, 104, 103, 99.8, 99]))
    sig = fp[fp.fp_signal.notna()]
    # 96 is 4% under the first high (100): SELL; 100 is 4% over the low since (96): BUY;
    # 99.8 is 4% under the high since the buy (104 * 0.96 = 99.84): SELL
    assert list(sig.fp_signal) == ["SELL", "BUY", "SELL"]
    assert list(sig.vl_week_close) == [96, 100, 99.8]
    assert fp.fp_state.iloc[0] == "UNKNOWN"


def test_the_weekly_close_is_the_last_session_of_the_week():
    days = pd.bdate_range("2024-01-01", "2024-01-12")
    s = pd.Series(range(len(days)), index=days, dtype=float)
    fp = z.four_percent(s)
    assert [str(d) for d in fp.index] == ["2024-01-05", "2024-01-12"]


class _Cur:
    def __init__(self, stored, bars):
        self.stored, self.bars, self.sql = stored, bars, []
        self.rows = []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        if "FROM stable_zweig" in sql:
            self.rows = self.stored
        elif "FROM stable_daily_bars" in sql:
            self.rows = self.bars

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Conn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_one_incremental_update_appends_tonight_from_stored_bars(monkeypatch):
    days = [d.date() for d in pd.bdate_range("2020-01-01", periods=1200)]
    stored = [(d, 300, 200, 0.6) for d in days]                # >= 1000 rows: incremental mode
    last, new = days[-1], days[-1] + timedelta(days=3)
    bars = ([(t, last, 10.0) for t in ("A", "B", "C")]
            + [("A", new, 11.0), ("B", new, 9.0), ("C", new, 12.0)])
    cur = _Cur(stored, bars)
    written = []
    monkeypatch.setattr("stable_engine.db.connect", lambda: _Conn(cur))
    monkeypatch.setattr("stable_engine.universe.universe_tickers", lambda: ["A", "B", "C"])
    monkeypatch.setattr(z, "_yf_closes",
                        lambda t, s, e: pd.DataFrame({z.VALUE_LINE_SYMBOL: [100.0, 105.0]},
                                                     index=[last, new]))
    import psycopg2.extras as px
    monkeypatch.setattr(px, "execute_values", lambda c, sql, rows: written.extend(rows))

    out = z.run_zweig_update(until=new)
    assert out["mode"] == "incremental" and out["last_session"] == str(new)
    tonight = [r for r in written if r[0] == new]
    assert len(tonight) == 1
    d, adv, dec, share = tonight[0][:4]
    assert (adv, dec) == (2, 1) and abs(share - 2 / 3) < 1e-9
    assert out["sources"]["breadth_thrust"].startswith("SUBSTITUTE")
