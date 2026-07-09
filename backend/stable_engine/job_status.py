"""Stable Engine job-status ledger + freshness SLOs (flatline detection).

CRITICAL: everything here writes via the hub's ASYNC pool (asyncpg / get_postgres_client),
NOT the engine's synchronous psycopg2. The whole point of this module is to detect the
disease that killed the pipe 2026-07-04 — the psycopg2 writer failing silently. If the
status ledger used psycopg2 too, it would die with the same illness and record nothing.

Two coupled signals:
  * job-status ledger (stable_job_status): last_success_at, last_error, consecutive_failures,
    alerted. Every scheduled job records success/failure here so a thrown exception is a
    counter increment, not a silent retry.
  * freshness SLOs: per-feed max data-age. When a feed ages past its SLO the read envelope
    escalates degraded -> flatline:true (a DEAD state, distinct from ordinary gray stale).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytz

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

# Per-feed freshness SLOs (seconds). tide is deliberately absent -> exempt (event-warmed
# UW cache, not a scheduled writer). RTH-only feeds only flatline during market hours.
SLO_SECONDS = {
    "nightly": 26 * 3600,   # close theme scores: nightly recompute every ~24h (+2h grace)
    "strip": 30 * 60,       # index/rates/fx live strip: 10-min cadence, 30-min SLO (RTH)
    "movers": 30 * 60,      # movers screener: 10-min cadence, 30-min SLO (RTH)
}
RTH_ONLY_FEEDS = {"strip", "movers"}
FAILURE_ALERT_THRESHOLD = 2  # consecutive failures before a flatline alert fires

# The scheduled jobs we track (job_name -> which feed it freshens).
JOB_FEEDS = {
    "nightly": "nightly",
    "provisional": "nightly",  # provisional snapshots also write theme_scores
    "strip": "strip",
    "movers": "movers",
}


def now_et() -> datetime:
    return datetime.now(ET)


def is_market_hours(dt_et: datetime | None = None) -> bool:
    dt = dt_et or now_et()
    if dt.weekday() >= 5:
        return False
    mins = dt.hour * 60 + dt.minute
    return 9 * 60 + 30 <= mins <= 16 * 60


def feed_flatline(feed: str, age_seconds: float | None, dt_et: datetime | None = None) -> bool:
    """True when a feed has aged past its SLO (DEAD). RTH-only feeds are exempt outside
    market hours (a movers feed that stops at the close is expected, not dead)."""
    slo = SLO_SECONDS.get(feed)
    if slo is None:
        return False  # tide / unknown -> exempt
    if age_seconds is None:
        # No data at all is only "dead" when the feed should be flowing.
        return (feed not in RTH_ONLY_FEEDS) or is_market_hours(dt_et)
    if feed in RTH_ONLY_FEEDS and not is_market_hours(dt_et):
        return False
    return age_seconds > slo


async def _ensure_table(conn) -> None:
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS stable_job_status (
               job_name TEXT PRIMARY KEY,
               last_success_at TIMESTAMPTZ,
               last_run_at TIMESTAMPTZ,
               last_error TEXT,
               consecutive_failures INT NOT NULL DEFAULT 0,
               alerted BOOLEAN NOT NULL DEFAULT FALSE,
               updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )"""
    )


async def mark_success(job_name: str) -> None:
    """Record a clean run: reset the failure counter and the one-shot alert flag."""
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await _ensure_table(conn)
            await conn.execute(
                """INSERT INTO stable_job_status
                     (job_name, last_success_at, last_run_at, last_error, consecutive_failures, alerted, updated_at)
                   VALUES ($1, now(), now(), NULL, 0, FALSE, now())
                   ON CONFLICT (job_name) DO UPDATE SET
                     last_success_at = now(), last_run_at = now(), last_error = NULL,
                     consecutive_failures = 0, alerted = FALSE, updated_at = now()""",
                job_name,
            )
    except Exception as e:
        logger.warning("[job_status] mark_success(%s) failed: %s", job_name, e)


async def mark_failure(job_name: str, err: str) -> bool:
    """Record a failed run. Returns True exactly once per incident — when the job first
    crosses into flatline (>= FAILURE_ALERT_THRESHOLD consecutive failures) and hasn't yet
    alerted. The caller fires the single Hermes alert on a True return."""
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await _ensure_table(conn)
            row = await conn.fetchrow(
                """INSERT INTO stable_job_status
                     (job_name, last_run_at, last_error, consecutive_failures, alerted, updated_at)
                   VALUES ($1, now(), $2, 1, FALSE, now())
                   ON CONFLICT (job_name) DO UPDATE SET
                     last_run_at = now(), last_error = $2,
                     consecutive_failures = stable_job_status.consecutive_failures + 1,
                     updated_at = now()
                   RETURNING consecutive_failures, alerted""",
                job_name, (err or "")[:2000],
            )
            fails = row["consecutive_failures"]
            if fails >= FAILURE_ALERT_THRESHOLD and not row["alerted"]:
                await conn.execute(
                    "UPDATE stable_job_status SET alerted = TRUE WHERE job_name = $1", job_name
                )
                return True
    except Exception as e:
        logger.warning("[job_status] mark_failure(%s) failed: %s", job_name, e)
    return False


async def get_all() -> list[dict]:
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await _ensure_table(conn)
            rows = await conn.fetch("SELECT * FROM stable_job_status ORDER BY job_name")
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[job_status] get_all failed: %s", e)
        return []


async def health_summary() -> dict:
    """Worst job status + oldest tracked feed age, for the /health stable_jobs block."""
    jobs = await get_all()
    now = datetime.now(timezone.utc)
    out_jobs: dict[str, dict] = {}
    worst = "ok"
    rank = {"ok": 0, "stale": 1, "flatline": 2}
    oldest_age = None
    for j in jobs:
        name = j["job_name"]
        ls = j["last_success_at"]
        age = (now - ls).total_seconds() if ls else None
        feed = JOB_FEEDS.get(name, name)
        fails = j["consecutive_failures"] or 0
        flat = fails >= FAILURE_ALERT_THRESHOLD or feed_flatline(feed, age)
        status = "flatline" if flat else ("stale" if fails > 0 else "ok")
        if rank[status] > rank[worst]:
            worst = status
        # Track the oldest age among feeds that should be flowing.
        if age is not None and (feed not in RTH_ONLY_FEEDS or is_market_hours()):
            oldest_age = age if oldest_age is None else max(oldest_age, age)
        out_jobs[name] = {
            "status": status,
            "consecutive_failures": fails,
            "last_success_age_s": round(age) if age is not None else None,
            "last_error": (j["last_error"] or None),
        }
    return {
        "worst_status": worst,
        "oldest_feed_age_s": round(oldest_age) if oldest_age is not None else None,
        "any_flatline": worst == "flatline",
        "jobs": out_jobs,
    }
