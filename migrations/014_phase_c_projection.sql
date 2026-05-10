-- Phase C: signal_outcomes → signals.outcome* projection
-- Indexes only. No schema changes (Phase A did the schema work).
-- See docs/codex-briefs/outcome-tracking-phase-c-projection-2026-05-09.md

BEGIN;

-- Speeds up the projection scan (signal_outcomes ordered by outcome_at)
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_resolved
  ON signal_outcomes (outcome_at)
  WHERE outcome IS NOT NULL;

-- Speeds up the projection-safety filter
-- (we never want to JOIN-and-skip on a sequential scan when looking for ACTUAL_TRADE/COUNTERFACTUAL)
CREATE INDEX IF NOT EXISTS idx_signals_outcome_source_projectable
  ON signals (signal_id)
  WHERE outcome_source IS NULL
     OR outcome_source IN ('BAR_WALK', 'PROJECTED_FROM_BAR_WALK');

COMMIT;
