-- 032_mark_status.sql — T1, the mark guard (R-IV.394).
--
-- `unified_positions.py` recomputed unrealized_pnl from `current_price` with NO
-- validation that the mark was present, fresh or sane, and wrote the result
-- unconditionally. Every later task in the ledger brief reads numbers that line
-- writes, which is why R-IV.271(e) orders this FIRST: fixing the account
-- vocabulary while the marks are unguarded produces a WELL-NAMED WRONG ANSWER,
-- and that is harder to detect than an obviously wrong one.
--
-- mark_status records WHY a P&L is or is not there:
--
--   OK        the mark passed present/fresh/sane; unrealized_pnl is computed
--   STALE     a mark exists but is too old to price against
--   REJECTED  a mark is present and failed a sanity predicate
--   ABSENT    no mark at all
--
-- NULL means the row predates this column. It is NOT a fourth failure state and
-- must not be read as one.
--
-- THE RULE THE COLUMN EXISTS TO ENFORCE: on any failure the job writes NOTHING
-- to unrealized_pnl -- it does not write zero. A zero P&L is a CLAIM that the
-- position is flat, and it is indistinguishable from a real flat position on
-- every surface downstream. The previous value is left standing, stamped with
-- the reason it was not updated.

ALTER TABLE unified_positions
    ADD COLUMN IF NOT EXISTS mark_status TEXT;

ALTER TABLE unified_positions
    ADD COLUMN IF NOT EXISTS mark_checked_at TIMESTAMPTZ;

COMMENT ON COLUMN unified_positions.mark_status IS
    'T1 mark guard: OK | STALE | REJECTED | ABSENT. NULL = predates the column, '
    'not a failure state. On any non-OK value unrealized_pnl was NOT written -- '
    'never zeroed. See migration 032.';

CREATE INDEX IF NOT EXISTS idx_unified_positions_mark_status
    ON unified_positions (mark_status)
    WHERE mark_status IS NOT NULL AND mark_status <> 'OK';

-- DOWN
-- DROP INDEX IF EXISTS idx_unified_positions_mark_status;
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS mark_checked_at;
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS mark_status;
