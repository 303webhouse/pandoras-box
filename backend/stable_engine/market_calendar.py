"""THE market calendar — T7 (DEF-GRADER-NO-HOLIDAY-CALENDAR).

ONE utility. Holidays are DATA, NOT LOGIC: an explicit list with a stated horizon
and a LOUD failure past it — never a computed rule that silently treats an unknown
year as all-weekdays.

WHAT THE COMPUTED FORM COSTS, measured on the one already in this repo.
`discord_bridge/bot.py::_us_market_holidays` derives holidays from rules for ANY
year, so it answers confidently for 2099. It also carries only eight entries and
OMITS TWO REAL MARKET HOLIDAYS:

    Juneteenth   — a market holiday since 2022
    Good Friday  — a market holiday that is not a federal one

So that helper reports the market OPEN on both, every year, silently. A rule-based
calendar cannot be audited by reading it; a list can be read against a published
schedule in a minute. That is the whole argument for this file.

DATES COMPUTED AND VERIFIED 2026-09-07 (anonymous Gregorian for Easter; nth/last
weekday for the rest), then written down explicitly. The computation was used to
AUTHOR the list, never to serve it at runtime — deriving once at authoring time is
sound, deriving at runtime is the failure this replaces.

Cross-check anchoring the whole set: Labor Day 2026 resolves to 2026-09-07, which
is the day this file was written and a market holiday.

NOT MODELLED, deliberately and stated so absence is not mistaken for coverage:
early closes (half days), and ad-hoc closures (national days of mourning, weather).
This calendar answers "is the market open on this date", at day granularity.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

__all__ = [
    "CalendarHorizonError", "MARKET_HOLIDAYS", "CALENDAR_FIRST", "CALENDAR_HORIZON",
    "is_trading_day", "is_trading_day_or_none", "previous_trading_day",
    "next_trading_day", "add_trading_days", "trading_days_between",
    "calendar_days_covering",
    "MARKET_CLOSE_ET", "MARKET_TZ", "is_session_settled", "last_settled_session",
]


class CalendarHorizonError(ValueError):
    """Raised for a date outside the explicitly enumerated range.

    This is the LOUD failure. It is a bug's alarm, not a condition to swallow: a
    caller that catches this and falls back to a weekday rule has rebuilt exactly
    the silent approximation this module exists to delete.
    """


CALENDAR_FIRST = date(2025, 1, 1)
CALENDAR_HORIZON = date(2027, 12, 31)

# Explicit. Renewal = extend this list from the published NYSE schedule.
MARKET_HOLIDAYS = frozenset({
    # ── 2025 ──
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
    # ── 2026 ──
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    # ── 2027 ──  (Jan 1 2028 falls on a Saturday and is observed 2027-12-31)
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24), date(2027, 12, 31),
})


# R-IV.1176. The regular NYSE close, named so nobody re-types 16:00 at a call site.
MARKET_CLOSE_ET = time(16, 0)
MARKET_TZ = ZoneInfo("America/New_York")  # NOT a fixed offset: this observes DST


def _now_et(now: Optional[datetime] = None) -> datetime:
    """The current Eastern wall clock, or a supplied instant converted to it.

    A naive `now` is read as UTC rather than as local time. This machine's clock is Denver,
    six hours off Eastern, so guessing wrong here moves the answer across the close for a
    quarter of every day -- and `TZ=` is silently ignored in this environment's shell, which
    is how a six-hour error got made in the first place.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(MARKET_TZ)


def is_session_settled(d: date, now: Optional[datetime] = None) -> Optional[bool]:
    """Has `d`'s regular session finished?

    THREE-STATE, and the third state is the point:

        True   -- `d` is a trading day and 16:00 ET on `d` has passed.
        False  -- `d` is a trading day and its close is still ahead.
        None   -- the question CANNOT be answered: `d` is past the enumerated calendar
                  horizon, or `d` is not a trading day at all, so there is no session on it
                  to settle.

    **A guard must treat None as "not settled"**, because "I could not tell" is not "fine" --
    the same rule that made the newest-edge read fail closed. **A reader must not be shown
    None as False**, because that asserts an open session on a date that has none.

    EARLY CLOSES ARE NOT MODELLED, following this module's standing decision. On a 13:00 ET
    half day this returns False between 13:00 and 16:00 even though the session has in fact
    settled. That withholds confidence in a session that deserved it; it never grants
    confidence to one that did not. Of the two possible errors it is the harmless one, and it
    is the reason a half-day's bars land three hours later than they could.
    """
    if is_trading_day_or_none(d) is not True:
        return None
    close_at = datetime.combine(d, MARKET_CLOSE_ET, tzinfo=MARKET_TZ)
    return _now_et(now) >= close_at


