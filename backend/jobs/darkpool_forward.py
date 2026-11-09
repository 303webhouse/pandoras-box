"""R-IV.1398(b)3 — the FORWARD dark-pool walk. One session a night, floored, census universe.

FUNDED AND LIVE under R-IV.1408(b)1, at 250 calls a night from the reserve; RAISED TO 400
(ceiling 384) under R-IV.1493(b)1. The universe is the CENSUS's eight names, which
R-IV.1408(b)3 settled -- not Tier-1's sixteen, despite the earlier ruling's wording, and
`census_names()` is named for what it is.

WHY 400 (R-IV.1493, from R-IV.1491(c)'s cost study). A complete session costs the sum, over the
eight names, of ceil(prints from 04:00 ET / 500) + 1 crossing page. Over the 48 sessions from
09-01 to 11-06: median 155, p90 199, highest 232 / 224 / 210, and 11-05 at about 345 (TSLA was
still partial at 320). The 240 ceiling covered 47 of 48 and cut 11-05 at AAPL, with MSFT and
TSLA never reached. Each walk stops at its session's start, so a normal night still spends about
155: the extra is spent only on a heavy day.

NON-TRADING NIGHTS CATCH UP (R-IV.1493(b)2). A Saturday, Sunday or holiday night has no session
of its own. It used to return "not a trading session" and spend nothing, which left 11-05's TSLA
waiting until Monday. It now walks only the backlog, oldest first, under the same nightly
ceiling, and when there is no backlog it opens no run and spends nothing. See `_catchup_night`.

AND IT CATCHES UP, under R-IV.1412(b): the session that just closed is walked first and
unconditionally, then whatever budget remains goes to the OLDEST unwritten session. Built
because the first version could never have collected 2026-10-23 -- `target_session` returns
only the session of the instant it is called at, so the one session the census's lapse actually
cost was in no future target. See `catchup_sessions`.

WHY THIS IS A SEPARATE INSTRUMENT AND NOT A DATE EDIT
    `darkpool_backfill.py` already walks a session per night, floored at 04:00 ET, and writes
    `darkpool_backfill_pages`. It stopped because of one line:

        ALLOWANCE_THROUGH = date(2026, 10, 23)

    and at 00:00 UTC on 2026-10-24 its nightly loop hit `today > ALLOWANCE_THROUGH` and
    RETURNED -- the loop ended, it did not sleep. That allowance was R-IV.921(b)3's, written
    for a CENSUS of past sessions, and that census is finished: 312 of 312 ticker-sessions
    collected and exhausted, `outstanding_ticker_sessions` 0, `dates_exhausted_but_floor_NOT
    _proved` 0 (measured on /api/darkpool-backfill/progress, as_of 2026-10-24T03:25:57Z).

    Pushing the date would work tonight and expire again at the next one, because a FORWARD
    collection has no end date to write. So the forward walk gets its own tag, its own quota
    and no expiry, and the census instrument is left exactly as it is -- including its lapse,
    which is now correct behaviour for a job whose work is done.

    R-IV.912(c)2 is untouched throughout: `darkpool_collector`, its tables and its caller tag
    are not read, written or referenced here.

FAIL-CLOSED UNTIL FUNDED, same contract as the quote grid
    `preflight()` refuses while `darkpool_forward` is absent from the governor's quota table,
    because an unregistered tag is not inert -- it runs on DEFAULT_QUOTA 500. R-IV.1398(b)3
    asked for the calls-per-night figure before this ships, and the figure is below.

CALLS PER NIGHT, MEASURED BEFORE A LINE OF THIS RAN
    The five most recent nights that walked exactly one new session across the eight names
    (`darkpool_backfill_runs`, via /api/darkpool-backfill/progress):

        run 15  2026-10-17  202      run 18  2026-10-22  131
        run 16  2026-10-20  140      run 19  2026-10-23  188
        run 17  2026-10-21  132

    mean 158.6, median 140, max 202. Per ticker-session: mean 16.4-25.2, max 29-43.

    So this job ADDS NOTHING: 158.6 calls a night is what was already being spent until the
    allowance lapsed. A 250/night quota covers the measured maximum with headroom, and the
    whole of it comes from the FOREIGN RESERVE, where the census tag holds 5,000 and spends
    131-202. The hub's own 26,050 DAILY_BUDGET table is asked for nothing.

IT MUST CREATE AND END A RUN, and that is not bookkeeping
    `scripts/f_export_gate.py` keys the F: archive export on
    `(latest_ended_run_id, eligible_count)` from `darkpool_backfill_runs`/`_sessions`. With the
    census loop dead, `latest_ended_run_id` is frozen at 19 forever -- so the export reports
    ALREADY_DONE on every tick, and `export_bars1m()` runs inside that gate, which is why the
    yfinance bars for 2026-10-23 were never written either. A forward walk that collected
    pages without ending a run would leave the export shut.

    That coupling is a fault in its own right and is NOT fixed here: the bars have nothing to
    do with the dark-pool counter, and de-coupling them needs its own ruling. This job makes
    the counter move again, which is the part R-IV.1398(b)3 covers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

logger = logging.getLogger("darkpool_forward")

JOB_NAME = "darkpool_forward"

#: Its own tag. Registration in the governor's quota table is the funding gate.
CALLER_TAG = "darkpool_forward"

ENV_FLAG = "DARKPOOL_FORWARD_ENABLED"

#: THE CENSUS'S EIGHT NAMES -- the universe TRITON-R and R2 actually read (R-IV.1408(b)3).
#:
#: NOT "Tier-1", and this function was called `tier_1_names` until the ruling settled it.
#: R-IV.1398(b)3 described this as "the §6.4 floored Tier-1 job", so the name followed the
#: ruling's wording; R-IV.1408(b)3 then named the set and it is explicitly NOT Tier-1's 16.
#: A label that contradicts the ruling is worse than no label, and this one was also published
#: on /health, so every reader of that surface was told the wrong thing about the scope.
#:
#: Taken from CORE_NAMES rather than retyped: the measured 158.6 calls/night is for exactly
#: this set, so a divergent list would make the funded figure describe a different job.
def census_names() -> Tuple[str, ...]:
    from jobs.darkpool_backfill import CORE_NAMES
    return CORE_NAMES


#: R-IV.1412(b): how far back the catch-up will look for an unwritten session.
#:
#: BOUNDED, because "the oldest unwritten session" over an unbounded history walks toward the
#: census's 2026-08-28 origin -- which is far outside the vendor's retention, so the night's
#: remainder would be spent on sessions that cannot be fetched at all. Ten trading sessions is
#: two weeks of market days: wide enough for any gap this job could realistically open (it
#: collects one session a night) and narrow enough that it stays inside what the vendor holds.
CATCHUP_LOOKBACK_SESSIONS = 10

#: Fraction of the registered quota one night may spend. Derived from the RULED quota rather
#: than written as a literal, so the two cannot drift -- the fault `_budget_from_governor`
#: was added to the census job to fix.
NIGHT_CEILING_FRACTION = 0.96

_last_result: dict = {}
_fired: set = set()
_preflight_logged = False


def reset_for_tests() -> None:
    global _last_result, _fired, _preflight_logged
    _last_result = {}
    _fired = set()
    _preflight_logged = False


# ---------------------------------------------------------------------------
# the two gates
# ---------------------------------------------------------------------------

def tag_is_registered() -> bool:
    """Is CALLER_TAG in the governor's quota table? An unreadable table is not a licence."""
    try:
        from integrations.uw_governor import FOREIGN_RESERVE_QUOTAS, QUOTAS
        return CALLER_TAG in QUOTAS or CALLER_TAG in FOREIGN_RESERVE_QUOTAS
    except Exception:                                               # noqa: BLE001
        return False


