"""Feed age in trading days — R-IV.871(c).

`nightly` and `provisional` run on weekdays and their feed carried a 26-hour SLO, so /health
read `degraded` with both `flatline` and `consecutive_failures = 0` from late Saturday until
Monday night. About one day a week.

THE TEST THAT MATTERS IS THE SECOND HALF. Silencing the weekend is easy and worthless on its
own: an alarm that cannot fire is not an improvement on one that always fires. So every
"quiet weekend" case below is paired with a weekday miss that MUST still be seen.
"""
from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models.feed_calendar_age import (  # noqa: E402
    CALENDAR_CADENCE, expected_session, is_calendar_cadence, is_overdue,
)

ET = ZoneInfo("America/New_York")

# 2026-10-12 is a Monday; 10-09 Friday; 10-10 Saturday; 10-11 Sunday.
FRI_NIGHT = datetime(2026, 10, 9, 21, 5, tzinfo=ET)       # a completed nightly pass
SAT_LATE = datetime(2026, 10, 10, 23, 0, tzinfo=ET)
SUN_EVENING = datetime(2026, 10, 11, 21, 30, tzinfo=ET)   # when /health said degraded
MON_MORNING = datetime(2026, 10, 12, 9, 0, tzinfo=ET)
MON_NIGHT = datetime(2026, 10, 12, 21, 30, tzinfo=ET)
TUE_MORNING = datetime(2026, 10, 13, 9, 0, tzinfo=ET)
WED_MORNING = datetime(2026, 10, 14, 9, 0, tzinfo=ET)


# ── the weekend is quiet because it is not a session ─────────────────────────

@pytest.mark.parametrize("when", [SAT_LATE, SUN_EVENING, MON_MORNING])
def test_fridays_pass_is_enough_until_monday_night(when):
    """The exact false alarm. By hours, Friday 21:05 is 26h+ stale by Sunday; by sessions it is
    current, because Saturday and Sunday owe nothing and Monday's window has not come."""
    overdue, reason = is_overdue("nightly", FRI_NIGHT, now_et=when)
    assert overdue is False, reason


def test_sunday_was_the_reported_degraded_moment():
    """Pinned to the measurement that started this: /health read degraded on Sunday evening with
    nightly 48.4h old and zero failures."""
    assert is_overdue("nightly", FRI_NIGHT, now_et=SUN_EVENING)[0] is False


# ── THE PAIR: a weekday miss must still be seen ─────────────────────────────

def test_a_missed_monday_night_is_overdue_on_tuesday_morning():
    """The half that matters. Last pass Friday, Monday's window has passed and nothing ran."""
    overdue, reason = is_overdue("nightly", FRI_NIGHT, now_et=TUE_MORNING)
    assert overdue is True
    assert "owes 2026-10-12" in reason


def test_two_missed_sessions_are_counted():
    overdue, reason = is_overdue("nightly", FRI_NIGHT, now_et=WED_MORNING)
    assert overdue is True
    assert "missed 2 session(s)" in reason


def test_monday_night_pass_clears_it():
    assert is_overdue("nightly", MON_NIGHT, now_et=TUE_MORNING)[0] is False


def test_overdue_the_moment_the_window_passes_without_a_run():
    """Monday 21:30 with only Friday's pass: today's window has gone by, so it is late NOW and
    not tomorrow. A grace of one more session would have hidden it until Tuesday."""
    assert CALENDAR_CADENCE["nightly"]["grace_sessions"] == 0
    assert is_overdue("nightly", FRI_NIGHT, now_et=MON_NIGHT)[0] is True


def test_never_recorded_is_overdue_not_unknown():
    overdue, reason = is_overdue("nightly", None, now_et=MON_MORNING)
    assert overdue is True
    assert "never recorded" in reason


# ── holidays come from the calendar, not from a weekday list ────────────────

def test_a_holiday_monday_does_not_accuse_the_job():
    """2026-11-26 is Thanksgiving (Thursday). On Friday 11-27 the session owed is Wednesday
    11-25, so a Wednesday-night pass is current -- a weekday list would have demanded Thursday
    and reported a failure that never happened."""
    fri = datetime(2026, 11, 27, 9, 0, tzinfo=ET)
    assert expected_session("nightly", fri).isoformat() == "2026-11-25"
    wed_night = datetime(2026, 11, 25, 21, 5, tzinfo=ET)
    assert is_overdue("nightly", wed_night, now_et=fri)[0] is False


