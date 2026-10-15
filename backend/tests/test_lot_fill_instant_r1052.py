"""R-IV.1052(e)(c)5 — store the fill INSTANT when it is known.

`book_instant` reads the principal's bare date as 00:00 Denver, which is the right reading of a
DATE and the wrong fill time whenever the book also holds a real timestamp for that same day.
AAPL and SRTY on 2026-10-14 were each stamped at Denver midnight with a real instant for that
day available on the row, which puts the lot hours before its fill and misorders it against its
siblings -- lots are read `ORDER BY fill_time, id`.

THE BOUND IS THE POINT, and every upgrade test here is paired with a backdating test. Upgrading
across days would overwrite "Monday at 00:00, day known, time unknown" with "Wednesday
afternoon, when I happened to type it", which is not evidence about Monday. A rule that always
preferred the richer instant would pass every upgrade test below and corrupt every backdated
entry in the book.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from zoneinfo import ZoneInfo

from api.unified_positions import _best_fill_instant, _entry_fill_time
from utils.book_time import DENVER, day_start, is_day_start, same_book_day

ET = ZoneInfo("America/New_York")


def _den(y, m, d, hh=0, mm=0, ss=0, us=0):
    return datetime(y, m, d, hh, mm, ss, us, tzinfo=DENVER).astimezone(timezone.utc)


# -- is_day_start: the discriminator ----------------------------------------------------

def test_a_bare_date_reads_as_day_start():
    from datetime import date
    assert is_day_start(day_start(date(2026, 10, 14))) is True


def test_an_afternoon_instant_does_not():
    assert is_day_start(_den(2026, 10, 14, 14, 31)) is False


def test_it_is_judged_in_DENVER_not_UTC():
    """THE SEASONAL TRAP. A bare Denver date is 06:00Z in summer and 07:00Z in winter, so any
    check written against a fixed UTC hour is right for half the year. Both halves here."""
    from datetime import date
    summer, winter = day_start(date(2026, 7, 15)), day_start(date(2026, 1, 15))
    assert summer.astimezone(timezone.utc).hour == 6
    assert winter.astimezone(timezone.utc).hour == 7
    assert is_day_start(summer) and is_day_start(winter)
    # and 06:00Z in WINTER is 23:00 the previous Denver day -- not a day start
    assert is_day_start(datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)) is False


def test_one_microsecond_past_midnight_is_not_a_day_start():
    """The boundary pair. Without it, a check that truncated to seconds would pass."""
    assert is_day_start(_den(2026, 10, 14, 0, 0, 0, 1)) is False


# -- same_book_day ---------------------------------------------------------------------

def test_a_late_ET_fill_is_still_the_same_DENVER_day_as_its_date():
    """16:15 ET on 10-14 is 20:15Z, still 14:15 in Denver -- the same day. A UTC-date
    comparison would be right here and wrong in the next test."""
    assert same_book_day(_den(2026, 10, 14), datetime(2026, 10, 14, 20, 15, tzinfo=timezone.utc))


def test_an_evening_denver_instant_whose_UTC_DATE_has_rolled_is_still_the_same_day():
    """THE ONE A UTC COMPARISON GETS WRONG. 19:00 Denver on 10-14 is 01:00Z on 10-15. The
    principal's day has not ended; the UTC day has."""
    evening = _den(2026, 10, 14, 19)
    assert evening.astimezone(timezone.utc).date().isoformat() == "2026-10-15"
    assert same_book_day(_den(2026, 10, 14), evening) is True


def test_different_days_are_different():
    assert same_book_day(_den(2026, 10, 14), _den(2026, 10, 15, 9)) is False


# -- _best_fill_instant: the upgrade, and its bound ------------------------------------

def test_a_midnight_stamp_is_upgraded_by_a_same_day_instant():
    """THE AAPL/SRTY CASE."""
    midnight = _den(2026, 10, 14)
    real = _den(2026, 10, 14, 7, 31, 12)
    assert _best_fill_instant(midnight, real) == real


def test_a_BACKDATED_entry_keeps_its_midnight():
    """THE CONTROL FOR THE WHOLE FILE. Monday's fill logged Wednesday: Wednesday's clock says
    nothing about Monday, so the day stays and the time stays unknown."""
    monday = _den(2026, 10, 12)
    wednesday = _den(2026, 10, 14, 9, 5)
    assert _best_fill_instant(monday, wednesday) == monday


