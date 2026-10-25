"""R-IV.1392(d) / R-IV.1441(d): the ARTEMIS_SHORT regrade's replay. Constructed bars, no network.

Pins: the walk is score_signals' own (imported, and the live loop calls the same function); the
replay freezes the FIRST night's verdict (a T1 touch is final even if the stop is hit later);
EXPIRED after MAX_SIGNAL_AGE_DAYS; the post-fire slice (a stop touched only on the fire day does
not count); a fire after the 21:00 ET run waits for the next night; and the change tally.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pandas as pd

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from jobs import artemis_regrade as R                                 # noqa: E402
from jobs import score_signals as S                                   # noqa: E402


def frame(rows):
    """rows: [(date, high, low, close)] -> a frame shaped like yfinance's daily history."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, *_ in rows]).tz_localize("America/New_York")
    return pd.DataFrame([r[1:] for r in rows], index=idx, columns=["High", "Low", "Close"])


def short(created, **kw):
    row = {"created_at": created, "direction": "SHORT", "entry": 100.0, "stop": 105.0,
           "t1": 95.0, "t2": 90.0, "invalidation_level": None}
    row.update(kw)
    return row


# Mon 2026-10-05 15:00 ET = 19:00 UTC (stored naive UTC, as signal_outcomes does)
FIRE = dt.datetime(2026, 10, 5, 19, 0)


def test_the_live_loop_and_the_regrade_share_ONE_walk():
    src = (_BACKEND / "jobs" / "score_signals.py").read_text(encoding="utf-8")
    assert "walk_outcome(\n                df, direction, entry, stop, t1, t2, invalidation)" in src.replace("\r\n", "\n")
    assert R.walk_outcome is S.walk_outcome
    assert R.REGRADE_GRADER_VERSION == S.GRADER_VERSION == "score_signals@6c4f943e"


def test_a_stop_touched_ONLY_on_the_fire_day_does_not_count_after_the_fix():
    bars = frame([("2026-10-05", 106, 99, 100), ("2026-10-06", 101, 94, 94.5)])
    assert R.replay(bars, short(FIRE), until=dt.date(2026, 10, 9))["outcome"] == "HIT_T1"
    assert R.replay(bars, short(FIRE), until=dt.date(2026, 10, 9), sliced=False)["outcome"] == "STOPPED_OUT"


def test_the_FIRST_nights_verdict_is_final_T1_then_stop_stays_HIT_T1():
    bars = frame([("2026-10-05", 100, 99, 100), ("2026-10-06", 100, 94, 95),
                  ("2026-10-07", 106, 95, 105)])
    r = R.replay(bars, short(FIRE), until=dt.date(2026, 10, 9))
    assert r["outcome"] == "HIT_T1" and r["night"] == "2026-10-06" and r["outcome_price"] == 95.0


def test_EXPIRED_once_older_than_the_age_cap_without_a_verdict():
    days = pd.bdate_range("2026-10-05", "2026-10-23")
    bars = frame([(d.date().isoformat(), 101, 99, 100) for d in days])
    r = R.replay(bars, short(FIRE), until=dt.date(2026, 10, 23))
    assert r["outcome"] == "EXPIRED" and r["days_to_outcome"] == S.MAX_SIGNAL_AGE_DAYS + 1


def test_PENDING_when_no_night_has_produced_a_verdict_yet():
    bars = frame([("2026-10-05", 101, 99, 100), ("2026-10-06", 101, 99, 100)])
    assert R.replay(bars, short(FIRE), until=dt.date(2026, 10, 6))["outcome"] == "PENDING"


def test_a_fire_after_the_21_00_ET_run_waits_for_the_next_night():
    late = dt.datetime(2026, 10, 6, 1, 30)            # Mon 21:30 ET
    bars = frame([("2026-10-05", 100, 99, 100), ("2026-10-06", 100, 94, 95)])
    r = R.replay(bars, short(late), until=dt.date(2026, 10, 9))
    assert r["night"] != "2026-10-05"


def test_nights_follow_the_graders_own_NYSE_calendar():
    nights = R.trading_nights(dt.date(2026, 11, 23), dt.date(2026, 11, 30))
    assert dt.date(2026, 11, 26) not in nights          # Thanksgiving
    assert all(d.weekday() < 5 for d in nights)


def test_the_tally_reports_direction_of_change():
    t = R.tally([("STOPPED_OUT", "HIT_T1"), ("HIT_T2", "STOPPED_OUT"), ("HIT_T1", "HIT_T2"),
                 ("PENDING", "EXPIRED"), ("HIT_T1", "HIT_T1")])
    assert t == {"loss->win": 1, "win->loss": 1, "win->win (HIT_T1->HIT_T2)": 1,
                 "other->other (PENDING->EXPIRED)": 1, "unchanged": 1}
