-- R-IV.463(c): a mark is a SIGNED net, read against the side the position was entered on.
-- For a set of legs whose value cannot change sign, the side follows from its payoff; for one
-- that can (a ratio, a risk reversal) entered without leg prices, it is recorded here at entry.
-- NULL = not recorded; the mark path then decides from the legs or says it cannot.
-- Mirrors backend/database/postgres_client.py (boot DDL).

ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS entry_side TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unified_positions_entry_side_check') THEN
        ALTER TABLE unified_positions ADD CONSTRAINT unified_positions_entry_side_check
            CHECK (entry_side IS NULL OR entry_side IN ('DEBIT', 'CREDIT'));
    END IF;
END $$;