def enabled() -> bool:
    """DEFAULT OFF. `or "false"` because Railway returns '' for an unset reference."""
    return (os.getenv(ENV_FLAG) or "false").strip().lower() == "true"


def preflight() -> Optional[str]:
    """None when the walk may run, else the reason it may not. Two gates, named separately."""
    if not tag_is_registered():
        return ("caller tag %r is NOT in the governor's quota table: R-IV.1398(b)3 requires "
                "the calls-per-night report and a funding ruling before this walk spends "
                "anything. Refusing rather than running on DEFAULT_QUOTA." % CALLER_TAG)
    if not enabled():
        return "%s is not 'true'" % ENV_FLAG
    return None


def night_ceiling() -> int:
    """Calls one night may spend, from the RULED quota."""
    if not tag_is_registered():
        return 0
    try:
        from integrations.uw_governor import quota_for
        quota, _tier = quota_for(CALLER_TAG)
    except Exception:                                               # noqa: BLE001
        return 0
    return int(quota * NIGHT_CEILING_FRACTION)


# ---------------------------------------------------------------------------
# which session
# ---------------------------------------------------------------------------

def target_session(now_et: datetime) -> Optional[date]:
    """The session this night's walk is for, or None when there is none.

    The window opens at 20:30 ET, AFTER the close, so the session that just ended is the ET
    date of the instant itself -- not yesterday. The census used `today - 1` because it was
    walking backwards through history from a UTC date, and reusing that here would walk
    yesterday every night and never collect the session that just finished.

    A non-trading date returns None rather than an empty walk, so a holiday is a stated
    absence rather than a run that collected nothing.
    """
    from jobs.darkpool_backfill import trading_sessions

    d = now_et.date()
    return d if trading_sessions(d, d) else None


