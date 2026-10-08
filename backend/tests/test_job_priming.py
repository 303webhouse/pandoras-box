"""Interval jobs are primed at boot, with a floor — R-IV.740(b).

THE BUG: `add_job(fn, 'interval', hours=1)` first fires one WHOLE INTERVAL after boot, because
APScheduler's `IntervalTrigger.__init__` does `start_date = start_date or (now + self.interval)`.
So the job never ran at boot, every deploy discarded up to an hour, and a deploy cadence faster
than the interval starved it outright. Measured 2026-10-07: eight deploys 16:11Z-19:37Z meant
`crypto_cycle` fired zero times in 3.5 hours. Nothing errored; the job was never due.

WHY THE FLOOR: priming unconditionally would have turned those eight deploys into eight full
cycles (~72 vendor calls each, against a shared 40/min budget) instead of zero.

THE RULED NUMBERS ARE HOURLY -- "younger than 50 minutes -> next run at last row + 60 minutes".
The implementation holds the floor as a FRACTION (50/60) so a 15-minute job gets the same rule at
its own scale. `test_the_ruled_hourly_numbers_are_reproduced_exactly` is the check that this
generalisation is faithful rather than a reinterpretation: at hours=1 it must be 50 and 60
minutes on the nose.
"""
import ast
import io
import os
from datetime import datetime, timedelta, timezone

import pytest

from scheduler.job_priming import (PRIME_DELAY_SECONDS, PRIME_FLOOR_FRACTION,
                                   PRIME_MIN_INTERVAL_SECONDS, primed_next_run)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 8, 1, 0, 0, tzinfo=timezone.utc)
HOUR = 3600.0
QUARTER = 900.0


def decide(*, age_seconds=None, interval=HOUR, provenance="table", now=NOW):
    last = None if age_seconds is None else now - timedelta(seconds=age_seconds)
    return primed_next_run(now=now, interval_seconds=interval,
                           last_stored_at=last, provenance=provenance)


class TestTheTwoControlsTheRulingNames:
    """"a simulated boot with a fresh row skips; one with a stale row runs" -- R-IV.740(b)."""

    def test_a_boot_with_a_FRESH_row_SKIPS_the_boot_run(self):
        when, reason = decide(age_seconds=10 * 60)          # 10 min old, hourly job
        assert when == NOW - timedelta(minutes=10) + timedelta(hours=1)
        assert when == NOW + timedelta(minutes=50)
        assert "SKIP boot run" in reason
        # and it is NOT the primed time
        assert when != NOW + timedelta(seconds=PRIME_DELAY_SECONDS)

    def test_a_boot_with_a_STALE_row_RUNS(self):
        when, reason = decide(age_seconds=90 * 60)          # 90 min old, hourly job
        assert when == NOW + timedelta(seconds=PRIME_DELAY_SECONDS)
        assert "prime at boot+180s" in reason
        assert "SKIP" not in reason

    def test_tonight_exactly(self):
        """The real numbers: last row 22:40:51Z, boot 01:0xZ. 2h20m old -> must run."""
        now = datetime(2026, 10, 8, 1, 5, 0, tzinfo=timezone.utc)
        last = datetime(2026, 10, 7, 22, 40, 51, tzinfo=timezone.utc)
        when, reason = primed_next_run(now=now, interval_seconds=HOUR,
                                       last_stored_at=last, provenance="table")
        assert when == now + timedelta(seconds=180)
        assert "prime" in reason


class TestTheFloorBoundary:
    def test_the_ruled_hourly_numbers_are_reproduced_exactly(self):
        """At hours=1 the fraction MUST come out as the ruled 50 minutes."""
        assert HOUR * PRIME_FLOOR_FRACTION == 3000.0            # 50 minutes
        assert 3000.0 / 60 == 50

    def test_just_under_the_floor_skips(self):
        when, reason = decide(age_seconds=50 * 60 - 1)
        assert "SKIP boot run" in reason
        # last + 3600 == (now - 2999) + 3600 == now + 601s, i.e. ten minutes out
        assert when == NOW + timedelta(seconds=601)

    def test_exactly_at_the_floor_RUNS(self):
        """"younger than 50 minutes" skips, so 50 minutes itself does not."""
        when, reason = decide(age_seconds=50 * 60)
        assert when == NOW + timedelta(seconds=PRIME_DELAY_SECONDS)
        assert "SKIP" not in reason

    def test_a_15_minute_job_gets_the_floor_at_ITS_scale(self):
        assert QUARTER * PRIME_FLOOR_FRACTION == 750.0          # 12.5 minutes
        when, reason = decide(age_seconds=10 * 60, interval=QUARTER)
        assert "SKIP boot run" in reason                        # 10m < 12.5m
        assert when == NOW + timedelta(minutes=5)               # last + 15m

        when, reason = decide(age_seconds=13 * 60, interval=QUARTER)
        assert "SKIP" not in reason                             # 13m >= 12.5m
        assert when == NOW + timedelta(seconds=PRIME_DELAY_SECONDS)


