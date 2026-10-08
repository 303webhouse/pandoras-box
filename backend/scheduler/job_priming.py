"""Prime interval jobs at boot, with a floor — R-IV.740(b).

THE FAULT THIS FIXES. `scheduler.add_job(fn, 'interval', hours=1)` passes no `start_date` and no
`next_run_time`, and APScheduler's own `IntervalTrigger.__init__` then does:

    start_date = start_date or (datetime.now(self.timezone) + self.interval)

So the first fire is one full hour AFTER the scheduler starts — the job never runs at boot. Every
deploy therefore discards up to a whole interval, and **a deploy cadence faster than the interval
starves the job indefinitely**: the timer is reset before it ever reaches zero. Measured
2026-10-07: eight deploys between 16:11Z and 19:37Z meant `crypto_cycle` fired ZERO times across
3.5 hours; the 19:37 boot then fired at 20:40:51Z (boot + build + 1h, exact); the 22:47 deploy's
23:50 fire was cancelled by a 23:05 deploy. Nothing was broken and nothing errored — the job was
simply never due.

THE SHAPE, as ruled. A primed first run ~3 minutes after boot, with a floor so a deploy storm
cannot multiply runs: if the last stored row is younger than the floor, the boot run is SKIPPED
and the next run is set to `last row + interval` instead.

Why a floor at all, rather than just running at boot: a full `crypto_cycle` is about a dozen
vendor calls per symbol across six symbols (~72) against a **shared 40/min Coinalyze budget**.
Priming unconditionally would have turned those eight deploys into eight full cycles instead of
zero — trading a starved job for a throttled one.

THE RULED NUMBERS ARE HOURLY: "younger than 50 minutes -> next run at last row + 60 minutes." A
15-minute job needs the same rule at its own scale, so the floor is held as a FRACTION of the
interval (50/60) rather than as 3000 seconds. At `hours=1` that reproduces the ruled numbers
exactly — 50 minutes and 60 minutes — which is the check that the generalisation is faithful and
not a reinterpretation.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Boot run fires about 3 minutes in, so the DB pool and vendor clients have settled. (The
# neighbouring asyncio loops already use 90s and 120s settling sleeps for the same reason.)
PRIME_DELAY_SECONDS = 180

# 50/60 of the interval. See the module docstring: at hours=1 this IS the ruled 50 minutes.
PRIME_FLOOR_FRACTION = 50.0 / 60.0

# Only jobs at or above this interval get primed. Below it, a deploy costs little and priming on
# every boot is the more expensive mistake.
PRIME_MIN_INTERVAL_SECONDS = 900

# A job's own output table is the best evidence that it ran, because it is the thing consumers
# read. `job_runs` is the fallback for jobs that write no row of their own.
FRESHNESS_TABLES: Dict[str, Tuple[str, str]] = {
    "crypto_cycle": ("crypto_cycle_log", "computed_at"),
    "crypto_regime": ("crypto_regime_log", "computed_at"),
    "crypto_tape_health": ("crypto_tape_health_log", "computed_at"),
}

# These two leave no row of their own: `composite_bias_refresh` recomputes a composite and
# `auto_dismiss_signals` mutates existing rows. `job_runs` is the only record they can have, and
# they are not wired into it yet — so `last_stored_at` will return provenance "unknown" for them
# and they will be primed on every boot. That is deliberate and it is cheap (no vendor fan-out),
# but it IS a floor that does not yet bite. Named here rather than left for someone to discover.
JOB_RUNS_ONLY = ("composite_bias_refresh", "auto_dismiss_signals")


def primed_next_run(
    *,
    now: datetime,
    interval_seconds: float,
    last_stored_at: Optional[datetime],
    provenance: str,
) -> Tuple[datetime, str]:
    """The first-run decision. PURE — no DB, no clock, no scheduler.

    Every argument is keyword-only and required so a caller cannot inherit another's answer by
    staying silent about it; `now` in particular is passed in, because a decision function that
    reads the clock itself cannot be tested at a chosen instant.

    Returns `(next_run_time, reason)`. The reason is returned rather than only logged so the
    caller can record WHY a job is due when it is, which is the thing nobody could see before.
    """
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive, got %r" % (interval_seconds,))
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    prime_at = now + timedelta(seconds=PRIME_DELAY_SECONDS)
    floor = interval_seconds * PRIME_FLOOR_FRACTION

    if last_stored_at is None:
        return prime_at, ("no stored row (%s) -> prime at boot+%ds"
                          % (provenance, PRIME_DELAY_SECONDS))

    last = last_stored_at if last_stored_at.tzinfo else last_stored_at.replace(tzinfo=timezone.utc)
    age = (now - last).total_seconds()

    if age < floor:
        candidate = last + timedelta(seconds=interval_seconds)
        if candidate <= prime_at:
            # The next scheduled moment is already here (or so close that waiting for it and
            # priming are the same act). Prime, so a job that is merely a little overdue is not
            # handed a next_run_time in the past.
            return prime_at, ("last row %.0fs old (floor %.0fs) but last+interval is already "
                              "due -> prime at boot+%ds" % (age, floor, PRIME_DELAY_SECONDS))
        return candidate, ("last row %.0fs old (< floor %.0fs, from %s) -> SKIP boot run, "
                           "next at last+%.0fs" % (age, floor, provenance, interval_seconds))

    return prime_at, ("last row %.0fs old (>= floor %.0fs, from %s) -> prime at boot+%ds"
                      % (age, floor, provenance, PRIME_DELAY_SECONDS))


async def last_stored_at(job_id: str) -> Tuple[Optional[datetime], str]:
    """`(timestamp, provenance)` for a job's most recent output.

    provenance is `"table"`, `"job_runs"`, or `"unknown"`. **"unknown" is not "never ran"** —
    `backend/jobs/job_runs.py` states the rule plainly: a job absent from `job_runs` is NOT
    WIRED, and that is never evidence that it did not run. So an unknown is returned as an
    unknown and the caller primes, which errs toward having data rather than toward trusting a
    silence.

    Never raises: a probe that fails must not prevent a scheduler from starting.
    """
    table = FRESHNESS_TABLES.get(job_id)
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            if table is not None:
                name, column = table
                # Identifiers come from the module-level map above, never from a caller.
                row = await conn.fetchrow(
                    "SELECT MAX(%s) AS newest FROM %s" % (column, name))
                if row and row["newest"]:
                    return row["newest"], "table"
                return None, "table"

            row = await conn.fetchrow(
                "SELECT MAX(finished_at) AS newest FROM job_runs "
                "WHERE job_name = $1 AND status = 'ok'", job_id)
            if row and row["newest"]:
                return row["newest"], "job_runs"
            return None, "unknown"
    except Exception as exc:
        logger.warning("[job_priming] freshness probe failed for %s: %s", job_id, exc)
        return None, "probe-failed"


async def prime(job_id: str, interval_seconds: float, *, now: Optional[datetime] = None
                ) -> Optional[datetime]:
    """The value to pass as `next_run_time`, or None to leave APScheduler's default alone.

    None is returned only for a job below `PRIME_MIN_INTERVAL_SECONDS`, so a caller that primes
    everything still gets the ruled behaviour.
    """
    if interval_seconds < PRIME_MIN_INTERVAL_SECONDS:
        return None
    now = now or datetime.now(timezone.utc)
    stored, provenance = await last_stored_at(job_id)
    when, reason = primed_next_run(now=now, interval_seconds=interval_seconds,
                                   last_stored_at=stored, provenance=provenance)
    logger.info("[job_priming] %s: %s (first run %s)", job_id, reason, when.isoformat())
    return when
