-- 030_instrument_class.sql  —  T5b PHASE A (R-IV.360(2)).
--
-- T5 classifies at INGEST. Stored rows carry no class, so the permanently
-- ungradeable index rows keep occupying the head of every grading pass:
-- they are the OLDEST ungraded rows (nothing ever clears them), and the queue
-- is `ORDER BY fired_at`, so they are selected first, every pass, forever.
--
-- MEASURED 2026-09-11: 100 cash-settled rows, ALL ungraded, out of 1,083
-- ungraded total. GRADE_LIMIT is 1000 and the 2026-09-11 pass reported
-- no_regular_session_bars=1000 — the ceiling exactly. The queue is saturated,
-- and ~9% of it is work that cannot succeed.
--
-- PHASE A ADDS THE COLUMN AND WRITES NOTHING.
--   The classification backfill is Phase B: scripts/backfill_030_class.py,
--   seal-gated, expected counts declared before the write.
--
-- NULL MEANS NOT YET CLASSIFIED. It does NOT mean "not an index".
--   The grader's queue predicate is therefore
--       instrument_class IS NULL OR instrument_class <> 'cash_settled_index'
--   — an unclassified row is NOT known to be ungradeable, and excluding it would
--   shrink the queue on the strength of a missing value. Absent is not a class.

ALTER TABLE triton_flow_shadow
    ADD COLUMN IF NOT EXISTS instrument_class TEXT;

COMMENT ON COLUMN triton_flow_shadow.instrument_class IS
    'instrument_class.classify() output: cash_settled_index | single_name | '
    'etf_* | unmapped. NULL = not yet classified, which is NOT a claim that the '
    'row is gradeable. See migration 030 and T5b.';

-- The queue index, matching the grader predicate exactly. Partial, because the
-- grader only ever reads ungraded rows.
CREATE INDEX IF NOT EXISTS idx_triton_shadow_ungraded_gradeable
    ON triton_flow_shadow (fired_at)
    WHERE graded_at IS NULL
      AND (instrument_class IS NULL OR instrument_class <> 'cash_settled_index');

-- DOWN
-- DROP INDEX IF EXISTS idx_triton_shadow_ungraded_gradeable;
-- ALTER TABLE triton_flow_shadow DROP COLUMN IF EXISTS instrument_class;
