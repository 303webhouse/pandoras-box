-- 043: a duplicate is retired by being marked, never by being deleted (R-IV.449(a)).
--
-- The book held one BITX round trip twice: the principal's own entry and, later, a
-- broker-matched create-and-close written by a reconciliation that could not see the first --
-- it was filed under a retired account alias, and the inventory was account-scoped. Both rows
-- were CLOSED, so the book carried two realized results for one trade.
--
-- DELETION IS NOT THE REMEDY. The duplicate is the only record that the duplication happened,
-- and the only evidence of what caused it. So the row stays, its notes stay, and it gains a
-- status that says what it is and a column that names the row it duplicates.
--
-- THE POINTER IS A COLUMN AND NOT A SENTENCE, for the same reason the broker reference is: a
-- keeper named in prose cannot be joined, counted, or checked. The constraints make the two
-- fields agree -- a DUPLICATE_OF row must name its keeper, a row that names one must carry the
-- status, and nothing may point at itself.
--
-- WHAT THIS DOES NOT DO: it does not move money. The keeper already carries the realized
-- figure; the duplicate simply stops being counted, because every rollup that sums realized
-- results asks for CLOSED or EXPIRED rather than for "not open" (see models/position_status.py,
-- which is where that question is now answered once).
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS duplicate_of TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'unified_positions_duplicate_pointer') THEN
        ALTER TABLE unified_positions ADD CONSTRAINT unified_positions_duplicate_pointer
            CHECK ((status = 'DUPLICATE_OF') = (duplicate_of IS NOT NULL));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'unified_positions_duplicate_not_self') THEN
        ALTER TABLE unified_positions ADD CONSTRAINT unified_positions_duplicate_not_self
            CHECK (duplicate_of IS NULL OR duplicate_of <> position_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_unified_positions_duplicate_of
    ON unified_positions (duplicate_of) WHERE duplicate_of IS NOT NULL;

-- DOWN
-- DROP INDEX IF EXISTS idx_unified_positions_duplicate_of;
-- ALTER TABLE unified_positions DROP CONSTRAINT IF EXISTS unified_positions_duplicate_not_self;
-- ALTER TABLE unified_positions DROP CONSTRAINT IF EXISTS unified_positions_duplicate_pointer;
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS duplicate_of;
-- (A DOWN must first restore every DUPLICATE_OF row to CLOSED, or the check it drops is the
--  only thing that was keeping those rows out of the totals.)