def catchup_sessions(session: date, done: set, names) -> List[date]:
    """Unwritten trading sessions before `session`, OLDEST FIRST, inside the lookback.

    "Unwritten" means at least one census name is missing from `done`, and `done` is
    `DONE_SQL`'s set -- `exhausted = TRUE`, nothing more. So a walk cut by the call budget
    (not exhausted) counts as unwritten and is resumed, which is what makes the catch-up
    converge. A walk the VENDOR ended (exhausted) counts as done even if it never reached its
    floor -- walking it again would only fetch the same short page (IWM 11-02, R-IV.1492(c)).
    The F: export gate's stricter `exhausted AND reached_floor AND prints_received > 0` is a
    different count and lives in `refresh_completeness`.

    `session` itself is excluded: it is walked first and unconditionally by the caller, and
    including it here would let the remainder be spent on it twice.
    """
    from jobs.darkpool_backfill import trading_sessions

    span = trading_sessions(session - timedelta(days=CATCHUP_LOOKBACK_SESSIONS * 3), session)
    span = [d for d in span if d < session][-CATCHUP_LOOKBACK_SESSIONS:]
    out = [d for d in span if any((t, d) not in done for t in names)]
    return out


# ---------------------------------------------------------------------------
# one night
# ---------------------------------------------------------------------------

def session_verdict(names, session: date, done, results: List[dict],
                    stop_reason: Optional[str]) -> Tuple[str, Optional[str]]:
    """R-IV.1451(b): did tonight finish THE SESSION THAT JUST CLOSED? -> (status, reason).

    `ok` only when every name is walked to its end (exhausted) tonight or by an earlier attempt.
    Otherwise `partial`, naming the names cut mid-walk and the names never reached -- never `ok`.
    Catch-up progress does not change this: the backlog is reported in the run summary.
    """
    from jobs.job_runs import STATUS_OK, STATUS_PARTIAL

    walked = {r["ticker"]: r for r in results}
    cut = [t for t in names if t in walked and not walked[t].get("exhausted")]
    unreached = [t for t in names if t not in walked and (t, session) not in done]
    if not cut and not unreached:
        return STATUS_OK, None
    parts = []
    if cut:
        parts.append("cut mid-walk: " + ",".join(cut))
    if unreached:
        parts.append("never reached: " + ",".join(unreached))
    parts.append("stop: " + _stop_text(stop_reason, [walked[t] for t in cut]))
    return STATUS_PARTIAL, "; ".join(parts)[:480]


