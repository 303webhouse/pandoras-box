-- 056: signals.outcome_source_valid admits 'UNGRADEABLE' (R-IV.1443(c))
--
-- MIRRORS backend/database/outcome_source_check.py, which init_database() runs at boot.
-- Nothing in the app executes migrations/*.sql; this file is the reviewable copy. The list
-- itself lives in OUTCOME_SOURCE_VALUES; keep the two in sync.
--
-- WHY. jobs/outcome_resolver._mark_ungradeable writes outcome_source = 'UNGRADEABLE', and
-- migration 017's list never had it. The first ungradeable row would be refused, stay
-- unresolved, and be retried every cycle. Only widens: no existing row is touched.
--
-- Rollback (only if no row carries the value):
--   SELECT COUNT(*) FROM signals WHERE outcome_source = 'UNGRADEABLE';   -- must be 0
--   then re-run migration 017's DROP/ADD.

BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE signals DROP CONSTRAINT IF EXISTS outcome_source_valid;
ALTER TABLE signals ADD CONSTRAINT outcome_source_valid CHECK (
    outcome_source IS NULL
    OR outcome_source IN (
        'BAR_WALK',
        'ACTUAL_TRADE',
        'COUNTERFACTUAL',
        'EXPIRED',
        'INVALIDATED',
        'PROJECTED_FROM_BAR_WALK',
        'OPTIONS_PNL',
        'FWD_RETURN',
        'COMMITTEE_REVIEW',
        'UNGRADEABLE'
    )
) NOT VALID;
COMMIT;
ALTER TABLE signals VALIDATE CONSTRAINT outcome_source_valid;
