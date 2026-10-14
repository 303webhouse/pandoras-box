"""Dark-pool BACKFILL for the Triton census — R-IV.921(b), ordered to run by R-IV.940(b).

WHY THIS IS URGENT. The vendor drops its oldest dark-pool session every trading day. Zero
sessions were saved before tonight, and 2026-09-01 rolls off around Thu 2026-10-15. A night not
run is a session gone for good: this is the one job here whose cost of delay is permanent.

WHAT IT IS NOT. It does not touch `darkpool_collector`, its tables or its caller tag: that is
SM7's registered instrument (R-IV.912(c)2). New tables, new caller tag, same page shape.

OUTCOME-BLIND, BY CONSTRUCTION. Nothing here reads a Triton outcome, a `triton_*` table, or any
grade. It stores raw vendor pages and derives nothing, so collecting cannot be steered by what
the collection would later show. The SEAL is therefore satisfied trivially rather than by a
predicate: there is no query here that could isolate rows by id or fired_at at all.

THE BUDGET IS THE FOREIGN RESERVE, NOT THE HUB'S. R-IV.921(b)3 allows 2,500 calls per UW day
through 2026-10-23. The hub's own QUOTAS table sums to exactly 26,000 against a 28,000
DAILY_BUDGET, so putting 2,500 in that table would break the budget this register spent weeks
measuring. The allowance comes out of UW_FOREIGN_RESERVE (12,000) instead, and the limit is
enforced HERE, by this job, plus the two stops the ruling names:
  * the account total: stop at 30,000 used, read from the vendor's own header;
  * any 429: stop, and trip the governor's breaker.

PAGINATION, AS MEASURED (R-IV.921(a)). `limit` is hard-capped at 500. `page` is SILENTLY
IGNORED -- it returns page one again, which is why the first probe's "identical" reading was
worthless until it was redone with a row fingerprint. `older_than` IS honoured and is the only
working cursor; the feed is newest-first, so each page asks for prints older than the oldest
print already seen.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("darkpool_backfill")

CALLER = "darkpool_backfill_triton"
PROVIDER = "unusual_whales"

#: R-IV.921(b)2 -- the 8 core names first, every session, before any other ticker.
CORE_NAMES = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")

#: R-IV.921(b)3. Enforced by this job; see the module docstring on why not via QUOTAS.
def _budget_from_governor() -> int:
    """The per-vendor-day allowance, READ from the governor rather than restated here.

    R-IV.983(c) raised it from 2,500 to 5,000, and raising it meant editing TWO places: this
    job's own constant and `FOREIGN_RESERVE_QUOTAS`. Those are the SAME FACT -- how many calls
    this caller may make in a vendor day -- and whichever of the two was lower would silently
    cap the other. So the governor is the one author and this asks it.

    Falls back to 5,000 only if the governor cannot be read, which would itself mean the job
    cannot run.
    """
    try:
        from integrations.uw_governor import quota_for
        q, _tier = quota_for(CALLER)
        return int(q)
    except Exception:                                               # noqa: BLE001
        return 5000


#: Read at call time, not import time, so a governor change does not need a redeploy of this
#: module to take effect. R-IV.983(c): 5,000 from the foreign reserve, through 2026-10-23,
#: because only 3 of 17 calibration sessions were complete for all 8 names while the oldest
#: roll off daily. Measured hub use is ~14,373/day, so the account stays near 19,400 of 40,000.
CALL_BUDGET_PER_UW_DAY = 5000
ACCOUNT_TOTAL_STOP = 30000
ALLOWANCE_THROUGH = date(2026, 10, 23)

#: The oldest session the vendor was still serving when this was written (probe, R-IV.912(c)1).
OLDEST_KNOWN_SESSION = date(2026, 8, 28)

#: R-IV.921(b)4 -- collected, flagged, and NEVER joined to triton_flow_shadow.
QUARANTINED_SESSIONS = frozenset({date(2026, 8, 28), date(2026, 8, 31)})

PAGE_LIMIT = 500
#: A RUNAWAY GUARD, not an expectation. The first live run set this to 60 on the strength of
#: "~29 pages measured for SPY" -- but that 29 was a fire-WINDOW slice, not a whole session.
#: Unfloored, a full session is far bigger: SPY, QQQ and NVDA each hit 60 pages (30,000 prints)
#: on 2026-08-28 WITHOUT exhausting, while IWM finished in 20 and SMH in 15. A ceiling that
#: truncates the three biggest names is a silent data gap in exactly the names that matter, so
#: it is now set high enough to be unreachable in practice and the cursor does the stopping.
MAX_PAGES_PER_TICKER_SESSION = 400

DDL = (
    """CREATE TABLE IF NOT EXISTS darkpool_backfill_pages (
           ticker TEXT NOT NULL,
           session_date DATE NOT NULL,
           page_no INT NOT NULL,
           older_than_cursor TEXT,
           row_count INT NOT NULL,
           payload JSONB NOT NULL,
           provider TEXT NOT NULL,
           quarantined BOOLEAN NOT NULL DEFAULT FALSE,
           fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
           PRIMARY KEY (ticker, session_date, page_no)
       )""",
    """CREATE TABLE IF NOT EXISTS darkpool_backfill_sessions (
           ticker TEXT NOT NULL,
           session_date DATE NOT NULL,
           pages_fetched INT NOT NULL,
           prints_received INT NOT NULL,
           exhausted BOOLEAN NOT NULL,
           stop_reason TEXT NOT NULL,
           quarantined BOOLEAN NOT NULL DEFAULT FALSE,
           calls_spent INT NOT NULL,
           collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
           PRIMARY KEY (ticker, session_date)
       )""",
    # R-IV.993(d): completeness is "the walk reached a print executed BEFORE the session's
    # 04:00 ET start". NULL means not yet determined -- which is NOT false, and must not be
    # read as "incomplete" by anything that gates on it.
    """ALTER TABLE darkpool_backfill_sessions
           ADD COLUMN IF NOT EXISTS reached_floor BOOLEAN""",
    """CREATE TABLE IF NOT EXISTS darkpool_backfill_runs (
           id SERIAL PRIMARY KEY,
           started_at TIMESTAMPTZ NOT NULL,
           ended_at TIMESTAMPTZ,
           uw_day DATE NOT NULL,
           calls_spent INT NOT NULL DEFAULT 0,
           stop_reason TEXT,
           summary JSONB
       )""",
)

INSERT_PAGE = """
    INSERT INTO darkpool_backfill_pages
        (ticker, session_date, page_no, older_than_cursor, row_count, payload, provider,
         quarantined)
    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
    ON CONFLICT (ticker, session_date, page_no) DO UPDATE SET
        older_than_cursor = EXCLUDED.older_than_cursor,
        row_count = EXCLUDED.row_count,
        payload = EXCLUDED.payload,
        quarantined = EXCLUDED.quarantined,
        fetched_at = NOW()
