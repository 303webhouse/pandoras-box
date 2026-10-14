"""Dark-pool backfill progress — the read path for R-IV.993(c)'s before/after measurement.

WHY A ROUTE. The figures R-IV.993(c) asks for -- calls per TICKER-SESSION before and after the
session-boundary stop -- are already recorded by the job in `darkpool_backfill_sessions`
(`calls_spent`, per ticker-session, per night). What was missing was a way to read them:
`railway logs` only reaches the CURRENT deployment, so the pre-fix run's own log lines are
unreachable the moment a new build swaps in, and that is exactly how last night's numbers went
dark. R-IV.552(b) -- routes exist so nobody needs direct SQL -- so this is the route.

READ-ONLY BY CONSTRUCTION. Every statement here is a SELECT. Nothing in this module writes,
and it touches none of SM7's registered `darkpool_*` collector tables (R-IV.912(c)2) -- only
the backfill's own three.

THE SEAL IS SATISFIED TRIVIALLY, not by a predicate: there is no query here that can isolate
rows by `id` or `fired_at`. These tables carry neither column.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from database.postgres_client import get_postgres_client
from utils.pivot_auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/darkpool-backfill", tags=["darkpool-backfill"])


#: Per ticker-session, as the job recorded it. `calls_spent` is the figure R-IV.993(c) wants.
SESSIONS_SQL = """
    SELECT ticker, session_date, pages_fetched, prints_received, exhausted,
           stop_reason, quarantined, calls_spent, collected_at, reached_floor
      FROM darkpool_backfill_sessions
     WHERE ($1::date IS NULL OR session_date >= $1)
       AND ($2::date IS NULL OR session_date <= $2)
     ORDER BY session_date, ticker
"""

RUNS_SQL = """
    SELECT id, started_at, ended_at, uw_day, calls_spent, stop_reason, summary
      FROM darkpool_backfill_runs
     ORDER BY id DESC
     LIMIT $1
"""

#: A ticker-session is NOT_APPLICABLE when the exchange was shut (R-IV.988(c)). Counted apart
#: from collected work, because folding the two together is how "secured" came to mean two
#: different things at once.
NOT_APPLICABLE_PREFIX = "NOT_APPLICABLE"

#: One session, per name: totals, RTH count, and the earliest/latest print by EXECUTED time.
SESSION_PRINTS_SQL = """
    SELECT p.ticker,
           COUNT(*)                                                AS total_rows,
           MIN((rec->>'executed_at')::timestamptz)                 AS earliest,
           MAX((rec->>'executed_at')::timestamptz)                 AS latest,
           COUNT(*) FILTER (
               WHERE ((rec->>'executed_at')::timestamptz AT TIME ZONE 'America/New_York')::time
                     >= time '09:30'
                 AND ((rec->>'executed_at')::timestamptz AT TIME ZONE 'America/New_York')::time
                     <  time '16:00'
                 AND ((rec->>'executed_at')::timestamptz AT TIME ZONE 'America/New_York')::date
                     = p.session_date
           )                                                       AS rth_prints,
           ARRAY_AGG(DISTINCT
               (((rec->>'executed_at')::timestamptz AT TIME ZONE 'America/New_York')::date)
               ::text)                                             AS exec_dates
      FROM darkpool_backfill_pages p,
           LATERAL jsonb_array_elements(
               CASE WHEN jsonb_typeof(p.payload->'data') = 'array'
                    THEN p.payload->'data' ELSE '[]'::jsonb END) AS rec
     WHERE p.session_date = $1
       AND (rec->>'executed_at') IS NOT NULL
     GROUP BY p.ticker
     ORDER BY p.ticker
"""

#: Per page: extent and TIMING. `fetched_at` is what answers "was this fetched after QUERY's
#: snapshot", which is the difference between staleness and a defect.
SESSION_PAGES_SQL = """
    SELECT p.ticker, p.page_no, p.row_count, p.fetched_at,
           (SELECT MIN((rec->>'executed_at')::timestamptz)
              FROM jsonb_array_elements(
                   CASE WHEN jsonb_typeof(p.payload->'data') = 'array'
                        THEN p.payload->'data' ELSE '[]'::jsonb END) AS rec
             WHERE (rec->>'executed_at') IS NOT NULL)                AS page_min
      FROM darkpool_backfill_pages p
     WHERE p.session_date = $1
     ORDER BY p.ticker, p.page_no