class TestItNeverHandsBackAPastTime:
    def test_a_next_run_closer_than_the_prime_delay_is_primed_instead(self):
        """A 15-minute job whose row is 730s old: under the floor (750s), but last+interval is
        only 170s away -- inside the prime delay. Returning it would schedule a first run before
        the pool has settled, and in the limit a time already gone.

        I first wrote this with an hourly job and it could not fail -- see
        `test_the_already_due_branch_is_unreachable_for_an_hourly_job` for why."""
        when, reason = decide(age_seconds=730, interval=QUARTER)
        assert when == NOW + timedelta(seconds=PRIME_DELAY_SECONDS)
        assert "already due" in reason

    def test_the_already_due_branch_is_unreachable_for_an_hourly_job(self):
        """Recorded so nobody later deletes the guard as dead code.

        The branch needs `age >= interval - PRIME_DELAY` AND `age < interval * 50/60`. Those
        overlap only while `interval/6 > PRIME_DELAY`, i.e. **interval < 1080s (18 min)**. So it
        is live for the two 15-minute jobs and genuinely unreachable for the three hourly ones.
        """
        assert HOUR - PRIME_DELAY_SECONDS == 3420
        assert HOUR * PRIME_FLOOR_FRACTION == 3000
        assert HOUR - PRIME_DELAY_SECONDS > HOUR * PRIME_FLOOR_FRACTION   # no overlap
        # and for a 15-minute job the window is [720, 750)
        assert QUARTER - PRIME_DELAY_SECONDS == 720
        assert QUARTER * PRIME_FLOOR_FRACTION == 750
        for age in (720, 735, 749):
            _, reason = decide(age_seconds=age, interval=QUARTER)
            assert "already due" in reason, age
        for age in (719, 750):
            _, reason = decide(age_seconds=age, interval=QUARTER)
            assert "already due" not in reason, age

    @pytest.mark.parametrize("age", [0, 1, 60, 600, 1799, 2999, 3000, 3001, 3599, 3600, 7200])
    def test_the_answer_is_never_before_now_at_any_age(self, age):
        when, _ = decide(age_seconds=age)
        assert when >= NOW, age

    def test_a_row_dated_in_the_FUTURE_does_not_produce_a_past_run(self):
        """Clock skew between the app and the DB is real; a negative age must not underflow."""
        when, reason = primed_next_run(now=NOW, interval_seconds=HOUR,
                                       last_stored_at=NOW + timedelta(minutes=5),
                                       provenance="table")
        assert when >= NOW
        assert when == NOW + timedelta(minutes=65)


class TestAbsenceIsNotStaleness:
    def test_no_row_at_all_primes(self):
        when, reason = decide(age_seconds=None)
        assert when == NOW + timedelta(seconds=PRIME_DELAY_SECONDS)
        assert "no stored row" in reason

    @pytest.mark.parametrize("prov", ["table", "job_runs", "unknown", "probe-failed"])
    def test_the_provenance_is_carried_into_the_reason(self, prov):
        """`backend/jobs/job_runs.py`: a job absent from job_runs is NOT WIRED, and that is never
        evidence it did not run. So the reason has to say WHERE the answer came from -- otherwise
        'no stored row' reads as 'the job is dead' when it may only mean 'nobody wired it'."""
        _, reason = decide(age_seconds=None, provenance=prov)
        assert prov in reason

    def test_a_failed_probe_primes_rather_than_skipping(self):
        """Erring toward having data. A probe that fails must not silently cancel a boot run."""
        when, _ = decide(age_seconds=None, provenance="probe-failed")
        assert when == NOW + timedelta(seconds=PRIME_DELAY_SECONDS)