"""

UPSERT_SESSION = """
    INSERT INTO darkpool_backfill_sessions
        (ticker, session_date, pages_fetched, prints_received, exhausted, stop_reason,
         quarantined, calls_spent, collected_at, reached_floor)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9)
    ON CONFLICT (ticker, session_date) DO UPDATE SET
        pages_fetched = EXCLUDED.pages_fetched,
        prints_received = EXCLUDED.prints_received,
        exhausted = EXCLUDED.exhausted,
        stop_reason = EXCLUDED.stop_reason,
        quarantined = EXCLUDED.quarantined,
        calls_spent = EXCLUDED.calls_spent,
        collected_at = NOW(),
        -- STICKY: once a walk has proved it crossed the floor, a later resumed run that
        -- stops for some other reason must not un-prove it.
        reached_floor = COALESCE(darkpool_backfill_sessions.reached_floor, FALSE)
                        OR COALESCE(EXCLUDED.reached_floor, FALSE)
"""

#: R-IV.1005(d). ONE definition of complete, asked by BUILD and QUERY alike, decided from the
#: RAW PAGES already stored -- no UW calls.
#:
#:   b1  an unbroken prefix reached a print executed BEFORE E 04:00 ET
#:   b2  the prefix ENDED BY EXHAUSTION -- the last page's row count is below the cap OBSERVED
#:       for that ticker-session -- and its earliest print is at or before E 09:30 ET
#:
#: The cap is MEASURED per ticker-session (`max(row_count)`), never the job's own PAGE_LIMIT:
#: 500 is what this job REQUESTS, not what the vendor promises, and a hardcoded cap would make
#: every final page look short the moment the vendor served fewer.
#:
#: `SUSPECT` is a THIRD state, not a flavour of complete: a short page at 04:00 ET is
#: exhaustion, a short page at 11:00 on SPY is truncation, and recording them alike is how
#: 09-08 came to sit on a permanent archive unproved.
SESSION_FLOOR_SQL = """
    (s.session_date::timestamp + time '04:00') AT TIME ZONE 'America/New_York'
"""

BACKFILL_REACHED_FLOOR_SQL = """
    WITH prints AS (
        SELECT p.ticker, p.session_date, p.page_no, p.row_count,
               MIN((rec->>'executed_at')::timestamptz) AS page_min
          FROM darkpool_backfill_pages p,
               LATERAL jsonb_array_elements(
                   CASE WHEN jsonb_typeof(p.payload->'data') = 'array'
                        THEN p.payload->'data' ELSE '[]'::jsonb END) AS rec
         WHERE (rec->>'executed_at') IS NOT NULL
         GROUP BY p.ticker, p.session_date, p.page_no, p.row_count
    ),
    agg AS (
        SELECT ticker, session_date,
               MIN(page_min)                                   AS earliest_print,
               MAX(row_count)                                  AS observed_cap,
               COUNT(*)                                        AS pages_held,
               MAX(page_no)                                    AS last_page,
               -- The UNBROKEN PREFIX: pages 1..n with no gap. If the highest page number
               -- exceeds the count of pages held, a page is missing and neither route may be
               -- claimed -- a chain with a hole is not a chain.
               (MAX(page_no) = COUNT(*))                       AS unbroken,
               (ARRAY_AGG(row_count ORDER BY page_no DESC))[1] AS last_row_count
          FROM prints
         GROUP BY ticker, session_date
    )
    UPDATE darkpool_backfill_sessions s
       SET reached_floor = CASE
             WHEN a.ticker IS NULL OR NOT a.unbroken THEN FALSE
             -- b1: crossed the floor.
             WHEN a.earliest_print < """ + SESSION_FLOOR_SQL.strip() + """ THEN TRUE
             -- b2: exhausted, and early enough to be the session's own start.
             WHEN a.last_row_count < a.observed_cap
              AND a.earliest_print <=
                  (s.session_date::timestamp + time '09:30') AT TIME ZONE 'America/New_York'
             THEN TRUE
             ELSE FALSE
           END
      FROM agg a
     WHERE a.ticker = s.ticker AND a.session_date = s.session_date
       -- EVERY ROW NOT YET PROVED, not only undecided ones. The b1-only pass had already
       -- written FALSE to 09-08, 09-14 and 09-21, so `reached_floor IS NULL` would have shut
       -- b2 out of exactly the sessions it exists for. TRUE is still never revisited, so a
       -- proved session can no more be un-proved than before -- the protection is the same,
       -- by a different clause.
       AND COALESCE(s.reached_floor, FALSE) = FALSE
       AND s.stop_reason NOT LIKE 'NOT_APPLICABLE%'
