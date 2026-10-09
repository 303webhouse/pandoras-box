"""Triton dark-pool collection (R-IV.823(e), amended by R-IV.826(c)).

WHY THIS EXISTS. Dark pool is Triton's last filter with no stored history. `darkpool_enrichment`
computed a dict per signal and nothing ever persisted it, and since 2026-06-07 it has raised on
every print it saw. QUERY's SM7 needs the prints themselves, for the sessions Triton fired in,
before the vendor's history window ages them out.

WHAT IT STORES, AND WHAT IT DOES NOT. Per TICKER-SESSION, not per row: every page the vendor
returns, raw, plus how many pages were fetched and whether the window's start was reached. It
derives no direction and no score. Classification is SM7's job, done later, on the raw pages.

THE WINDOW. From the session's latest fire back to 240 regular-session minutes before its
earliest fire, reaching into the prior session(s) when the earliest fire is too close to the
open. Each market date in the window is paged separately (`date` + `older_than`, 500 a page),
newest first.

ORDER. The depth probe runs once, on the first night (R-IV.826(c)): three calls at the oldest,
a middle and the most recent fire still needed, logged and published on this job's /health
entry. Until a probe has succeeded, ONLY tonight's session is collected. After it, tonight's
session first, then the backlog OLDEST FIRST, because the oldest sessions age out of the vendor's
window first (a 2026-04-23 probe measured a 30-trading-day cap; re-measured, not assumed).

BUDGET. After the 16:00 ET close only. The run stops at whichever comes first:
  * 19:50 ET (the charter's hard stop);
  * ten minutes before UW's 00:00Z reset. That is 20:00 ET under EDT but 19:00 ET under EST
    (from 2026-11-01), so after the DST change this, not 19:50, is the binding stop. Spending
    past the reset spends tomorrow's quota and can trip Triton's 17K shed inside the window.
  * the ACCOUNT's day total reaching 30,000 of 40,000 (UW's own header count where current,
    our count otherwise, whichever is larger).

THE SEAL. Rows with `id <= 377783 AND fired_at >= 2026-08-17` (the Triton holdout) are excluded
in SQL and again in Python. Nothing here logs or counts them.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

JOB_NAME = "darkpool_collector"
PROVIDER = "uw"

# The Triton holdout, both predicates (triton-holdout-registration-2026-09-01.md:44).
SEAL_MAX_ID = 377783
SEAL_FROM = datetime(2026, 8, 17, tzinfo=UTC)

LOOKBACK_RTH_MINUTES = 240
PAGE_LIMIT = 500                 # the vendor's maximum (api_spec.yaml, /api/darkpool/{ticker})
MAX_PAGES_PER_WINDOW = 60        # 30,000 prints; a window that needs more is recorded as capped
POST_CLOSE_START = time(16, 0)
HARD_STOP_ET = time(19, 50)
RESET_MARGIN = timedelta(minutes=10)
ACCOUNT_STOP_AT = 30_000
LAST_RUN_KEY = "darkpool_collector:last_run"
LAST_RUN_TTL_S = 7 * 86400

# How one market date's paging ended.
REACHED_START = "reached_start"  # a page reached back past the window's start
EXHAUSTED = "exhausted"          # a short page: the date holds no older prints
EMPTY = "empty"                  # the FIRST page was empty: no prints, or beyond the vendor's depth
PAGE_CAP = "page_cap"
STALLED = "stalled"              # the cursor did not move
ERROR = "error"                  # the request failed, or the body had no `data` list
INTERRUPTED = "interrupted"      # the run stopped mid-window (budget / deadline / vendor gate)

REACHED = (REACHED_START, EXHAUSTED)
# A window with one of these is not attempted again. ERROR and INTERRUPTED are retried.
TERMINAL = (REACHED_START, EXHAUSTED, EMPTY, PAGE_CAP, STALLED)

FORWARD = "forward"
BACKFILL = "backfill"


# ── DDL (created by the job itself, as uw_daily_burn and stable_job_status are) ──────────────
DDL = (
    """CREATE TABLE IF NOT EXISTS darkpool_windows (
           ticker TEXT NOT NULL,
           session_date DATE NOT NULL,
           first_fire_at TIMESTAMPTZ NOT NULL,
           last_fire_at TIMESTAMPTZ NOT NULL,
           window_start TIMESTAMPTZ NOT NULL,
           window_end TIMESTAMPTZ NOT NULL,
           pages_fetched INT NOT NULL,
           prints_received INT NOT NULL,
           window_start_reached BOOLEAN NOT NULL,
           stop_reason TEXT NOT NULL,
           segments JSONB NOT NULL,
           mode TEXT NOT NULL,
           provider TEXT NOT NULL,
           collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
           PRIMARY KEY (ticker, session_date)
       )""",
    """CREATE TABLE IF NOT EXISTS darkpool_pages (
           ticker TEXT NOT NULL,
           session_date DATE NOT NULL,
           page_no INT NOT NULL,
           request_date DATE NOT NULL,
           older_than_ms BIGINT NOT NULL,
           row_count INT NOT NULL,
           payload JSONB NOT NULL,
           provider TEXT NOT NULL,
           fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
           PRIMARY KEY (ticker, session_date, page_no)
       )""",
    """CREATE TABLE IF NOT EXISTS darkpool_depth_probes (
           id SERIAL PRIMARY KEY,
           probed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
           ok BOOLEAN NOT NULL,
           result JSONB NOT NULL
       )""",
)

FIRES_SQL = """
    SELECT id, ticker, fired_at
      FROM triton_flow_shadow
     WHERE fired_at >= $1 AND fired_at < $2
       AND NOT (id <= $3 AND fired_at >= $4)
       AND COALESCE(instrument_class, '') <> 'cash_settled_index'
