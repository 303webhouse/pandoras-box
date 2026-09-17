"""The post-close shadow grading pass (R-IV.423(c), R-IV.429(b)).

Once per trading session, after the bars settle: for every population, grade each row that
does not yet have all of its grades, write the graded ones (insert-only), record the run, and
rebuild that population's cell report. Zero UW calls; bars come from bars.fetch_daily.

The report is computed in a worker thread: block bootstraps over thousands of rows are CPU
work, and this runs inside the app's event loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import GRADER_VERSION
from . import bars as bars_mod
from . import grade as G
from . import independent
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
    for hold in pop.walk_holds:
        yield "walk", hold


def grade_rows(pop: Population, rows: List[G.ShadowRow], series: Dict[str, Any],
               done: Dict, held_keys: set, through: date):
    """Pure core of a pass: ([(row, sign, grade)] for every GRADED result, counts)."""
    counts: Counter = Counter()
    graded = []
    for row in rows:
        sign = G.direction_sign(row.direction)
        s = series.get(row.ticker)
        for method, h in _methods(pop):
            key = (row.signal_id, method, h)
            if key in held_keys:
                counts["held_earlier"] += 1
                continue
            if key in done:
                counts["already_graded" if done[key] == bars_mod.BASIS_ID
                       else "basis_differs_not_regraded"] += 1
                continue
            g = (G.grade_return(row, s, h, through) if method == "return"
                 else G.grade_walk(row, s, h, through, time_exit_label=pop.time_exit_label))
            if g.status == G.GRADED:
                graded.append((row, sign, g))
            elif g.status == G.PENDING:
                counts["pending"] += 1
            else:
                counts["ungraded:" + (g.reason or "unknown")] += 1
    return graded, counts


def _rotation(tickers, through: date):
    """A daily-rotating order, so tickers UW never covers cannot hold the same slots forever."""
    return sorted(tickers, key=lambda t: hashlib.md5(f"{t}|{through}".encode()).hexdigest())


async def check_independent(pop: Population, graded, series: Dict[str, Any], counts: Counter,
                            through: date, run_id: Optional[int],
                            fetch_uw=independent.fetch_uw_closes):
    """R-IV.432(e). Returns (grade records to write, hold records). A row whose window spans a
    calendar event is written only if the second vendor agrees."""
    needs = [x for x in graded if independent.spans_event(x[2])]
    tickers = _rotation({row.ticker for row, _, _ in needs}, through)
    allowed = set(tickers[:independent.MAX_TICKERS_PER_PASS])
    counts["independent_tickers"] = len(allowed)
    counts["independent_tickers_deferred"] = len(tickers) - len(allowed)
    uw: Dict[str, Any] = {}
    for t in sorted(allowed):
        start = independent.fetch_start([g for row, _, g in needs if row.ticker == t])
        uw[t] = await fetch_uw(t, start)

    writes, holds = [], []
    for row, sign, g in graded:
        if independent.spans_event(g):
            if row.ticker not in allowed:
                counts["independent_deferred"] += 1
                continue
            detail = independent.compare(g, series[row.ticker], uw.get(row.ticker))
            if detail["verdict"] == "unavailable":
                counts["independent_unavailable"] += 1
                continue
            if detail["verdict"] == "disagree":
                holds.append(store.hold_record(g, pop.name, "independent_price_disagrees", detail,
                                               row.tags, GRADER_VERSION, run_id))
                counts["held:independent_price_disagrees"] += 1
                continue
            g.basis["independent"] = detail
            g.flags.append("independent_agrees")
        writes.append(store.grade_record(g, pop.name, sign, row.tags, GRADER_VERSION, run_id))
        counts["graded"] += 1
        for f in g.flags:
            counts["flag:" + f] += 1
    return writes, holds


async def grade_population(conn, pop: Population, through: date,
                           fetch=bars_mod.fetch_daily,
                           fetch_uw=independent.fetch_uw_closes) -> Dict[str, Any]:
    since = datetime.combine(pop.since, time(0, 0))           # naive UTC, as the column is
    recs = [dict(r) for r in await conn.fetch(pop.sql(), since)]
    rows = [pop.to_row(r) for r in recs]
    run_id = await store.start_run(conn, "shadow_grade", pop.name, GRADER_VERSION,
                                   {"since": pop.since, "through": through,
                                    "horizons": pop.horizons, "walk_holds": pop.walk_holds,
                                    "entry_kind": pop.entry_kind, "basis_id": bars_mod.BASIS_ID,
                                    "independent_vendor": independent.VENDOR,
                                    "independent_tolerance": independent.AGREE_TOL,
                                    "population_note": pop.note})
    try:
        ids = [r.signal_id for r in rows]
        done = await store.existing(conn, pop.name, ids) if rows else {}
        held_keys = await store.held(conn, pop.name, ids, bars_mod.BASIS_ID) if rows else set()
        need = [r for r in rows
                if any((r.signal_id, m, h) not in done and (r.signal_id, m, h) not in held_keys
                       for m, h in _methods(pop))]
        series: Dict[str, Any] = {}
        if need:
            first = min(S.as_utc(r.fired_at).date() for r in need)
            start = S.start_covering(PRIOR_SESSIONS_FOR_FETCH, first)
            series = await asyncio.to_thread(fetch, {r.ticker for r in need}, start, through)
        graded, counts = grade_rows(pop, rows, series, done, held_keys, through)
        writes, holds = await check_independent(pop, graded, series, counts, through, run_id,
                                                fetch_uw)
        counts["written"] = await store.insert_grades(conn, writes)
        counts["holds_written"] = await store.insert_holds(conn, holds)
        counts.update({"population_rows": len(rows), "rows_needing_grades": len(need),
                       "tickers_requested": len({r.ticker for r in need}),
                       "tickers_returned": len(series),
                       "bars_fetched_at": next(iter(series.values())).fetched_at if series else None})
        if counts["written"] or counts["holds_written"]:
            graded_rows = await store.load_graded(conn, pop.name)
            held_rows = await store.load_holds(conn, pop.name)
            results = await asyncio.to_thread(report_mod.build, pop, graded_rows, held_rows)
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
