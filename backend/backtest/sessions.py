"""Session arithmetic for grading.

THE ANCHOR SESSION of a signal is the session whose prices its entry belongs to:
  * fired on a trading day (any time, including pre-open and after the close): that day;
  * fired on a weekend or holiday: the previous trading day (the price seen then is that
    session's close).
T+n is the n-th trading day after the anchor, from the one market calendar -- never a
weekday count, never a tolerance. A date the calendar cannot answer for raises
CalendarHorizonError, and the caller records the row as ungraded for that reason.

History runs (engine.py) take their sessions from the vendor's own bar dates instead,
because the calendar is enumerated only from 2025.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from stable_engine import market_calendar as cal

ET = ZoneInfo("America/New_York")
SESSION_CLOSE = time(16, 0)
BARS_SETTLED_AFTER = time(16, 20)   # a session's daily bar is not read before this


def as_utc(ts: datetime) -> datetime:
    """signals.timestamp is TIMESTAMP (naive UTC); treat naive as UTC."""
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def anchor_session(fired_at: datetime) -> date:
    d = as_utc(fired_at).astimezone(ET).date()
    return d if cal.is_trading_day(d) else cal.previous_trading_day(d)


def nth_session(anchor: date, n: int) -> date:
    return cal.add_trading_days(anchor, n)


def sessions_after(anchor: date, n: int) -> List[date]:
    """The n trading days after `anchor`, in order."""
    out, d = [], anchor
    for _ in range(n):
        d = cal.next_trading_day(d)
        out.append(d)
    return out


def complete_through(now: Optional[datetime] = None) -> date:
    """The last session whose daily bar can be read as final."""
    now_et = (now or datetime.now(timezone.utc)).astimezone(ET)
    d = now_et.date()
    if cal.is_trading_day(d) and now_et.time() >= BARS_SETTLED_AFTER:
        return d
    return cal.previous_trading_day(d)


class SeriesSessions:
    """The same interface over a vendor series' own dates (history runs only)."""

    def __init__(self, dates):
        self._dates = sorted(dates)
        self._pos = {d: i for i, d in enumerate(self._dates)}

    def nth_session(self, anchor: date, n: int) -> Optional[date]:
        i = self._pos.get(anchor)
        if i is None or i + n >= len(self._dates):
            return None
        return self._dates[i + n]

    def sessions_after(self, anchor: date, n: int) -> List[date]:
        i = self._pos.get(anchor)
        return [] if i is None else self._dates[i + 1:i + 1 + n]


def start_covering(n_sessions: int, end: date) -> date:
    """The calendar date n sessions before `end` (for fetch windows) -- from the calendar,
    not a weekday multiplier."""
    return end - timedelta(days=cal.calendar_days_covering(n_sessions, end))
