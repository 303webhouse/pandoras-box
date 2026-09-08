"""T3 — the grader liveness sentinel (R-IV.295(a)).

§1.1 REGISTRATION, asserted here rather than described:
  predicate            "a pass completed within 26h, when a pass was due"
  expected satisfaction ~100% OF CALENDAR DAYS
  state change          a missed trading day
  reachability          proven below by driving the age past threshold

The weekend cases are the point. A bare 26h SLO on a weekday-only job is a
guaranteed false red ~104x/year — signals_freshness says so in its own comments
about STRIKE_IB_BREAK — so satisfaction of ~100% of CALENDAR days is only true
if the SLO is gated on a pass being due.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from stable_engine import signals_freshness as sf

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


class TestPassOverdue:
    def test_friday_pass_covers_saturday(self):
        """THE WEEKEND CASE. Friday's pass is >26h old on Saturday evening and
        must NOT alarm: no pass was due in between."""
        assert sf._pass_overdue(date(2026, 9, 4), _et(2026, 9, 5, 20)) is False

    def test_friday_pass_covers_sunday(self):
        assert sf._pass_overdue(date(2026, 9, 4), _et(2026, 9, 6, 23)) is False

    def test_friday_pass_is_overdue_by_tuesday_evening(self):
        """CORRECTED under T7 (R-IV.319(b)). This lane wrote it on 09-06 asserting
        that a Friday pass is overdue by MONDAY 09-07 evening -- and 09-07 is Labor
        Day, so no pass was ever due. THE TEST ENCODED THE HOLIDAY FALSE RED AS
        CORRECT BEHAVIOUR, in the very sentinel built to remove false reds.

        Tuesday 09-08 is the first session after, and Friday's pass is overdue then.
        """
        assert sf._pass_overdue(date(2026, 9, 4), _et(2026, 9, 8, 18)) is True

    def test_not_overdue_before_the_post_close_hour(self):
        """Monday 10:00 ET: Monday's pass is not due yet; Friday's still covers."""
        assert sf._pass_overdue(date(2026, 9, 4), _et(2026, 9, 7, 10)) is False

    def test_never_run_is_overdue(self):
        assert sf._pass_overdue(None, _et(2026, 9, 8, 18)) is True

    def test_same_day_pass_is_current(self):
        assert sf._pass_overdue(date(2026, 9, 8), _et(2026, 9, 8, 18)) is False


class TestClassStatus:
    JOB = "triton_grader"

    def test_registered_and_has_an_slo(self):
        assert self.JOB in sf.REGISTERED_CLASSES
        assert sf.SLO_SECONDS[self.JOB] == 26 * 3600
        assert sf.AGE_SOURCES[self.JOB] == sf.AGE_SOURCE_JOB_RUNS
        assert self.JOB in sf.SESSION_JOB_CLASSES

    def test_not_overdue_is_ok_however_old(self, monkeypatch):
        """A weekend age of 60h with no pass due is OK, not flatline."""
        monkeypatch.setattr(sf, "_pass_overdue", lambda *a, **k: False)
        assert sf._class_status(self.JOB, 60 * 3600, 0, date(2026, 9, 4)) == "ok"

    def test_overdue_and_past_slo_is_flatline(self, monkeypatch):
        """REACHABILITY: the staleness branch CAN fire. This is the deafness
        test in unit form — the sentinel must be provable, not assumed."""
        monkeypatch.setattr(sf, "_pass_overdue", lambda *a, **k: True)
        assert sf._class_status(self.JOB, 27 * 3600, 0, date(2026, 9, 4)) == "flatline"

    def test_overdue_but_inside_slo_is_ok(self, monkeypatch):
        monkeypatch.setattr(sf, "_pass_overdue", lambda *a, **k: True)
        assert sf._class_status(self.JOB, 3 * 3600, 0, date(2026, 9, 7)) == "ok"

    def test_unreadable_age_is_no_data_never_flatline(self, monkeypatch):
        """An unreadable age must not be rendered as an outage."""
        monkeypatch.setattr(sf, "_pass_overdue", lambda *a, **k: True)
        assert sf._class_status(self.JOB, None, 0, None) == "no_data"

    def test_producer_classes_are_unaffected(self):
        """The hook must not change any existing class's behaviour."""
        assert sf._class_status("crypto_scanner", 1, 0) == "ok"
        assert sf._class_status("crypto_scanner", 13 * 3600, 0) == "flatline"
