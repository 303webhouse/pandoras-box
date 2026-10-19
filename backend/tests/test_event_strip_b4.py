"""B4's Event Strip: what is scheduled, what is a rule, and what is an ESTIMATE.

The distinction is the point of this file. FOMC/CPI/jobs/GDP/PCE are published dates. Monthly
OpEx is a rule that has not changed since listed options began. The book's expiries are facts
in the book. THE BUYBACK BLACKOUT IS AN ESTIMATE -- there is no public per-issuer blackout
calendar -- and an estimate drawn next to three kinds of fact has to say so, every time.
"""
from __future__ import annotations

import datetime as _dt

from models import event_strip_b4 as es

WEEKDAYS = lambda d: d.weekday() < 5                                # noqa: E731


# ── 1. monthly OpEx is computed, not tabulated ────────────────────────────

def test_THIRD_FRIDAY_IS_COMPUTED_FOR_EVERY_SHAPE_OF_MONTH():
    """A table of expiry dates goes stale silently. These are months whose 1st falls on each
    weekday, which is where an off-by-one in the formula shows up."""
    assert es.third_friday(2026, 1) == _dt.date(2026, 1, 16)
    assert es.third_friday(2026, 5) == _dt.date(2026, 5, 15)
    assert es.third_friday(2026, 10) == _dt.date(2026, 10, 16)
    assert es.third_friday(2026, 11) == _dt.date(2026, 11, 20)
    assert es.third_friday(2027, 1) == _dt.date(2027, 1, 15)
    for y in (2025, 2026, 2027):
        for m in range(1, 13):
            d = es.third_friday(y, m)
            assert d.weekday() == 4, (y, m, d)
            assert 15 <= d.day <= 21, "the third Friday is always the 15th-21st"


def test_NEXT_OPEX_ROLLS_TO_THE_NEXT_MONTH_ONCE_PAST():
    d, days, basis = es.next_opex(_dt.date(2026, 10, 17))
    assert d == _dt.date(2026, 11, 20) and days == 34
    assert "third Friday of 2026-11" in basis
    # On the day itself it is still this month's.
    assert es.next_opex(_dt.date(2026, 10, 16))[0] == _dt.date(2026, 10, 16)


def test_WITHOUT_A_CALENDAR_THE_BASIS_SAYS_NO_HOLIDAY_ADJUSTMENT_WAS_APPLIED():
    """The real rule moves a holiday expiry to the Thursday. Without a calendar this returns
    the raw third Friday AND SAYS SO, rather than presenting an unadjusted date as adjusted."""
    _, _, basis = es.next_opex(_dt.date(2026, 10, 17))
    assert "no holiday adjustment applied" in basis
    # With a calendar that calls the third Friday a holiday, it moves back and says why.
    cal = lambda d: False if d == _dt.date(2026, 11, 20) else True   # noqa: E731
    d, _, basis2 = es.next_opex(_dt.date(2026, 10, 17), is_trading_day=cal)
    assert d == _dt.date(2026, 11, 19) and "moved back" in basis2


# ── 2. the strip counts SESSIONS, not days ────────────────────────────────

def test_THE_STRIP_IS_TEN_SESSIONS_AND_SKIPS_THE_WEEKEND():
    """A calendar-day strip would show a weekend as two quiet days and push real events off
    the end. The tile's promise is "the next ten SESSIONS"."""
    days = es.sessions_ahead(_dt.date(2026, 10, 19), 10, is_trading_day=WEEKDAYS)
    assert len(days) == 10
    assert all(d.weekday() < 5 for d in days)
    assert days[0] == _dt.date(2026, 10, 19) and days[-1] == _dt.date(2026, 10, 30)


def test_AN_UNSURE_CALENDAR_SHOWS_THE_DAY():
    """`is_trading_day_or_none` returns None past its horizon, and None is not False. Hiding a
    session because the calendar was unsure would silently shorten the window -- and a day
    shown in error is visible, while a day dropped is not."""
    days = es.sessions_ahead(_dt.date(2026, 10, 19), 5, is_trading_day=lambda d: None)
    assert len(days) == 5


# ── 3. macro classification ───────────────────────────────────────────────

def test_AN_FOMC_DECISION_IS_THE_LOUDEST_THING_ON_THE_STRIP():
    assert es.classify_macro("FOMC rate decision") == ("FOMC 2pm", es.KIND_TOP)
    assert es.classify_macro("FOMC statement") == ("FOMC 2pm", es.KIND_TOP)
    # Day one of the meeting is macro, not the top line.
    assert es.classify_macro("FOMC meeting begins") == ("FOMC", es.KIND_MACRO)