"""

#: The THIRD state. Reported, never silently folded into complete or incomplete: a short page
#: mid-morning on a liquid name suggests truncation, not exhaustion, and wants a human.
SUSPECT_SESSIONS_SQL = """
    WITH prints AS (
        SELECT p.ticker, p.session_date, p.page_no, p.row_count,
               MIN((rec->>'executed_at')::timestamptz) AS page_min
          FROM darkpool_backfill_pages p,
               LATERAL jsonb_array_elements(
                   CASE WHEN jsonb_typeof(p.payload->'data') = 'array'
                        THEN p.payload->'data' ELSE '[]'::jsonb END) AS rec
         WHERE (rec->>'executed_at') IS NOT NULL
         GROUP BY p.ticker, p.session_date, p.page_no, p.row_count
    ),
    agg AS (
        SELECT ticker, session_date, MIN(page_min) AS earliest_print,
               MAX(row_count) AS observed_cap, COUNT(*) AS pages_held,
               MAX(page_no) AS last_page,
               (MAX(page_no) = COUNT(*)) AS unbroken,
               (ARRAY_AGG(row_count ORDER BY page_no DESC))[1] AS last_row_count
          FROM prints GROUP BY ticker, session_date
    )
    SELECT a.ticker, a.session_date, a.earliest_print, a.observed_cap, a.last_row_count,
           a.pages_held, a.unbroken
      FROM agg a
      JOIN darkpool_backfill_sessions s
        ON s.ticker = a.ticker AND s.session_date = a.session_date
     WHERE a.unbroken
       AND a.last_row_count < a.observed_cap
       AND a.earliest_print >= (a.session_date::timestamp + time '04:00')
                               AT TIME ZONE 'America/New_York'
       AND a.earliest_print > (a.session_date::timestamp + time '09:30')
                              AT TIME ZONE 'America/New_York'
       AND s.stop_reason NOT LIKE 'NOT_APPLICABLE%'
     ORDER BY a.session_date, a.ticker
"""

#: Which ROUTE proved each complete session, so a report can say b1 or b2 rather than just
#: "complete". The same CASE as the UPDATE, read back rather than re-derived by a caller.
COMPLETENESS_ROUTE_SQL = """
    WITH prints AS (
        SELECT p.ticker, p.session_date, p.page_no, p.row_count,
               MIN((rec->>'executed_at')::timestamptz) AS page_min
          FROM darkpool_backfill_pages p,
               LATERAL jsonb_array_elements(
                   CASE WHEN jsonb_typeof(p.payload->'data') = 'array'
                        THEN p.payload->'data' ELSE '[]'::jsonb END) AS rec
         WHERE (rec->>'executed_at') IS NOT NULL
         GROUP BY p.ticker, p.session_date, p.page_no, p.row_count
    ),
    agg AS (
        SELECT ticker, session_date, MIN(page_min) AS earliest_print,
               MAX(row_count) AS observed_cap, COUNT(*) AS pages_held,
               MAX(page_no) AS last_page,
               (MAX(page_no) = COUNT(*)) AS unbroken,
               (ARRAY_AGG(row_count ORDER BY page_no DESC))[1] AS last_row_count
          FROM prints GROUP BY ticker, session_date
    )
    SELECT a.ticker, a.session_date, a.earliest_print, a.observed_cap, a.last_row_count,
           a.unbroken, s.reached_floor, s.prints_received,
           CASE
             WHEN NOT a.unbroken THEN 'broken_chain'
             WHEN a.earliest_print < (a.session_date::timestamp + time '04:00')
                                     AT TIME ZONE 'America/New_York' THEN 'b1'
             WHEN a.last_row_count < a.observed_cap
              AND a.earliest_print <= (a.session_date::timestamp + time '09:30')
                                      AT TIME ZONE 'America/New_York' THEN 'b2'
             WHEN a.last_row_count < a.observed_cap THEN 'SUSPECT'
             ELSE 'incomplete'
           END AS route
      FROM agg a
      JOIN darkpool_backfill_sessions s
        ON s.ticker = a.ticker AND s.session_date = a.session_date
     WHERE s.stop_reason NOT LIKE 'NOT_APPLICABLE%'
     ORDER BY a.session_date, a.ticker
"""

#: Already finished, so a resumed run skips it. Only `exhausted` counts as done: a session
#: stopped by the budget must be retried, or the night it was cut short becomes a hole.
#: Resume a ticker-session that a previous run cut short. The cursor for the NEXT page is the
#: oldest print on the LAST page already stored, which is exact because the raw payload is kept.
#: Without this, `collect_one` restarted at page 1 every run and the three biggest names could
#: never finish: each run would spend the same calls re-fetching the same first pages forever.
RESUME_SQL = """
    SELECT page_no, payload
      FROM darkpool_backfill_pages
     WHERE ticker = $1 AND session_date = $2
     ORDER BY page_no DESC
     LIMIT 1