def backlog_verdict(pending: List[date], names, done, catchup: List[dict],
                    stop_reason: Optional[str]) -> Tuple[str, Optional[str]]:
    """R-IV.1493(b)2: did a catch-up-only night clear the backlog it found? -> (status, reason).

    `ok` only when every ticker-session that was pending is now walked to its end, whether by
    tonight or earlier. Otherwise `partial`, naming what is left and why the walk stopped.
    """
    from jobs.job_runs import STATUS_OK, STATUS_PARTIAL

    walked = {(r["ticker"], r["session"]): r for r in catchup}
    left, cut_rows = [], []
    for d in pending:
        for t in names:
            if (t, d) in done:
                continue
            r = walked.get((t, d.isoformat()))
            if r is not None and r.get("exhausted"):
                continue
            left.append("%s %s" % (d.isoformat(), t))
            if r is not None:
                cut_rows.append(r)
    if not left:
        return STATUS_OK, None
    # The list is capped, not the reason: the stop must survive the 480-character field.
    listing = ",".join(left)
    if len(listing) > 240:
        listing = listing[:240].rsplit(",", 1)[0] + ",... (%d in all)" % len(left)
    return STATUS_PARTIAL, ("backlog left: %s; stop: %s"
                            % (listing, _stop_text(stop_reason, cut_rows)))[:480]


def _stop_text(stop_reason: Optional[str], cut_rows: List[dict]) -> str:
    """R-IV.1493(b)3: why the walk stopped, never "unknown".

    The night's own reason first. That is set at every break site: by `budget.stop()`, or by
    `budget.run_out()` through `_out_of_budget`. Failing that, the cut rows' own stops, which
    `collect_one` always writes (a vendor error, for one). The last fallback cannot be reached
    from the code as written, and its wording says so rather than passing for a reason.
    """
    if stop_reason:
        return stop_reason
    own = ["%s: %s" % (r["ticker"], r["stop"]) for r in cut_rows if r.get("stop")]
    if own:
        return "; ".join(own)
    return "NOT RECORDED (a fault: every break site records one)"


def _out_of_budget(budget) -> bool:
    """True when the walk must stop here, with work still left.

    R-IV.1493(b)3: a budget that ran out is RECORDED as having run out. Before this, the loops
    broke on `remaining <= 0` and left `stop_reason` None. Call it only when a ticker-session is
    still to be walked, so a night that finished on its last call is not labelled as cut.
    """
    if budget.stopped:
        return True
    if budget.remaining <= 0:
        budget.run_out()
        return True
    return False


async def _walk_backlog(pool, pending: List[date], names, done, budget, summary: dict,
                        catchup: List[dict]) -> None:
    """Walk the pending sessions OLDEST FIRST until the budget stops. Appends to `catchup`.

    Oldest first because the vendor drops its oldest dark-pool session every trading day, so
    of two unwritten sessions the older one has less time left. Shared by the trading night,
    where it gets the remainder, and by the catch-up-only night, where it gets everything.
    """
    from jobs.darkpool_backfill import collect_one

    for older in pending:
        if _out_of_budget(budget):
            break
        touched = False
        for ticker in names:
            if (ticker, older) in done:
                continue
            if _out_of_budget(budget):
                break
            catchup.append(await collect_one(pool, ticker, older, budget, CALLER_TAG))
            touched = True
        if touched:
            summary["catchup_sessions"].append(older.isoformat())


