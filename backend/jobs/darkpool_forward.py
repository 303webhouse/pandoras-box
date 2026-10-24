"""R-IV.1398(b)3 — the FORWARD dark-pool walk. One session a night, floored, census universe.

FUNDED AND LIVE under R-IV.1408(b)1: 250 calls a night from the reserve. The universe is the
CENSUS's eight names, which R-IV.1408(b)3 settled -- not Tier-1's sixteen, despite the earlier
ruling's wording, and `census_names()` is named for what it is.

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
    `DONE_SQL`'s set -- `exhausted AND reached_floor AND prints_received > 0`. So a
    ticker-session that was walked but never reached its floor still counts as unwritten and
    will be resumed, which is what makes the catch-up converge instead of declaring victory on
    a partial walk.

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

async def walk_night(now: Optional[datetime] = None,
                     session: Optional[date] = None) -> dict:
    """Walk Tier-1 for one session, floored. Creates and ENDS a run. Never raises."""
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
        return {"session": None, "reason": "not a trading session", "collected": 0}

    names = census_names()
    ceiling = night_ceiling()
    budget = Budget(ceiling)

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
            if budget.stopped or budget.remaining <= 0:
                break
            if (ticker, session) in done:
                # Already exhausted and floored by an earlier attempt at this same night.
                # Idempotent by design: the window retries until 23:00 ET, and a retry that
                # re-walked a finished ticker would spend the night's budget twice.
                summary["already_done"] += 1
                continue
            results.append(await collect_one(pool, ticker, session, budget, CALLER_TAG))

        # ── 2. THE REMAINDER goes to the OLDEST unwritten session.
        # Oldest first because the vendor drops its oldest dark-pool session every trading
        # day, so of two unwritten sessions the older one has less time left.
        pending = catchup_sessions(session, done, names)
        summary["catchup_pending"] = [d.isoformat() for d in pending]
        for older in pending:
            if budget.stopped or budget.remaining <= 0:
                break
            touched = False
            for ticker in names:
                if budget.stopped or budget.remaining <= 0:
                    break
                if (ticker, older) in done:
                    continue
                catchup.append(await collect_one(pool, ticker, older, budget, CALLER_TAG))
                touched = True
            if touched:
                summary["catchup_sessions"].append(older.isoformat())
    except asyncio.CancelledError:
        # A deploy cancels this task mid-walk. CancelledError derives from BaseException, so
        # an `except Exception` would be blind to it -- which is how the census job left run 7
        # recorded as in progress forever, and the gate then read that silence as a wait.
        await _end_run(pool, run_id, budget.calls, "cancelled mid-walk", summary)
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

    await _end_run(pool, run_id, budget.calls,
                   budget.stop_reason or "walked the Tier-1 list", summary)
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
                if not out.get("blocked") and out.get("session"):
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