"""

DONE_SQL = """
    SELECT ticker, session_date FROM darkpool_backfill_sessions WHERE exhausted = TRUE
"""


def trading_sessions(start: date, end: date) -> List[date]:
    """Trading days from start to end inclusive, per the EXCHANGE CALENDAR — R-IV.988(c).

    `weekday() < 5` was wrong and cost about 8 calls a night on a closed market: 2026-09-07 is
    Labor Day. `strike_ib_converter.py:653` already records having made exactly this mistake,
    so it was a repeat rather than a discovery.

    `stable_engine.market_calendar.is_trading_day` is the ONE author of "is the market open",
    and it RAISES past its enumerated horizon rather than inferring -- which is the right
    disposition and is why the fallback below logs loudly instead of guessing a weekday.
    """
    try:
        from stable_engine.market_calendar import is_trading_day
    except Exception:                                               # noqa: BLE001
        logger.error("[dp-backfill] market calendar unavailable; refusing to guess a calendar",
                     exc_info=True)
        return []
    out, d = [], start
    while d <= end:
        try:
            if is_trading_day(d):
                out.append(d)
        except Exception as exc:                                    # noqa: BLE001
            # Past the calendar's horizon. NOT silently included or excluded.
            logger.error("[dp-backfill] %s is outside the enumerated calendar (%s); extend "
                         "MARKET_HOLIDAYS rather than inferring", d, type(exc).__name__)
        d += timedelta(days=1)
    return out


def session_start_utc(session: date) -> datetime:
    """04:00 ET on the session date, as an aware UTC instant — the walk's floor (R-IV.988(b)).

    04:00 ET rather than 09:30 because the dark-pool feed carries extended-hours prints: the UW
    probe for 2026-08-28 spanned 13:45Z-23:59Z, and the archived 1-minute bars run 04:00-19:59
    ET for the same reason. A 09:30 floor would stop the walk before the session's own
    pre-market prints had been collected.
    """
    return datetime(session.year, session.month, session.day, 4, 0,
                    tzinfo=_ET_ZONE()).astimezone(timezone.utc)


def _parse_executed(ts: Any) -> Optional[datetime]:
    """An aware UTC datetime from the vendor's `executed_at`, or None. NEVER raises."""
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _rows_of(resp: Any) -> List[dict]:
    if not isinstance(resp, dict):
        return []
    data = resp.get("data")
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _oldest_cursor(rows: List[dict]) -> Optional[str]:
    """The oldest `executed_at` on the page -- the cursor for the next, older page."""
    stamps = [str(r.get("executed_at") or r.get("timestamp") or "") for r in rows]
    stamps = [s for s in stamps if s]
    return min(stamps) if stamps else None


class Budget:
    """The three stops, in one place so every call site asks the same object."""

    def __init__(self, call_budget: int = CALL_BUDGET_PER_UW_DAY):
        self.call_budget = call_budget
        self.calls = 0
        self.stop_reason: Optional[str] = None

    def spend(self) -> None:
        self.calls += 1

    @property
    def remaining(self) -> int:
        return max(0, self.call_budget - self.calls)

    def stop(self, reason: str) -> None:
        if not self.stop_reason:
            self.stop_reason = reason
            logger.error("[dp-backfill] STOP: %s (after %d calls)", reason, self.calls)

    @property
    def stopped(self) -> bool:
        return self.stop_reason is not None

    async def check_account(self) -> None:
        """The account-total stop, read from the vendor's own header. Fails OPEN on an
        unreadable account, exactly as the governor does: an unmeasured account must not become
        an outage of its own. The call budget still bounds the run either way."""
        try:
            from integrations.uw_api import account_quota
            q = await account_quota()
            used = q.get("used")
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("[dp-backfill] account total unreadable (%s) - continuing on the "
                           "call budget alone", type(exc).__name__)
            return
        if isinstance(used, int) and used >= ACCOUNT_TOTAL_STOP:
            self.stop("account total %d reached the %d stop" % (used, ACCOUNT_TOTAL_STOP))


async def fetch_page(ticker: str, session: date, cursor: Optional[str],
                     budget: Budget) -> Tuple[Optional[dict], Optional[str]]:
    """One vendor page. Returns (response, error). Spends exactly one call."""
    from integrations.uw_api import _uw_request

    params: Dict[str, Any] = {"date": session.isoformat(), "limit": PAGE_LIMIT}
    if cursor:
        params["older_than"] = cursor
    budget.spend()
    try:
        resp = await _uw_request("/api/darkpool/%s" % ticker, params=params, caller=CALLER)
    except Exception as exc:                                        # noqa: BLE001
        msg = "%s: %s" % (type(exc).__name__, exc)
        if "429" in msg or "rate" in msg.lower():
            budget.stop("vendor refused with 429 - %s" % msg[:120])
            try:
                from integrations.uw_governor import trip_breaker
                trip_breaker("darkpool_backfill saw a 429")
            except Exception:                                       # noqa: BLE001
                pass
        return None, msg
    # The governor's sentinel is falsy; it means the call was never issued.
    if resp is not None and not isinstance(resp, dict):
        detail = "governor blocked: %r" % (resp,)
        # A QUOTA BLOCK IS A RUN-LEVEL FACT, NOT A PER-SESSION ERROR. Treated as the latter on
        # the first night, the run walked on through 18 further sessions writing empty rows and
        # reported a "newest session touched" of 09-16 that it had never actually read. It cost
        # no calls, but a progress figure that counts sessions nobody fetched is worse than no
        # figure at all.
        if "QUOTA_EXCEEDED" in detail or "quota" in detail.lower():
            budget.stop(detail)
        return None, detail
    return resp, None