async def walk_night(now: Optional[datetime] = None,
                     session: Optional[date] = None) -> dict:
    """Walk the census names for one session, floored. Creates and ENDS a run. Never raises.

    On a night with no session of its own (Saturday, Sunday, a holiday) it walks the backlog
    only (R-IV.1493(b)2). See `_catchup_night`.
    """
    global _preflight_logged

    block = preflight()
    if block is not None:
        if not _preflight_logged:
            logger.warning("[dp-forward] NOT RUNNING: %s", block)
            _preflight_logged = True
        return {"session": None, "reason": block, "blocked": True, "collected": 0}

    from jobs.darkpool_backfill import (
        Budget, DDL, DONE_SQL, collect_one, refresh_completeness,
    )
    from database.postgres_client import get_postgres_client
    from integrations.uw_spend_ledger import uw_day

    now = now or datetime.now(timezone.utc)
    if session is None:
        session = target_session(now.astimezone(_et()))
    if session is None:
        # R-IV.1493(b)2: no session closed tonight, so the whole night goes to the backlog.
        return await _catchup_night(now)

    names = census_names()
    ceiling = night_ceiling()
    budget = Budget(ceiling)

    from jobs.job_runs import JOB_DARKPOOL_FORWARD, STATUS_ERROR, finish_run, start_run
    job_run_id = await start_run(JOB_DARKPOOL_FORWARD, session)

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        for stmt in DDL:
            await conn.execute(stmt)
        done = {(r["ticker"], r["session_date"]) for r in await conn.fetch(DONE_SQL)}
        run_id = await conn.fetchval(
            "INSERT INTO darkpool_backfill_runs (started_at, uw_day, calls_spent) "
            "VALUES (NOW(), $1, 0) RETURNING id", uw_day(now))

    summary = {"session": session.isoformat(), "run_id": run_id, "names": list(names),
               "ceiling": ceiling, "collected": 0, "already_done": 0, "pages": 0,
               "prints": 0, "exhausted": 0, "floored": 0, "calls_spent": 0,
               # R-IV.1412(b): reported separately from the current session's figures, so
               # "the live session was collected" and "the backlog moved" are never one number.
               "catchup_sessions": [], "catchup_collected": 0, "catchup_pending": []}

    await budget.check_account()
    results: List[dict] = []
    catchup: List[dict] = []
    try:
        # ── 1. THE SESSION THAT JUST CLOSED, first and unconditionally (R-IV.1412(b)).
        # Nothing else will ever target it again: `target_session` only returns the session of
        # the instant it is called at, so a session missed here is missed for good. That is
        # exactly how 2026-10-23 was lost, and it is why the backlog gets the REMAINDER rather
        # than the priority.
        for ticker in names:
            if (ticker, session) in done:
                # Already exhausted and floored by an earlier attempt at this same night.
                # Idempotent by design: the window retries until 23:00 ET, and a retry that
                # re-walked a finished ticker would spend the night's budget twice.
                summary["already_done"] += 1
                continue
            # After the done check, so a budget is only recorded as run out when a name
            # was still to walk (R-IV.1493(b)3).
            if _out_of_budget(budget):
                break
            results.append(await collect_one(pool, ticker, session, budget, CALLER_TAG))

        # ── 2. THE REMAINDER goes to the OLDEST unwritten session.
        pending = catchup_sessions(session, done, names)
        summary["catchup_pending"] = [d.isoformat() for d in pending]
        await _walk_backlog(pool, pending, names, done, budget, summary, catchup)
    except asyncio.CancelledError:
        # A deploy cancels this task mid-walk. CancelledError derives from BaseException, so
        # an `except Exception` would be blind to it -- which is how the census job left run 7
        # recorded as in progress forever, and the gate then read that silence as a wait.
        await _end_run(pool, run_id, budget.calls, "cancelled mid-walk", summary)
        await finish_run(job_run_id, STATUS_ERROR, rows_touched=len(results) + len(catchup),
                         error="cancelled mid-walk")
        raise

    summary["collected"] = len(results)
    summary["catchup_collected"] = len(catchup)
    # Pages and prints cover BOTH, because they describe what landed in the archive; the
    # ticker-session counts stay split, because those answer "did the live session get done".
    both = results + catchup
    summary["pages"] = sum(r["pages"] for r in both)
    summary["prints"] = sum(r["prints"] for r in both)
    summary["exhausted"] = sum(1 for r in results if r["exhausted"])
    summary["catchup_exhausted"] = sum(1 for r in catchup if r["exhausted"])
    summary["floored"] = sum(1 for r in results if r.get("reached_floor"))
    summary["calls_spent"] = budget.calls

    # The eligible count the F: export gate reads is
    # `exhausted AND reached_floor AND prints_received > 0`, and `reached_floor` for any row a
    # walk could not prove directly is settled here. It costs no vendor calls.
    try:
        await refresh_completeness(pool)
    except Exception:                                               # noqa: BLE001
        logger.warning("[dp-forward] completeness refresh failed", exc_info=True)

    status, why = session_verdict(names, session, done, results, budget.stop_reason)
    summary["status"] = status
    summary["status_reason"] = why
    await _end_run(pool, run_id, budget.calls,
                   budget.stop_reason or WALKED_TO_THE_END, summary)
    await finish_run(job_run_id, status, rows_touched=len(results) + len(catchup),
                     skip_reason=why)
    if why:
        logger.warning("[dp-forward] run %s session %s PARTIAL: %s", run_id, session, why)
    _last_result.clear()
    _last_result.update(summary)
    logger.info("[dp-forward] run %s session %s: %d walked, %d already done, %d pages, "
                "%d prints, %d floored, %d/%d calls; catch-up %d ticker-sessions over %s "
                "(pending %s)",
                run_id, session, summary["collected"], summary["already_done"],
                summary["pages"], summary["prints"], summary["floored"],
                budget.calls, ceiling, summary["catchup_collected"],
                summary["catchup_sessions"] or "-", summary["catchup_pending"] or "-")
    return summary


