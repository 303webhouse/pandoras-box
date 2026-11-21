"""The ARTEMIS_SHORT one-shot regrade: the WRITE (R-IV.1443(b), R-IV.1501(d)(e), R-IV.1506(c)).

ONE-SHOT. Started once at boot; refuses if its snapshot table exists. Remove this module and its
boot line in the next push after it succeeds (R-IV.1443(b)6).

WHAT IT WRITES
  * signal_outcomes: the 1,019 ARTEMIS_SHORT rows graded BEFORE the post-fire fix (6c4f943e)
    whose fixed-grader replay differs: outcome, outcome_price, outcome_at (21:00 ET on the
    replay night, when score_signals would have graded it), days_to_outcome, max_favorable,
    max_adverse, grader_version.
  * signals: the copies (outcome_source BAR_WALK or PROJECTED_FROM_BAR_WALK, plus the EXPIRED
    projections of rows in the write set), re-projected from signal_outcomes with
    score_signals' own SET clause, so that the drift view shows no ARTEMIS drift (R-IV.1443(b)2).
  * Untouched: PENDING rows and rows without price data (R-IV.1443(b)4), rows graded after the
    fix (the fixed grader wrote them), COUNTERFACTUAL / NULL-sourced signals rows.

ORDER, each step able to stop the run with nothing written:
  1. advisory lock; refuse if the snapshot table exists.
  2. read rows, fetch unadjusted daily bars, replay night by night to 11-20 with the SAME
     functions the dry run used (artemis_regrade.replay -> score_signals.walk_outcome).
  3. the write set must equal the 11-21 dry run: EXPECTED_COUNT rows and EXPECTED_SHA256 over
     "id|outcome|price|night". Different -> completed_defective, nothing written.
  4. snapshot every ARTEMIS row of BOTH tables into SNAPSHOT_TABLE (its own commit), hash it
     in the database.
  5. one transaction: the signal_outcomes updates (each must still hold the outcome the replay
     started from), the signals re-projection, then the drift check -- any ARTEMIS drift on a
     graded row rolls the whole transaction back.
  6. job_runs: status, rows_touched, detail = {snapshot hash, counts, overnight rows, ...}.

RESTORE (from the snapshot; see RESTORE_SQL).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time as _time
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
JOB_NAME = "artemis_regrade"
SIGNAL_TYPE = "ARTEMIS_SHORT"
SNAPSHOT_TABLE = "artemis_regrade_snapshot"
LOCK_KEY = 1443_1506_0001                  # pg advisory lock; any constant unique to this job

#: 6c4f943e, the post-fire fix. Rows graded before it are the population (R-IV.1501(e)).
FIX_AT = datetime(2026, 10, 17, 9, 1, 26, tzinfo=timezone.utc)
#: The last trading night the 11-21 dry run replayed to.
UNTIL = date(2026, 11, 20)
RUN_HOUR_ET = 21

#: The 11-21 dry run (C:\lane-state\artemis\artemis-dryrun-rows-20261121T080653Z.csv).
EXPECTED_COUNT = 1019
EXPECTED_SHA256 = "a160556823cbba58ba2fe50035a86338f694dd9d295a219a2420c0697ccda4d9"

COPY_SOURCES = ("BAR_WALK", "PROJECTED_FROM_BAR_WALK")
GRADED = ("HIT_T1", "HIT_T2", "STOPPED_OUT")

READ_SQL = """
    SELECT so.id, so.signal_id, so.symbol, so.direction, so.entry, so.stop, so.t1, so.t2,
           so.invalidation_level, so.created_at, so.outcome, so.outcome_at
    FROM signal_outcomes so
    WHERE so.signal_type = $1
    ORDER BY so.id
"""

SNAPSHOT_SQL = f"""
    CREATE TABLE {SNAPSHOT_TABLE} AS
    SELECT so.id AS so_id, so.signal_id,
           so.outcome AS so_outcome, so.outcome_price AS so_outcome_price,
           so.outcome_at AS so_outcome_at, so.days_to_outcome AS so_days_to_outcome,
           so.max_favorable AS so_max_favorable, so.max_adverse AS so_max_adverse,
           so.grader_version AS so_grader_version,
           (s.signal_id IS NOT NULL) AS has_signal,
           s.outcome AS s_outcome, s.outcome_pnl_pct AS s_outcome_pnl_pct,
           s.outcome_resolved_at AS s_outcome_resolved_at, s.outcome_source AS s_outcome_source,
           NOW() AS taken_at
    FROM signal_outcomes so LEFT JOIN signals s ON s.signal_id = so.signal_id
    WHERE so.signal_type = 'ARTEMIS_SHORT'
