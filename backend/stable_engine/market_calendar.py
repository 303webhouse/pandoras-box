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

from datetime import date, timedelta
from typing import Optional

__all__ = [
    "CalendarHorizonError", "MARKET_HOLIDAYS", "CALENDAR_FIRST", "CALENDAR_HORIZON",
    "is_trading_day", "is_trading_day_or_none", "previous_trading_day",
    "next_trading_day", "add_trading_days", "trading_days_between",
    "calendar_days_covering",
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
