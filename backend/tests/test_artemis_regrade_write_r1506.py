"""R-IV.1443(b) / R-IV.1501(d)(e) / R-IV.1506(c): the ARTEMIS_SHORT one-shot regrade WRITE.

What is pinned, and why each matters:
  * the live grader's SQL is byte-identical to the literal it replaced, plus grader_version;
    and it still grades when the column is missing (it logs, it does not lose the grade);
  * the regrade re-projects onto signals with the live grader's OWN SET clause;
  * the population is "graded before the fix" and the write set is exactly the replay's changes;
  * the digest is the dry run's form;
  * run_once's refusals write NOTHING (lock held, snapshot exists, digest differs), the snapshot
    is taken BEFORE the transaction, and a row that moved or any graded drift ROLLS BACK.

The database is a recording fake (no Postgres here). The SQL itself was checked against the live
schema read-only (PREPARE/EXPLAIN, C:\\lane-state\\artemis\\explain_sql.py), and the replay was
run against live rows and a live Yahoo download (verify_write_set.py): 1,019 rows, the pinned sha.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import os
import pathlib
import sys

import pandas as pd
import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from jobs import artemis_regrade_write as W                           # noqa: E402
from jobs import job_runs                                             # noqa: E402
from jobs import score_signals as S                                   # noqa: E402

#: The live UPDATE as origin/main (391902aa) held it, verbatim.
OLD_LIVE_SQL = """
            WITH updated_so AS (
                UPDATE signal_outcomes
                SET outcome = $1, outcome_price = $2, outcome_at = NOW(),
                    days_to_outcome = $3, max_favorable = $4, max_adverse = $5
                WHERE signal_id = $6
                RETURNING signal_id
            )
            UPDATE signals s
            SET outcome = CASE
                    WHEN $1 IN ('HIT_T1', 'HIT_T2') THEN 'WIN'
                    WHEN $1 = 'STOPPED_OUT' THEN 'LOSS'
                    ELSE NULL
                END,
                outcome_pnl_pct = CASE
                    WHEN $1 IN ('HIT_T1','HIT_T2') AND s.direction = 'LONG'  THEN (s.target_1 - s.entry_price) / s.entry_price * 100
                    WHEN $1 IN ('HIT_T1','HIT_T2') AND s.direction = 'SHORT' THEN (s.entry_price - s.target_1) / s.entry_price * 100
                    WHEN $1 = 'STOPPED_OUT'        AND s.direction = 'LONG'  THEN (s.stop_loss - s.entry_price) / s.entry_price * 100
                    WHEN $1 = 'STOPPED_OUT'        AND s.direction = 'SHORT' THEN (s.entry_price - s.stop_loss) / s.entry_price * 100
                    ELSE NULL
                END,
                outcome_resolved_at = CASE
                    WHEN $1 IN ('HIT_T1','HIT_T2','STOPPED_OUT') THEN NOW()
                    ELSE NULL
                END,
                outcome_source = CASE
                    WHEN $1 IN ('HIT_T1','HIT_T2','STOPPED_OUT') THEN 'PROJECTED_FROM_BAR_WALK'
                    WHEN $1 = 'EXPIRED' THEN 'EXPIRED'
                    WHEN $1 = 'INVALIDATED' THEN 'INVALIDATED'
                    ELSE NULL
                END
            FROM updated_so
            WHERE s.signal_id = updated_so.signal_id
              AND s.outcome_source IS NULL
            """


# ── the live grader ─────────────────────────────────────────────────────────

def test_the_live_sql_is_byte_identical_to_what_it_replaced():
    assert S.LIVE_UPDATE_SQL_UNVERSIONED == OLD_LIVE_SQL


def test_the_live_sql_adds_only_grader_version():
    assert S.LIVE_UPDATE_SQL.replace(", grader_version = $7", "") == OLD_LIVE_SQL
    assert "grader_version = $7" in S.LIVE_UPDATE_SQL


class _LiveConn:
    def __init__(self, missing_column=False):
        self.missing, self.calls = missing_column, []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        if self.missing and "grader_version" in sql:
            raise type("UndefinedColumnError", (Exception,), {})("no column")


class _LivePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        c = self.conn

        class _A:
            async def __aenter__(self):
                return c

            async def __aexit__(self, *a):
                return False
        return _A()


def test_every_new_grade_records_the_grader_version():
    c = _LiveConn()
    asyncio.run(S._update_outcome(_LivePool(c), "SIG1", "HIT_T2", 90.0, 3, 10.0, 2.0))
    assert len(c.calls) == 1
    sql, args = c.calls[0]
    assert sql == S.LIVE_UPDATE_SQL and args[-1] == S.GRADER_VERSION == "score_signals@6c4f943e"
    assert args[:6] == ("HIT_T2", 90.0, 3, 10.0, 2.0, "SIG1")


def test_a_missing_column_still_grades_without_the_version():
    c = _LiveConn(missing_column=True)
    asyncio.run(S._update_outcome(_LivePool(c), "SIG1", "STOPPED_OUT", 105.0, 1, 0.0, 5.0))
    assert [s for s, _ in c.calls] == [S.LIVE_UPDATE_SQL, S.LIVE_UPDATE_SQL_UNVERSIONED]
    assert c.calls[1][1] == ("STOPPED_OUT", 105.0, 1, 0.0, 5.0, "SIG1")


def test_the_regrade_projects_with_the_live_graders_own_clause():
    sql = W.reproject_sql()
    assert S.signals_projection_set("so.outcome", "so.outcome_at") in sql
    # ...and that clause is the live one with only the two expressions substituted.
    assert (S.signals_projection_set("so.outcome", "so.outcome_at")
            .replace("so.outcome_at", "NOW()").replace("so.outcome", "$1")
            == S.signals_projection_set("$1", "NOW()"))


# ── population, write set, digest ───────────────────────────────────────────

FIRE = dt.datetime(2026, 10, 5, 19, 0)          # Mon 15:00 ET, naive UTC as stored


def frame(rows):
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, *_ in rows])
    return pd.DataFrame([r[1:] for r in rows], index=idx, columns=["High", "Low", "Close"])


def row(i, sym, outcome, graded_at, **kw):
    r = {"id": i, "signal_id": "S%d" % i, "symbol": sym, "direction": "SHORT", "entry": 100.0,
         "stop": 105.0, "t1": 95.0, "t2": 90.0, "invalidation_level": None,
         "created_at": FIRE, "outcome": outcome, "outcome_at": graded_at}
    r.update(kw)
    return r


PRE = dt.datetime(2026, 10, 6, 1, 0, tzinfo=dt.timezone.utc)
POST = dt.datetime(2026, 10, 18, 1, 0, tzinfo=dt.timezone.utc)
#: the stop is touched ONLY on the fire day; T1 the day after -> pre-fix STOPPED_OUT, fixed HIT_T1
BARS = {"AAA": frame([("2026-10-05", 106, 99, 100), ("2026-10-06", 101, 94, 94.5)]),
        "BBB": frame([("2026-10-05", 100, 99, 100), ("2026-10-06", 100, 94, 95)])}


def test_population_is_graded_before_the_fix_only():
    rows = [row(1, "AAA", "STOPPED_OUT", PRE), row(2, "AAA", "STOPPED_OUT", POST),
            row(3, "AAA", "PENDING", None), row(4, "AAA", None, None)]
    assert [r["id"] for r in W.population(rows)] == [1]


def test_the_write_set_is_exactly_the_replays_changes():
    rows = [row(1, "AAA", "STOPPED_OUT", PRE),        # changes -> HIT_T1
            row(2, "BBB", "HIT_T1", PRE),             # unchanged
            row(3, "ZZZ", "STOPPED_OUT", PRE),        # no bars: kept
            row(4, "AAA", "STOPPED_OUT", POST)]       # graded after the fix: not the population
    ws = W.write_set(rows, BARS)
    assert [(w["id"], w["old"], w["outcome"], w["night"]) for w in ws] == \
        [(1, "STOPPED_OUT", "HIT_T1", "2026-10-06")]
    assert ws[0]["price"] == 95.0 and ws[0]["days"] == 1


def test_the_digest_is_the_dry_runs_form():
    ws = [{"id": 7, "outcome": "HIT_T2", "price": 90.0, "night": "2026-10-07"},
          {"id": 3, "outcome": "STOPPED_OUT", "price": None, "night": "2026-10-06"}]
    want = hashlib.sha256(b"3|STOPPED_OUT||2026-10-06\n7|HIT_T2|90.000000|2026-10-07").hexdigest()
    assert W.digest(ws) == want


def test_outcome_at_is_21_00_ET_on_the_replay_night():
    assert W.night_instant("2026-10-06") == dt.datetime(2026, 10, 7, 1, 0, tzinfo=dt.timezone.utc)
    assert W.night_instant("2026-03-02") == dt.datetime(2026, 3, 3, 2, 0, tzinfo=dt.timezone.utc)


def test_overnight_rows_are_utc_date_not_et_date():
    late = row(9, "AAA", "STOPPED_OUT", PRE, created_at=dt.datetime(2026, 10, 6, 2, 30))
    assert W.overnight_ids([row(1, "AAA", "STOPPED_OUT", PRE), late]) == [9]


# ── run_once: refusals, order, rollback ─────────────────────────────────────

class _Txn:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.log.append("BEGIN")

    async def __aexit__(self, et, ev, tb):
        self.conn.log.append("ROLLBACK" if et else "COMMIT")
        return False


class _Conn:
    def __init__(self, rows, lock=True, snapshot_exists=False, so_updated=None, drift=0):
        self.rows, self.lock, self.snap = rows, lock, snapshot_exists
        self.so_updated, self.drift, self.log = so_updated, drift, []

    async def fetchval(self, sql, *a):
        if "pg_try_advisory_lock" in sql:
            return self.lock
        if "to_regclass" in sql:
            return "artemis_regrade_snapshot" if self.snap else None
        if "grader_version IS NOT NULL" in sql:
            return 1

    async def fetch(self, sql, *a):
        self.log.append("READ")
        return self.rows

    async def fetchrow(self, sql, *a):
        if "sha256" in sql:
            self.log.append("HASH")
            return {"n": len(self.rows), "sha256": "f" * 64}
        if "v_outcome_drift" in sql:
            self.log.append("DRIFT")
            return {"graded": self.drift, "pending": 2, "pending_ids": [30379, 30381]}

    async def execute(self, sql, *a):
        if sql.lstrip().startswith("CREATE TABLE"):
            self.log.append("SNAPSHOT")
        elif "UPDATE signal_outcomes" in sql:
            self.log.append("UPDATE_SO")
            n = self.so_updated if self.so_updated is not None else len(a[0])
            return "UPDATE %d" % n
        elif sql.lstrip().startswith("UPDATE signals"):
            self.log.append("REPROJECT")
            return "UPDATE 1"
        elif "advisory_unlock" in sql:
            self.log.append("UNLOCK")
        return "OK"

    def transaction(self):
        return _Txn(self)


def _run(conn, expected=None, monkeypatch=None):
    import database.postgres_client as pg

    finished = []

    class _P:
        def acquire(self):
            class _A:
                async def __aenter__(self_):
                    return conn

                async def __aexit__(self_, *a):
                    return False
            return _A()

    async def pool():
        return _P()

    async def start(job, sd):
        return 1

    async def finish(run_id, status, **kw):
        finished.append((status, kw))

    saved = (pg.get_postgres_client, job_runs.start_run, job_runs.finish_run,
             W.EXPECTED_COUNT, W.EXPECTED_SHA256)
    pg.get_postgres_client, job_runs.start_run, job_runs.finish_run = pool, start, finish
    if expected:
        W.EXPECTED_COUNT, W.EXPECTED_SHA256 = expected
    try:
        out = asyncio.run(W.run_once(fetch_bars=lambda syms, first, until: BARS))
    finally:
        (pg.get_postgres_client, job_runs.start_run, job_runs.finish_run,
         W.EXPECTED_COUNT, W.EXPECTED_SHA256) = saved
    return out, finished


ROWS = [row(1, "AAA", "STOPPED_OUT", PRE), row(2, "BBB", "HIT_T1", PRE)]
PIN = (1, W.digest(W.write_set(ROWS, BARS)))
WRITES = {"SNAPSHOT", "UPDATE_SO", "REPROJECT"}


def test_a_held_lock_writes_nothing():
    c = _Conn(ROWS, lock=False)
    out, fin = _run(c, PIN)
    assert out["status"] == "locked" and not WRITES & set(c.log)
    assert fin[0][0] == job_runs.STATUS_SKIPPED


def test_an_existing_snapshot_refuses_and_writes_nothing():
    c = _Conn(ROWS, snapshot_exists=True)
    out, fin = _run(c, PIN)
    assert out["status"].startswith("refused") and not WRITES & set(c.log)
    assert fin[0][0] == job_runs.STATUS_SKIPPED and "exists" in fin[0][1]["skip_reason"]


def test_a_regrade_that_differs_from_the_dry_run_writes_nothing():
    c = _Conn(ROWS)
    out, fin = _run(c, (1, "0" * 64))                  # the real pin would not match these rows
    assert out["status"] == "differs" and not WRITES & set(c.log)
    assert fin[0][0] == job_runs.STATUS_COMPLETED_DEFECTIVE and "NOTHING written" in fin[0][1]["error"]


def test_the_happy_path_snapshots_first_then_one_transaction():
    c = _Conn(ROWS)
    out, fin = _run(c, PIN)
    assert out["status"] == "ok", out
    assert c.log == ["READ", "SNAPSHOT", "HASH", "BEGIN", "UPDATE_SO", "REPROJECT", "DRIFT",
                     "COMMIT", "UNLOCK"]
    status, kw = fin[0]
    assert status == job_runs.STATUS_OK and kw["rows_touched"] == 1
    d = kw["detail"]
    assert d["snapshot_sha256"] == "f" * 64 and d["snapshot_rows"] == 2
    assert d["drift_graded_after"] == 0 and d["drift_pending_ids"] == [30379, 30381]
    assert d["write_count"] == 1 and "overnight_ids" in d


def test_a_row_that_moved_rolls_everything_back():
    c = _Conn(ROWS, so_updated=0)
    out, fin = _run(c, PIN)
    assert out["status"] == "rolled back" and "ROLLBACK" in c.log and "COMMIT" not in c.log
    assert fin[0][0] == job_runs.STATUS_ERROR and "ROLLED BACK" in fin[0][1]["error"]


def test_graded_drift_after_the_write_rolls_everything_back():
    c = _Conn(ROWS, drift=3)
    out, fin = _run(c, PIN)
    assert out["status"] == "rolled back" and c.log[-2:] == ["ROLLBACK", "UNLOCK"]
    assert "drift" in fin[0][1]["error"]


def test_the_pin_is_the_11_21_dry_run():
    assert (W.EXPECTED_COUNT, W.EXPECTED_SHA256) == (
        1019, "a160556823cbba58ba2fe50035a86338f694dd9d295a219a2420c0697ccda4d9")
    assert W.UNTIL == dt.date(2026, 11, 20)


# ── wiring and schema ───────────────────────────────────────────────────────

def test_boot_schedules_the_one_shot():
    src = (_BACKEND / "main.py").read_text(encoding="utf-8")
    assert "asyncio.create_task(_artemis_regrade.run_at_startup())" in src


def test_boot_adds_both_columns_and_057_mirrors_them():
    pg = (_BACKEND / "database" / "postgres_client.py").read_text(encoding="utf-8")
    assert "ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS grader_version TEXT" in pg
    assert "ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS detail JSONB" in pg
    mig = (_BACKEND.parent / "migrations" / "057_grader_version_and_job_runs_detail.sql"
           ).read_text(encoding="utf-8")
    assert "grader_version TEXT" in mig and "detail JSONB" in mig


def test_finish_run_without_detail_runs_its_old_statement():
    import database.postgres_client as pg
    seen = []

    class _C:
        async def execute(self, sql, *a):
            seen.append((sql, a))

    class _P:
        def acquire(self):
            class _A:
                async def __aenter__(self_):
                    return _C()

                async def __aexit__(self_, *a):
                    return False
            return _A()

    async def pool():
        return _P()

    real = pg.get_postgres_client
    pg.get_postgres_client = pool
    try:
        asyncio.run(job_runs.finish_run(5, "ok", rows_touched=1))
        asyncio.run(job_runs.finish_run(6, "ok", rows_touched=1, detail={"k": 1}))
    finally:
        pg.get_postgres_client = real
    assert "detail" not in seen[0][0] and len(seen[0][1]) == 5
    assert "detail = $6::jsonb" in seen[1][0] and seen[1][1][-1] == '{"k": 1}'