def settlement_reason(d: date, now: Optional[datetime] = None) -> str:
    """Why `is_session_settled` answered as it did, in words a payload can carry.

    Exists so the None above is never ambiguous to a reader: one value, but the two causes
    stay distinguishable. A single None standing for two different situations is the fault
    that made `source_ref` unusable as a key.
    """
    settled = is_session_settled(d, now)
    if settled is True:
        return "%s closed at 16:00 ET" % d
    if settled is False:
        return "%s has not reached its 16:00 ET close" % d
    if is_trading_day_or_none(d) is None:
        return "%s is past the enumerated calendar horizon" % d
    return "%s is not a trading day, so it has no session to settle" % d


def last_settled_session(now: Optional[datetime] = None) -> date:
    """The newest trading day whose 16:00 ET close has passed.

    This is the honest right edge for anything that stores or scores daily bars. Walking back
    from today handles all three awkward cases without special-casing any of them: mid-session
    on a trading day gives yesterday, a weekend gives Friday, and a holiday gives the day
    before it.
    """
    cur = _now_et(now).date()
    # BOUNDED, because the loop's exit depends on the calendar being able to answer. Outside
    # the enumerated range `is_session_settled` returns None forever: measured with a clock set
    # to 2024, the unbounded version walked back to `date.min` and raised `OverflowError` from
    # inside a date subtraction. A hang or a stray OverflowError is strictly worse than this
    # module's stated loud failure. Ten days clears the longest real run of closed days
    # (a holiday landing beside a weekend) several times over.
    for _ in range(10):
        if is_session_settled(cur, now) is True:
            return cur
        cur = previous_trading_day(cur) if is_trading_day_or_none(cur) is True \
            else cur - timedelta(days=1)
    raise CalendarHorizonError(
        "no settled session within 10 days of %s — the clock is probably outside the "
        "enumerated calendar (%s..%s); extend MARKET_HOLIDAYS, do NOT infer"
        % (_now_et(now).date(), CALENDAR_FIRST, CALENDAR_HORIZON))


def _check(d: date) -> None:
    if d < CALENDAR_FIRST or d > CALENDAR_HORIZON:
        raise CalendarHorizonError(
            "date %s is outside the enumerated calendar (%s..%s) — extend "
            "MARKET_HOLIDAYS from the published schedule; do NOT infer"
            % (d, CALENDAR_FIRST, CALENDAR_HORIZON)
        )


def is_trading_day(d: date) -> bool:
    """True when the market is open. RAISES past the horizon."""
    _check(d)
    return d.weekday() < 5 and d not in MARKET_HOLIDAYS


def is_trading_day_or_none(d: date) -> Optional[bool]:
    """For callers that must not raise (a health read, a background loop).

    Returns None past the horizon. **None is not False and it is certainly not
    True** — a caller that collapses it has re-created the silent approximation.
    """
    try:
        return is_trading_day(d)
    except CalendarHorizonError:
        return None


def previous_trading_day(d: date) -> date:
    cur = d - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date) -> date:
    cur = d + timedelta(days=1)
    while not is_trading_day(cur):
        cur += timedelta(days=1)
    return cur


def add_trading_days(d: date, n: int) -> date:
    """The nth trading day strictly after `d` (n >= 1)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    cur = d
    for _ in range(n):
        cur = next_trading_day(cur)
    return cur


def trading_days_between(start: date, end: date) -> int:
    """Trading days in (start, end] — how many sessions elapsed."""
    if end <= start:
        return 0
    n, cur = 0, start
    while cur < end:
        cur += timedelta(days=1)
        if is_trading_day(cur):
            n += 1
    return n


def calendar_days_covering(n_trading_days: int, ending: Optional[date] = None) -> int:
    """Calendar days needed to reach back over `n_trading_days` sessions.

    T6 uses this instead of a multiplier. `20 * 1.6` is the weekday approximation
    wearing a different constant — it happens to be right most weeks and wrong
    across every holiday, which is the failure mode that is hardest to notice.
    """
    if n_trading_days < 1:
        raise ValueError("n_trading_days must be >= 1")
    end = ending or date.today()
    _check(end)
    cur, seen = end, 0
    while seen < n_trading_days:
        cur -= timedelta(days=1)
        _check(cur)
        if is_trading_day(cur):
            seen += 1
    return (end - cur).days
