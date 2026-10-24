"""R-IV.1297(f)2 — cta_scanner judged on whether it RAN, with a 60-minute RTH SLO.

WHY STEP 2 WAITED, and it is the load-bearing fact. `signals_freshness.py` says twice that
re-pointing a class at `job_runs` it does not write renders `no_data` -- which does NOT degrade
-- so the sentinel is silently disarmed and /health goes green while becoming incapable of
firing. The producer's `start_run("cta_scanner", ...)` shipped first (c7261e90, deployed
2026-10-22 17:27:14Z) and R-IV.1398(a) cleared the move on measured evidence: 2026-10-23
carried 26 rows, all `ok`, the first in-RTH row 1.2 minutes after the open.

AND TWO GUARANTEED FALSE REDS HAD TO BE CLOSED BEFORE THE BOUND COULD TIGHTEN:

  1. `_job_alive_status` checked `age > SLO` with no RTH gate, and cta_scanner is the FIRST
     RTH-only member of JOB_ALIVE_CLASSES -- so a 60-minute bound would read flatline at
     17:30 ET and hold it all night and all weekend, on a registered class.
  2. At 09:31 ET the newest run can still be yesterday's, so the age is ~17 hours while the
     session is one minute old. A 60-minute bound cannot honestly be breached by a session
     younger than 60 minutes.

Each is tested as a case that WOULD have been a false red, not as a property that happens to
hold.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from stable_engine import signals_freshness as sf

ET = ZoneInfo("America/New_York")
OK_RUN = {"status": "ok", "rows_touched": 3}

FRI = (2026, 10, 23)
SAT = (2026, 10, 24)
MON = (2026, 10, 26)


def _at(ymd, hh, mm, ss=0):
    return datetime(ymd[0], ymd[1], ymd[2], hh, mm, ss, tzinfo=ET)


# ── 1. the move itself, and its precondition ────────────────────────────────

def test_cta_is_judged_on_whether_it_RAN_not_on_whether_it_emitted():
    """The scanner emits only when an asset leaves a no-signal zone, so signal age answered
    the wrong question: a session where nothing qualified read exactly like a dead scanner."""
    assert sf.AGE_SOURCES["cta_scanner"] == sf.AGE_SOURCE_JOB_RUNS


def test_it_is_an_ALIVE_class_so_an_ERRORED_run_is_visible():
    """`last_completed` returns only `ok` or `skipped`, so an errored run comes back None and
    renders `no_data` instead of the flatline it is. For a class whose whole question is
    liveness that is backwards -- which is what JOB_ALIVE_CLASSES exists to fix."""
    assert "cta_scanner" in sf.JOB_ALIVE_CLASSES


def test_the_producer_writes_the_job_runs_row_FIRST():
    """THE ORDERING PRECONDITION, asserted rather than trusted. Re-pointing a class at a
    job_runs row nobody writes renders `no_data`, which does not degrade -- the surface would
    go green while the sentinel became incapable of ever firing, and the approval's own
    control would pass vacuously."""
    import os
    sched = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "scheduler", "bias_scheduler.py")
    with open(sched, encoding="utf-8-sig") as fh:
        src = fh.read()
    assert 'start_run("cta_scanner"' in src or "start_run('cta_scanner'" in src, (
        "cta_scanner is pointed at job_runs but nothing writes its run row: the sentinel is "
        "disarmed, not armed")


def test_the_job_name_needs_no_alias():
    """The class name and the job_runs name are the same string, so no AGE_SOURCE_JOB_NAME
    entry is needed -- and a stray one would send the read to a job that never writes."""
    assert sf.AGE_SOURCE_JOB_NAME.get("cta_scanner") is None


def test_the_slo_is_sixty_minutes():
    """4h -> 60 minutes, which only the move to run age makes safe: on SIGNAL age a 60-minute
    bound would be a false-flatline machine. On run age it is a 4x envelope over measured
    behaviour -- 26 runs across a ~6.5-hour session is one roughly every 15 minutes."""
    assert sf.SLO_SECONDS["cta_scanner"] == 60 * 60


# ── 2. the nightly and weekend false reds ───────────────────────────────────

@pytest.mark.parametrize("ymd,hh,mm,age_s,label", [
    (FRI, 16, 30, 2 * 3600, "half an hour after the close"),
    (FRI, 17, 30, 2 * 3600, "the evening"),
    (FRI, 23, 59, 8 * 3600, "midnight"),
    (SAT, 12, 0, 44 * 3600, "Saturday noon"),
    (MON, 9, 0, 65 * 3600, "Monday pre-open, after a whole weekend"),
])
def test_it_does_NOT_flatline_outside_the_session(ymd, hh, mm, age_s, label):
    """cta_scanner is RTH-only, and RTH_ONLY_CLASSES was consulted ONLY by `_class_status` --
    the job-alive path ignored it. A 60-minute bound there is a red every single evening, on a
    REGISTERED class, so /health would be degraded nightly."""
    status, note = sf._job_alive_status("cta_scanner", age_s, OK_RUN, dt_et=_at(ymd, hh, mm))
    assert status == "ok", (label, status, note)
    assert "outside RTH" in (note or ""), note


def test_WITHOUT_the_gate_the_evening_WOULD_have_been_a_flatline():
    """POSITIVE CONTROL (Convention #30). A guard never shown to be load-bearing cannot be
    told from dead code, so the gate is removed and the false red must reappear."""
    evening = _at(FRI, 17, 30)
    assert sf._job_alive_status("cta_scanner", 2 * 3600, OK_RUN, dt_et=evening)[0] == "ok"

    real = sf.RTH_ONLY_CLASSES
    sf.RTH_ONLY_CLASSES = frozenset(c for c in real if c != "cta_scanner")
    try:
        bad = sf._job_alive_status("cta_scanner", 2 * 3600, OK_RUN, dt_et=evening)
    finally:
        sf.RTH_ONLY_CLASSES = real

    assert bad[0] == "flatline", (
        "removing cta_scanner from RTH_ONLY_CLASSES did NOT reproduce the nightly false red, "
        "so the gate is not what prevents it and this test proves nothing: %r" % (bad,))


# ── 3. the false red at the open ────────────────────────────────────────────

@pytest.mark.parametrize("hh,mm,age_s", [
    (9, 30, 65 * 3600),     # the bell
    (9, 31, 17 * 3600),     # QUERY measured the first row at +1.2 minutes
    (9, 45, 17 * 3600),
    (10, 29, 17 * 3600),    # 59 minutes in: a 60-minute bound still cannot be breached
])
def test_a_session_YOUNGER_than_the_slo_cannot_breach_it(hh, mm, age_s):
    """At 09:31 the newest run may still be yesterday's close, so the age is ~17 hours while
    the session is one minute old. Judging a 60-minute bound against that would have called a
    healthy scanner dead every morning until its first scan landed."""
    status, note = sf._job_alive_status("cta_scanner", age_s, OK_RUN, dt_et=_at(MON, hh, mm))
    assert status == "ok", (hh, mm, status, note)
    assert "into the session" in (note or ""), note


def test_the_elapsed_helper_is_None_outside_rth_and_counts_from_0930():
    assert sf.rth_elapsed_seconds(_at(MON, 9, 29)) is None
    assert sf.rth_elapsed_seconds(_at(SAT, 12, 0)) is None
    assert sf.rth_elapsed_seconds(_at(MON, 9, 30)) == 0.0
    assert sf.rth_elapsed_seconds(_at(MON, 10, 30)) == 3600.0
    assert sf.rth_elapsed_seconds(_at(MON, 9, 30, 42)) == 42.0


# ── 4. the alarm still fires ─────────────────────────────────────────────────

@pytest.mark.parametrize("hh,mm,age_s", [
    (10, 31, 61 * 60),
    (12, 0, 90 * 60),
    (14, 0, 3 * 3600),
    (15, 59, 4 * 3600),
])
def test_it_DOES_flatline_when_the_scheduler_stops_mid_session(hh, mm, age_s):
    """The point of the whole change. Two gates that between them exempted everything would be
    a sentinel that cannot fail -- the fault this module's own header names."""
    status, note = sf._job_alive_status("cta_scanner", age_s, OK_RUN, dt_et=_at(MON, hh, mm))
    assert status == "flatline", (hh, mm, status, note)
    assert "scheduler is not firing" in (note or ""), note


def test_an_ERRORED_run_flatlines_whatever_the_clock_says():
    """Only the AGE bound is gated on session time. An error is an error whenever it happened,
    and gating it would have hidden a scan that tried and failed until the next open."""
    for when in (_at(FRI, 22, 0), _at(SAT, 12, 0), _at(MON, 9, 31), _at(MON, 14, 0)):
        status, note = sf._job_alive_status(
            "cta_scanner", 120, {"status": "error", "error": "boom"}, dt_et=when)
        assert status == "flatline", (when, status)
        assert "errored" in note, note


def test_a_MISSING_run_record_is_not_health_whatever_the_clock_says():
    """An absent record is unknown at 03:00 just as much as at noon, and claiming health on an
    absent record is the fault the alive/emitted split exists to remove."""
    for when in (_at(FRI, 22, 0), _at(MON, 14, 0)):
        status, _note = sf._job_alive_status("cta_scanner", None, None, dt_et=when)
        assert status == "no_data", (when, status)


# ── 5. the gate did not leak ─────────────────────────────────────────────────

@pytest.mark.parametrize("cls", ["crypto_scanner", "crypto_engine", "crypto_cvd_engine"])
def test_the_24_7_classes_are_UNAFFECTED_by_the_rth_gate(cls):
    """POSITIVE CONTROL. Crypto trades round the clock and must still flatline at 03:00 --
    anti-fake-sick. The gate keys on RTH_ONLY_CLASSES, which none of them is in, and this
    asserts the consequence rather than the membership."""
    status, note = sf._job_alive_status(cls, 13 * 3600, OK_RUN, dt_et=_at(SAT, 3, 0))
    assert status == "flatline", (cls, status, note)


def test_cta_is_the_ONLY_rth_only_member_of_the_alive_set():
    """Stated so the next person adding an RTH-only alive class knows the gate already exists
    and is theirs to reuse -- and so a change to that intersection fails here first."""
    assert sf.JOB_ALIVE_CLASSES & sf.RTH_ONLY_CLASSES == {"cta_scanner"}


def test_a_quiet_scan_is_still_quiet_and_not_an_alarm():
    """A scanner that ran and emitted nothing because every asset sits in a no-signal zone is
    QUIET. The emitted count is reported beside the status and cannot move it."""
    status, note = sf._job_alive_status(
        "cta_scanner", 300, {"status": "ok", "rows_touched": 0}, dt_et=_at(MON, 14, 0))
    assert status == "ok"
    assert note == "ran and emitted nothing"


# ── 6. a scan IN FLIGHT is not a failed scan ────────────────────────────────
#
# FOUND WHILE SHIPPING THIS RULING, and beyond its letter. `last_run` returns the most recent
# row WHATEVER its status, including a `running` one, and `_job_alive_status` treated anything
# outside ("ok","success","completed","skipped") as an error. So a /health read landing while a
# scan was mid-pass reported `flatline -- the scan errored: running`: false, and with a message
# that sends the next reader hunting an exception that never happened.
#
# Pre-existing for the three crypto classes. cta_scanner runs roughly every fifteen minutes
# through the session, so adding it widens the window the fault can be caught in -- which is
# why the fix belongs with the change that widens it.

def _running(minutes_ago, naive=False):
    from datetime import datetime, timedelta, timezone
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    if naive:
        started = started.replace(tzinfo=None)
    return {"status": "running", "started_at": started}


def test_a_scan_in_flight_is_OK_and_not_an_error():
    status, note = sf._job_alive_status("cta_scanner", None, _running(2),
                                        dt_et=_at(MON, 14, 0))
    assert status == "ok", (status, note)
    assert note == "a scan is in flight"


def test_a_HUNG_scan_is_still_caught_so_the_sentinel_can_still_fire():
    """The loosening above cannot be unbounded. `age` comes from `finished_at`, which stays
    NULL while a run is in flight, so calling every `running` row healthy would leave a scan
    that HANGS with the newest row `running`, the age None, and no bound able to catch it --
    a sentinel that cannot fail. The discriminator is how long it has been running."""
    status, note = sf._job_alive_status("cta_scanner", None, _running(90),
                                        dt_et=_at(MON, 14, 0))
    assert status == "flatline", (status, note)
    assert "has not finished" in note, note


def test_a_naive_started_at_is_read_as_utc_and_not_silently_skipped():
    """The column is TIMESTAMPTZ, but naive values have come back through other paths in this
    module before. Treating one as unreadable would make a hung scan look healthy."""
    status, note = sf._job_alive_status("cta_scanner", None, _running(90, naive=True),
                                        dt_et=_at(MON, 14, 0))
    assert status == "flatline", (status, note)


def test_an_in_flight_scan_is_not_judged_OUTSIDE_the_session():
    """Same gate as the age bound, and from the same helper: an RTH-only scanner is not judged
    at all outside its session, so a run left `running` at the close is not an overnight red."""
    status, _note = sf._job_alive_status("cta_scanner", None, _running(90),
                                         dt_et=_at(FRI, 22, 0))
    assert status == "ok"


def test_a_running_row_with_no_started_at_cannot_be_judged_and_says_so():
    status, note = sf._job_alive_status("cta_scanner", None, {"status": "running"},
                                        dt_et=_at(MON, 14, 0))
    assert status == "ok"
    assert note == "a scan is in flight"


def test_the_running_label_comes_from_job_runs_and_cannot_DRIFT():
    """R-IV.925(b): the label is asked for, not retyped. A fallback to a different string
    would make the in-flight branch dead code and every mid-pass read an error again."""
    from jobs.job_runs import STATUS_RUNNING
    assert sf._status_running() == STATUS_RUNNING == "running"


def test_the_HUNG_bound_is_UNGATED_for_the_24_7_classes():
    """POSITIVE CONTROL. Crypto must still catch a hang at 03:00 -- the gate keys on
    RTH_ONLY_CLASSES and none of them is in it."""
    status, note = sf._job_alive_status("crypto_scanner", None, _running(13 * 60),
                                        dt_et=_at(SAT, 3, 0))
    assert status == "flatline", (status, note)


def test_both_time_bounds_share_ONE_gate():
    """A gate written twice is a gate that will disagree with itself, and whichever copy is
    looser decides. `_slo_gate` is the single author for "it has not run" and "it started and
    never finished" alike."""
    assert sf._slo_gate("cta_scanner", _at(FRI, 17, 30)) == "outside RTH"
    assert "into the session" in sf._slo_gate("cta_scanner", _at(MON, 9, 31))
    assert sf._slo_gate("cta_scanner", _at(MON, 14, 0)) is None
    assert sf._slo_gate("crypto_scanner", _at(SAT, 3, 0)) is None