def test_an_instant_is_never_overwritten():
    """If the principal gave a TIME, that is the answer. A later same-day stamp must not
    replace it -- this function upgrades unknowns, it does not arbitrate between two knowns."""
    given = _den(2026, 10, 14, 7, 31)
    later = _den(2026, 10, 14, 15, 59)
    assert _best_fill_instant(given, later) == given


def test_another_midnight_is_not_an_upgrade():
    """A candidate that is itself a bare date carries no time of day, so it is not richer."""
    midnight = _den(2026, 10, 14)
    assert _best_fill_instant(midnight, _den(2026, 10, 14)) == midnight


def test_candidates_are_tried_in_order():
    midnight = _den(2026, 10, 14)
    first, second = _den(2026, 10, 14, 8), _den(2026, 10, 14, 12)
    assert _best_fill_instant(midnight, first, second) == first
    # and an unusable leading candidate is skipped rather than ending the search
    assert _best_fill_instant(midnight, None, "not a datetime", second) == second


def test_a_naive_candidate_is_read_as_UTC():
    """book_time's stated convention: a value with no zone came from a machine, and a
    machine's clock here is UTC. Guessing Denver instead would move it by six hours."""
    midnight = _den(2026, 10, 14)
    naive = datetime(2026, 10, 14, 20, 15)          # 20:15Z == 14:15 Denver, same day
    assert _best_fill_instant(midnight, naive) == naive.replace(tzinfo=timezone.utc)


def test_none_resolved_stays_none():
    assert _best_fill_instant(None, _den(2026, 10, 14, 9)) is None


def test_the_result_is_always_UTC():
    """Everything downstream stores UTC; returning a Denver-localised datetime would store the
    right instant and render differently in any naive comparison."""
    out = _best_fill_instant(_den(2026, 10, 14), _den(2026, 10, 14, 9, 30))
    assert out.tzinfo is not None and out.utcoffset() == timedelta(0)


# -- _entry_fill_time: the writer the ruling named --------------------------------------

def test_the_rows_own_timestamp_wins_over_the_principals_bare_date():
    req = SimpleNamespace(entry_date="2026-10-14")
    row = {"entry_date": _den(2026, 10, 14, 7, 31, 12),
           "created_at": _den(2026, 10, 14, 16, 2)}
    assert _entry_fill_time(req, row) == _den(2026, 10, 14, 7, 31, 12)


def test_created_at_is_used_only_when_entry_date_offers_no_time():
    req = SimpleNamespace(entry_date="2026-10-14")
    row = {"entry_date": _den(2026, 10, 14), "created_at": _den(2026, 10, 14, 16, 2)}
    assert _entry_fill_time(req, row) == _den(2026, 10, 14, 16, 2)


def test_a_backdated_request_is_not_dragged_to_the_write_day():
    """R-IV.474(b) already had to correct a row whose entry_date was the write's own clock.
    This is that defect's mirror image, and the same-day bound is what prevents it."""
    req = SimpleNamespace(entry_date="2026-10-12")
    row = {"entry_date": _den(2026, 10, 12), "created_at": _den(2026, 10, 14, 9, 5)}
    assert _entry_fill_time(req, row) == _den(2026, 10, 12)


def test_with_no_date_at_all_the_creation_stamp_still_answers():
    req = SimpleNamespace(entry_date=None)
    row = {"created_at": _den(2026, 10, 14, 16, 2)}
    assert _entry_fill_time(req, row) == _den(2026, 10, 14, 16, 2)


def test_an_unparseable_date_does_not_crash_the_writer():
    req = SimpleNamespace(entry_date="not a date")
    row = {"created_at": _den(2026, 10, 14, 16, 2)}
    assert _entry_fill_time(req, row) == _den(2026, 10, 14, 16, 2)


# -- the rule lives in ONE place --------------------------------------------------------

def test_book_time_owns_the_denver_convention():
    """`is_day_start` and `same_book_day` are imported from book_time, not re-derived in the
    API module. One fact with two authors has no author, and this one decides what a date
    MEANS -- the exact failure book_time was created to end."""
    import inspect

    from api import unified_positions as up
    src = inspect.getsource(up._best_fill_instant)
    assert "ZoneInfo" not in src, "the API module must not build its own zone"
    assert "America/Denver" not in src, "the zone name belongs to book_time alone"
    assert up.is_day_start is is_day_start and up.same_book_day is same_book_day
