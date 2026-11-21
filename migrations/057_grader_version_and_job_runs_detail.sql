-- 057: signal_outcomes.grader_version and job_runs.detail (R-IV.1443(b)3 and (b)6)
--
-- MIRRORS backend/database/postgres_client.py init_database(), which runs both at boot.
-- Nothing in the app executes migrations/*.sql; this file is the reviewable copy.
--
-- grader_version: every grade score_signals writes from this push on names the grader that
--   produced it (jobs/score_signals.GRADER_VERSION); the ARTEMIS regrade stamps the rows it
--   rewrites with the same value.
-- detail: a run's structured record; the ARTEMIS regrade puts its snapshot hash here.
--
-- Both are metadata-only ADD COLUMNs (no rewrite). Rollback: DROP COLUMN, once nothing reads them.

BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS grader_version TEXT;
COMMIT;

ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS detail JSONB;

-- The ARTEMIS regrade creates its own snapshot table, once, as its first write
-- (jobs/artemis_regrade_write.SNAPSHOT_SQL): artemis_regrade_snapshot, one row per
-- ARTEMIS_SHORT signal_outcomes row with its signals copy. It is the restore source
-- (jobs/artemis_regrade_write.RESTORE_SQL) and is kept.