#: R-IV.997(c). A run whose process died without closing its row. Reconciled on startup
#: because only one process collects at a time, so a null `ended_at` on anything but the
#: current run means the process that owned it is gone.
KILLED_BY_DEPLOY = "KILLED_BY_DEPLOY"

RECONCILE_ORPHANED_RUNS_SQL = """
    UPDATE darkpool_backfill_runs
       SET ended_at = COALESCE(ended_at, NOW()),
           stop_reason = COALESCE(stop_reason, $2)
     WHERE ended_at IS NULL
       AND id <> $1
 RETURNING id, started_at
"""

#: The ACTIVE run, for the deploy guard and the nightly export (R-IV.997(b)/(c)).
ACTIVE_RUN_SQL = """
    SELECT id, started_at, uw_day, calls_spent
      FROM darkpool_backfill_runs
     WHERE ended_at IS NULL
     ORDER BY id DESC
     LIMIT 1
"""


async def reconcile_orphaned_runs(pool, current_run_id: int = -1) -> List[dict]:
    """Close every run row whose process is gone. Returns what was closed."""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(RECONCILE_ORPHANED_RUNS_SQL, current_run_id,
                                    KILLED_BY_DEPLOY)
    except Exception:                                               # noqa: BLE001
        logger.warning("[dp-backfill] could not reconcile orphaned runs", exc_info=True)
        return []
    out = [dict(r) for r in rows]
    for r in out:
        logger.warning("[dp-backfill] run %s had no ended_at and its process is gone -> %s "
                       "(started %s)", r["id"], KILLED_BY_DEPLOY, r["started_at"])
    return out


async def active_run(pool) -> Optional[dict]:
    """The run still in progress, or None. The one question (b) and (c) both ask."""
    try:
        async with pool.acquire() as conn:
            for stmt in DDL:
                await conn.execute(stmt)
            row = await conn.fetchrow(ACTIVE_RUN_SQL)
    except Exception:                                               # noqa: BLE001
        logger.warning("[dp-backfill] could not read the active run", exc_info=True)
        return None
    return dict(row) if row else None


async def refresh_completeness(pool) -> dict:
    """Apply the b1/b2 completeness definition and report what it decided. ZERO UW calls.

    Run at loop STARTUP as well as per-run, because the definition changes with rulings while
    the stored pages do not: a session that became provable under b2 should not have to wait
    for the next nightly window to be recorded as such.
    """
    out = {"updated": 0, "routes": {}, "suspect": [], "complete_by_date_route": {}}
    try:
        async with pool.acquire() as conn:
            for stmt in DDL:
                await conn.execute(stmt)
            tag = await conn.execute(BACKFILL_REACHED_FLOOR_SQL)
            try:
                out["updated"] = int(str(tag).rsplit(" ", 1)[-1])
            except (ValueError, IndexError):
                out["updated"] = -1
            routes = [dict(r) for r in await conn.fetch(COMPLETENESS_ROUTE_SQL)]
            suspect = [dict(r) for r in await conn.fetch(SUSPECT_SESSIONS_SQL)]
    except Exception:                                               # noqa: BLE001
        logger.warning("[dp-backfill] completeness refresh failed", exc_info=True)
        return out

    for r in routes:
        out["routes"][r["route"]] = out["routes"].get(r["route"], 0) + 1
        if r["route"] in ("b1", "b2"):
            key = r["session_date"].isoformat()
            out["complete_by_date_route"].setdefault(key, {}).setdefault(
                r["route"], []).append(r["ticker"])
    out["suspect"] = [
        {"ticker": r["ticker"], "session_date": r["session_date"].isoformat(),
         "earliest_print": r["earliest_print"].isoformat() if r["earliest_print"] else None,
         "observed_cap": r["observed_cap"], "last_row_count": r["last_row_count"]}
        for r in suspect]
    logger.info("[dp-backfill] completeness: %d rows decided, routes %s, %d SUSPECT",
                out["updated"], out["routes"], len(out["suspect"]))
    for sx in out["suspect"]:
        logger.warning("[dp-backfill] SUSPECT %s %s: exhausted (last page %s of cap %s) but "
                       "earliest print %s is after 09:30 ET -- truncation, not exhaustion?",
                       sx["ticker"], sx["session_date"], sx["last_row_count"],
                       sx["observed_cap"], sx["earliest_print"])
    return out