"""
DONE_SQL = "SELECT ticker, session_date FROM darkpool_windows WHERE stop_reason = ANY($1::text[])"
PROBE_DONE_SQL = "SELECT EXISTS (SELECT 1 FROM darkpool_depth_probes WHERE ok)"
INSERT_PROBE = "INSERT INTO darkpool_depth_probes (ok, result) VALUES ($1, $2::jsonb)"
DELETE_PAGES = "DELETE FROM darkpool_pages WHERE ticker = $1 AND session_date = $2"
INSERT_PAGE = """
    INSERT INTO darkpool_pages
        (ticker, session_date, page_no, request_date, older_than_ms, row_count, payload, provider)
    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
"""
UPSERT_WINDOW = """
    INSERT INTO darkpool_windows
        (ticker, session_date, first_fire_at, last_fire_at, window_start, window_end,
         pages_fetched, prints_received, window_start_reached, stop_reason, segments, mode,
         provider, collected_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, NOW())
    ON CONFLICT (ticker, session_date) DO UPDATE SET
        first_fire_at = EXCLUDED.first_fire_at, last_fire_at = EXCLUDED.last_fire_at,
        window_start = EXCLUDED.window_start, window_end = EXCLUDED.window_end,
        pages_fetched = EXCLUDED.pages_fetched, prints_received = EXCLUDED.prints_received,
        window_start_reached = EXCLUDED.window_start_reached,
        stop_reason = EXCLUDED.stop_reason, segments = EXCLUDED.segments,
        mode = EXCLUDED.mode, provider = EXCLUDED.provider, collected_at = NOW()
