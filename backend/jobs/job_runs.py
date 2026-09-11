"""Durable job-run bookkeeping — T2 of the grader-precondition build.

R-IV.287(4): the schema is generic; THIS BUILD WIRES ONE JOB (the Triton grader).
A job absent from `job_runs` is NOT WIRED — it is never evidence that the job did
not run. See migrations/028_job_runs.sql.

WHY THIS EXISTS. `last_run` lived in process memory, so a restart re-armed the day
and a missed day left no trace. "Did it run?" was unanswerable; it is now a SELECT.

FAILURE POSTURE — deliberate, and the opposite of the metrics modules.
`signals_freshness.record_attempt` swallows everything because a metric must never
break a pipeline. This module is not a metric: `has_completed()` GATES the run, so
its failure mode decides whether work happens.

  - Write failures are swallowed. Bookkeeping must not kill the job it records.
  - `has_completed()` returns a TRI-STATE: True / False / None (unreadable).
  - The CALLER decides what unknown means, and for the grader unknown means RUN.

That last choice is the load-bearing one, so it is argued rather than assumed: the
grader is idempotent — it only touches rows with `graded_at IS NULL`, and grading a
row makes it ineligible — so a duplicate pass converges and costs one wasted query.
A SKIPPED pass is the defect this whole build exists to remove. Between an
idempotent repeat and a silent stop, the repeat is strictly safer, and it is bounded
by the loop's own 30-minute cadence.
"""

import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# Wired in this build. Kept as a constant so the loop and the reader cannot drift.
JOB_TRITON_GRADER = "triton_grader"   # the string R-IV.295(a) rules
JOB_NIGHTLY = "stable_nightly"      # the string R-IV.360(1) rules

# Terminal statuses, enumerated. Anything else is not a completion.
STATUS_RUNNING = "running"
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"
STATUS_SKIPPED = "skipped"


async def start_run(job_name: str, session_date: date) -> Optional[int]:
    """Open a run row. Returns its id, or None if bookkeeping is unavailable."""
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "INSERT INTO job_runs (job_name, session_date, status) "
                "VALUES ($1, $2, $3) RETURNING id",
                job_name, session_date, STATUS_RUNNING,
            )
    except Exception as exc:
        logger.warning("[job_runs] start_run(%s) failed: %s", job_name, exc)
        return None


async def finish_run(run_id: Optional[int], status: str,
                     rows_touched: Optional[int] = None,
                     skip_reason: Optional[str] = None,
                     error: Optional[str] = None) -> None:
    """Close a run row. No-op when start_run could not open one."""
    if run_id is None:
        return
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE job_runs SET finished_at = NOW(), status = $2, "
                "rows_touched = $3, skip_reason = $4, error = $5 WHERE id = $1",
                run_id, status, rows_touched,
                (skip_reason or None), (error[:500] if error else None),
            )
    except Exception as exc:
        logger.warning("[job_runs] finish_run(%s) failed: %s", run_id, exc)


async def has_completed(job_name: str, session_date: date) -> Optional[bool]:
    """TRI-STATE. True = a successful run exists for this session date.
    False = none exists. None = the question could not be answered.

    None is not False. A caller that collapses them has decided what an
    unreadable database means without saying so.
    """
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            found = await conn.fetchval(
                "SELECT 1 FROM job_runs WHERE job_name = $1 AND session_date = $2 "
                "AND status = $3 LIMIT 1",
                job_name, session_date, STATUS_OK,
            )
        return found is not None
    except Exception as exc:
        logger.warning("[job_runs] has_completed(%s) unreadable: %s", job_name, exc)
        return None


async def last_completed(job_name: str) -> Optional[dict]:
    """The most recent run that COUNTS AS RAN, for the T3 sentinel (R-IV.295(a)).

    `ok` OR `skipped`. A pass that ran and skipped for a stated reason (T4) ran:
    **the sentinel measures the pass, not the grades.** `timeout` and `error` are
    excluded — those are the pass failing, which is precisely what must alarm.

    Returns None when there is no such run OR when the table cannot be read. The
    caller must not read None as "stale": see signals_freshness, which renders an
    unreadable age as unknown rather than as an age past its SLO.
    """
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT session_date, finished_at, status FROM job_runs "
                "WHERE job_name = $1 AND status = ANY($2::text[]) "
                "AND finished_at IS NOT NULL "
                "ORDER BY finished_at DESC LIMIT 1",
                job_name, [STATUS_OK, STATUS_SKIPPED],
            )
        return dict(row) if row else None
    except Exception as exc:
        logger.warning("[job_runs] last_completed(%s) failed: %s", job_name, exc)
        return None


async def last_run(job_name: str) -> Optional[dict]:
    """The most recent run row for /health and the build report, or None."""
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT session_date, started_at, finished_at, status, rows_touched, "
                "skip_reason, error FROM job_runs WHERE job_name = $1 "
                "ORDER BY started_at DESC LIMIT 1",
                job_name,
            )
        return dict(row) if row else None
    except Exception as exc:
        logger.warning("[job_runs] last_run(%s) failed: %s", job_name, exc)
        return None