async def collect_one(pool, ticker: str, session: date, budget: Budget) -> dict:
    """Every page of one ticker-session, oldest-cursor-walked. Stores raw, derives nothing."""
    quarantined = session in QUARANTINED_SESSIONS
    floor_utc = session_start_utc(session)      # R-IV.988(b): the walk's floor
    cursor: Optional[str] = None
    pages = prints = spent_here = 0
    exhausted = False
    reached_floor = False          # proved only by crossing the floor, never by any other stop
    stop = "ran to the page ceiling"

    # RESUME where a previous run stopped, rather than re-walking from page 1.
    first_page = 1
    async with pool.acquire() as conn:
        row = await conn.fetchrow(RESUME_SQL, ticker, session)
    if row:
        payload = row["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = None
        resume_cursor = _oldest_cursor(_rows_of(payload)) if payload else None
        if resume_cursor:
            cursor = resume_cursor
            first_page = int(row["page_no"]) + 1
            logger.info("[dp-backfill] %-5s %s resuming at page %d", ticker, session,
                        first_page)

    for page_no in range(first_page, MAX_PAGES_PER_TICKER_SESSION + 1):
        if budget.stopped:
            stop = "run stopped: %s" % budget.stop_reason
            break
        if budget.remaining <= 0:
            stop = "call budget exhausted"
            break
        before = budget.calls
        resp, err = await fetch_page(ticker, session, cursor, budget)
        spent_here += budget.calls - before
        if err:
            stop = "error: %s" % err
            break
        rows = _rows_of(resp)
        if not rows:
            exhausted = True
            stop = "vendor returned no rows" if page_no == 1 else "no further rows"
            break
        async with pool.acquire() as conn:
            await conn.execute(INSERT_PAGE, ticker, session, page_no, cursor, len(rows),
                               json.dumps(resp), PROVIDER, quarantined)
        pages += 1
        prints += len(rows)
        nxt = _oldest_cursor(rows)

        # ── R-IV.988(b): STOP AT THE SESSION'S START ────────────────────────────────────
        # The vendor's `date` does not bound the response, so without this the chain walks on
        # into earlier sessions and re-fetches prints already held -- measured at 36-55%
        # duplication by `tracking_id`. Completeness is decided by the EXECUTED date reached,
        # not by which query returned the page.
        oldest_seen = _parse_executed(nxt)
        if oldest_seen is not None and oldest_seen < floor_utc:
            exhausted = True
            # THE ONLY PLACE THIS IS SET TRUE. Every other stop below leaves it False, because
            # a short page and a stalled cursor prove nothing about coverage -- which is how
            # 09-08, 09-14 and 09-21 reached the permanent archive unproved.
            reached_floor = True
            stop = ("reached prints executed before the %s 04:00 ET start (oldest %s)"
                    % (session, oldest_seen.isoformat()))
            break

        # A cursor that does not move would re-request the same page forever. The measured
        # behaviour of `page` was exactly this, which is why only `older_than` is used.
        if not nxt or nxt == cursor:
            exhausted = True
            stop = "cursor stopped advancing"
            break
        cursor = nxt
        if len(rows) < PAGE_LIMIT:
            exhausted = True
            stop = "short page - session complete"
            break

    # The session row records the WHOLE session, so a resumed run does not report the
    # totals shrinking back to just its own slice.
    async with pool.acquire() as conn:
        tot = await conn.fetchrow(
            "SELECT count(*) AS pages, COALESCE(sum(row_count), 0) AS prints "
            "FROM darkpool_backfill_pages WHERE ticker = $1 AND session_date = $2",
            ticker, session)
        await conn.execute(UPSERT_SESSION, ticker, session, int(tot["pages"]),
                           int(tot["prints"]), exhausted, stop, quarantined, spent_here,
                           reached_floor)
    pages, prints = int(tot["pages"]), int(tot["prints"])
    logger.info("[dp-backfill] %-5s %s pages=%-3d prints=%-6d exhausted=%s (%s)",
                ticker, session, pages, prints, exhausted, stop)
    return {"ticker": ticker, "session": session.isoformat(), "pages": pages,
            "prints": prints, "exhausted": exhausted, "stop": stop, "calls": spent_here,
            "quarantined": quarantined, "reached_floor": reached_floor}


async def run(call_budget: Optional[int] = None,
              until_session: Optional[date] = None,
              names: Tuple[str, ...] = CORE_NAMES) -> dict:
    from database.postgres_client import get_postgres_client
    from integrations.uw_spend_ledger import uw_day

    today = datetime.now(timezone.utc).date()
    if today > ALLOWANCE_THROUGH:
        return {"ok": False, "reason": "the R-IV.921(b)3 allowance lapsed on %s"
                % ALLOWANCE_THROUGH.isoformat()}

    if call_budget is None:
        call_budget = _budget_from_governor()
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        for stmt in DDL:
            await conn.execute(stmt)
        done = {(r["ticker"], r["session_date"]) for r in await conn.fetch(DONE_SQL)}
        run_id = await conn.fetchval(
            "INSERT INTO darkpool_backfill_runs (started_at, uw_day, calls_spent) "
            "VALUES (NOW(), $1, 0) RETURNING id", uw_day())
    # R-IV.997(c): close any run whose process is gone BEFORE collecting, so a null ended_at
    # never means two things at once. Repairs run 7, which my own deploy killed.
    await reconcile_orphaned_runs(pool, run_id)

    budget = Budget(call_budget)
    end = until_session or (today - timedelta(days=1))
    sessions = trading_sessions(OLDEST_KNOWN_SESSION, end)   # OLDEST FIRST, as ruled
    # R-IV.988(c): record the closed dates before collecting, so the archive explains its own
    # gaps. Costs no UW calls -- it only writes rows.
    try:
        await mark_closed_sessions(pool, OLDEST_KNOWN_SESSION, end, names)
    except Exception:                                           # noqa: BLE001
        logger.warning("[dp-backfill] could not mark closed sessions", exc_info=True)
    # R-IV.993(d): decide `reached_floor` for every legacy row from the pages already stored.
    # Costs no UW calls. Runs before collection so the night's work is chosen against the
    # ruled definition of complete rather than the permissive one.
    await refresh_completeness(pool)
    results: List[dict] = []
    logger.info("[dp-backfill] run %s: %d candidate sessions %s..%s, %d names, budget %d calls",
                run_id, len(sessions), sessions[0], sessions[-1], len(names), call_budget)

    await budget.check_account()
    checked_at = 0
    # R-IV.997(c): a deploy cancels this task mid-walk. CancelledError derives from
    # BaseException, so every `except Exception` in this module was blind to it -- which is
    # why run 7 is still recorded as though it were in progress.
    try:
        for session in sessions:
            if budget.stopped or budget.remaining <= 0:
                break
            for ticker in names:
                if budget.stopped or budget.remaining <= 0:
                    break
                if (ticker, session) in done:
                    continue
                results.append(await collect_one(pool, ticker, session, budget))
                # Re-read the account total every ~200 calls: often enough to stop before
                # 30,000, rarely enough not to spend the budget on asking.
                if budget.calls - checked_at >= 200:
                    checked_at = budget.calls
                    await budget.check_account()
    except asyncio.CancelledError:
        await _close_run_as_killed(pool, run_id, budget.calls)
        raise

    secured = sorted({r["session"] for r in results if r["exhausted"] and r["prints"] > 0})
    summary = {
        "sessions_touched": sorted({r["session"] for r in results}),
        "oldest_secured": secured[0] if secured else None,
        "newest_secured": secured[-1] if secured else None,
        "ticker_sessions_exhausted": sum(1 for r in results if r["exhausted"]),
        "empty_ticker_sessions": sum(1 for r in results if r["prints"] == 0),
        "prints": sum(r["prints"] for r in results),
        "pages": sum(r["pages"] for r in results),
        "calls_spent": budget.calls,
        "stop_reason": budget.stop_reason or "completed the candidate list",
        "per_ticker": {t: sum(1 for r in results
                              if r["ticker"] == t and r["exhausted"] and r["prints"] > 0)
                       for t in names},
    }
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE darkpool_backfill_runs SET ended_at = NOW(), calls_spent = $1, "
            "stop_reason = $2, summary = $3::jsonb WHERE id = $4",
            budget.calls, summary["stop_reason"], json.dumps(summary), run_id)
    return {"ok": True, "run_id": run_id, **summary}


