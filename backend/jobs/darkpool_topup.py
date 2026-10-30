"""R-IV.1456(f): ONE weekend top-up of the dark-pool catch-up, up to 1,000 calls. One-shot.

The nightly forward walk (jobs/darkpool_forward.py) spends at most 240 calls, and only what the
session that just closed leaves over goes to the backlog. Nights 10-27 -> 10-29 were held to 62 by
the off-hours factor (fixed in 415791a9), so 10-23 and the 10-26 -> 10-29 names NVDA, AAPL, MSFT
and TSLA are unwritten, and the vendor drops its oldest dark-pool session every trading day:
10-23 is recoverable only through Fri 11-06's walk. This run spends the reserve on the backlog,
OLDEST FIRST, on a weekend when no walk runs.

HOW IT RUNS. Server-side, never from Nick's PC: at startup, only when the variable
`DARKPOOL_TOPUP_ARM` equals ARM_VALUE exactly. Setting it is a deploy. Then:
  * a Postgres advisory lock, so two processes cannot both run it;
  * REFUSES if any `darkpool_topup` row already exists in job_runs (one run, ever -- a second
    one is a new ruling, not a retry);
  * REFUSES on a trading day (the nightly walk owns weekdays; this is a weekend run);
  * its own governor tag, `darkpool_topup`, funded from the foreign reserve at exactly 1,000;
  * the same `collect_one` the nightly walk uses, so pages land exactly as the walk's do;
  * one job_runs row: `ok` when every pending ticker-session is exhausted, else `partial` with
    the ones left, and in `skip_reason` the calls spent and every ticker-session written.
The next push removes this module and its startup hook.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

from jobs.job_runs import JOB_DARKPOOL_TOPUP as JOB_NAME  # noqa: E402
CALLER_TAG = "darkpool_topup"
ARM_ENV = "DARKPOOL_TOPUP_ARM"
ARM_VALUE = "R-IV.1456f"
MAX_CALLS = 1000
#: Arbitrary but fixed: the advisory-lock key for this one job.
LOCK_KEY = 1456_0006


def armed() -> bool:
    return (os.getenv(ARM_ENV) or "").strip() == ARM_VALUE


def anchor_after(today_et: date) -> Optional[date]:
    """The first trading session after `today_et`. The catch-up looks at the ten sessions
    BEFORE it, so on a weekend that is the ten that end with Friday."""
    from jobs.darkpool_backfill import trading_sessions
    later = trading_sessions(today_et + timedelta(days=1), today_et + timedelta(days=10))
    return later[0] if later else None


def plan(anchor: date, done: set, names) -> List[tuple]:
    """(session, ticker) in the order they will be walked: oldest session first, census order
    within a session, skipping what is already exhausted."""
    from jobs.darkpool_forward import catchup_sessions
    out = []
    for s in catchup_sessions(anchor, done, names):
        out.extend((s, t) for t in names if (t, s) not in done)
    return out


def verdict(todo: List[tuple], results: List[dict], stop_reason: Optional[str]):
    """`ok` only when every planned ticker-session came back exhausted."""
    # collect_one returns the session as an ISO string; key on that.
    got = {(str(r.get("session")), r.get("ticker")): r for r in results}
    left = []
    for s, t in todo:
        r = got.get((s.isoformat(), t))
        if r is None:
            left.append("%s %s never reached" % (s.isoformat(), t))
        elif not r.get("exhausted"):
            left.append("%s %s cut mid-walk" % (s.isoformat(), t))
    if not left:
        return "ok", None
    return "partial", "%s; stop: %s" % ("; ".join(left), stop_reason or "-")


async def run_once(now: Optional[datetime] = None) -> dict:
    """The top-up. Never raises out; every refusal is logged with its reason and returned."""
    from jobs.darkpool_backfill import (Budget, DDL, DONE_SQL, _ET_ZONE, collect_one,
                                        refresh_completeness, trading_sessions)
    from jobs.darkpool_forward import census_names
    from jobs.job_runs import STATUS_ERROR, finish_run, start_run
    from database.postgres_client import get_postgres_client
    from integrations.uw_spend_ledger import uw_day

    now = now or datetime.now(timezone.utc)
    today_et = now.astimezone(_ET_ZONE()).date()
    if trading_sessions(today_et, today_et):
        return _refused("today (%s ET) is a trading day; the nightly walk owns it" % today_et)
    anchor = anchor_after(today_et)
    if anchor is None:
        return _refused("no trading session in the next ten days to anchor the catch-up")

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        got = await conn.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_KEY)
        if not got:
            return _refused("another process holds the top-up lock")
        try:
            prior = await conn.fetchval(
                "SELECT count(*) FROM job_runs WHERE job_name = $1", JOB_NAME)
            if prior:
                return _refused("%d %s row(s) already in job_runs: one run only" % (prior,
                                                                                 JOB_NAME))
            for stmt in DDL:
                await conn.execute(stmt)
            done = {(r["ticker"], r["session_date"]) for r in await conn.fetch(DONE_SQL)}
            names = census_names()
            todo = plan(anchor, done, names)
            job_run_id = await start_run(JOB_NAME, todo[0][0] if todo else today_et)
            run_id = await conn.fetchval(
                "INSERT INTO darkpool_backfill_runs (started_at, uw_day, calls_spent) "
                "VALUES (NOW(), $1, 0) RETURNING id", uw_day(now))
        finally:
            # Released once the run row exists: from here job_runs itself refuses a second run.
            await conn.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)

    budget = Budget(MAX_CALLS)
    await budget.check_account()
    results: List[dict] = []
    logger.warning("[dp-topup] START run %s: %d ticker-sessions pending across %s, budget %d",
                   run_id, len(todo), sorted({s.isoformat() for s, _ in todo}), MAX_CALLS)
    try:
        for s, t in todo:
            if budget.stopped or budget.remaining <= 0:
                break
            r = await collect_one(pool, t, s, budget, CALLER_TAG)
            results.append(dict(r, session=s.isoformat(), ticker=t))
    except asyncio.CancelledError:
        await _end(pool, run_id, budget.calls, "cancelled mid-walk", results)
        await finish_run(job_run_id, STATUS_ERROR, rows_touched=len(results),
                         error="cancelled mid-walk after %d calls" % budget.calls)
        raise

    try:
        await refresh_completeness(pool)
    except Exception:                                               # noqa: BLE001
        logger.warning("[dp-topup] completeness refresh failed", exc_info=True)

    status, why = verdict(todo, results, budget.stop_reason)
    written = ["%s %s%s" % (r["session"], r["ticker"],
                            "" if r.get("exhausted") else " (cut)") for r in results]
    detail = "calls %d/%d; written %s%s" % (budget.calls, MAX_CALLS, ", ".join(written) or "-",
                                            ("; LEFT: " + why) if why else "")
    await _end(pool, run_id, budget.calls, budget.stop_reason or "walked the backlog", results)
    await finish_run(job_run_id, status, rows_touched=len(results), skip_reason=detail[:4000])
    logger.warning("[dp-topup] END run %s: %s; %s", run_id, status, detail[:1500])
    return {"status": status, "calls": budget.calls, "run_id": run_id,
            "job_run_id": job_run_id, "written": written, "left": why}


def _refused(why: str) -> dict:
    logger.warning("[dp-topup] REFUSED: %s", why)
    return {"status": "refused", "reason": why}


async def _end(pool, run_id: int, calls: int, stop_reason: str, results: List[dict]) -> None:
    """Stamp ended_at: the F: export gate reads a run with no end as still in progress."""
    summary = {"job": JOB_NAME, "results": [
        {"session": r["session"], "ticker": r["ticker"],
         "exhausted": bool(r.get("exhausted")), "pages": r.get("pages"),
         "prints": r.get("prints")} for r in results]}
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE darkpool_backfill_runs SET ended_at = NOW(), calls_spent = $1, "
                "stop_reason = $2, summary = $3::jsonb WHERE id = $4",
                calls, stop_reason, json.dumps(summary), run_id)
    except Exception:                                               # noqa: BLE001
        logger.error("[dp-topup] could NOT end run %s", run_id, exc_info=True)


async def start_if_armed() -> None:
    """Startup hook: waits for the app to settle, then runs once if armed. Never raises."""
    if not armed():
        return
    try:
        await asyncio.sleep(90)
        await run_once()
    except asyncio.CancelledError:
        raise
    except Exception:                                               # noqa: BLE001
        logger.error("[dp-topup] failed", exc_info=True)
