"""PYTHIA feed health — R-IV.1037(c)2. rejecting / quiet / flowing, on RTH hours.

Every verdict is paired with a control, because each failure mode here has an opposite: a check
that always says `rejecting` is as useless as one that always says `flowing`, and a `quiet`
measured in WALL hours would call a healthy feed broken every evening.
"""
from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from models import pythia_feed_health as fh

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=ET)


# -- RTH arithmetic ---------------------------------------------------------------------

def test_rth_hours_inside_one_session():
    """10:00 -> 13:30 on a Wednesday is 3.5 hours, all of it inside RTH."""
    assert fh.rth_hours_between(_et(2026, 10, 14, 10), _et(2026, 10, 14, 13, 30)) == 3.5


def test_time_outside_RTH_does_not_count():
    """THE POINT OF THE WHOLE FILE. 16:05 -> 19:05 is three WALL hours and ZERO RTH hours:
    nothing could have arrived. A wall-hour threshold would call a healthy feed quiet every
    evening."""
    assert fh.rth_hours_between(_et(2026, 10, 14, 16, 5), _et(2026, 10, 14, 19, 5)) == 0.0
    # pre-open likewise
    assert fh.rth_hours_between(_et(2026, 10, 14, 4), _et(2026, 10, 14, 9)) == 0.0


def test_an_overnight_counts_only_the_two_sessions_it_touches():
    """15:30 Wed -> 10:30 Thu = 0.5 (Wed close) + 1.0 (Thu open) = 1.5, not 19."""
    assert fh.rth_hours_between(_et(2026, 10, 14, 15, 30), _et(2026, 10, 15, 10, 30)) == 1.5


def test_a_weekend_contributes_nothing():
    """Friday 15:00 -> Monday 10:00: 1.0 + 0.5 = 1.5 RTH hours across ~67 wall hours."""
    fri, mon = _et(2026, 10, 9, 15), _et(2026, 10, 12, 10)
    assert fri.weekday() == 4 and mon.weekday() == 0
    assert fh.rth_hours_between(fri, mon) == 1.5


def test_a_HOLIDAY_contributes_nothing():
    """2026-09-07 is Labor Day. Counting it would inflate elapsed RTH hours and call a healthy
    feed quiet -- the same calendar error that spent ~8 UW calls a night on a closed market."""
    from stable_engine.market_calendar import is_trading_day
    assert is_trading_day(date(2026, 9, 7)) is False
    # Friday 09-04 15:30 -> Tuesday 09-08 10:00 skips both the weekend AND Monday.
    assert fh.rth_hours_between(_et(2026, 9, 4, 15, 30), _et(2026, 9, 8, 10)) == 1.0


def test_it_is_never_negative_and_handles_None():
    assert fh.rth_hours_between(_et(2026, 10, 14, 13), _et(2026, 10, 14, 10)) == 0.0
    assert fh.rth_hours_between(None, _et(2026, 10, 14, 10)) == 0.0
    assert fh.rth_hours_between(_et(2026, 10, 14, 10), None) == 0.0


# -- the verdicts ----------------------------------------------------------------------

def test_one_rejection_since_the_last_accept_is_REJECTING():
    """No window needed: a refusal is POSITIVE evidence that alerts arrive and are refused.
    This is the v2.6 cutover -- 65 consecutive 401s that the session-based status called ok."""
    v = fh.classify(_et(2026, 10, 14, 14, 38), 1, now=_et(2026, 10, 14, 14, 40))
    assert v["feed_health"] == fh.REJECTING, v
    assert "arriving and are being refused" in v["basis"]


def test_rejecting_wins_even_when_an_event_arrived_seconds_ago():
    """THE ORDERING CONTROL. A fresh accepted event must not mask refusals -- 51 tickers
    rejected while one succeeded is still a broken feed."""
    v = fh.classify(_et(2026, 10, 14, 14, 38), 65, now=_et(2026, 10, 14, 14, 38, 30))
    assert v["feed_health"] == fh.REJECTING, v


def test_no_rejections_and_a_recent_event_is_FLOWING():
    v = fh.classify(_et(2026, 10, 14, 13), 0, now=_et(2026, 10, 14, 14))
    assert v["feed_health"] == fh.FLOWING, v
    assert v["rth_hours_since_last_accept"] == 1.0


def test_over_three_RTH_hours_with_no_rejections_is_QUIET():
    v = fh.classify(_et(2026, 10, 14, 10), 0, now=_et(2026, 10, 14, 14))
    assert v["rth_hours_since_last_accept"] == 4.0
    assert v["feed_health"] == fh.QUIET, v


def test_exactly_three_RTH_hours_is_still_FLOWING():
    """The threshold is "more than", so the boundary is not quiet. Without this pair an
    off-by-one that fired at exactly 3.0 would pass the test above."""
    v = fh.classify(_et(2026, 10, 14, 10), 0, now=_et(2026, 10, 14, 13))
    assert v["rth_hours_since_last_accept"] == 3.0
    assert v["feed_health"] == fh.FLOWING, v


def test_a_quiet_OVERNIGHT_is_not_quiet():
    """16:05 Wed with the last event at 14:38 Wed: 1.37 RTH hours, and the clock stops at the
    close. At 09:00 Thu it is STILL not quiet, because no RTH time has passed."""
    v = fh.classify(_et(2026, 10, 14, 14, 38), 0, now=_et(2026, 10, 15, 9))
    assert v["feed_health"] == fh.FLOWING, v
    assert v["rth_hours_since_last_accept"] < 3.0


def test_an_UNREADABLE_rejection_count_is_UNKNOWN_not_flowing():
    """None means NOT MEASURED. Letting it read as zero would make an unreadable count report
    a healthy feed -- the fake-healthy answer this register keeps finding."""
    v = fh.classify(_et(2026, 10, 14, 14), None, now=_et(2026, 10, 14, 15))
    assert v["feed_health"] == fh.UNKNOWN, v
    assert "NOT 'flowing'" in v["basis"]


def test_no_accepted_event_ever_and_no_rejections_is_UNKNOWN():
    v = fh.classify(None, 0, now=_et(2026, 10, 14, 15))
    assert v["feed_health"] == fh.UNKNOWN, v
    assert "nothing to judge" in v["basis"]


def test_every_verdict_carries_the_figures_it_was_decided_from():
    v = fh.classify(_et(2026, 10, 14, 10), 0, now=_et(2026, 10, 14, 14))
    for k in ("feed_health", "last_accepted_at", "last_accepted_at_et",
              "rejected_since_last_accept", "rth_hours_since_last_accept",
              "quiet_after_rth_hours", "basis"):
        assert k in v, k
    assert v["basis"]


def test_unknown_is_a_declared_state_not_an_accident():
    assert fh.UNKNOWN in fh.FEED_STATES
    assert set(fh.FEED_STATES) == {"rejecting", "quiet", "flowing", "unknown"}


def test_nothing_here_reads_a_clock_of_its_own():
    """`now` is injected so the verdicts are testable. A function that called
    datetime.now() internally could only be tested by waiting."""
    src = inspect.getsource(fh.classify)
    fn = ast.parse(src).body[0]
    doc = fn.body[0].value if fn.body and isinstance(fn.body[0], ast.Expr) else None
    code = chr(10).join(ast.unparse(n) for n in fn.body
                        if not (isinstance(n, ast.Expr) and n.value is doc))
    assert "now = now or" in code, "classify() must accept an injected now"