class TestItRefusesNonsense:
    def test_a_naive_now_is_refused(self):
        with pytest.raises(ValueError):
            primed_next_run(now=datetime(2026, 10, 8, 1, 0, 0), interval_seconds=HOUR,
                            last_stored_at=None, provenance="table")

    @pytest.mark.parametrize("bad", [0, -1, -3600])
    def test_a_nonpositive_interval_is_refused(self, bad):
        with pytest.raises(ValueError):
            primed_next_run(now=NOW, interval_seconds=bad, last_stored_at=None,
                            provenance="table")

    def test_a_naive_last_row_is_read_as_UTC(self):
        """asyncpg hands back naive timestamps from some columns; treating one as local time
        would move the age by hours and flip the floor."""
        when, _ = primed_next_run(now=NOW, interval_seconds=HOUR,
                                  last_stored_at=datetime(2026, 10, 8, 0, 50, 0),
                                  provenance="table")
        assert when == NOW + timedelta(minutes=50)

    def test_every_argument_is_keyword_only(self):
        """So a caller cannot inherit another's answer by staying silent about it."""
        with pytest.raises(TypeError):
            primed_next_run(NOW, HOUR, None, "table")


class TestEveryIntervalJobIsPrimed:
    """Structural: a job added later without priming must fail here, not go unnoticed."""

    MULT = {"weeks": 604800, "days": 86400, "hours": 3600, "minutes": 60, "seconds": 1}

    def _interval_jobs(self, src):
        out = []
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_job"):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            trig = None
            if len(node.args) >= 2:
                try:
                    trig = ast.literal_eval(node.args[1])
                except Exception:
                    trig = None
            if trig != "interval":
                continue
            secs = 0
            for unit, mult in self.MULT.items():
                if unit in kw:
                    try:
                        secs += ast.literal_eval(kw[unit]) * mult
                    except Exception:
                        pass
            jid = None
            if "id" in kw:
                try:
                    jid = ast.literal_eval(kw["id"])
                except Exception:
                    pass
            out.append((jid, secs, "next_run_time" in kw))
        return out

    def test_the_scheduler_source_has_every_long_interval_job_primed(self):
        src = io.open(os.path.join(BACKEND, "scheduler", "bias_scheduler.py"),
                      encoding="utf-8-sig").read()
        jobs = self._interval_jobs(src)
        assert jobs, "found no interval jobs -- the parser is broken, not the file"
        unprimed = [(j, s) for j, s, primed in jobs
                    if s >= PRIME_MIN_INTERVAL_SECONDS and not primed]
        assert not unprimed, ("interval jobs >= %ds with no next_run_time: %s"
                              % (PRIME_MIN_INTERVAL_SECONDS, unprimed))

    def test_the_five_ruled_jobs_are_the_ones_primed(self):
        src = io.open(os.path.join(BACKEND, "scheduler", "bias_scheduler.py"),
                      encoding="utf-8-sig").read()
        primed = {j for j, s, p in self._interval_jobs(src) if p}
        assert primed == {"auto_dismiss_signals", "crypto_regime", "crypto_cycle",
                          "crypto_tape_health", "composite_bias_refresh"}, primed

    def test_the_short_interval_jobs_are_deliberately_NOT_primed(self):
        """Below 15 minutes a deploy costs little, and priming every boot is the worse mistake."""
        src = io.open(os.path.join(BACKEND, "scheduler", "bias_scheduler.py"),
                      encoding="utf-8-sig").read()
        short = {j: p for j, s, p in self._interval_jobs(src)
                 if s < PRIME_MIN_INTERVAL_SECONDS}
        assert short, "expected some sub-15-minute interval jobs"
        assert not any(short.values()), short

    def test_THE_CHECKER_CAN_FAIL(self):
        """POSITIVE CONTROL (#30). The structural test above passes on a file that is already
        correct, so on its own it proves nothing. This feeds it a job that is NOT primed and
        requires that it be caught."""
        bad = (
            "sched.add_job(fn, 'interval', hours=1, id='unprimed_job', name='x')\n"
            "sched.add_job(fn, 'interval', minutes=20, id='primed_job', "
            "next_run_time=z, name='y')\n"
            "sched.add_job(fn, 'interval', minutes=5, id='short_job', name='z')\n"
        )
        jobs = self._interval_jobs(bad)
        assert ("unprimed_job", 3600, False) in jobs
        assert ("primed_job", 1200, True) in jobs
        assert ("short_job", 300, False) in jobs
        unprimed = [(j, s) for j, s, p in jobs
                    if s >= PRIME_MIN_INTERVAL_SECONDS and not p]
        assert unprimed == [("unprimed_job", 3600)], unprimed


class TestPrimeSkipsShortJobs:
    @pytest.mark.asyncio
    async def test_a_sub_threshold_job_gets_no_next_run_time(self):
        """prime() returns None below the threshold, so a caller that primes everything still
        gets the ruled behaviour and APScheduler's default is left alone."""
        from scheduler.job_priming import prime
        assert await prime("btc_signals_refresh", 300) is None
        assert await prime("strc_circuit_breaker_poller", 299) is None