"""


# ── pure helpers ──────────────────────────────────────────────────────────────────────────
def is_sealed(row_id: int, fired_at: datetime) -> bool:
    """The holdout predicate. Both halves, always."""
    return row_id <= SEAL_MAX_ID and fired_at >= SEAL_FROM


def _at(d: date, t: time) -> datetime:
    return datetime.combine(d, t).replace(tzinfo=ET)


def _midnight_et(d: date) -> datetime:
    return _at(d, time(0, 0))


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def window_start(first_fire: datetime) -> datetime:
    """240 regular-session minutes before the earliest fire, walking back across sessions.

    A fire outside regular hours is anchored to the nearer edge of its session. Early closes
    are not modelled: the calendar has no half-day table, so a 13:00 close is treated as 16:00.
    """
    from stable_engine.market_calendar import previous_trading_day
    from stable_engine.sessions import REGULAR_CLOSE, REGULAR_OPEN

    fire = first_fire.astimezone(ET)
    day = fire.date()
    opened, closed = _at(day, REGULAR_OPEN), _at(day, REGULAR_CLOSE)
    anchor = min(max(fire, opened), closed)
    need = timedelta(minutes=LOOKBACK_RTH_MINUTES)
    have = anchor - opened
    if have >= need:
        return anchor - need
    need -= have
    while True:
        day = previous_trading_day(day)
        opened, closed = _at(day, REGULAR_OPEN), _at(day, REGULAR_CLOSE)
        if need <= closed - opened:
            return closed - need
        need -= closed - opened


def segments(start: datetime, end: datetime) -> List[Tuple[date, datetime, datetime]]:
    """(market date, lower, upper) for each trading date the window touches, newest first."""
    from stable_engine.market_calendar import previous_trading_day

    first, last = start.astimezone(ET).date(), end.astimezone(ET).date()
    out = []
    d = last
    while d >= first:
        upper = end if d == last else _midnight_et(d + timedelta(days=1))
        lower = start if d == first else _midnight_et(d)
        out.append((d, lower, upper))
        d = previous_trading_day(d)
    return out


def deadline_for(now_utc: datetime) -> datetime:
    """The earlier of 19:50 ET and ten minutes before the next 00:00Z reset."""
    hard = _at(now_utc.astimezone(ET).date(), HARD_STOP_ET).astimezone(UTC)
    reset = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=UTC) + timedelta(days=1)
    return min(hard, reset - RESET_MARGIN)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, str):
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _span(prints: List[dict]) -> Tuple[Optional[datetime], Optional[datetime]]:
    stamps = [t for t in (_parse_ts(p.get("executed_at")) for p in prints
                          if isinstance(p, dict)) if t]
    return (min(stamps), max(stamps)) if stamps else (None, None)


@dataclass
class Group:
    ticker: str
    session: date
    first_fire: datetime
    last_fire: datetime


def group_fires(rows) -> List[Group]:
    """Ticker-sessions from fire rows. A sealed row is dropped here as well as in SQL."""
    groups: Dict[Tuple[str, date], Group] = {}
    for r in rows:
        rid, ticker, fired = r["id"], r["ticker"], r["fired_at"]
        if rid is None or not ticker or fired is None or is_sealed(rid, fired):
            continue
        key = (ticker.upper(), fired.astimezone(ET).date())
        g = groups.get(key)
        if g is None:
            groups[key] = Group(key[0], key[1], fired, fired)
        else:
            g.first_fire = min(g.first_fire, fired)
            g.last_fire = max(g.last_fire, fired)
    return list(groups.values())


# ── budget ────────────────────────────────────────────────────────────────────────────────
async def account_day_total(now_utc: datetime) -> int:
    """The account's spend today: UW's own header count if it was read since 00:00Z, our count
    otherwise -- whichever is larger, since ours cannot see the key's other client."""
    from integrations.uw_api import REDIS_KEY_UW_QUOTA
    from integrations.uw_api_cache import get_daily_count

    total = 0
    try:
        total = int(await get_daily_count() or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[darkpool] own count unreadable: %s", exc)
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        raw = await client.get(REDIS_KEY_UW_QUOTA) if client else None
        if raw:
            q = json.loads(raw)
            at = _parse_ts(q.get("at"))
            reset = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=UTC)
            if isinstance(q.get("used"), int) and at and at >= reset:
                total = max(total, q["used"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[darkpool] account header unreadable: %s", exc)
    return total


@dataclass
class Budget:
    deadline: datetime
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    total: Callable[[datetime], Awaitable[int]] = account_day_total
    stopped: Optional[str] = None

    async def check(self) -> Optional[str]:
        if self.stopped:
            return self.stopped
        now = self.now()
        if now >= self.deadline:
            self.stopped = "deadline %s" % self.deadline.isoformat()
        else:
            spent = await self.total(now)
            if spent >= ACCOUNT_STOP_AT:
                self.stopped = "account total %d >= %d" % (spent, ACCOUNT_STOP_AT)
        return self.stopped


def _vendor_gate(body: Any) -> Optional[str]:
    """A governor / breaker / 429 refusal stops the night; a plain failure fails one window."""
    from integrations.uw_governor import UWUnavailable
    if isinstance(body, UWUnavailable):
        return "vendor unavailable: %s" % (getattr(body, "reason", None) or "unknown")
    return None


# ── paging ────────────────────────────────────────────────────────────────────────────────
Fetch = Callable[[str, str, int, int], Awaitable[Any]]


@dataclass
class WindowResult:
    pages: int = 0
    prints: int = 0
    segments: List[dict] = field(default_factory=list)


async def _page_date(conn, fetch: Fetch, g: Group, d: date, lower: datetime, upper: datetime,
                     budget: Budget, res: WindowResult) -> str:
    cursor = upper
    seg = {"date": d.isoformat(), "lower": lower.isoformat(), "upper": upper.isoformat(),
           "pages": 0, "prints": 0}
    res.segments.append(seg)
    while True:
        stop = await budget.check()
        if stop:
            seg["stop_reason"] = INTERRUPTED
            return INTERRUPTED
        if res.pages >= MAX_PAGES_PER_WINDOW:
            seg["stop_reason"] = PAGE_CAP
            return PAGE_CAP
        body = await fetch(g.ticker, d.isoformat(), _ms(cursor), PAGE_LIMIT)
        gate = _vendor_gate(body)
        if gate:
            budget.stopped = gate
            seg["stop_reason"] = INTERRUPTED
            return INTERRUPTED
        data = body.get("data") if isinstance(body, dict) else None
        if not body or not isinstance(data, list):
            seg["stop_reason"] = ERROR
            return ERROR
        res.pages += 1
        seg["pages"] += 1
        await conn.execute(INSERT_PAGE, g.ticker, g.session, res.pages, d, _ms(cursor),
                           len(data), json.dumps(body), PROVIDER)
        res.prints += len(data)
        seg["prints"] += len(data)
        if not data:
            seg["stop_reason"] = EMPTY if seg["pages"] == 1 else EXHAUSTED
            return seg["stop_reason"]
        oldest, _ = _span(data)
        if oldest is None:
            seg["stop_reason"] = ERROR
            return ERROR
        seg["oldest_executed_at"] = oldest.isoformat()
        if oldest <= lower:
            seg["stop_reason"] = REACHED_START
        elif len(data) < PAGE_LIMIT:
            seg["stop_reason"] = EXHAUSTED
        elif oldest >= cursor:
            seg["stop_reason"] = STALLED
        else:
            cursor = oldest
            continue
        return seg["stop_reason"]


async def collect_window(conn, fetch: Fetch, g: Group, mode: str, budget: Budget) -> WindowResult:
    """Page one ticker-session's window and record it. A retried window starts clean."""
    start, end = window_start(g.first_fire), g.last_fire
    await conn.execute(DELETE_PAGES, g.ticker, g.session)
    res = WindowResult()
    reason = REACHED_START
    for d, lower, upper in segments(start, end):
        reason = await _page_date(conn, fetch, g, d, lower, upper, budget, res)
        if reason not in REACHED:
            break
    reached = reason in REACHED
    await conn.execute(UPSERT_WINDOW, g.ticker, g.session, g.first_fire, g.last_fire, start, end,
                       res.pages, res.prints, reached, reason, json.dumps(res.segments), mode,
                       PROVIDER)
    return res


# ── the depth probe (R-IV.826(c)) ─────────────────────────────────────────────────────────
async def run_probe(fetch: Fetch, fires: List[datetime], tickers: Dict[datetime, str],
                    today: date) -> dict:
    """Three calls: the oldest fire still needed, a middle one, the most recent."""
    from stable_engine.market_calendar import trading_days_between

    ordered = sorted(fires)
    picks = [("oldest", ordered[0]), ("mid", ordered[len(ordered) // 2]),
             ("recent", ordered[-1])]
    calls = []
    for label, fired in picks:
        session = fired.astimezone(ET).date()
        body = await fetch(tickers[fired], session.isoformat(), _ms(fired), PAGE_LIMIT)
        call = {"label": label, "ticker": tickers[fired], "requested_date": session.isoformat(),
                "older_than": fired.isoformat(),
                "trading_days_back": trading_days_between(session, today)}
        gate = _vendor_gate(body)
        data = body.get("data") if isinstance(body, dict) else None
        if gate:
            call["status"] = gate
        elif not body or not isinstance(data, list):
            call["status"] = "error"
        else:
            oldest, newest = _span(data)
            dates = sorted({t.astimezone(ET).date().isoformat() for t in
                            (_parse_ts(p.get("executed_at")) for p in data if isinstance(p, dict))
                            if t})
            call.update(status="ok" if data else "empty", rows=len(data),
                        oldest_executed_at=oldest.isoformat() if oldest else None,
                        newest_executed_at=newest.isoformat() if newest else None,
                        dates_returned=dates,
                        matches_requested_date=dates == [session.isoformat()] if data else None)
        calls.append(call)
    return {"ok": any(c["status"] in ("ok", "empty") for c in calls), "calls": calls,
            "probed_on": today.isoformat()}


# ── one night ─────────────────────────────────────────────────────────────────────────────
async def collect(now_utc: Optional[datetime] = None, fetch: Optional[Fetch] = None,
                  budget: Optional[Budget] = None) -> dict:
    """One nightly pass. Returns a summary carrying `rows_touched` (pages stored)."""
    from database.postgres_client import get_postgres_client
    from jobs.stable_jobs import OutputCheckFailed
    from jobs.triton_shadow_common import TRITON_WINDOW_FIRST_SESSION
    from stable_engine.market_calendar import is_trading_day

    if fetch is None:
        from integrations.uw_api import get_darkpool_ticker_page as fetch
    now = now_utc or datetime.now(UTC)
    today = now.astimezone(ET).date()
    summary: dict = {"session": today.isoformat(), "rows_touched": 0, "windows": {},
                     "pending": 0, "probe": None, "stopped": None}
    if not is_trading_day(today) or now.astimezone(ET).time() < POST_CLOSE_START:
        summary["skipped"] = "not after a trading session's close"
        return summary
    if budget is None:
        # A pinned `now_utc` pins the clock too, so a replayed night is judged on its own hours.
        budget = (Budget(deadline=deadline_for(now), now=lambda: now) if now_utc
                  else Budget(deadline=deadline_for(now)))
    summary["deadline"] = budget.deadline.isoformat()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        for stmt in DDL:
            await conn.execute(stmt)
        rows = await conn.fetch(FIRES_SQL, _midnight_et(TRITON_WINDOW_FIRST_SESSION),
                                _midnight_et(today + timedelta(days=1)), SEAL_MAX_ID, SEAL_FROM)
        groups = group_fires(rows)
        done = {(r["ticker"], r["session_date"]) for r in await conn.fetch(DONE_SQL, list(TERMINAL))}
        pending = [g for g in groups if (g.ticker, g.session) not in done]
        summary["pending"] = len(pending)

        probe_ok = bool(await conn.fetchval(PROBE_DONE_SQL))
        if not probe_ok and pending and not await budget.check():
            fires = {}
            for g in pending:
                fires.setdefault(g.first_fire, g.ticker)
                fires.setdefault(g.last_fire, g.ticker)
            probe = await run_probe(fetch, list(fires), fires, today)
            logger.info("[darkpool] depth probe: %s", json.dumps(probe))
            await conn.execute(INSERT_PROBE, probe["ok"], json.dumps(probe))
            summary["probe"] = probe
            probe_ok = probe["ok"]

        forward = sorted((g for g in pending if g.session == today), key=lambda g: g.ticker)
        backlog = sorted((g for g in pending if g.session < today),
                         key=lambda g: (g.session, g.ticker)) if probe_ok else []
        summary["backfill_allowed"] = probe_ok
        attempted = 0
        for mode, items in ((FORWARD, forward), (BACKFILL, backlog)):
            for g in items:
                if await budget.check():
                    break
                attempted += 1
                res = await collect_window(conn, fetch, g, mode, budget)
                summary["rows_touched"] += res.pages
                reason = res.segments[-1]["stop_reason"] if res.segments else INTERRUPTED
                key = "%s:%s" % (mode, reason)
                summary["windows"][key] = summary["windows"].get(key, 0) + 1
        summary["stopped"] = budget.stopped

    await _publish_last_run(summary)
    logger.info("[darkpool] night %s: %d pages, windows %s, stopped=%s", today,
                summary["rows_touched"], summary["windows"], summary["stopped"])
    if attempted and not summary["rows_touched"] and not budget.stopped:
        raise OutputCheckFailed("darkpool: %d windows attempted, no page stored" % attempted)
    return summary


async def _publish_last_run(summary: dict) -> None:
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        if client:
            slim = {k: v for k, v in summary.items() if k != "probe"}
            await client.setex(LAST_RUN_KEY, LAST_RUN_TTL_S, json.dumps(slim, default=str))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[darkpool] last-run publish failed: %s", exc)


async def run_nightly() -> None:
    """The scheduled entry point: one pass, recorded for /health and in `job_runs`."""
    from jobs.stable_jobs import _record

    await _record(JOB_NAME, collect, session_date=datetime.now(ET).date())


# ── /health ───────────────────────────────────────────────────────────────────────────────
async def health_detail() -> dict:
    """The probe's result and the collection's state, for this job's /health entry."""
    out: dict = {}
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            if not await conn.fetchval("SELECT to_regclass('darkpool_depth_probes') IS NOT NULL"):
                return {"depth_probe": {"state": "NOT_RUN"}, "windows": {}}
            probe = await conn.fetchrow(
                "SELECT probed_at, ok, result FROM darkpool_depth_probes ORDER BY id DESC LIMIT 1")
            out["depth_probe"] = ({"state": "OK" if probe["ok"] else "FAILED",
                                   "probed_at": probe["probed_at"].isoformat(),
                                   "result": json.loads(probe["result"])}
                                  if probe else {"state": "NOT_RUN"})
            rows = await conn.fetch(
                "SELECT stop_reason, COUNT(*) AS n, COALESCE(SUM(pages_fetched), 0) AS pages "
                "FROM darkpool_windows GROUP BY stop_reason")
            out["windows"] = {r["stop_reason"]: {"n": int(r["n"]), "pages": int(r["pages"])}
                              for r in rows}
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        raw = await client.get(LAST_RUN_KEY) if client else None
        out["last_run"] = json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001
        out["last_run_error"] = type(exc).__name__
    return out
