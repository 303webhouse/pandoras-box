"""Triton Amendment 4(e) — fresh-grade one cohort, append versions, touch nothing else.

    python -m jobs.triton_fresh_grade --cohort W1
    python -m jobs.triton_fresh_grade --ids 460533,461002
    python -m jobs.triton_fresh_grade --cohort W1 --plan      (measure, write nothing)

WHAT THIS COMMAND MAY WRITE, and it is a short list:

  * `triton_grade_versions` — one appended row per graded row. Nothing is updated.
  * `triton_session_bar_attempts` — the failed-request counter Amendment 4(c) needs.

It does NOT touch `triton_flow_shadow`. Not its returns, not `provider`, and above
all not `graded_at`: 4(e) says the grades made before Amendment 4 are KEPT and used
by no read, so overwriting them would destroy the very comparison that shows what
the substitution did. The read consumes the appended versions and names them.

THE THREE REQUESTS, HERE VERSUS IN THE NIGHTLY PASS. 4(c) calls a bar missing only
after three separate requests fail. The nightly grader counts one per pass, which is
right for a job that has tomorrow. This command has to reach a verdict *immediately
before a read* (4(e)), so it makes the attempts itself — `--attempts` separate
fetches, each a real vendor round trip, each recorded — and only then names a gap.
Same threshold, same counter, and the verdict is never reached on one failure.

Amendment 4(b) is enforced by construction: every horizon close comes from
`close_on_session`, which cannot substitute, and the session it came from is written
beside the figure. A horizon with no bar is written as NULL with its session listed
in `session_gaps`, never as a neighbour's close.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from jobs.triton_shadow_grader import (
    HORIZONS, SESSION_GAP, SESSION_GAP_MIN_ATTEMPTS, SESSION_BAR_RETRYING,
    HORIZON_NOT_A_SESSION, _count_bar_absence, _dir_adj, _gap_text,
    _bounded_lookback, _split_ex_dates, spans_corporate_action,
)
from jobs.triton_shadow_common import (
    PROVIDER_NONE, cohort_bounds, cohort_of, close_on_session,
    fetch_r_close_index, horizon_is_session, nth_trading_day, triton_row_pinned, _f,
)

logger = logging.getLogger("triton_fresh_grade")

OUT_OF_WINDOW = "out_of_window"
NOT_A_SESSION_FIRE = "fire_date_not_a_session"


async def _select(conn, row_ids: Optional[List[int]], cohort: Optional[str],
                  limit: Optional[int]):
    if row_ids:
        return await conn.fetch(
            """
            SELECT id, ticker, direction, fired_at, spot_at_fire
              FROM triton_flow_shadow
             WHERE id = ANY($1::int[])
             ORDER BY id
            """,
            row_ids,
        )
    lo, hi = cohort_bounds(cohort)
    return await conn.fetch(
        """
        SELECT id, ticker, direction, fired_at, spot_at_fire
          FROM triton_flow_shadow
         WHERE fired_at >= $1::date
           AND fired_at < ($2::date + 1)
           AND (instrument_class IS NULL OR instrument_class <> 'cash_settled_index')
         ORDER BY fired_at, id
         LIMIT $3
        """,
        lo, hi, limit or 100000,
    )


async def _series_with_attempts(ticker: str, lookback: int, wanted: List[date],
                                pool, attempts: int):
    """Fetch the pinned series, re-requesting while any wanted session is absent.

    Returns (idx, provider, tries). Each pass through the loop is a separate vendor
    request and, for every session still absent at the end of it, one recorded failed
    request — so the counter and the fetch log cannot disagree about how many were
    made.
    """
    idx: Dict[date, float] = {}
    provider = PROVIDER_NONE
    tries = 0
    for _ in range(max(1, attempts)):
        tries += 1
        got, prov = await fetch_r_close_index(ticker, lookback, pinned=True)
        if got:
            idx = got
            provider = prov
        missing = [d for d in wanted if d not in idx]
        for d in missing:
            await _count_bar_absence(pool, ticker, d, provider or PROVIDER_NONE)
        if not missing:
            break
    return idx, provider, tries


async def fresh_grade(*, row_ids: Optional[List[int]] = None,
                      cohort: Optional[str] = None,
                      limit: Optional[int] = None,
                      attempts: int = SESSION_GAP_MIN_ATTEMPTS,
                      plan: bool = False) -> Dict[str, Any]:
    """Grade the named rows afresh under Amendment 4(b)/(c). Never raises."""
    from database.postgres_client import get_postgres_client

    out: Dict[str, Any] = {
        "cohort": cohort, "requested_ids": row_ids, "plan": plan,
        "selected": 0, "versions_written": 0, "skipped": {},
        "rows": [], "session_gaps": [], "attempts_each": attempts,
    }

    def _skip(reason: str) -> None:
        out["skipped"][reason] = out["skipped"].get(reason, 0) + 1

    if not row_ids and not cohort:
        out["error"] = "name a --cohort or --ids"
        return out
    if cohort and cohort_bounds(cohort) is None:
        out["error"] = "unknown cohort %r (W1..W7)" % cohort
        return out

    pool = await get_postgres_client()
    if not pool:
        out["error"] = "no database pool"
        return out

    async with pool.acquire() as conn:
        rows = await _select(conn, row_ids, cohort, limit)
    out["selected"] = len(rows)
    if not rows:
        return out

    today = datetime.now(timezone.utc).date()
    by_ticker: Dict[str, list] = {}
    for r in rows:
        fired = r["fired_at"]
        fd = fired.date() if hasattr(fired, "date") else fired
        # Amendment 4(c) is window-scoped. An out-of-window row belongs to the open
        # UW-first path with its neighbour probe intact, so grading it here would
        # apply a rule it was never registered under.
        if not triton_row_pinned(fired):
            _skip(OUT_OF_WINDOW)
            continue
        if horizon_is_session(fd) is not True:
            _skip(NOT_A_SESSION_FIRE)
            continue
        by_ticker.setdefault((r["ticker"] or "").upper(), []).append((r, fd))

    for ticker, group in sorted(by_ticker.items()):
        if not ticker:
            _skip("blank_ticker")
            continue
        ex_dates = await asyncio.to_thread(_split_ex_dates, ticker)
        if ex_dates is None:
            _skip("corporate_action_calendar_unavailable")
            continue
        keep = [(r, fd) for r, fd in group
                if not spans_corporate_action(ex_dates, fd, today)]
        for _ in range(len(group) - len(keep)):
            _skip("held_corporate_action")
        if not keep:
            continue

        earliest = min(fd for _, fd in keep)
        lookback = _bounded_lookback(earliest, today)
        # Every session this cohort's rows will ask for, so one fetch cycle serves
        # them all and the retry decision is made against the whole demand.
        wanted = sorted({
            d for _, fd in keep
            for d in [fd] + [nth_trading_day(fd, k) for k in HORIZONS]
            if d <= today
        })
        idx, provider, tries = await _series_with_attempts(
            ticker, lookback, wanted, pool, attempts)
        if not idx:
            _skip("no_regular_session_bars")
            continue

        for r, fd in keep:
            direction = r["direction"] or "BULL"
            entry = _f(r["spot_at_fire"])
            entry_session = fd if (entry and entry > 0) else None
            if not entry or entry <= 0:
                entry = close_on_session(idx, fd)
                entry_session = fd if entry else None
            if not entry or entry <= 0:
                _skip("no_entry_price")
                continue

            vals = {k: None for k in HORIZONS}
            sess = {k: None for k in HORIZONS}
            gaps: Dict[int, date] = {}
            for k in HORIZONS:
                tgt = nth_trading_day(fd, k)
                if tgt > today:
                    continue                      # horizon not reached yet
                if horizon_is_session(tgt) is not True:
                    gaps[k] = tgt
                    _skip(HORIZON_NOT_A_SESSION)
                    continue
                close_k = close_on_session(idx, tgt)
                if close_k is None:
                    gaps[k] = tgt
                    _skip(SESSION_GAP if tries >= attempts else SESSION_BAR_RETRYING)
                    continue
                vals[k] = _dir_adj(entry, close_k, direction)
                sess[k] = tgt

            record = {
                "row_id": r["id"], "ticker": ticker, "cohort": cohort_of(fd),
                "fired_session": str(fd), "provider": provider,
                "entry_session": str(entry_session) if entry_session else None,
                "fetch_attempts": tries,
                **{"fwd_ret_%dd" % k: vals[k] for k in HORIZONS},
                **{"session_%dd" % k: (str(sess[k]) if sess[k] else None)
                   for k in HORIZONS},
                "session_gaps": _gap_text(gaps),
            }
            out["rows"].append(record)
            for k, d in gaps.items():
                out["session_gaps"].append({
                    "row_id": r["id"], "ticker": ticker, "horizon": "%dd" % k,
                    "session": str(d),
                    "class": SESSION_GAP if tries >= attempts else SESSION_BAR_RETRYING,
                })

            if plan:
                continue
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO triton_grade_versions
                        (row_id, version, fwd_ret_1d, fwd_ret_3d, fwd_ret_5d,
                         provider, pinned, entry_session,
                         session_1d, session_3d, session_5d, session_gaps)
                    SELECT $1, COALESCE(MAX(version), 0) + 1, $2, $3, $4, $5, TRUE,
                           $6, $7, $8, $9, $10
                    FROM triton_grade_versions WHERE row_id = $1
                    """,
                    r["id"], vals[1], vals[3], vals[5], provider,
                    entry_session, sess[1], sess[3], sess[5], _gap_text(gaps),
                )
            out["versions_written"] += 1

    return out


def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="triton_fresh_grade",
        description="Amendment 4(e): grade a Triton cohort afresh and append versions.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cohort", help="W1..W7")
    g.add_argument("--ids", help="comma-separated triton_flow_shadow ids")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--attempts", type=int, default=SESSION_GAP_MIN_ATTEMPTS,
                    help="separate vendor requests before a bar is called missing")
    ap.add_argument("--plan", action="store_true",
                    help="measure and print; write no versions")
    a = ap.parse_args()

    ids = None
    if a.ids:
        ids = [int(x) for x in a.ids.replace(" ", "").split(",") if x]

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s:%(name)s:%(message)s")
    res = asyncio.run(fresh_grade(row_ids=ids, cohort=a.cohort, limit=a.limit,
                                  attempts=a.attempts, plan=a.plan))

    import json
    print(json.dumps(res, indent=2, default=str))
    return 0 if not res.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
