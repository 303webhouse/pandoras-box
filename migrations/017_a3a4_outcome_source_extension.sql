-- Migration 017: extend outcome_source_valid CHECK on signals
-- Adds OPTIONS_PNL, FWD_RETURN, COMMITTEE_REVIEW to the allowed set.
-- Postgres CHECK constraints cannot be altered in-place — must drop and recreate.
-- No existing rows are touched; only the allowed-value set widens.
--
-- Rollback:
--   Before rolling back, confirm no rows have the new values:
--   SELECT outcome_source, COUNT(*) FROM signals
--     WHERE outcome_source IN ('OPTIONS_PNL','FWD_RETURN','COMMITTEE_REVIEW')
--     GROUP BY 1;
--   If zero rows: proceed to rollback.
--   ALTER TABLE signals DROP CONSTRAINT IF EXISTS outcome_source_valid;
--   ALTER TABLE signals ADD CONSTRAINT outcome_source_valid CHECK (
--     outcome_source IS NULL OR outcome_source IN (
--       'BAR_WALK','ACTUAL_TRADE','COUNTERFACTUAL',
--       'EXPIRED','INVALIDATED','PROJECTED_FROM_BAR_WALK'
--     )
--   );

BEGIN;

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
        'OPTIONS_PNL',        -- A3: B2 options expression grade (pointer; data in signal_options_expressions)
        'FWD_RETURN',         -- A3: fixed-horizon forward return (pointer; data in signal_forward_returns)
        'COMMITTEE_REVIEW'    -- A4: Olympus committee pass (pointer; data in committee_passes)
    )
);

COMMIT;
