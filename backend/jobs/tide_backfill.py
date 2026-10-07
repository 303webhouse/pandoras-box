"""Backfill `market_tide_history` over a span of sessions — R-IV.675(c).

ONE CALL PER SESSION. Measured 2026-10-06: `/api/market/market-tide?date=YYYY-MM-DD` serves a
past session's whole series (81 rows at a 300 s interval), so the cost is the number of sessions
and nothing more. Over `triton_flow_shadow`'s span that is 66 calls, 0.17% of a 40,000/day quota.

THE WRITE IS NOT RE-IMPLEMENTED HERE. It calls `market_tide_sink.persist_series`, the same
function the live warmer uses, so the backfill and the collector cannot drift about what a row
means, what the key is, or how a premium is parsed. What this module owns is only *which
sessions to ask for* and *what to report*.

Idempotent by construction: the sink upserts on `tick_at`, so re-running a session converges.
A session the vendor will not serve is reported as such and is NOT written as an empty success —
the difference between "no tide that day" and "we failed to ask" is the whole point of a sink.

Run:
    python -m jobs.tide_backfill --dsn <postgres dsn> [--from YYYY-MM-DD] [--to YYYY-MM-DD]
    python -m jobs.tide_backfill --dsn <dsn> --from-shadow      # the triton_flow_shadow span
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


async def sessions_from_shadow(conn) -> List[date]:
    """Every ET session that has a `triton_flow_shadow` row. The population's own calendar, not
    a guess at one: a weekday the poller was dark is a session with nothing to align to."""
    rows = await conn.fetch(
        "SELECT DISTINCT (fired_at AT TIME ZONE 'America/New_York')::date AS d "
        "FROM triton_flow_shadow ORDER BY d")
    return [r["d"] for r in rows]


def weekdays_between(a: date, b: date) -> List[date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


async def backfill(dsn: str, sessions: List[date]) -> dict:
    import asyncpg

    from integrations.uw_api import get_market_tide_for_date
    from jobs.market_tide_sink import persist_series

    conn = await asyncpg.connect(dsn)
    try:
        written = 0
        ok, empty, failed = [], [], []
        for i, s in enumerate(sessions, 1):
            iso = s.isoformat()
            try:
                payload = await get_market_tide_for_date(iso)
            except Exception as exc:  # noqa: BLE001
                failed.append((iso, "fetch raised %s" % type(exc).__name__))
                print("  %3d/%d %s  FETCH FAILED %s" % (i, len(sessions), iso,
                                                        type(exc).__name__), flush=True)
                continue
            res = await persist_series(conn, payload, source="backfill")
            if res.get("skipped"):
                # A vendor that serves no rows for a date and a call that failed are DIFFERENT
                # facts, and both are recorded rather than collapsed into "0 written".
                (empty if "no rows" in (res.get("skip_reason") or "") else failed).append(
                    (iso, res.get("skip_reason")))
                print("  %3d/%d %s  SKIP  %s" % (i, len(sessions), iso, res.get("skip_reason")),
                      flush=True)
            else:
                written += res["written"]
                live = res.get("liveness") or {}
                ok.append((iso, res["written"]))
                print("  %3d/%d %s  %3d rows  intervals=%s complete=%s"
                      % (i, len(sessions), iso, res["written"],
                         live.get("distinct_intervals_s"), live.get("complete")), flush=True)
        return {"sessions": len(sessions), "written": written, "ok": len(ok),
                "empty": empty, "failed": failed, "calls_spent": len(sessions)}
    finally:
        await conn.close()


async def _main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", required=True)
    p.add_argument("--from", dest="start")
    p.add_argument("--to", dest="end")
    p.add_argument("--from-shadow", action="store_true")
    a = p.parse_args()

    import asyncpg

    if a.from_shadow:
        conn = await asyncpg.connect(a.dsn)
        try:
            sessions = await sessions_from_shadow(conn)
        finally:
            await conn.close()
    else:
        if not (a.start and a.end):
            print("give --from and --to, or --from-shadow")
            return 2
        sessions = weekdays_between(date.fromisoformat(a.start), date.fromisoformat(a.end))

    print("sessions to ask for: %d (%s .. %s)"
          % (len(sessions), sessions[0] if sessions else "-", sessions[-1] if sessions else "-"))
    res = await backfill(a.dsn, sessions)
    print("\n--- backfill result ---")
    print("  sessions asked : %d  (calls spent: %d)" % (res["sessions"], res["calls_spent"]))
    print("  rows written   : %d" % res["written"])
    print("  sessions ok    : %d" % res["ok"])
    print("  served nothing : %d  %s" % (len(res["empty"]), [e[0] for e in res["empty"]][:12]))
    print("  FAILED         : %d  %s" % (len(res["failed"]), res["failed"][:6]))
    return 0 if not res["failed"] else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(asyncio.run(_main()))