"""

SNAPSHOT_HASH_SQL = f"""
    SELECT COUNT(*) AS n,
           encode(sha256(convert_to(string_agg(t::text, E'\\n' ORDER BY t.so_id), 'UTF8')), 'hex')
               AS sha256
    FROM {SNAPSHOT_TABLE} t
"""

UPDATE_SO_SQL = """
    UPDATE signal_outcomes so
    SET outcome = w.outcome, outcome_price = w.price, outcome_at = w.at,
        days_to_outcome = w.days, max_favorable = w.mfe, max_adverse = w.mae,
        grader_version = $9
    FROM unnest($1::int[], $2::text[], $3::numeric[], $4::timestamptz[], $5::int[],
                $6::numeric[], $7::numeric[], $8::text[])
         AS w(id, outcome, price, at, days, mfe, mae, old)
    WHERE so.id = w.id AND so.outcome = w.old AND so.signal_type = 'ARTEMIS_SHORT'
"""


def reproject_sql() -> str:
    from jobs.score_signals import signals_projection_set
    return ("""
    UPDATE signals s
    SET """ + signals_projection_set("so.outcome", "so.outcome_at") + """
    FROM signal_outcomes so
    WHERE so.signal_id = s.signal_id
      AND so.signal_type = 'ARTEMIS_SHORT'
      AND so.outcome IN ('HIT_T1', 'HIT_T2', 'STOPPED_OUT')
      AND (s.outcome_source IN ('BAR_WALK', 'PROJECTED_FROM_BAR_WALK')
           OR (s.outcome_source = 'EXPIRED' AND so.id = ANY($1::int[])))
      AND s.outcome IS DISTINCT FROM
          (CASE WHEN so.outcome IN ('HIT_T1', 'HIT_T2') THEN 'WIN' ELSE 'LOSS' END)
    """)


DRIFT_SQL = """
    SELECT COUNT(*) FILTER (WHERE so.outcome <> 'PENDING') AS graded,
           COUNT(*) FILTER (WHERE so.outcome = 'PENDING') AS pending,
           array_agg(so.id ORDER BY so.id) FILTER (WHERE so.outcome = 'PENDING') AS pending_ids
    FROM v_outcome_drift d JOIN signal_outcomes so ON so.signal_id = d.signal_id
    WHERE so.signal_type = 'ARTEMIS_SHORT'
"""

VERSION_COUNT_SQL = "SELECT COUNT(*) FROM signal_outcomes WHERE grader_version IS NOT NULL"

RESTORE_SQL = f"""
-- signal_outcomes back to the snapshot (only rows this job wrote carry its grader_version)
UPDATE signal_outcomes so SET outcome = t.so_outcome, outcome_price = t.so_outcome_price,
    outcome_at = t.so_outcome_at, days_to_outcome = t.so_days_to_outcome,
    max_favorable = t.so_max_favorable, max_adverse = t.so_max_adverse,
    grader_version = t.so_grader_version
FROM {SNAPSHOT_TABLE} t WHERE so.id = t.so_id;
-- signals copies back to the snapshot
UPDATE signals s SET outcome = t.s_outcome, outcome_pnl_pct = t.s_outcome_pnl_pct,
    outcome_resolved_at = t.s_outcome_resolved_at, outcome_source = t.s_outcome_source
FROM {SNAPSHOT_TABLE} t WHERE t.has_signal AND s.signal_id = t.signal_id;
"""


# ── the replay, exactly as the dry run did it ──────────────────────────────────

def fetch_bars_unadjusted(symbols, first: date, until: date) -> Dict[str, Any]:
    """{symbol: DataFrame(High, Low, Close)}, unadjusted daily bars, the dry run's call and its
    CSV round trip (naive midnight index, float64 values). Symbols Yahoo has nothing for are
    simply absent, as in the dry run."""
    import pandas as pd
    import yfinance as yf

    out: Dict[str, Any] = {}
    syms = sorted(symbols)
    for i in range(0, len(syms), 40):
        chunk = syms[i:i + 40]
        df = yf.download(chunk, start=first.isoformat(),
                         end=(until + timedelta(days=1)).isoformat(), interval="1d",
                         auto_adjust=False, actions=False, group_by="ticker",
                         progress=False, threads=False)
        for s in chunk:
            try:
                d = df[s].dropna(subset=["High", "Low", "Close"])
            except KeyError:
                continue
            if d.empty:
                continue
            idx = pd.to_datetime([ts.date().isoformat() for ts in d.index])
            out[s] = pd.DataFrame({"High": d["High"].astype(float).values,
                                   "Low": d["Low"].astype(float).values,
                                   "Close": d["Close"].astype(float).values},
                                  index=idx).sort_index()
        _time.sleep(2)
    return out


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def population(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rows graded BEFORE the fix: a decided outcome and an outcome_at before FIX_AT."""
    return [r for r in rows
            if r.get("outcome") not in (None, "PENDING")
            and r.get("outcome_at") is not None and _aware(r["outcome_at"]) < FIX_AT]


