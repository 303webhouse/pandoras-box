"""Hermes phase 2 — the session displacement alarm — R-IV.820(h)2.

WHAT PHASE 1 CANNOT SEE, measured: QQQ closed 2026-10-08 at −1.65% while its largest 30-minute
velocity breach all day was −1.01%. Phase 1 fires on velocity, so it catches a lurch and misses a
grind, and the principal learned about that selloff from social media. A move can be large and
never fast.

THRESHOLDS ARE CALIBRATED, NOT CHOSEN. 19 sessions from 09-15 on 5-minute bars:
SPY 1.00% kept (3/19), QQQ 1.25% → 1.75% (1.25 and 1.50 both 5/19), SMH 2.00% → 3.00%
(2.00 was 8/19). The bar is one session in five.

AND THE CONTROL NEARLY CONFLICTED WITH THE BAR. 10-08's largest QQQ displacement was
−1.757929%, so 1.50% passes the control by 0.258pp and fires 26.3% of sessions; 1.75% passes by
0.0079pp and fires 15.8%; 2.00% misses the control. 1.75% is the ONLY value satisfying both.
That margin is pinned below, because a later edit that nudges the threshold up by a quarter point
would silently un-catch the event this whole alarm was built for.

Convention #30: every "it alerts" is paired with a case that must NOT, because an alarm that
fired on everything would pass every positive test and be ignored within a week.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from webhooks import hermes_session as hs  # noqa: E402

ET = ZoneInfo("America/New_York")
# QQQ's largest session displacement on 2026-10-08, from the calibration replay.
QQQ_1008_PEAK = -1.757929410718476


class TestTheCalibratedThresholds:
    def test_they_are_the_measured_figures_not_the_starting_ones(self):
        assert hs.SESSION_THRESHOLD_PCT == {"SPY": 1.0, "QQQ": 1.75, "SMH": 3.0}
        assert hs.STARTING_THRESHOLD_PCT == {"SPY": 1.0, "QQQ": 1.25, "SMH": 2.0}

    def test_the_noise_bar_and_the_step_are_the_ruled_ones(self):
        assert hs.MAX_FIRE_RATE == 0.2
        assert hs.CALIBRATION_STEP_PCT == 0.25
        assert hs.REALERT_STEP_PCT == 0.5

    def test_the_10_08_control_still_fires_at_the_calibrated_QQQ_threshold(self):
        """THE POSITIVE CONTROL, and the reason this alarm exists."""
        ok, reason = hs.should_alert("QQQ", QQQ_1008_PEAK)
        assert ok, reason

    def test_the_control_margin_is_RECORDED_because_it_is_eight_thousandths(self):
        """A later edit raising QQQ to 2.00% would pass every other test in this file and
        silently stop catching 10-08. This is the test that would fail."""
        thr = hs.SESSION_THRESHOLD_PCT["QQQ"]
        assert abs(QQQ_1008_PEAK) >= thr, "the control no longer fires"
        margin = abs(QQQ_1008_PEAK) - thr
        assert margin < 0.01, "margin changed; re-run the calibration before trusting it"
        assert hs.should_alert("QQQ", -2.00)[0] is True   # a worse day still fires

    def test_a_quarter_point_higher_would_miss_the_control(self):
        """Stated as a test so the knife-edge is a fact in the suite, not a note in a report."""
        ok, _ = hs.should_alert("QQQ", QQQ_1008_PEAK, overrides={"QQQ": 2.00})
        assert ok is False


class TestDisplacement:
    def test_it_is_signed_and_relative_to_the_prior_close(self):
        assert hs.displacement_pct(100.0, 98.35) == pytest.approx(-1.65)
        assert hs.displacement_pct(100.0, 101.65) == pytest.approx(1.65)

    @pytest.mark.parametrize("pc,last", [(None, 100.0), (100.0, None), (None, None),
                                         ("x", 100.0), (100.0, "x")])
    def test_anything_missing_is_None_and_never_zero(self, pc, last):
        """0.0 would read as "unchanged" — the fake-zero this register keeps removing."""
        assert hs.displacement_pct(pc, last) is None

    def test_a_zero_prior_close_is_None_not_flat(self):
        """The ratio is undefined, not flat."""
        assert hs.displacement_pct(0, 100.0) is None


class TestTheThresholdGate:
    @pytest.mark.parametrize("sym,move,fires", [
        ("SPY", 1.05, True), ("SPY", 0.95, False),
        ("QQQ", 1.80, True), ("QQQ", 1.70, False),
        ("SMH", 3.10, True), ("SMH", 2.90, False),
    ])
    def test_each_symbol_uses_its_own_line(self, sym, move, fires):
        assert hs.should_alert(sym, move)[0] is fires

    @pytest.mark.parametrize("sym", ["SPY", "QQQ", "SMH"])
    def test_it_fires_in_EITHER_direction(self, sym):
        thr = hs.SESSION_THRESHOLD_PCT[sym]
        assert hs.should_alert(sym, thr + 0.1)[0] is True
        assert hs.should_alert(sym, -(thr + 0.1))[0] is True

    def test_exactly_AT_the_threshold_fires(self):
        """The boundary, stated rather than left to a `>` written from memory."""
        assert hs.should_alert("SPY", 1.0)[0] is True
        assert hs.should_alert("SPY", -1.0)[0] is True

    @pytest.mark.parametrize("sym", ["USO", "IBIT", "TLT", "GLD", "HYG", "XLF", "IYR", "", None])
    def test_an_untracked_symbol_never_alerts(self, sym):
        """CONTROL. Phase 1's own measurement: on 10-08 a size-ranked alarm would have spent the
        session shouting about oil while the equity selloff ranked below all of it."""
        ok, reason = hs.should_alert(sym, -9.0)
        assert ok is False and reason


class TestTheRealertLadder:
    def test_a_first_crossing_alerts(self):
        assert hs.should_alert("QQQ", -1.80, None)[0] is True

    def test_extending_half_a_point_further_re_alerts(self):
        assert hs.should_alert("QQQ", -2.35, -1.80)[0] is True

    def test_drifting_less_than_half_a_point_does_NOT(self):
        """The whole point of the ladder: one event is one message, not thirty."""
        assert hs.should_alert("QQQ", -2.00, -1.80)[0] is False
        assert hs.should_alert("QQQ", -1.85, -1.80)[0] is False

    def test_coming_back_toward_flat_does_not_re_alert(self):
        assert hs.should_alert("QQQ", -1.80, -2.50)[0] is False

    def test_exactly_half_a_point_further_DOES_re_alert(self):
        assert hs.should_alert("QQQ", -2.30, -1.80)[0] is True

    def test_a_reversal_through_the_other_side_is_a_NEW_event(self):
        """"Crosses its threshold, in either direction" — a session that was −1.8% and is now
        +1.8% is genuinely two things worth knowing, so the ladder applies within a sign only."""
        ok, reason = hs.should_alert("QQQ", 1.80, -1.80)
        assert ok is True and "reversed" in reason

    def test_a_reversal_that_does_not_reach_the_line_still_does_not_alert(self):
        """CONTROL for the rule above: the threshold gate runs first."""
        assert hs.should_alert("QQQ", 0.90, -1.80)[0] is False


class TestNotEvaluableIsNeverSilent:
    def test_a_missing_mark_says_so(self):
        ok, reason = hs.should_alert("QQQ", None)
        assert ok is False
        assert "NOT EVALUABLE" in reason

    def test_every_refusal_carries_a_reason(self):
        """"Did not alert" and "was never evaluated" are different facts, and only one is a
        defect."""
        for sym, move in (("QQQ", None), ("QQQ", 0.1), ("USO", -9.0), ("", 5.0), (None, 5.0)):
            ok, reason = hs.should_alert(sym, move)
            assert ok is False and reason.strip(), (sym, move)


class TestTheSessionWindow:
    @pytest.mark.parametrize("hhmm,inside", [
        ((9, 29), False), ((9, 30), True), ((12, 0), True), ((16, 0), True), ((16, 1), False),
        ((4, 0), False), ((20, 0), False),
    ])
    def test_regular_hours_only(self, hhmm, inside):
        when = datetime(2026, 10, 8, hhmm[0], hhmm[1], tzinfo=ET)
        assert hs.in_rth(when) is inside

    @pytest.mark.parametrize("day", [10, 11])     # 2026-10-10 Sat, 10-11 Sun
    def test_weekends_are_out(self, day):
        assert hs.in_rth(datetime(2026, 10, day, 12, 0, tzinfo=ET)) is False

    def test_a_naive_datetime_is_REFUSED_not_assumed(self):
        """Guessing a timezone would shift the whole window by hours, and this machine silently
        ignores `TZ=`."""
        assert hs.in_rth(datetime(2026, 10, 8, 12, 0)) is False

    def test_a_UTC_instant_is_converted_not_compared_raw(self):
        """Both instants are chosen so that raw UTC and converted ET DISAGREE — otherwise the
        test would pass against code that never converted at all.

        19:59Z is 15:59 EDT, inside, while a raw 19:59 is outside 09:30-16:00.
        13:00Z is 09:00 EDT, outside, while a raw 13:00 is inside.
        """
        assert hs.in_rth(datetime(2026, 10, 8, 19, 59, tzinfo=timezone.utc)) is True
        assert hs.in_rth(datetime(2026, 10, 8, 13, 0, tzinfo=timezone.utc)) is False


class TestItShipsDark:
    def test_the_flag_defaults_OFF(self, monkeypatch):
        monkeypatch.delenv(hs.FLAG, raising=False)
        assert hs.is_enabled() is False

    @pytest.mark.parametrize("val", ["", "   ", "0", "false", "no", "off", "maybe"])
    def test_anything_but_an_explicit_yes_is_off(self, monkeypatch, val):
        monkeypatch.setenv(hs.FLAG, val)
        assert hs.is_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
    def test_an_explicit_yes_enables_it(self, monkeypatch, val):
        monkeypatch.setenv(hs.FLAG, val)
        assert hs.is_enabled() is True

    def test_the_empty_string_is_off_which_is_the_Railway_trap(self):
        """Railway returns '' for an unset reference, so `os.getenv(k, default)` would hand back
        '' and read as set-but-empty. The `or` form is required."""
        monkeypatch = None
        import os
        old = os.environ.get(hs.FLAG)
        os.environ[hs.FLAG] = ""
        try:
            assert hs.is_enabled() is False
        finally:
            if old is None:
                os.environ.pop(hs.FLAG, None)
            else:
                os.environ[hs.FLAG] = old


class TestTheMessage:
    def test_it_states_the_time_in_MOUNTAIN_and_the_numbers_behind_it(self):
        now = datetime(2026, 10, 8, 20, 2, tzinfo=timezone.utc)   # 14:02 MDT
        msg = hs.format_message("QQQ", -1.76, 600.0, 589.44, now)
        assert "QQQ" in msg and "-1.76%" in msg
        assert "589.44" in msg and "600.00" in msg
        assert "14:02 MT" in msg
        assert "down" in msg

    def test_an_up_move_reads_as_up(self):
        now = datetime(2026, 10, 8, 20, 2, tzinfo=timezone.utc)
        assert "up" in hs.format_message("SPY", 1.20, 600.0, 607.2, now)

    def test_co_breaches_are_named(self):
        now = datetime(2026, 10, 8, 20, 2, tzinfo=timezone.utc)
        msg = hs.format_message("QQQ", -1.76, 600.0, 589.44, now, co=[("SMH", -3.65)])
        assert "SMH" in msg and "-3.65%" in msg


class TestTheCalibrationScriptIsHonest:
    def test_it_measures_intraday_not_the_close(self):
        """A daily close understates the alarm: a session that touched −1.4% and closed −0.6%
        would fire in life and not in a close-only replay."""
        import io
        import os

        p = os.path.join(__file__.rsplit("backend", 1)[0], "scripts",
                         "hermes_phase2_calibrate.py")
        src = io.open(p, encoding="utf-8").read()
        assert 'interval="5m"' in src
        assert "in_rth(when)" in src

    def test_it_uses_the_prior_sessions_last_bar_as_the_base(self):
        """A gap IS displacement — measuring from the session's own open would hide exactly the
        gap-down morning the principal wants to hear about."""
        import io
        import os

        p = os.path.join(__file__.rsplit("backend", 1)[0], "scripts",
                         "hermes_phase2_calibrate.py")
        src = io.open(p, encoding="utf-8").read()
        assert "sessions[cand][-1][1]" in src
        assert "no prior session close in range" in src

    def test_it_reports_a_conflict_rather_than_resolving_one(self):
        import io
        import os

        p = os.path.join(__file__.rsplit("backend", 1)[0], "scripts",
                         "hermes_phase2_calibrate.py")
        src = io.open(p, encoding="utf-8").read()
        assert "CALIBRATION AND CONTROL CONFLICT" in src
