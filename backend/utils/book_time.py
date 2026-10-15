"""One instant for one date, on every path into the book (R-IV.464(a)).

THE PRINCIPAL READS HIS BOOK IN MOUNTAIN TIME. A bare date stored as 00:00 UTC renders as the day
BEFORE on every surface he reads, so a date in this book is that day at **00:00 in Denver** --
06:00 UTC in summer, 07:00 in winter. That is the convention the rows corrected by hand already
used; until this module the close path read the same input as 00:00 UTC, so one date meant two
instants depending on which door it came through.

A value that already carries a time keeps it. A value that carries no zone is read as UTC: it came
from a machine, and a machine's clock here is UTC.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")


def day_start(day: date) -> datetime:
    """00:00 in Denver on that day, as an instant."""
    return datetime(day.year, day.month, day.day, tzinfo=DENVER).astimezone(timezone.utc)


def book_instant(value: Any, field: str = "date") -> datetime:
    """A date or timestamp from a caller, as the instant the book stores. Raises ValueError."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    if isinstance(value, date):
        return day_start(value)
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is empty")
    if len(text) <= 10:
        return day_start(date.fromisoformat(text))
    when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def optional_instant(value: Any, field: str = "date") -> Optional[datetime]:
    return None if value in (None, "") else book_instant(value, field)


def is_day_start(when: datetime) -> bool:
    """True when `when` is exactly 00:00 in Denver — i.e. a DATE was stored, not an instant.

    R-IV.1052(e)(c)5 needs to tell "the principal gave me a date" from "the principal gave me a
    time", and after `book_instant` both are a UTC datetime. The discriminator is what the
    instant looks like IN DENVER, because that is the zone the convention is written in: a bare
    date becomes 06:00Z in summer and 07:00Z in winter, so comparing against either in UTC
    would be right for half the year.

    THE ONE CASE IT CANNOT SEE: a genuine fill at exactly 00:00:00.000000 Denver reads as a
    bare date. No exchange this book trades is open then, so the ambiguity is unreachable in
    practice — but it is an ambiguity, and it is written down rather than left to be discovered.
    """
    local = when.astimezone(DENVER)
    return (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0)


def same_book_day(a: datetime, b: datetime) -> bool:
    """Whether two instants fall on the same DENVER day — the principal's day.

    Not the UTC day: a 16:15 ET fill is already the next UTC day for part of the year, so a UTC
    comparison would call two instants from one afternoon different days (convention #39, in the
    zone this module owns).
    """
    return a.astimezone(DENVER).date() == b.astimezone(DENVER).date()