def night_instant(night_iso: str) -> datetime:
    """21:00 ET on the replay night, in UTC: when score_signals would have graded the row."""
    d = date.fromisoformat(night_iso)
    return datetime.combine(d, time(RUN_HOUR_ET, 0), tzinfo=ET).astimezone(timezone.utc)


def write_set(rows: List[Dict[str, Any]], bars: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The rows whose fixed-grader replay differs from what is stored, with the new values."""
    from jobs.artemis_regrade import replay

    out = []
    for r in population(rows):
        b = bars.get(r["symbol"])
        if b is None:
            continue                                   # no price data: keep (R-IV.1443(b)4)
        res = replay(b, r, until=UNTIL, sliced=True)
        if res["outcome"] in ("PENDING",) or res["outcome"] == r["outcome"]:
            continue
        out.append({"id": int(r["id"]), "old": r["outcome"], "outcome": res["outcome"],
                    "price": res["outcome_price"], "night": res["night"],
                    "days": res["days_to_outcome"], "mfe": res["max_favorable"],
                    "mae": res["max_adverse"]})
    out.sort(key=lambda w: w["id"])
    return out


def digest(ws: List[Dict[str, Any]]) -> str:
    """sha256 over "id|outcome|price|night" in id order -- the dry run's form, byte for byte."""
    lines = ["%d|%s|%s|%s" % (w["id"], w["outcome"],
                              ("%.6f" % float(w["price"])) if w["price"] is not None else "",
                              w["night"]) for w in sorted(ws, key=lambda w: w["id"])]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def overnight_ids(rows: List[Dict[str, Any]]) -> List[int]:
    """Rows whose UTC date differs from their ET date (R-IV.1443(b)5)."""
    return sorted(int(r["id"]) for r in rows
                  if _aware(r["created_at"]).date() != _aware(r["created_at"]).astimezone(ET).date())


# ── the run ────────────────────────────────────────────────────────────────────

async def run_once(fetch_bars=None) -> Dict[str, Any]:
    """The whole one-shot. Never raises; every exit closes its job_runs row."""
    from database.postgres_client import get_postgres_client
    from jobs.job_runs import (STATUS_COMPLETED_DEFECTIVE, STATUS_ERROR, STATUS_OK,
                               STATUS_SKIPPED, finish_run, start_run)
    from jobs.score_signals import GRADER_VERSION

    fetch_bars = fetch_bars or fetch_bars_unadjusted
    run_id = await start_run(JOB_NAME, datetime.now(ET).date())
    detail: Dict[str, Any] = {"grader_version": GRADER_VERSION, "until_night": UNTIL.isoformat(),
                              "expected_count": EXPECTED_COUNT, "expected_sha256": EXPECTED_SHA256}
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_KEY):
            await finish_run(run_id, STATUS_SKIPPED, skip_reason="another run holds the lock")
            return {"status": "locked"}
        try:
            if await conn.fetchval("SELECT to_regclass($1::text)", SNAPSHOT_TABLE) is not None:
                await finish_run(run_id, STATUS_SKIPPED,
                                 skip_reason="snapshot %s exists: refusing (R-IV.1443(b)6)"
                                             % SNAPSHOT_TABLE)
                return {"status": "refused: snapshot exists"}

            rows = [dict(r) for r in await conn.fetch(READ_SQL, SIGNAL_TYPE)]
            first = min(_aware(r["created_at"]) for r in rows).date() - timedelta(days=3)
            bars = await asyncio.to_thread(fetch_bars, {r["symbol"] for r in rows}, first, UNTIL)
            ws = write_set(rows, bars)
            got = digest(ws)
            ov = overnight_ids(rows)
            detail.update({"rows": len(rows), "population_pre_fix": len(population(rows)),
                           "symbols_with_bars": len(bars), "write_count": len(ws),
                           "write_sha256": got, "overnight_ids": ov,
                           "overnight_in_write_set": len(set(ov) & {w["id"] for w in ws})})
            if len(ws) != EXPECTED_COUNT or got != EXPECTED_SHA256:
                await finish_run(run_id, STATUS_COMPLETED_DEFECTIVE, rows_touched=0,
                                 error="regrade differs from the 11-21 dry run (%d rows, sha %s);"
                                       " NOTHING written" % (len(ws), got[:12]), detail=detail)
                logger.error("[artemis_regrade] differs from the dry run: %d rows sha %s -- "
                             "nothing written", len(ws), got[:12])
                return {"status": "differs", **detail}

            # 4. snapshot, its own commit, then its hash
            await conn.execute(SNAPSHOT_SQL)
            await conn.execute(f"ALTER TABLE {SNAPSHOT_TABLE} ADD PRIMARY KEY (so_id)")
            snap = await conn.fetchrow(SNAPSHOT_HASH_SQL)
            detail.update({"snapshot_table": SNAPSHOT_TABLE, "snapshot_rows": int(snap["n"]),
                           "snapshot_sha256": snap["sha256"]})

            # 5. one transaction
            ids = [w["id"] for w in ws]
            try:
                async with conn.transaction():
                    await conn.execute("SET LOCAL lock_timeout = '10s'")
                    tag = await conn.execute(
                        UPDATE_SO_SQL, ids, [w["outcome"] for w in ws],
                        [w["price"] for w in ws], [night_instant(w["night"]) for w in ws],
                        [w["days"] for w in ws], [w["mfe"] for w in ws],
                        [w["mae"] for w in ws], [w["old"] for w in ws], GRADER_VERSION)
                    n_so = int(str(tag).split()[-1])
                    if n_so != len(ws):
                        raise RuntimeError("signal_outcomes updated %d of %d (a row moved since "
                                           "the replay read it)" % (n_so, len(ws)))
                    tag2 = await conn.execute(reproject_sql(), ids)
                    n_sig = int(str(tag2).split()[-1])
                    drift = await conn.fetchrow(DRIFT_SQL)
                    if int(drift["graded"] or 0) != 0:
                        raise RuntimeError("drift view still shows %d graded ARTEMIS rows"
                                           % drift["graded"])
            except Exception as exc:                                # noqa: BLE001
                detail["rolled_back"] = "%s: %s" % (type(exc).__name__, exc)
                await finish_run(run_id, STATUS_ERROR, rows_touched=0,
                                 error="ROLLED BACK, nothing written; snapshot kept: %s"
                                       % detail["rolled_back"], detail=detail)
                logger.error("[artemis_regrade] rolled back: %s", detail["rolled_back"])
                return {"status": "rolled back", **detail}

            detail.update({"signal_outcomes_updated": n_so, "signals_reprojected": n_sig,
                           "drift_graded_after": 0,
                           "drift_pending_after": int(drift["pending"] or 0),
                           "drift_pending_ids": list(drift["pending_ids"] or []),
                           "rows_with_grader_version": int(await conn.fetchval(VERSION_COUNT_SQL))})
            await finish_run(run_id, STATUS_OK, rows_touched=n_so, detail=detail)
            logger.info("[artemis_regrade] DONE: %d signal_outcomes, %d signals copies, snapshot "
                        "%s rows sha %s", n_so, n_sig, detail["snapshot_rows"],
                        detail["snapshot_sha256"])
            return {"status": "ok", **detail}
        except Exception as exc:                                    # noqa: BLE001
            detail["error"] = "%s: %s" % (type(exc).__name__, exc)
            await finish_run(run_id, STATUS_ERROR, rows_touched=0, error=detail["error"][:480],
                             detail=detail)
            logger.error("[artemis_regrade] failed: %s", detail["error"])
            return {"status": "error", **detail}
        finally:
            try:
                await conn.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)
            except Exception:                                       # noqa: BLE001
                pass


async def run_at_startup(delay_s: int = 180) -> None:
    """Boot hook: wait for the app to settle, then run once. Catches everything."""
    await asyncio.sleep(delay_s)
    try:
        out = await run_once()
        logger.info("[artemis_regrade] startup run: %s", out.get("status"))
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[artemis_regrade] startup run crashed: %s", exc)
