"""The post-close shadow grading pass (R-IV.423(c), R-IV.429(b)).

Once per trading session, after the bars settle: for every population, grade each row that
does not yet have all of its grades, write the graded ones (insert-only), record the run, and
rebuild that population's cell report. Zero UW calls; bars come from bars.fetch_daily.

The report is computed in a worker thread: block bootstraps over thousands of rows are CPU
work, and this runs inside the app's event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import GRADER_VERSION
from . import bars as bars_mod
from . import grade as G
from . import report as report_mod
from . import sessions as S
from . import store
from .populations import POPULATIONS, Population

logger = logging.getLogger(__name__)

JOB_NAME = "shadow_grader"
RUN_TIME_ET = (17, 40)
RETRY_EVERY_S = 30 * 60
RETRY_UNTIL_HOUR_ET = 20
PRIOR_SESSIONS_FOR_FETCH = 5      # the anchor's prior close must be in the series


def _methods(pop: Population):
    for h in pop.horizons:
        yield "return", h
    if pop.walk_hold:
        yield "walk", pop.walk_hold


def grade_rows(pop: Population, rows: List[G.ShadowRow], series: Dict[str, Any],
               done: Dict, through: date, run_id: Optional[int]):
    """Pure core of a pass: (insert records, counts)."""
    counts: Counter = Counter()
    records = []
    for row in rows:
        sign = G.direction_sign(row.direction)
        s = series.get(row.ticker)
        for method, h in _methods(pop):
            key = (row.signal_id, method, h)
            if key in done:
                counts["already_graded" if done[key] == bars_mod.BASIS_ID
                       else "basis_differs_not_regraded"] += 1
                continue
            g = (G.grade_return(row, s, h, through) if method == "return"
                 else G.grade_walk(row, s, h, through, time_exit_label=pop.time_exit_label))
            if g.status == G.GRADED:
                records.append(store.grade_record(g, pop.name, sign, row.tags, GRADER_VERSION, run_id))
                counts["graded"] += 1
                for f in g.flags:
                    counts["flag:" + f] += 1
            elif g.status == G.PENDING:
                counts["pending"] += 1
            else:
                counts["ungraded:" + (g.reason or "unknown")] += 1
    return records, counts


async def grade_population(conn, pop: Population, through: date,
                           fetch=bars_mod.fetch_daily) -> Dict[str, Any]:
    since = datetime.combine(pop.since, time(0, 0))           # naive UTC, as the column is
    recs = [dict(r) for r in await conn.fetch(pop.sql(), since)]
    rows = [pop.to_row(r) for r in recs]
    run_id = await store.start_run(conn, "shadow_grade", pop.name, GRADER_VERSION,
                                   {"since": pop.since, "through": through,
                                    "horizons": pop.horizons, "walk_hold": pop.walk_hold,
                                    "entry_kind": pop.entry_kind, "basis_id": bars_mod.BASIS_ID,
                                    "population_note": pop.note})
    try:
        done = await store.existing(conn, pop.name, [r.signal_id for r in rows]) if rows else {}
        need = [r for r in rows
                if any((r.signal_id, m, h) not in done for m, h in _methods(pop))]
        series: Dict[str, Any] = {}
        if need:
            first = min(S.as_utc(r.fired_at).date() for r in need)
            start = S.start_covering(PRIOR_SESSIONS_FOR_FETCH, first)
            series = await asyncio.to_thread(fetch, {r.ticker for r in need}, start, through)
        records, counts = grade_rows(pop, rows, series, done, through, run_id)
        counts["written"] = await store.insert_grades(conn, records)
        counts.update({"population_rows": len(rows), "rows_needing_grades": len(need),
                       "tickers_requested": len({r.ticker for r in need}),
                       "tickers_returned": len(series),
                       "bars_fetched_at": next(iter(series.values())).fetched_at if series else None})
        if counts["written"]:
            graded = await store.load_graded(conn, pop.name)
            results = await asyncio.to_thread(report_mod.build, pop, graded)
            counts["result_rows"] = await store.write_results(conn, run_id, pop.name, results)
        await store.finish_run(conn, run_id, "ok", dict(counts))
        return dict(counts)
    except Exception as exc:
        await store.finish_run(conn, run_id, "error", {}, f"{type(exc).__name__}: {exc}")
        raise


async def run_shadow_grader(session_date: date) -> Dict[str, Any]:
    """One pass over every population. Raises if every population failed."""
    from database.postgres_client import get_postgres_client

    through = S.complete_through()
    pool = await get_postgres_client()
    out: Dict[str, Any] = {"through": through.isoformat()}
    failures = 0
    for name, pop in POPULATIONS.items():
        try:
            async with pool.acquire() as conn:
                out[name] = await grade_population(conn, pop, through)
        except Exception as exc:  # noqa: BLE001 -- one population must not stop the others
            failures += 1
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
            logger.warning("[shadow_grader] %s failed: %s", name, exc)
    if failures == len(POPULATIONS):
        raise RuntimeError("every population failed: %s" % out)
    logger.info("[shadow_grader] pass complete: %s", out)
    return out