async def _close_run_as_killed(pool, run_id: int, calls: int) -> None:
    """Best-effort: stamp a cancelled run before the loop finishes tearing down.

    SHIELDED AND TIMED OUT, and not relied upon. A write issued while the task is being
    cancelled may itself be cancelled, which is exactly why `reconcile_orphaned_runs` exists
    and is the mechanism that actually guarantees the record.
    """
    async def _write():
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE darkpool_backfill_runs SET ended_at = NOW(), calls_spent = $1, "
                "stop_reason = $2 WHERE id = $3 AND ended_at IS NULL",
                calls, KILLED_BY_DEPLOY, run_id)
    try:
        await asyncio.wait_for(asyncio.shield(asyncio.ensure_future(_write())), timeout=5.0)
        logger.warning("[dp-backfill] run %s cancelled mid-walk -> %s", run_id,
                       KILLED_BY_DEPLOY)
    except BaseException:                                           # noqa: BLE001
        # Deliberately swallowed: startup reconciliation will close it on the next boot.
        logger.warning("[dp-backfill] run %s cancelled; could not stamp it now, startup "
                       "reconciliation will", run_id)


# ── R-IV.950(c): the nightly trigger ────────────────────────────────────────────────────────

#: 20:30 ET, half an hour after the vendor's own day rolls at 20:00, so the fresh allowance is
#: certainly available and the evening is not shared with the close-time collectors.
NIGHTLY_START_ET = (20, 30)
#: Retried until this hour, for the reason the nightly recompute records: a one-shot window
#: loses a session permanently if the single attempt fails, and these sessions are unrepairable.
NIGHTLY_RETRY_UNTIL_HOUR_ET = 23
NIGHTLY_TICK_SECONDS = 60

ALL_SECURED_SQL = """
    SELECT count(*) AS secured
      FROM darkpool_backfill_sessions
     WHERE exhausted = TRUE AND reached_floor = TRUE AND prints_received > 0
       AND ticker = ANY($1::text[]) AND session_date = ANY($2::date[])
"""


#: A session the EXCHANGE was shut. Recorded rather than skipped: `remaining_work` already
#: drops these from its denominator via `trading_sessions`, but an unexplained hole in the
#: archive cannot be told from one nobody collected.
NOT_APPLICABLE_REASON = "NOT_APPLICABLE: the exchange was closed on this date"

MARK_NOT_APPLICABLE_SQL = """
    INSERT INTO darkpool_backfill_sessions
        (ticker, session_date, pages_fetched, prints_received, exhausted, stop_reason,
         quarantined, calls_spent)
    VALUES ($1, $2, 0, 0, TRUE, $3, FALSE, 0)
    ON CONFLICT (ticker, session_date) DO UPDATE
       SET exhausted = TRUE, stop_reason = $3
     WHERE darkpool_backfill_sessions.prints_received = 0
"""


async def mark_closed_sessions(pool, start: date, end: date,
                               names: Tuple[str, ...] = CORE_NAMES) -> int:
    """Record every CLOSED date in the window as NOT_APPLICABLE. Returns rows touched.

    Guarded on `prints_received = 0`: 2026-09-07 was enqueued for weeks before this ruling and
    the walk that ran on it DID return prints -- prints executed on 09-04, because the vendor's
    `date` does not bound the response. Overwriting a row that holds real prints would discard
    them to tidy a label.
    """
    closed = []
    d = start
    while d <= end:
        if d not in set(trading_sessions(d, d)):
            closed.append(d)
        d += timedelta(days=1)
    if not closed:
        return 0
    touched = 0
    async with pool.acquire() as conn:
        for stmt in DDL:
            await conn.execute(stmt)
        for session in closed:
            for ticker in names:
                await conn.execute(MARK_NOT_APPLICABLE_SQL, ticker, session,
                                   NOT_APPLICABLE_REASON)
                touched += 1
    logger.info("[dp-backfill] marked %d closed-session rows NOT_APPLICABLE (%s)",
                touched, ", ".join(str(c) for c in closed))
    return touched


