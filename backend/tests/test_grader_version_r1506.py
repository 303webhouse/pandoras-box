"""R-IV.1506(c) / R-IV.1513(a)3: what stays after the ARTEMIS_SHORT one-shot regrade is removed.

The one-shot (jobs/artemis_regrade_write.py) ran once on a617eca0 (job_runs 21176, 11-21
09:13-09:14Z) and is removed in the next push, per R-IV.1443(b)6. What it left behind is pinned
here:
  * the live grader's SQL is byte-identical to the literal it replaced, plus grader_version;
    and it still grades when the column is missing (it logs, it does not lose the grade);
  * boot no longer schedules the one-shot, and the module is gone;
  * boot still adds signal_outcomes.grader_version and job_runs.detail (057 mirrors them), and
    finish_run without detail runs its old statement.
The snapshot table artemis_regrade_snapshot stays in the database (it is the restore source).
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

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



# ── wiring and schema ───────────────────────────────────────────────────────

def test_boot_no_longer_schedules_the_one_shot():
    src = (_BACKEND / "main.py").read_text(encoding="utf-8")
    assert "artemis_regrade_write" not in src
    assert "run_at_startup" not in src


def test_the_one_shot_module_is_gone():
    assert not (_BACKEND / "jobs" / "artemis_regrade_write.py").exists()

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
