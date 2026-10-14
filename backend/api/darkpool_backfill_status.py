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
        "dates_complete_all_names": sorted({
            r["session_date"].isoformat() for r in done
            if r.get("prints_received")
        }),
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
        "filter": "exhausted = TRUE AND prints_received > 0",
        "ticker_sessions": len(eligible),
        "by_session_date": {k: sorted(v) for k, v in sorted(by_date.items())},
    }
