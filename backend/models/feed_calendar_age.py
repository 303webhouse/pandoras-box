"""Feed age in TRADING DAYS, derived from the calendar — R-IV.871(c).

THE DEFECT. `nightly` and `provisional` run on weekdays only, and their feed carried a 26-hour
SLO with no notion of a weekend. So from late Saturday until Monday night's pass landed,
`/health` reported `degraded` with both jobs `flatline` and `consecutive_failures = 0` -- they
had not failed, they had not been due. Roughly one day a week, every week.

The cost is not the noise itself, it is R-IV.127: a genuine nightly failure on a Wednesday was
indistinguishable from the weekly cry of wolf. An alarm that is wrong every weekend is an alarm
nobody reads on Wednesday.

AGE IN HOURS IS THE WRONG UNIT, AND A WEEKDAY LIST IS THE WRONG FIX. The ruling is explicit:
derive it from the calendar. A restated `{"Mon".."Fri"}` set would be a second copy of the
market calendar, and the two would drift the first time a holiday fell on a weekday -- the same
"one fact, several writers" shape as the cache pins and the suppress set.

SO THE QUESTION IS NOT "HOW OLD IS THIS" BUT "HAS IT RUN FOR THE MOST RECENT SESSION THAT
EXPECTED IT". A job that runs after the close has a window per session; the newest session whose
window has already passed is what it owes. That formulation answers both cases with one rule:

  Sunday, last ran Friday 21:00    -> owes Friday    -> Friday >= Friday -> FINE
  Wednesday 10:00, last ran Monday -> owes Tuesday   -> Monday < Tuesday -> OVERDUE

The weekend is quiet because Saturday and Sunday are not sessions, not because they are listed
anywhere. And a weekday miss is visible the next morning, which is the half of this that
actually matters.

IT CAN REFUSE. Past the enumerated calendar horizon this returns None -- not False -- so the
caller falls back to the old hour-based SLO rather than silently declaring everything healthy.
None is not False, and it is certainly not True (market_calendar's own doctrine).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Jobs whose cadence is defined by the market calendar, keyed by JOB name rather than feed:
# `nightly` and `provisional` share one feed but owe their sessions at different times, so a
# per-feed rule could not describe both. `last_window_et` is the latest time in a session by
# which that job should have run (provisional runs 08:00, 09:45 and 16:05 -- the last is what
# makes it overdue). `grace_sessions` tolerates that many additional missed sessions before
# calling it; 0 means "the next morning".
CALENDAR_CADENCE: Dict[str, Dict] = {
    "nightly":     {"last_window_et": (21, 0), "grace_sessions": 0},
    "provisional": {"last_window_et": (16, 5), "grace_sessions": 0},
}


def is_calendar_cadence(job_name: str) -> bool:
    return job_name in CALENDAR_CADENCE


def expected_session(job_name: str, now_et: datetime) -> Optional[date]:
    """The newest session whose run window has already passed. None if the calendar cannot say.

    Note this walks the MARKET calendar, so a holiday Monday is skipped and Tuesday morning asks
    for Friday's pass rather than accusing the job of missing a session that did not exist.
    """
    from stable_engine.market_calendar import (
        CalendarHorizonError, is_trading_day, previous_trading_day,
    )

    cfg = CALENDAR_CADENCE.get(job_name)
    if cfg is None:
        return None
    hh, mm = cfg["last_window_et"]
    try:
        today = now_et.date()
        if is_trading_day(today) and (now_et.hour, now_et.minute) >= (hh, mm):
            d = today
        else:
            d = previous_trading_day(today)
        for _ in range(int(cfg.get("grace_sessions") or 0)):
            d = previous_trading_day(d)
        return d
    except CalendarHorizonError:
        return None
    except Exception:                                               # noqa: BLE001
        return None


def is_overdue(job_name: str, last_success_at: Optional[datetime], *,
               now_et: Optional[datetime] = None) -> Tuple[Optional[bool], str]:
    """(overdue?, reason). None means "cannot say" -- the caller keeps its existing rule.

    A reason always accompanies the verdict: "quiet because it is Sunday" and "quiet because it
    died on Wednesday" are different facts, and only one of them is an incident.
    """
    if job_name not in CALENDAR_CADENCE:
        return None, "not a calendar-cadence job"

    now_et = now_et or datetime.now(ET)
    expected = expected_session(job_name, now_et)
    if expected is None:
        return None, "market calendar cannot place %s" % now_et.date()

    if last_success_at is None:
        # Never recorded. Overdue rather than unknown: a job with a session owing and no record
        # of ever completing one is exactly the thing this is for.
        return True, "never recorded a successful pass (owes session %s)" % expected

    tz = last_success_at.tzinfo
    last_et = (last_success_at.astimezone(ET) if tz is not None else
               last_success_at.replace(tzinfo=ET))
    last_session = last_et.date()

    if last_session >= expected:
        return False, "ran for session %s (owes %s)" % (last_session, expected)

    from stable_engine.market_calendar import trading_days_between
    try:
        missed = trading_days_between(last_session, expected)
    except Exception:                                               # noqa: BLE001
        missed = None
    return True, ("missed %s session(s): last ran for %s, owes %s"
                  % (missed if missed is not None else "?", last_session, expected))
