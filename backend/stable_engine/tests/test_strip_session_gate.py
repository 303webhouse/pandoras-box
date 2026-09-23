"""The index strip must span the two sessions it claims to. No DB, no network.

Regression for the 2026-09-23 P0: Yahoo's /1d endpoint omitted 2026-09-22 — a
full trading session — for every US ETF on the strip. The old code took the last
two ROWS of the frame and called them today and yesterday, so it computed each
"1-day" change across 09-21 -> 09-23 and served it with a fresh timestamp and a
green health dot. Every symbol was wrong by exactly its own 09-22 return:

    QQQ  served +0.024%   true -0.69%    (sign inverted)
    IWM  served -0.632%   true -1.15%
    DIA  served -0.718%   true -0.39%
    SPY  served -0.492%   true -0.45%    (close only because 09-22 was flat)

Run:  PYTHONPATH=backend python -m pytest backend/stable_engine/tests
"""

from datetime import date, datetime

import pandas as pd
import pytest

from stable_engine.strip import _closes_by_session, _resolve, session_pair

# The real frame served on 2026-09-23, with the real gap.
CLOSES = {
    "QQQ": {date(2026, 9, 17): 716.1737, date(2026, 9, 18): 720.6990,
            date(2026, 9, 21): 741.4700, date(2026, 9, 23): 742.2445},
    "SPY": {date(2026, 9, 17): 760.7110, date(2026, 9, 18): 761.6900,
            date(2026, 9, 21): 773.5000, date(2026, 9, 23): 769.9400},
}
CUR, PRIOR = date(2026, 9, 23), date(2026, 9, 22)
# Recovered from Yahoo's intraday bars; matches the independent live quote (747.46).
QQQ_TRUE_PRIOR_CLOSE = 747.465


def _pct(last, base):
    return round((last / base - 1.0) * 100, 3)


def test_the_gap_is_what_inverted_the_sign():
    """Documents the defect: the last two ROWS are not the last two SESSIONS."""
    ordered = sorted(CLOSES["QQQ"])
    positional = _pct(CLOSES["QQQ"][ordered[-1]], CLOSES["QQQ"][ordered[-2]])
    truthful = _pct(CLOSES["QQQ"][CUR], QQQ_TRUE_PRIOR_CLOSE)
    assert ordered[-2] == date(2026, 9, 21) != PRIOR      # iloc[-2] is not yesterday
    assert positional > 0 and truthful < 0               # and the sign flips on it
    assert abs(positional - truthful) > 0.7              # by ~0.8 percentage points


def test_missing_prior_session_yields_no_number_and_a_reason():
    last, base, reason = _resolve(CLOSES["QQQ"], CUR, PRIOR, None)
    assert last == CLOSES["QQQ"][CUR]        # today's price is still sourceable
    assert base is None                      # but the change is not
    assert reason and str(PRIOR) in reason   # and the reason names the session


def test_recovered_prior_close_restores_the_true_change():
    last, base, reason = _resolve(CLOSES["QQQ"], CUR, PRIOR, QQQ_TRUE_PRIOR_CLOSE)
    assert reason is None
    assert base == QQQ_TRUE_PRIOR_CLOSE
    assert _pct(last, base) == pytest.approx(-0.69, abs=0.02)   # not +0.02


def test_a_present_prior_session_is_used_directly():
    by = dict(CLOSES["SPY"]); by[PRIOR] = 773.38
    last, base, reason = _resolve(by, CUR, PRIOR, 999.0)   # repair must not win
    assert reason is None and base == 773.38
    assert _pct(last, base) == pytest.approx(-0.45, abs=0.02)


def test_absent_current_session_is_never_backfilled_from_an_older_bar():
    by = {d: v for d, v in CLOSES["SPY"].items() if d != CUR}
    last, base, reason = _resolve(by, CUR, PRIOR, 773.38)
    assert last is None and base is None
    assert reason and str(CUR) in reason


def test_closes_by_session_keys_on_the_bar_date():
    idx = pd.to_datetime(["2026-09-21", "2026-09-23"])
    frame = pd.DataFrame({"Close": [741.47, 742.2445]}, index=idx)
    by = _closes_by_session(frame, "QQQ", single=True)
    assert by == {date(2026, 9, 21): 741.47, date(2026, 9, 23): 742.2445}
    assert PRIOR not in by


@pytest.mark.parametrize("now,cur,prior", [
    # RTH on a Wednesday -> today vs the prior session.
    (datetime(2026, 9, 23, 10, 30), date(2026, 9, 23), date(2026, 9, 22)),
    # Before the bell there is no bar for today, so the pair shifts back.
    (datetime(2026, 9, 23, 8, 0), date(2026, 9, 22), date(2026, 9, 21)),
    # Exactly the opening bell counts as open.
    (datetime(2026, 9, 23, 9, 30), date(2026, 9, 23), date(2026, 9, 22)),
    # Saturday -> Friday vs Thursday.
    (datetime(2026, 9, 26, 12, 0), date(2026, 9, 25), date(2026, 9, 24)),
    # Monday after Thanksgiving 2026-11-26 (holiday) -> skips it and the weekend.
    (datetime(2026, 11, 27, 10, 0), date(2026, 11, 27), date(2026, 11, 25)),
])
def test_session_pair_follows_the_market_calendar(now, cur, prior):
    assert session_pair(now) == (cur, prior)
