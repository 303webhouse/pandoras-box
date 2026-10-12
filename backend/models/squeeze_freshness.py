"""Is a squeeze score recent enough to add its bonus? — R-IV.867(c), HYDRA P1.

THE DEFECT. `signals/pipeline.py` looked up `squeeze_scores` by ticker and added +4 or +8 to the
signal's score on `composite_score >= 20`, with NO freshness condition at all. `squeeze_scores`
holds one upserted row per ticker, so a row that stopped being refreshed keeps its last value
forever and keeps paying the bonus forever. Short interest is a twice-monthly figure and
days-to-cover moves with volume: a score from weeks ago is not a weak signal, it is a different
market. The bonus was being paid on it.

WHY A TRADING DAY AND NOT 24 HOURS. The collector runs on market days. Measured in hours, every
Monday morning would read as two days stale and the bonus would vanish for the whole session
through no fault of the data; measured in trading days, Friday's score is one day old on Monday,
which is what it actually is. The rule is therefore: the score must have been written on or
after the PREVIOUS TRADING DAY, in ET, relative to the session being scored.

FAIL CLOSED, AND SAY SO. Three things can make freshness unanswerable: no timestamp, a timestamp
with no timezone, and a date outside the enumerated market calendar (which raises rather than
guessing). In every one of them this returns NOT FRESH with a reason. That direction is the safe
one for a BONUS -- the signal simply does not get its +4, which is the status quo this ruling
restores -- whereas the opposite direction is the bug itself: a score of unknown age paying out
as though it were today's. A reason is returned alongside, never just False, because "no bonus
because the score is old" and "no bonus because nobody wrote a timestamp" are different facts
and only one of them is a data-collection problem.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# The ruling's window: "older than one trading day" is ignored.
MAX_AGE_TRADING_DAYS = 1

# The qualifying bar, unchanged by this ruling -- restated here only so the decision and the
# thresholds it is paired with live in one module.
MIN_COMPOSITE = 20.0
HIGH_COMPOSITE = 30.0
BONUS_HIGH = 8
BONUS_LOW = 4

REASON_NO_TIMESTAMP = "no updated_at recorded"
REASON_NAIVE = "updated_at has no timezone — refusing to assume one"
REASON_NO_CALENDAR = "market calendar cannot place the date"


def bonus_for(composite_score: Optional[float]) -> int:
    """The bonus a composite score earns, before any freshness test. 0 when it does not qualify."""
    try:
        cs = float(composite_score if composite_score is not None else 0)
    except (TypeError, ValueError):
        return 0
    if cs < MIN_COMPOSITE:
        return 0
    return BONUS_HIGH if cs >= HIGH_COMPOSITE else BONUS_LOW


def cutoff_date(as_of: date) -> Optional[date]:
    """The oldest ET date a score may carry and still count. None when the calendar cannot say.

    One trading day back, so on a Monday this is the preceding Friday and Friday's score counts.
    """
    from stable_engine.market_calendar import CalendarHorizonError, previous_trading_day

    try:
        d = as_of
        for _ in range(MAX_AGE_TRADING_DAYS):
            d = previous_trading_day(d)
        return d
    except CalendarHorizonError:
        return None
    except Exception:                                               # noqa: BLE001
        return None


def is_fresh(updated_at: Optional[datetime], *,
             now: Optional[datetime] = None) -> Tuple[bool, str]:
    """(fresh?, reason). `now` is injectable so a test never depends on the wall clock."""
    if updated_at is None:
        return False, REASON_NO_TIMESTAMP
    if updated_at.tzinfo is None or updated_at.tzinfo.utcoffset(updated_at) is None:
        # Guessing UTC here would be wrong by up to a day at the boundary, and the boundary is
        # the only place this decision is interesting.
        return False, REASON_NAIVE

    now = now or datetime.now(ET)
    today_et = now.astimezone(ET).date()
    score_et = updated_at.astimezone(ET).date()

    cutoff = cutoff_date(today_et)
    if cutoff is None:
        return False, REASON_NO_CALENDAR

    if score_et >= cutoff:
        return True, "written %s, cutoff %s" % (score_et, cutoff)
    return False, "stale: written %s, cutoff %s" % (score_et, cutoff)


def decide(composite_score: Optional[float], updated_at: Optional[datetime], *,
           now: Optional[datetime] = None) -> Tuple[int, Optional[str]]:
    """(bonus, skipped_reason).

    `skipped_reason` is set ONLY when a score that WOULD have paid out was refused on freshness
    — the case worth recording, because it is the one that used to pay silently. A score that
    never qualified is not a skip; it is an ordinary miss, and conflating the two would bury the
    signal this ruling is looking for in noise.
    """
    bonus = bonus_for(composite_score)
    if bonus == 0:
        return 0, None
    fresh, reason = is_fresh(updated_at, now=now)
    if fresh:
        return bonus, None
    return 0, reason
