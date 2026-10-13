"""One budget, one day — R-IV.950(b). The VENDOR's day, resetting 20:00 ET, DST-aware.

WHAT THIS CLOSES. Every Redis counter keyed on `date.today()`, the LOCAL calendar date of
whichever process made the call. One budget therefore had THREE boundaries: UTC on Railway,
Mountain on a local run, and 20:00 ET in the spend ledger. A local batch at 18:30 MT read the
previous day's bucket, saw it full, and stopped -- while the app had rolled two and a half
hours earlier.
"""
from __future__ import annotations

import ast
import inspect
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from integrations import uw_api_cache as cache  # noqa: E402
from integrations.uw_spend_ledger import UW_DAY_ROLLOVER_HOUR_ET, uw_day  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    MT = ZoneInfo("America/Denver")
    UTC = timezone.utc
except ImportError:                                                 # pragma: no cover
    import pytz
    ET = pytz.timezone("America/New_York")
    MT = pytz.timezone("America/Denver")
    UTC = pytz.UTC


# ── the three cases the ruling names ─────────────────────────────────────

def test_1959_ET_and_2001_ET_are_DIFFERENT_days():
    a = uw_day(datetime(2026, 10, 12, 19, 59, tzinfo=ET))
    b = uw_day(datetime(2026, 10, 12, 20, 1, tzinfo=ET))
    assert a == date(2026, 10, 12)
    assert b == date(2026, 10, 13)
    assert a != b


def test_a_MOUNTAIN_time_machine_at_1830_MT_is_on_the_NEW_day():
    """18:30 MT is 20:30 ET. This is the exact case that cost a night's allowance: the local
    process computed 2026-10-12 from its own clock and read a bucket that was already full."""
    assert uw_day(datetime(2026, 10, 12, 18, 30, tzinfo=MT)) == date(2026, 10, 13)


def test_the_boundary_is_exactly_2000_ET():
    assert UW_DAY_ROLLOVER_HOUR_ET == 20
    assert uw_day(datetime(2026, 10, 12, 20, 0, tzinfo=ET)) == date(2026, 10, 13)
    assert uw_day(datetime(2026, 10, 12, 19, 59, 59, tzinfo=ET)) == date(2026, 10, 12)


# ── the same instant, read from three machines ───────────────────────────

def test_three_timezones_reading_ONE_instant_agree():
    """THE POINT OF THE RULING. The same moment must land on one day whoever asks."""
    instant = datetime(2026, 10, 13, 0, 30, tzinfo=UTC)      # = 20:30 ET on 10-12
    answers = {uw_day(instant.astimezone(tz)) for tz in (UTC, ET, MT)}
    assert answers == {date(2026, 10, 13)}, answers


def test_it_is_DST_aware_and_not_a_fixed_offset():
    """ET is UTC-4 in October and UTC-5 in January. A fixed offset would put one of these on
    the wrong day, which is the failure the ruling says to avoid by naming the zone."""
    # 2026-01-15 20:30 ET (EST, UTC-5) -> 01:30 UTC on the 16th
    assert uw_day(datetime(2026, 1, 15, 20, 30, tzinfo=ET)) == date(2026, 1, 16)
    # the equivalent instants expressed in UTC land on the same vendor day
    assert uw_day(datetime(2026, 1, 16, 1, 30, tzinfo=UTC)) == date(2026, 1, 16)
    assert uw_day(datetime(2026, 7, 15, 19, 59, tzinfo=ET)) == date(2026, 7, 15)   # EDT


# ── every counter now keys on it ─────────────────────────────────────────

def test_no_counter_key_computes_its_own_date():
    """Read from the PARSED tree: a `date.today()` CALL anywhere in the counter module would be
    a second boundary. The module's own prose discusses `date.today()` in order to explain why
    it is wrong, so a grep would match the explanation."""
    tree = ast.parse(inspect.getsource(cache))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "today"]
    assert calls == [], "a counter still computes its own date (%d call(s))" % len(calls)


def test_the_counter_module_asks_the_ONE_author():
    assert cache._vendor_day_str() == uw_day().isoformat()


def test_the_helper_never_raises_and_always_returns_a_date_string(monkeypatch):
    """An unbuildable counter key would take the governor's whole instrument down, so it fails
    back to the UTC date rather than raising: an unmeasured budget must not become an outage of
    its own."""
    import integrations.uw_spend_ledger as ledger

    def boom(now=None):
        raise RuntimeError("no tz database")

    monkeypatch.setattr(ledger, "uw_day", boom)
    out = cache._vendor_day_str()
    assert len(out) == 10 and out.count("-") == 2
    date.fromisoformat(out)      # parses, so it is a usable key


def test_the_rollover_hour_has_one_author():
    """Not restated in the counter module: it is imported from the ledger, so the boundary
    cannot drift between the two."""
    src = inspect.getsource(cache)
    assert "UW_DAY_ROLLOVER_HOUR_ET = " not in src
    assert "uw_day" in src


# ── the practical consequence the ruling draws ───────────────────────────

def test_the_vendor_day_that_began_at_2000_ET_is_its_own_budget():
    """R-IV.950(b)'s closing sentence: the day that began at 20:00 ET on 10-12 has its own
    2,500. Under the old local-date keying a Mountain-time run could not see that."""
    before = uw_day(datetime(2026, 10, 12, 19, 0, tzinfo=ET))
    after = uw_day(datetime(2026, 10, 12, 21, 0, tzinfo=ET))
    assert before == date(2026, 10, 12) and after == date(2026, 10, 13)
    # and a Mountain machine at the same two instants agrees
    assert uw_day(datetime(2026, 10, 12, 17, 0, tzinfo=MT)) == before
    assert uw_day(datetime(2026, 10, 12, 19, 0, tzinfo=MT)) == after
