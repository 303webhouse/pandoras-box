-- 029_grade_provider.sql  —  PHASE A of the R-IV.325(b) provider backfill.
--
-- Every graded row must record WHICH FEED produced its closes. UW and yfinance
-- disagree by adjustment convention (uw_api.py:602-606), so an unlabelled
-- forward return is not comparable across the seam, and a benchmark arm built
-- from a mixed population is partly measuring the seam.
--
-- PHASE A ADDS THE COLUMN AND WRITES NOTHING.
--   The backfill is Phase B and does NOT run here, because the expected count
--   must be taken AT THE DEPLOY: the grader can run between measuring and
--   writing, and a count measured an hour early is a different population.
--   Phase B is scripts/backfill_029_provider.py, seal-gated.
--
-- THE INVARIANT PHASE B ESTABLISHES, both directions, forever after:
--
--        provider IS NULL   <->   graded_at IS NULL
--
--   NULL is reserved for NOT GRADED. It must never come to mean "graded, vendor
--   unknown" -- that would let a real state and an absent one share a
--   representation, which is DEF-BIAS-NULL-AS-NEUTRAL's exact failure one table
--   over. The backfill is what keeps the column honest; without it the column
--   is born ambiguous.
--
-- WHY BACKFILLING 'uw' IS CERTAINTY AND NOT ASSUMPTION:
--   before the fallback shipped, get_ohlc was the ONLY path to a Triton close.
--   No third possibility existed. The retired certificate still certifies the
--   past. This is the one case where writing a value we did not observe is
--   correct -- because it was not observable otherwise, and leaving it NULL
--   would assert an ignorance we do not have.

ALTER TABLE triton_flow_shadow
    ADD COLUMN IF NOT EXISTS provider TEXT;

COMMENT ON COLUMN triton_flow_shadow.provider IS
    'Feed that produced the closes for this grade: uw | yfinance | mixed | none. '
    'NULL means NOT GRADED, never "unknown" -- invariant: provider IS NULL <-> '
    'graded_at IS NULL. Established by migration 029 Phase B (R-IV.325(b)).';

-- Partial: the population of interest is graded rows. Unfiltered, this would
-- index a column that is NULL for every row until Phase B runs.
CREATE INDEX IF NOT EXISTS idx_triton_shadow_provider
    ON triton_flow_shadow (provider, graded_at DESC)
    WHERE provider IS NOT NULL;

-- DOWN
-- DROP INDEX IF EXISTS idx_triton_shadow_provider;
-- ALTER TABLE triton_flow_shadow DROP COLUMN IF EXISTS provider;