#: The run-level reason when nothing stopped the walk. It used to read "walked the Tier-1
#: list", which named the wrong universe (R-IV.1408(b)3). Now worded so it cannot be mistaken
#: for BUDGET_RAN_OUT (R-IV.1493(b)3).
WALKED_TO_THE_END = "walked every name it reached to its end; budget not exhausted"


async def _catchup_night(now: datetime) -> dict:
    """R-IV.1493(b)2: a night with no session of its own walks ONLY the backlog.

    Spends only while gaps remain, under the same nightly ceiling: `night_ceiling()` from the
    same quota, on its own UW day. With nothing pending it opens NO run, neither the
    `darkpool_backfill_runs` row the F: export gate keys on nor a `job_runs` row, and spends
    nothing. It still returns `fired`, so the loop does not re-read the backlog every minute
    until 23:59 ET.

    The lookback is anchored on the night's own date. That date is not a session, so every
    trading session before it is a candidate, including Friday's, which Friday night's own
    walk may have left short.
    """
    from jobs.darkpool_backfill import Budget, DDL, DONE_SQL, refresh_completeness
    from database.postgres_client import get_postgres_client
    from integrations.uw_spend_ledger import uw_day
    from jobs.job_runs import JOB_DARKPOOL_FORWARD, STATUS_ERROR, finish_run, start_run

    night = now.astimezone(_et()).date()
    names = census_names()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        for stmt in DDL:
            await conn.execute(stmt)
        done = {(r["ticker"], r["session_date"]) for r in await conn.fetch(DONE_SQL)}

    pending = catchup_sessions(night, done, names)
    if not pending:
        logger.info("[dp-forward] %s is not a trading session and nothing is pending: "
                    "no run, no calls", night)
        return {"session": None, "night": night.isoformat(), "catchup_only": True,
                "reason": "not a trading session; no backlog", "collected": 0,
                "calls_spent": 0, "fired": True}

    ceiling = night_ceiling()
    budget = Budget(ceiling)
    job_run_id = await start_run(JOB_DARKPOOL_FORWARD, night)
    async with pool.acquire() as conn:
        run_id = await conn.fetchval(
            "INSERT INTO darkpool_backfill_runs (started_at, uw_day, calls_spent) "
            "VALUES (NOW(), $1, 0) RETURNING id", uw_day(now))

    summary = {"session": None, "night": night.isoformat(), "catchup_only": True,
               "fired": True, "run_id": run_id, "names": list(names), "ceiling": ceiling,
               "collected": 0, "already_done": 0, "pages": 0, "prints": 0, "exhausted": 0,
               "floored": 0, "calls_spent": 0, "catchup_sessions": [],
               "catchup_collected": 0, "catchup_pending": [d.isoformat() for d in pending]}

    await budget.check_account()
    catchup: List[dict] = []
    try:
        await _walk_backlog(pool, pending, names, done, budget, summary, catchup)
    except asyncio.CancelledError:
        await _end_run(pool, run_id, budget.calls, "cancelled mid-walk", summary)
        await finish_run(job_run_id, STATUS_ERROR, rows_touched=len(catchup),
                         error="cancelled mid-walk")
        raise

    summary["catchup_collected"] = len(catchup)
    summary["pages"] = sum(r["pages"] for r in catchup)
    summary["prints"] = sum(r["prints"] for r in catchup)
    summary["catchup_exhausted"] = sum(1 for r in catchup if r["exhausted"])
    summary["calls_spent"] = budget.calls

    try:
        await refresh_completeness(pool)
    except Exception:                                               # noqa: BLE001
        logger.warning("[dp-forward] completeness refresh failed", exc_info=True)

    status, why = backlog_verdict(pending, names, done, catchup, budget.stop_reason)
    summary["status"] = status
    summary["status_reason"] = why
    # The job_runs row says what kind of night it was even when it is `ok`, so a Saturday
    # row is never read as a session's own walk.
    note = why or ("not a trading session: catch-up only, walked %s"
                   % (",".join(summary["catchup_sessions"]) or "-"))
    await _end_run(pool, run_id, budget.calls, budget.stop_reason or WALKED_TO_THE_END,
                   summary)
    await finish_run(job_run_id, status, rows_touched=len(catchup), skip_reason=note)
    if why:
        logger.warning("[dp-forward] run %s catch-up night %s PARTIAL: %s", run_id, night, why)
    _last_result.clear()
    _last_result.update(summary)
    logger.info("[dp-forward] run %s catch-up night %s: %d ticker-sessions over %s, %d pages, "
                "%d prints, %d/%d calls (pending %s)",
                run_id, night, len(catchup), summary["catchup_sessions"] or "-",
                summary["pages"], summary["prints"], budget.calls, ceiling,
                summary["catchup_pending"])
    return summary


