"""R-IV.1073(c) — UW IV term-structure backfill for the 8 census names, 2026-09-01 → 09-24.

APPROVED SCOPE, and the guard below is the scope rather than a comment about it:

    8 census names (R-IV.958(f)) x 17 trading sessions = 136 calls
    funded from the 12,000 FOREIGN RESERVE, via the `iv_term_backfill` tag (165)
    NOT from `iv_snapshot` (250/day, DAILY_BUDGET, measured peak 208)
    NOT from `darkpool_collector` or `triton_flow_shadow` -- both at their ceilings
    PRE-2026-09-25 DATES ONLY. A reserve date is never requested.

WHY THE DATE GUARD IS A HARD REFUSAL AND NOT A RANGE FILTER. The reserve window
(2026-09-25 → 10-09) is the sealed TRITON-R holdout that R-IV.1064(a) pulls and
R-IV.1073(d) says nobody analyses before step 8. Fetching one of those dates here would put
holdout-window data in a table this lane reads freely -- and a filter that merely *skips* such
a date leaves the next caller free to pass one. So `ceiling_date` is asserted on every single
request, and a violation raises rather than warns.

Storage reuses `jobs/iv_snapshot`'s DDL, UPSERT, summarize and PROVIDER: that module is the one
author of `iv_snapshots`, and a backfill writing its own near-identical schema is how a table
ends up with two definitions. Only the SCOPE differs, because the scope is this ruling's.

Reports COUNTS ONLY. No IV value, no price, is printed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "backend"))

#: R-IV.958(f)'s census universe. Eight names, stated here because this backfill's scope is
#: the ruling's and not `iv_snapshot`'s ~100-name nightly universe.
CENSUS = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")

#: The first date this backfill may NOT touch. Everything from here on is the sealed reserve
#: window that R-IV.1064(a) pulls and nobody analyses before step 8.
RESERVE_FIRST_DATE = date(2026, 9, 25)

WINDOW_START = date(2026, 9, 1)
WINDOW_END = date(2026, 9, 24)

CALLER_TAG = "iv_term_backfill"


class ReserveDateRequested(RuntimeError):
    """A caller asked for a date inside the sealed reserve window."""


def assert_not_reserve(session: date) -> None:
    """RAISE on any date at or after the reserve window's first day.

    Asserted per request, not once per run: a per-run check passes while a loop that computes
    its own dates walks straight past it.
    """
    if session >= RESERVE_FIRST_DATE:
        raise ReserveDateRequested(
            "refusing %s: the sealed reserve window begins %s and this backfill is pre-%s only "
            "(R-IV.1073(c))" % (session, RESERVE_FIRST_DATE, RESERVE_FIRST_DATE))


def sessions() -> list:
    """The trading sessions in the approved window, from the exchange calendar."""
    from stable_engine.market_calendar import is_trading_day

    out, d = [], WINDOW_START
    while d <= WINDOW_END:
        if is_trading_day(d):
            assert_not_reserve(d)
            out.append(d)
        d += timedelta(days=1)
    return out


async def run(dry_run: bool = False) -> dict:
    from integrations.uw_api import get_iv_term_structure
    from integrations.uw_governor import UWUnavailable, quota_for
    from jobs.iv_snapshot import DDL, PROVIDER, UPSERT, summarize

    quota, tier = quota_for(CALLER_TAG)
    days = sessions()
    planned = len(days) * len(CENSUS)
    print("caller tag        : %s  quota=%d tier=%s" % (CALLER_TAG, quota, tier))
    print("window            : %s -> %s  (%d sessions)" % (WINDOW_START, WINDOW_END, len(days)))
    print("names             : %s" % ", ".join(CENSUS))
    print("planned calls     : %d" % planned)
    print("reserve guard     : refusing anything >= %s" % RESERVE_FIRST_DATE)
    if planned > quota:
        raise RuntimeError("planned %d calls exceeds the %s quota of %d"
                           % (planned, CALLER_TAG, quota))
    if dry_run:
        return {"dry_run": True, "planned_calls": planned, "sessions": len(days)}

    from database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    tally = {"calls": 0, "rows_written": 0, "no_live_iv": 0, "unparseable": 0,
             "refused": 0, "already_present": 0}
    per_session = {}
    async with pool.acquire() as conn:
        await conn.execute(DDL)

        # RESUME, because the first run was blocked mid-way by the off-hours haircut and a
        # retry that re-fetched what it already had would spend 41 reserve calls to learn
        # nothing. Reads which (ticker, session) pairs are already stored for this provider
        # and skips them, so a resume costs exactly the calls still owed.
        have = set()
        try:
            rows = await conn.fetch(
                "SELECT ticker, session_date FROM iv_snapshots"
                " WHERE provider = $1 AND session_date BETWEEN $2 AND $3",
                PROVIDER, WINDOW_START, WINDOW_END)
            have = {(r["ticker"], r["session_date"]) for r in rows}
        except Exception as exc:                                    # noqa: BLE001
            # NAMED. An unreadable resume set is not an empty one: treating it as empty would
            # re-fetch the whole window, which is the waste this block exists to prevent.
            print("  resume set unreadable (%s); proceeding as if nothing is stored"
                  % type(exc).__name__)
        tally["already_present"] = len(have)
        if have:
            print("already stored in this window: %d pair(s) -- skipping those" % len(have))

        for session in days:
            assert_not_reserve(session)              # again, per session
            w = e = f = 0
            for ticker in CENSUS:
                if (ticker, session) in have:
                    continue
                body = await get_iv_term_structure(ticker, session.isoformat(),
                                                   caller=CALLER_TAG)
                tally["calls"] += 1
                if isinstance(body, UWUnavailable):
                    # The governor refused. STOP -- continuing would spend the rest of the
                    # reserve on calls that cannot land, and a partial day silently stored is
                    # worse than a named stop.
                    tally["refused"] += 1
                    print("  GOVERNOR REFUSED at %s %s (%s) after %d calls"
                          % (session, ticker, getattr(body, "reason", "?"), tally["calls"]))
                    return {**tally, "per_session": per_session, "stopped_early": True}
                data = body.get("data") if isinstance(body, dict) else None
                if not isinstance(data, list):
                    f += 1
                    tally["unparseable"] += 1
                    continue
                s = summarize(data, session)
                if s["iv_near"] is None:
                    e += 1
                    tally["no_live_iv"] += 1
                await conn.execute(UPSERT, ticker, session, s["near_expiry"], s["near_dte"],
                                   s["iv_near"], s["iv_30d"], s["iv_30d_method"],
                                   json.dumps(body), PROVIDER)
                w += 1
                tally["rows_written"] += 1
            per_session[session.isoformat()] = {"written": w, "no_live_iv": e, "unparseable": f}
            print("  %s  written=%d no_live_iv=%d unparseable=%d" % (session, w, e, f))
    return {**tally, "per_session": per_session, "stopped_early": False}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="plan and check the guard; issue no calls")
    args = ap.parse_args()
    out = asyncio.run(run(dry_run=args.dry_run))
    print("\n=== COUNTS ONLY ===")
    print(json.dumps({k: v for k, v in out.items() if k != "per_session"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
