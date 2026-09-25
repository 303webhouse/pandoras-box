"""THE session calendar — which session an instant falls in. R-IV.566(e)3.

Four answers, and they are a vocabulary rather than a boolean:

    regular       09:30-16:00 ET on a session
    pre_market    04:00-09:30 ET on a session
    after_hours   16:00-20:00 ET on a session
    closed        everything else, and every minute of a non-session day

WHY THIS MODULE EXISTS. There were already two `is_rth` implementations that did not
agree. `jobs/stable_jobs.is_rth` reads `dt.hour` straight off whatever it is handed
and calls holidays "best-effort", so it answers on a UTC datetime as though it were
ET and says a Thanksgiving 10:00 is a trading session.
`integrations/uw_governor._is_rth` converts properly and consults the holiday
calendar. A signal tagged by the first and a quota gated by the second would disagree
about the same minute, and the River's whole drop/hold policy (R-IV.565) keys on this
answer -- an intraday signal is dropped or kept on it.

So: one author, built on `market_calendar`, which holds holidays as DATA with a loud
failure past its horizon rather than a computed rule that answers confidently for any
year.

FAILING SAFE MEANS DIFFERENT THINGS TO DIFFERENT CALLERS, so this module does not
choose for them. It returns `None` when the calendar cannot answer, and each caller
says what that means: the governor fails OPEN (gating a live caller on a calendar
error turns a data problem into an outage), while a signal tagger should fail to
`closed`-or-unknown rather than silently claim a session.

NOT MODELLED, deliberately: early closes. `market_calendar` says so too. A half day
reads as a regular session until 16:00, which is wrong by three hours twice a year,
and is stated here rather than discovered.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

REGULAR = "regular"
PRE_MARKET = "pre_market"
AFTER_HOURS = "after_hours"
CLOSED = "closed"

SESSIONS = (REGULAR, PRE_MARKET, AFTER_HOURS, CLOSED)

# The boundaries, in ET. Inclusive of the open, exclusive of the close, so 16:00:00
# is the first instant of after-hours and never both.
PRE_MARKET_OPEN = time(4, 0)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
AFTER_HOURS_CLOSE = time(20, 0)


def to_et(instant: datetime) -> datetime:
    """The instant on the exchange's clock.

    A NAIVE datetime is read as UTC, because that is what this database stores: ten
    of the twelve timestamp columns on `signals` are `timestamp without time zone`
    holding UTC-naive values. Reading them as local is the RV1 defect itself, and a
    helper that repeated it here would tag every overnight signal with the wrong
    session.
    """
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(ET)


def session_at(instant: Optional[datetime]) -> Optional[str]:
    """Which session the instant falls in, or None when it cannot be decided.

    None means the calendar could not answer -- past its stated horizon, or no
    instant at all. It is NOT `closed`: "the market was shut" and "nobody knows" are
    different claims, and a tagger that collapses them would drop a signal on the
    strength of a missing answer.
    """
    if instant is None:
        return None
    try:
        et = to_et(instant)
        from stable_engine.market_calendar import is_trading_day_or_none

        trading = is_trading_day_or_none(et.date())
    except Exception:  # noqa: BLE001
        return None
    if trading is None:
        return None
    if not trading:
        return CLOSED
    t = et.time()
    if REGULAR_OPEN <= t < REGULAR_CLOSE:
        return REGULAR
    if PRE_MARKET_OPEN <= t < REGULAR_OPEN:
        return PRE_MARKET
    if REGULAR_CLOSE <= t < AFTER_HOURS_CLOSE:
        return AFTER_HOURS
    return CLOSED


def is_rth(instant: Optional[datetime]) -> Optional[bool]:
    """True only during a regular session. None when the calendar cannot answer.

    Tri-state on purpose: a caller that needs a boolean must say which way an
    unreadable calendar falls, rather than inheriting whichever way this module
    happened to round.
    """
    s = session_at(instant)
    return None if s is None else s == REGULAR


def is_outside_regular_hours(instant: Optional[datetime]) -> Optional[bool]:
    """The question R-IV.565's drop/hold policy actually asks."""
    s = session_at(instant)
    return None if s is None else s != REGULAR