"""

SESSION_ROWS_SQL = """
    SELECT ticker, pages_fetched, prints_received, exhausted, reached_floor,
           calls_spent, stop_reason, collected_at
      FROM darkpool_backfill_sessions
     WHERE session_date = $1
     ORDER BY ticker
"""


#: The ONE statement of what the export may write. Reported verbatim in the payload, so a
#: reader never has to trust a prose restatement of it -- the first version of this route
#: said "exhausted AND prints_received > 0" while actually also requiring reached_floor.
ELIGIBLE_FILTER = "exhausted = TRUE AND reached_floor = TRUE AND prints_received > 0"

#: The census. A DATE is complete only when every one of these is (R-IV.958(f)).
CENSUS = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")


def _by_date(rows: List[Dict[str, Any]]) -> Dict[str, set]:
    """{session_date: set(tickers)} — so "every census name" is a set comparison, not a count.

    A count would accept eight rows for seven names plus a duplicate.
    """
    out: Dict[str, set] = {}
    for r in rows:
        out.setdefault(r["session_date"].isoformat(), set()).add(r["ticker"])
    return out


def _percentiles(values: List[int]) -> Dict[str, Optional[float]]:
    """mean / median / max over a list of call counts. None on an empty list, never 0.

    Zero would read as "no calls needed" where the truth is "nothing measured" -- the
    fake-healthy reading this register keeps finding.
    """
    if not values:
        return {"n": 0, "mean": None, "median": None, "max": None, "total": None}
    s = sorted(values)
    mid = len(s) // 2
    median = float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0
    return {"n": len(s), "mean": round(sum(s) / len(s), 1), "median": median,
            "max": s[-1], "total": sum(s)}


@router.get("/progress")
async def progress(
    since: Optional[str] = Query(None, description="session_date lower bound, YYYY-MM-DD"),
    until: Optional[str] = Query(None, description="session_date upper bound, YYYY-MM-DD"),
    runs: int = Query(10, ge=1, le=100),
    _auth: Any = Depends(require_api_key),
) -> Dict[str, Any]:
    """Per-ticker-session call counts, the run ledger, and what is still outstanding.

    `calls_per_ticker_session` is grouped by the UW day the work was collected on, so a
    before/after comparison across a deploy is a comparison of two nights rather than of two
    log windows -- and survives the deployment swap that hid last night's figures.
    """
    def _d(v: Optional[str]) -> Optional[date]:
        if not v:
            return None
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(SESSIONS_SQL, _d(since), _d(until))]
        run_rows = [dict(r) for r in await conn.fetch(RUNS_SQL, runs)]

    collected, not_applicable = [], []
    for r in rows:
        if (r.get("stop_reason") or "").startswith(NOT_APPLICABLE_PREFIX):
            not_applicable.append(r)
        else:
            collected.append(r)

    # Grouped by the NIGHT the work happened, which is what "before" and "after" mean here.
    by_night: Dict[str, List[int]] = {}
    for r in collected:
        if not r.get("calls_spent"):
            continue                        # nothing spent on this row this run; not a zero
        ts = r.get("collected_at")
        night = ts.date().isoformat() if isinstance(ts, datetime) else "unknown"
        by_night.setdefault(night, []).append(int(r["calls_spent"]))

    done = [r for r in collected if r.get("exhausted")]
    outstanding = [r for r in collected if not r.get("exhausted")]

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "window": {"since": since, "until": until},
        "ticker_sessions": {
            "rows": len(rows),
            "collected": len(collected),
            "not_applicable": len(not_applicable),
            "exhausted": len(done),
            "outstanding": len(outstanding),
        },
        # The headline figure for R-IV.993(c).
        "calls_per_ticker_session": {
            "all_time": _percentiles([int(r["calls_spent"]) for r in collected
                                      if r.get("calls_spent")]),
            "by_collected_night": {k: _percentiles(v) for k, v in sorted(by_night.items())},
        },
        # RENAMED AND CORRECTED. The first version of this field was called
        # `dates_complete_all_names` and checked NEITHER completeness (reached_floor) nor all
        # names -- it would have reported 22 dates where 16 are provable and 14 are inside
        # QUERY's window. A label that answers a different question than it names is how a
        # confident wrong answer gets made.
        "dates_proved_complete_every_census_name": sorted(
            d for d, names in _by_date(
                [r for r in collected
                 if r.get("exhausted") and r.get("reached_floor")
                 and (r.get("prints_received") or 0) > 0]).items()
            if set(CENSUS) <= names),
        "dates_exhausted_but_floor_NOT_proved": sorted(
            d for d, names in _by_date(
                [r for r in collected
                 if r.get("exhausted") and not r.get("reached_floor")]).items()),
        "outstanding_ticker_sessions": [
            {"ticker": r["ticker"], "session_date": r["session_date"].isoformat(),
             "pages": r["pages_fetched"], "prints": r["prints_received"],
             "calls_spent": r["calls_spent"], "stop_reason": r["stop_reason"]}
            for r in outstanding
        ][:200],
        "runs": [
            {"id": r["id"],
             "uw_day": r["uw_day"].isoformat() if r.get("uw_day") else None,
             "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
             "ended_at": r["ended_at"].isoformat() if r.get("ended_at") else None,
             "calls_spent": r["calls_spent"], "stop_reason": r["stop_reason"]}
            for r in run_rows
        ],
    }


@router.get("/session-detail")
async def session_detail(
    session: str = Query(..., description="session_date, YYYY-MM-DD"),
    _auth: Any = Depends(require_api_key),
) -> Dict[str, Any]:
    """Everything stored about one session, per name — R-IV.1010(b).

    WHAT IS AND IS NOT RECORDED, stated plainly: pages carry `page_no`, `row_count` and
    `fetched_at`, so a walk's extent and timing are recoverable. THERE IS NO per-page run id,
    so "which walk fetched this page" can only be INFERRED by clustering `fetched_at`. That is
    a gap in the instrument, not a fact about the data, and it is named here rather than
    papered over with a confident-looking id.

    RTH is 09:30-16:00 America/New_York, counted from each print's own `executed_at`. The
    earliest print is reported by EXECUTED time, never by which query returned the page --
    that distinction is the one that made "sessions secured" wrong in both directions.
    """
    try:
        sd = date.fromisoformat(session)
    except ValueError:
        return {"error": "session must be YYYY-MM-DD", "got": session}

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        prints = [dict(r) for r in await conn.fetch(SESSION_PRINTS_SQL, sd)]
        pages = [dict(r) for r in await conn.fetch(SESSION_PAGES_SQL, sd)]
        srows = [dict(r) for r in await conn.fetch(SESSION_ROWS_SQL, sd)]

    by_ticker: Dict[str, Any] = {}
    for r in prints:
        by_ticker[r["ticker"]] = {
            "total_rows": int(r["total_rows"] or 0),
            "rth_prints": int(r["rth_prints"] or 0),
            "earliest_print_et": (r["earliest"].astimezone(ET).isoformat()
                                  if r["earliest"] else None),
            "latest_print_et": (r["latest"].astimezone(ET).isoformat()
                                if r["latest"] else None),
            "executed_dates": sorted(set((r["exec_dates"] or []))),
            "pages": [], "session_row": None,
        }
    for p in pages:
        by_ticker.setdefault(p["ticker"], {"pages": [], "session_row": None})["pages"].append({
            "page_no": p["page_no"],
            "row_count": p["row_count"],
            "fetched_at_utc": (p["fetched_at"].astimezone(timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%SZ") if p["fetched_at"] else None),
            "fetched_at_et": (p["fetched_at"].astimezone(ET).isoformat()
                              if p["fetched_at"] else None),
            "page_earliest_et": (p["page_min"].astimezone(ET).isoformat()
                                 if p["page_min"] else None),
        })
    for s_ in srows:
        by_ticker.setdefault(s_["ticker"], {"pages": []})["session_row"] = {
            "pages_fetched": s_["pages_fetched"], "prints_received": s_["prints_received"],
            "exhausted": s_["exhausted"], "reached_floor": s_["reached_floor"],
            "calls_spent": s_["calls_spent"], "stop_reason": s_["stop_reason"],
            "collected_at_utc": (s_["collected_at"].astimezone(timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ")
                                 if s_["collected_at"] else None),
        }
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "session_date": session,
        "basis": ("RTH is 09:30-16:00 America/New_York on each print's own executed_at; "
                  "the earliest print is by EXECUTED time, not by which query returned it "
                  "(convention #39). There is NO per-page run id stored, so walk identity is "
                  "inferable only by clustering fetched_at."),
        "tickers": dict(sorted(by_ticker.items())),
    }


@router.get("/completeness")
async def completeness(_auth: Any = Depends(require_api_key)) -> Dict[str, Any]:
    """Which ROUTE proved each ticker-session complete — R-IV.1005(d).

    `b1` the walk reached a print executed before E 04:00 ET.
    `b2` the walk ENDED BY EXHAUSTION (final page below the cap OBSERVED for that
         ticker-session, never a hardcoded one) and its earliest print is at or before 09:30 ET.
    `SUSPECT` exhausted, but the earliest print is AFTER 09:30 ET -- a short page mid-morning
         on a liquid name suggests truncation, not exhaustion. NOT complete.
    `broken_chain` a page is missing, so neither route may be claimed.

    Read-only. The routes are read back from the same CASE the job writes, never re-derived
    here: two authors of "complete" is the fault R-IV.993(d) closed.
    """
    from jobs.darkpool_backfill import COMPLETENESS_ROUTE_SQL, CORE_NAMES
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(COMPLETENESS_ROUTE_SQL)]

    by_route: Dict[str, int] = {}
    by_date: Dict[str, Dict[str, list]] = {}
    for r in rows:
        by_route[r["route"]] = by_route.get(r["route"], 0) + 1
        by_date.setdefault(r["session_date"].isoformat(), {}).setdefault(
            r["route"], []).append(r["ticker"])
    census = set(CORE_NAMES)
    complete_dates = sorted(
        d for d, routes in by_date.items()
        if census <= set(sum((routes.get(k, []) for k in ("b1", "b2")), [])))
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "definition": ("b1: a print executed before E 04:00 ET. b2: final page below the "
                       "OBSERVED cap and earliest print at or before E 09:30 ET. Sessions "
                       "and thresholds are America/New_York (convention #39)."),
        "by_route": by_route,
        "dates_complete_every_census_name": complete_dates,
        "by_session_date": {k: {kk: sorted(vv) for kk, vv in v.items()}
                            for k, v in sorted(by_date.items())},
        "suspect": [
            {"ticker": r["ticker"], "session_date": r["session_date"].isoformat(),
             "earliest_print": (r["earliest_print"].isoformat()
                                if r["earliest_print"] else None),
             "observed_cap": r["observed_cap"], "last_row_count": r["last_row_count"]}
            for r in rows if r["route"] == "SUSPECT"],
    }


@router.get("/export-manifest")
async def export_manifest(_auth: Any = Depends(require_api_key)) -> Dict[str, Any]:
    """Which ticker-sessions the F: export is ENTITLED to write — R-IV.993(d).

    The export runs on Nick's machine (F:/MANDARAX is a local drive and Railway cannot write
    to it), so it needs this list over HTTP rather than a query of its own. Same filter the
    export already applies -- `exhausted AND prints_received > 0` -- served from ONE place so
    the hub and the exporter cannot disagree about what "complete" means.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(SESSIONS_SQL, None, None)]
    # Same column the job writes and the export reads -- R-IV.993(d). `exhausted` alone
    # put three unproved dates on the permanent archive.
    eligible = [r for r in rows
                if r.get("exhausted") and r.get("reached_floor")
                and (r.get("prints_received") or 0) > 0]
    by_date: Dict[str, List[str]] = {}
    for r in eligible:
        by_date.setdefault(r["session_date"].isoformat(), []).append(r["ticker"])
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        # Stated from ONE place so the response cannot misreport the filter it used.
        "filter": ELIGIBLE_FILTER,
        "ticker_sessions": len(eligible),
        "by_session_date": {k: sorted(v) for k, v in sorted(by_date.items())},
    }