async def _end_run(pool, run_id: int, calls: int, stop_reason: str, summary: dict) -> None:
    """Stamp `ended_at`. THE F: EXPORT GATE DEPENDS ON THIS HAPPENING.

    A run left with a null `ended_at` is read by the gate as RUN_IN_PROGRESS -- it waits, and
    keeps waiting, which is a silence that looks like patience. Best-effort and never raising,
    because failing here would be worse than the walk having not run at all.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE darkpool_backfill_runs SET ended_at = NOW(), calls_spent = $1, "
                "stop_reason = $2, summary = $3::jsonb WHERE id = $4",
                calls, stop_reason, json.dumps(summary), run_id)
    except Exception:                                               # noqa: BLE001
        logger.error("[dp-forward] could NOT end run %s -- the F: export gate will read it "
                     "as a run still in progress and will not export", run_id, exc_info=True)


def _et():
    from jobs.darkpool_backfill import _ET_ZONE
    return _ET_ZONE()


# ---------------------------------------------------------------------------
# the loop and /health
# ---------------------------------------------------------------------------

async def run_forever() -> None:
    """Fire once per vendor day inside the nightly window. NEVER raises out of the loop.

    The window and the retry bound are the census job's -- imported rather than retyped,
    because "when the nightly runs" is one fact and two copies of it would drift.
    """
    from jobs.darkpool_backfill import NIGHTLY_RETRY_UNTIL_HOUR_ET, NIGHTLY_START_ET
    from integrations.uw_spend_ledger import uw_day

    await asyncio.sleep(120)
    while True:
        try:
            now = datetime.now(timezone.utc)
            et = now.astimezone(_et())
            key = uw_day(now).isoformat()
            in_window = ((et.hour, et.minute) >= NIGHTLY_START_ET
                         and et.hour <= NIGHTLY_RETRY_UNTIL_HOUR_ET)
            if in_window and key not in _fired:
                out = await walk_night(now=now)
                # FIRED ONLY ON A REAL WALK. Marking the vendor day done on a blocked or
                # non-trading tick would consume the night: the retry window exists so a
                # transient failure gets another attempt, and a gate that is opened at 21:00
                # must still be able to collect at 21:30.
                # A catch-up-only night (R-IV.1493(b)2) has no session but did run.
                if not out.get("blocked") and (out.get("session") or out.get("fired")):
                    _fired.add(key)
        except Exception:                                           # noqa: BLE001
            logger.error("[dp-forward] nightly error", exc_info=True)
        await asyncio.sleep(60)


async def status() -> dict:
    """For /health. Names the gate, so a refusal by ruling is not mistaken for a breakage."""
    block = preflight()
    now_et = datetime.now(timezone.utc).astimezone(_et())
    return {
        "job": JOB_NAME,
        "caller_tag": CALLER_TAG,
        "blocked": block,
        "tag_registered": tag_is_registered(),
        "env_enabled": enabled(),
        #: Renamed from `tier_1` under R-IV.1408(b)3: the universe is the census's eight, not
        #: Tier-1's sixteen, and the old key published the opposite on every read.
        "census_names": list(census_names()),
        "target_session": (lambda d: d.isoformat() if d else None)(target_session(now_et)),
        "nights_fired_this_process": sorted(_fired),
        "ceiling": night_ceiling(),
        "last_night": dict(_last_result) if _last_result else None,
    }