def test_THE_MACRO_WORDS_COVER_THE_RULED_SET():
    """FOMC / CPI / jobs / GDP / PCE, which is B4's own list."""
    for name, word in (("Consumer Price Index", "CPI"), ("Nonfarm Payrolls", "JOBS"),
                       ("Unemployment Rate", "JOBS"), ("GDP Q3 advance", "GDP"),
                       ("PCE Price Index", "PCE")):
        assert es.macro_word(name) == word, name


def test_AN_UNRECOGNISED_EVENT_IS_SHOWN_NOT_DROPPED():
    """R-IV.925(b) says do not invent a label. It does not say hide what you cannot classify:
    a dropped event is a strip that looks quieter than the week really is."""
    strip = es.build_strip(_dt.date(2026, 10, 19), is_trading_day=WEEKDAYS,
                           macro=[{"date": _dt.date(2026, 10, 21),
                                   "name": "Treasury 20Y auction"}])
    day = [d for d in strip["days"] if d["iso"] == "2026-10-21"][0]
    assert day["events"] and "Treasury" in day["events"][0]["k"]
    assert day["events"][0]["kind"] == es.KIND_MACRO


# ── 4. the blackout is an ESTIMATE and says so ────────────────────────────

def test_THE_BLACKOUT_CARRIES_ITS_RULE_AND_THE_WORD_ESTIMATE():
    """Drawn next to three kinds of fact, so it has to be told apart from them every time it
    is shown -- not just in a doc."""
    strip = es.build_strip(_dt.date(2026, 10, 19), is_trading_day=WEEKDAYS)
    assert strip["blackout_label"] == "BUYBACK BLACKOUT est."
    assert "ESTIMATE, not a schedule" in strip["blackout_rule"]
    assert "no public per-issuer blackout calendar" in strip["blackout_rule"]
    assert str(es.BLACKOUT_BEFORE_QUARTER_END_DAYS) in strip["blackout_rule"]


def test_THE_BLACKOUT_WINDOW_IS_THE_ONE_THE_RULE_DESCRIBES():
    """Mid-October is inside the window that opened before the 9/30 quarter end; mid-November
    is outside it. Checked on the boundaries, which is where a window rule is wrong."""
    # 9-30 minus 14 days IS 9-16, so 9-16 is inside the window and 9-15 is the first day
    # outside it. My first version of this test asserted 9-16 False and was simply wrong
    # about its own arithmetic -- the rule is "within 14 days before", inclusive.
    assert es.in_blackout(_dt.date(2026, 9, 16)) is True
    assert es.in_blackout(_dt.date(2026, 9, 15)) is False
    assert es.in_blackout(_dt.date(2026, 10, 30)) is True
    assert es.in_blackout(_dt.date(2026, 10, 31)) is False
    # And the year boundary, where a 12-31 quarter end reaches into January.
    assert es.in_blackout(_dt.date(2027, 1, 15)) is True


# ── 5. the assembled strip ────────────────────────────────────────────────

def test_THE_STRIP_PUTS_EVERY_SOURCE_ON_THE_RIGHT_DAY():
    strip = es.build_strip(
        _dt.date(2026, 10, 19), is_trading_day=WEEKDAYS,
        macro=[{"date": _dt.date(2026, 10, 28), "name": "FOMC rate decision"},
               {"date": _dt.date(2026, 10, 30), "name": "PCE Price Index"}],
        book_expiries=[{"date": _dt.date(2026, 10, 21), "label": "VIX spread exp"}],
        earnings=[{"date": _dt.date(2026, 10, 21), "in_book": True},
                  {"date": _dt.date(2026, 10, 21), "in_book": False},
                  {"date": _dt.date(2026, 10, 22), "in_book": False}])
    by = {d["iso"]: d for d in strip["days"]}
    assert by["2026-10-21"]["earn"] == 2 and by["2026-10-21"]["book_earn"] == 1
    assert by["2026-10-22"]["earn"] == 1 and by["2026-10-22"]["book_earn"] == 0
    assert by["2026-10-21"]["events"][0]["kind"] == es.KIND_BOOK
    assert by["2026-10-28"]["events"][0]["kind"] == es.KIND_TOP
    assert by["2026-10-30"]["events"][0]["k"] == "PCE"
    # An event outside the ten sessions is not drawn on the last day as a consolation.
    far = es.build_strip(_dt.date(2026, 10, 19), is_trading_day=WEEKDAYS,
                         macro=[{"date": _dt.date(2026, 12, 15), "name": "CPI"}])
    assert all(not d["events"] for d in far["days"])


def test_EVERY_DAY_CARRIES_ITS_OWN_ISO_DATE():
    """The mock had `dow` and `dd` only. A strip whose cells cannot be matched back to a date
    cannot be checked against anything -- including by QUERY."""
    strip = es.build_strip(_dt.date(2026, 10, 19), is_trading_day=WEEKDAYS)
    for d in strip["days"]:
        assert _dt.date.fromisoformat(d["iso"])
        assert d["dd"] == "%02d" % _dt.date.fromisoformat(d["iso"]).day
