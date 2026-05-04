-- Phase A of outcome tracking unification.
-- Adds outcome_source column to signals, supporting view + diff-log stub.
-- See docs/codex-briefs/outcome-tracking-unification-2026-05-03-v2.md

-- 1. outcome_source column on signals
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS outcome_source VARCHAR(30);

-- Allowed values:
--   NULL                       — unresolved (no outcome yet)
--   BAR_WALK                   — resolver wrote this (yfinance forward bar walk)
--   ACTUAL_TRADE               — Ariadne wrote this (real position close)
--   COUNTERFACTUAL             — counterfactual analysis writer
--   EXPIRED                    — signal time-window elapsed (from signal_outcomes)
--   INVALIDATED                — signal contradicted before resolution (from signal_outcomes)
--   PROJECTED_FROM_BAR_WALK    — reserved for Phase C (signal_outcomes projection)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'outcome_source_valid' AND table_name = 'signals'
    ) THEN
        ALTER TABLE signals
            ADD CONSTRAINT outcome_source_valid CHECK (
                outcome_source IS NULL
                OR outcome_source IN (
                    'BAR_WALK',
                    'ACTUAL_TRADE',
                    'COUNTERFACTUAL',
                    'EXPIRED',
                    'INVALIDATED',
                    'PROJECTED_FROM_BAR_WALK'
                )
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_signals_outcome_source
    ON signals(outcome_source) WHERE outcome_source IS NOT NULL;

-- 2. signal_outcome_diff_log — stub for Phase C
CREATE TABLE IF NOT EXISTS signal_outcome_diff_log (
    id SERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES signals(signal_id),
    old_outcome VARCHAR,
    new_outcome VARCHAR,
    old_outcome_source VARCHAR(30),
    new_outcome_source VARCHAR(30),
    old_pnl_pct DOUBLE PRECISION,
    new_pnl_pct DOUBLE PRECISION,
    old_resolved_at TIMESTAMPTZ,
    new_resolved_at TIMESTAMPTZ,
    backfill_run_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_diff_log_run ON signal_outcome_diff_log(backfill_run_id);
CREATE INDEX IF NOT EXISTS idx_diff_log_signal ON signal_outcome_diff_log(signal_id);

-- 3. v_outcome_drift — bar-walk-only drift detection
-- Scoped to BAR_WALK and PROJECTED_FROM_BAR_WALK so we don't false-positive
-- on Ariadne (ACTUAL_TRADE legitimately disagrees with bar walk) or
-- counterfactual rows (different semantic entirely).
CREATE OR REPLACE VIEW v_outcome_drift AS
SELECT s.signal_id,
       s.outcome AS signals_outcome,
       s.outcome_source,
       so.outcome AS signal_outcomes_outcome,
       s.outcome_pnl_pct AS signals_pnl,
       so.max_favorable AS so_mfe,
       so.max_adverse AS so_mae,
       s.outcome_resolved_at AS signals_resolved_at,
       so.outcome_at AS signal_outcomes_resolved_at
FROM signals s
JOIN signal_outcomes so ON so.signal_id = s.signal_id
WHERE s.outcome IS NOT NULL
  AND so.outcome IS NOT NULL
  AND s.outcome_source IN ('BAR_WALK', 'PROJECTED_FROM_BAR_WALK')
  AND (
        (s.outcome = 'WIN'  AND so.outcome NOT IN ('HIT_T1','HIT_T2'))
     OR (s.outcome = 'LOSS' AND so.outcome != 'STOPPED_OUT')
  );