def test_the_holiday_pair_a_real_miss_around_it_is_still_seen():
    """And the pair, so the holiday exemption cannot be mistaken for a blanket amnesty."""
    fri = datetime(2026, 11, 27, 9, 0, tzinfo=ET)
    tue_night = datetime(2026, 11, 24, 21, 5, tzinfo=ET)
    overdue, reason = is_overdue("nightly", tue_night, now_et=fri)
    assert overdue is True, reason


# ── provisional has its own window ──────────────────────────────────────────

def test_provisional_owes_its_session_from_1605_not_2100():
    """It runs 08:00, 09:45 and 16:05, so a miss is late the same evening rather than the next
    day. nightly and provisional share one FEED, which is why the rule is keyed on the JOB."""
    assert CALENDAR_CADENCE["provisional"]["last_window_et"] == (16, 5)
    at_1700 = datetime(2026, 10, 12, 17, 0, tzinfo=ET)
    assert expected_session("provisional", at_1700).isoformat() == "2026-10-12"
    assert expected_session("nightly", at_1700).isoformat() == "2026-10-09"


# ── it refuses rather than guessing ─────────────────────────────────────────

def test_a_job_without_a_calendar_cadence_returns_none():
    """None, not False: the caller must keep its hour-based SLO for strip/movers/ext_hours,
    which have real intraday cadences."""
    for job in ("strip", "movers", "ext_hours", "hermes_session_poll"):
        assert is_calendar_cadence(job) is False
        assert is_overdue(job, FRI_NIGHT, now_et=MON_MORNING)[0] is None


def test_past_the_calendar_horizon_it_returns_none():
    """Past the enumerated calendar it must not answer. False here would silently declare every
    feed healthy forever, which is strictly worse than the weekend noise."""
    far = datetime(2031, 3, 4, 9, 0, tzinfo=ET)
    assert expected_session("nightly", far) is None
    overdue, reason = is_overdue("nightly", FRI_NIGHT, now_et=far)
    assert overdue is None
    assert "cannot place" in reason


def test_a_naive_last_success_is_read_as_et_not_rejected():
    """asyncpg hands back aware timestamps, but a naive one must not crash a health read."""
    naive = datetime(2026, 10, 9, 21, 5)
    assert is_overdue("nightly", naive, now_et=MON_MORNING)[0] is False


# ── a recorded failure is independent of the calendar ───────────────────────

def test_health_summary_still_flatlines_on_consecutive_failures(monkeypatch):
    """Belt and braces for (c)'s requirement: the calendar can only ever excuse SILENCE. A job
    that ran and FAILED is flatlined by the failure counter, weekend or not. Asserted against
    the real health_summary so the wiring is covered, not just the helper."""
    import asyncio

    from stable_engine import job_status as js

    async def fake_get_all():
        return [{"job_name": "nightly", "last_success_at": FRI_NIGHT,
                 "consecutive_failures": 3, "last_error": "boom"}]

    async def no_unrecorded():
        return []

    monkeypatch.setattr(js, "get_all", fake_get_all)
    monkeypatch.setattr(js, "unrecorded_failures", no_unrecorded)
    out = asyncio.run(js.health_summary())
    assert out["jobs"]["nightly"]["status"] == "flatline"
    assert out["any_flatline"] is True


def test_health_summary_is_calm_on_a_quiet_weekend(monkeypatch):
    """The pair, through the same real function: zero failures and Friday's pass is not an
    incident. This is the assertion that would have failed before (c)."""
    import asyncio

    from stable_engine import job_status as js

    async def fake_get_all():
        return [{"job_name": "nightly", "last_success_at": FRI_NIGHT,
                 "consecutive_failures": 0, "last_error": None},
                {"job_name": "provisional", "last_success_at": FRI_NIGHT,
                 "consecutive_failures": 0, "last_error": None}]

    async def no_unrecorded():
        return []

    monkeypatch.setattr(js, "get_all", fake_get_all)
    monkeypatch.setattr(js, "unrecorded_failures", no_unrecorded)
    out = asyncio.run(js.health_summary())
    assert out["any_flatline"] is False, out["jobs"]
    assert out["jobs"]["nightly"]["status"] == "ok"
    assert "session_cadence" in out["jobs"]["nightly"]