async def remaining_work(pool, names=CORE_NAMES, until_session: Optional[date] = None) -> dict:
    """How much of the vendor's remaining window is NOT yet secured.

    R-IV.950(c): the job stops itself once every session the vendor still holds is secured. That
    has to be a MEASUREMENT, not a date arithmetic guess -- the vendor drops its oldest session
    daily, so "every session it still holds" moves every night.
    """
    end = until_session or (datetime.now(timezone.utc).date() - timedelta(days=1))
    sessions = trading_sessions(OLDEST_KNOWN_SESSION, end)
    wanted = len(sessions) * len(names)
    async with pool.acquire() as conn:
        for stmt in DDL:
            await conn.execute(stmt)
        secured = await conn.fetchval(ALL_SECURED_SQL, list(names), sessions)
    secured = int(secured or 0)
    return {"wanted": wanted, "secured": secured, "remaining": max(0, wanted - secured),
            "sessions": len(sessions), "names": len(names),
            "complete": secured >= wanted}


async def darkpool_backfill_loop() -> None:
    """One-minute ticker that fires the backfill once per VENDOR day from 20:30 ET.

    NEVER RAISES out of the loop: a collector that dies on one bad night stops collecting for
    every night after it, and the sessions it would have taken are not recoverable.
    """
    from integrations.uw_spend_ledger import uw_day

    try:
        from database.postgres_client import get_postgres_client
    except Exception:                                               # noqa: BLE001
        logger.error("[dp-backfill] cannot import the pool; the nightly will not run",
                     exc_info=True)
        return

    fired: set = set()
    # R-IV.1005(d): apply the completeness definition at startup. It costs no UW calls, and a
    # ruling that changes the definition should not have to wait for the next nightly window
    # before the archive reflects it.
    try:
        pool0 = await get_postgres_client()
        await reconcile_orphaned_runs(pool0)
        await refresh_completeness(pool0)
    except Exception:                                               # noqa: BLE001
        logger.warning("[dp-backfill] startup completeness refresh failed", exc_info=True)
    logger.info("[dp-backfill] nightly loop armed for %02d:%02d ET, retry until %02d:00 ET",
                NIGHTLY_START_ET[0], NIGHTLY_START_ET[1], NIGHTLY_RETRY_UNTIL_HOUR_ET)
    while True:
        try:
            now = datetime.now(timezone.utc)
            et = now.astimezone(_ET_ZONE())
            today = datetime.now(timezone.utc).date()
            # The allowance lapses on its own date, and the job refuses past it anyway.
            if today > ALLOWANCE_THROUGH:
                logger.info("[dp-backfill] allowance lapsed on %s; loop going quiet",
                            ALLOWANCE_THROUGH.isoformat())
                return
            key = uw_day(now).isoformat()
            in_window = ((et.hour, et.minute) >= NIGHTLY_START_ET
                         and et.hour <= NIGHTLY_RETRY_UNTIL_HOUR_ET)
            if in_window and key not in fired:
                pool = await get_postgres_client()
                work = await remaining_work(pool)
                if work["complete"]:
                    # Stops ITSELF, as ruled -- and says so once per vendor day rather than
                    # every minute, so "nothing left to do" is visible without being noise.
                    fired.add(key)
                    logger.info("[dp-backfill] every session the vendor still holds is secured "
                                "(%d of %d ticker-sessions); nothing to collect on UW day %s",
                                work["secured"], work["wanted"], key)
                else:
                    logger.info("[dp-backfill] UW day %s: %d of %d ticker-sessions secured, "
                                "%d remaining -- starting", key, work["secured"],
                                work["wanted"], work["remaining"])
                    out = await run()
                    # SUCCESS IS RECORDED ONLY AFTER A RUN THAT COMPLETED. A failed pass marked
                    # as fired is one of the two ways the nightly recompute used to lose a
                    # session, and these sessions cannot be re-collected later.
                    if out.get("ok"):
                        fired.add(key)
                        logger.info("[dp-backfill] UW day %s done: %s", key,
                                    {k: out.get(k) for k in
                                     ("oldest_secured", "newest_secured",
                                      "ticker_sessions_exhausted", "calls_spent",
                                      "stop_reason")})
                    else:
                        logger.error("[dp-backfill] UW day %s run refused: %s -- will retry",
                                     key, out.get("reason"))
        except Exception as exc:                                    # noqa: BLE001
            # exc_info, because the message alone is not diagnosable. A tick that died with
            # "'NoneType' object is not subscriptable" and no traceback took three guesses to
            # place, and these sessions cannot be re-collected if a night is lost to it.
            logger.error("[dp-backfill] nightly tick failed (will retry): %s: %s",
                         type(exc).__name__, exc, exc_info=True)
        await asyncio.sleep(NIGHTLY_TICK_SECONDS)


def _ET_ZONE():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except ImportError:                                             # pragma: no cover
        import pytz
        return pytz.timezone("America/New_York")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)
    budget = int(os.getenv("DP_BACKFILL_BUDGET") or CALL_BUDGET_PER_UW_DAY)
    out = asyncio.run(run(call_budget=budget))
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
