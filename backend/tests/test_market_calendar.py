"""T7 — the one market calendar, and T6's bound on top of it.

Every date below was computed at authoring time and written down; these tests
re-assert the written list, so a hand edit that corrupts a date fails here.
"""

from datetime import date

import pytest

from stable_engine import market_calendar as mc
from jobs.triton_shadow_grader import (
    _bounded_lookback, GRADER_LOOKBACK_FALLBACK_DAYS, GRADER_LOOKBACK_TRADING_DAYS,
)


class TestTheTwoMissingHolidays:
    """The reason this module exists: the repo's computed helper omits both."""

    @pytest.mark.parametrize("d", [date(2025, 6, 19), date(2026, 6, 19), date(2027, 6, 18)])
    def test_juneteenth_is_closed(self, d):
        assert mc.is_trading_day(d) is False

    @pytest.mark.parametrize("d", [date(2025, 4, 18), date(2026, 4, 3), date(2027, 3, 26)])
    def test_good_friday_is_closed(self, d):
        assert mc.is_trading_day(d) is False


class TestKnownDays:
    def test_labor_day_2026_is_closed(self):
        """The anchor for the whole set — the day this calendar was written."""
        assert mc.is_trading_day(date(2026, 9, 7)) is False

    def test_the_day_after_labor_day_is_open(self):
        assert mc.is_trading_day(date(2026, 9, 8)) is True

    def test_weekends_are_closed(self):
        assert mc.is_trading_day(date(2026, 9, 5)) is False   # Sat
        assert mc.is_trading_day(date(2026, 9, 6)) is False   # Sun

    def test_observed_july_4_2026_is_the_friday(self):
        """July 4 2026 is a Saturday; the market closes Friday the 3rd."""
        assert mc.is_trading_day(date(2026, 7, 3)) is False
        assert mc.is_trading_day(date(2026, 7, 6)) is True

    def test_new_year_2028_observed_in_2027(self):
        """Jan 1 2028 is a Saturday, observed 2027-12-31 — inside this horizon."""
        assert mc.is_trading_day(date(2027, 12, 31)) is False


class TestLoudFailure:
    def test_past_horizon_raises(self):
        with pytest.raises(mc.CalendarHorizonError):
            mc.is_trading_day(date(2028, 1, 3))

    def test_before_first_raises(self):
        with pytest.raises(mc.CalendarHorizonError):
            mc.is_trading_day(date(2024, 12, 31))

    def test_or_none_returns_None_not_True(self):
        out = mc.is_trading_day_or_none(date(2028, 1, 3))
        assert out is None
        assert out is not True
        assert out is not False

    def test_horizon_boundary_is_inclusive(self):
        assert mc.is_trading_day_or_none(date(2027, 12, 31)) is False


class TestNavigation:
    def test_previous_trading_day_skips_labor_day_weekend(self):
        assert mc.previous_trading_day(date(2026, 9, 8)) == date(2026, 9, 4)

    def test_next_trading_day_skips_labor_day_weekend(self):
        assert mc.next_trading_day(date(2026, 9, 4)) == date(2026, 9, 8)

    def test_add_trading_days_crosses_the_holiday(self):
        assert mc.add_trading_days(date(2026, 9, 4), 1) == date(2026, 9, 8)
        assert mc.add_trading_days(date(2026, 9, 4), 3) == date(2026, 9, 10)

    def test_trading_days_between_excludes_the_holiday(self):
        """(09-04, 09-11] holds Sep 8, 9, 10, 11 — FOUR sessions. The naive count
        of seven calendar days minus a weekend gives five; Labor Day is the fifth."""
        assert mc.trading_days_between(date(2026, 9, 4), date(2026, 9, 11)) == 4

    def test_zero_and_backwards_ranges(self):
        assert mc.trading_days_between(date(2026, 9, 8), date(2026, 9, 8)) == 0
        assert mc.trading_days_between(date(2026, 9, 8), date(2026, 9, 1)) == 0


class TestCalendarDaysCovering:
    def test_derived_not_multiplied(self):
        """29 calendar days hold 20 sessions ending 2026-09-08; 20*1.6 says 32."""
        assert mc.calendar_days_covering(20, date(2026, 9, 8)) == 29

    def test_it_actually_covers(self):
        n = mc.calendar_days_covering(20, date(2026, 9, 8))
        start = date(2026, 9, 8) - __import__("datetime").timedelta(days=n)
        assert mc.trading_days_between(start, date(2026, 9, 8)) >= 20


class TestT6Bound:
    def test_the_pinned_case_is_bounded(self):
        """2026-07-02 is where the 72 index rows pinned the window. Unbounded it
        was 80 and growing by one a day."""
        assert _bounded_lookback(date(2026, 7, 2), date(2026, 9, 8)) == 41

    def test_takes_the_smaller_when_less_is_needed(self):
        assert _bounded_lookback(date(2026, 9, 1), date(2026, 9, 8)) == 19

    def test_bound_covers_at_least_20_trading_days(self):
        assert GRADER_LOOKBACK_TRADING_DAYS >= 20

    def test_it_does_not_grow_with_the_anchor(self):
        """The defect in one assertion: an older anchor must NOT widen the window."""
        a = _bounded_lookback(date(2026, 7, 2), date(2026, 9, 8))
        b = _bounded_lookback(date(2026, 1, 2), date(2026, 9, 8))
        assert a == b

    def test_past_horizon_uses_the_stated_fallback(self):
        assert _bounded_lookback(date(2028, 1, 2), date(2028, 3, 1)) == GRADER_LOOKBACK_FALLBACK_DAYS
