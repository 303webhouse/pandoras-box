-- 042: the broker's reference on the position row (R-IV.448(b)).
--
-- Spine asserted the column existed at R-IV.446 and it did not; nine captured references were
-- living in `notes`, where they are prose. A reference in prose can be read by a human and by
-- nothing else: it cannot be joined, counted, or checked, and the verification stamp that
-- depends on it cannot be enforced.
--
-- WHY TWO COLUMNS AND NOT ONE, read off the captured set rather than assumed. Of the nine
-- positions, several carry TWO references -- the order that opened the row and the order that
-- closed it (BITX 26259-MCQGWD in, 26259-PBRZHP out; GDXJ 26257-MF58HB in, 26259-N7ZZ4J out).
-- One column would have forced a choice between them, and the loser would have stayed in the
-- prose this migration exists to empty.
--
-- WHY NEITHER IS UNIQUE HERE, where the lot-level one is. A confirmation number identifies one
-- FILL, and one fill can close several positions: 26257-PBS5D3 is the 60-share SOXS sale and
-- covers three rows; 26254-Q7D3D4 covers both COPX lots. Unique at the lot level is right --
-- the same fill twice is a double count. Unique at the position level would be WRONG, and
-- would have rejected the correction set's own evidence.
--
-- BROKER_VERIFIED on a position carries the same three pieces as a lot or a leg: the
-- reference, what was matched, and when the match was made. Provenance is backfilled from how
-- each row arrived -- the mapping migration 037 applied to lots -- and never to BROKER_VERIFIED,
-- which is reachable only through the verify transition.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS broker_ref      TEXT;
ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS exit_broker_ref TEXT;
ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS provenance      TEXT;
ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS verified_at     TIMESTAMPTZ;
ALTER TABLE unified_positions ADD COLUMN IF NOT EXISTS verified_event  TEXT;

UPDATE unified_positions
   SET provenance = CASE
        WHEN source IN ('IMPORTED_HISTORICAL', 'CSV_IMPORT', 'CSV_SYNC', 'CSV_RECONCILE',
                        'fidelity_confirm') THEN 'IMPORTED'
        ELSE 'PRINCIPAL_REPORTED'
   END
 WHERE provenance IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'unified_positions_provenance_check') THEN
        ALTER TABLE unified_positions ADD CONSTRAINT unified_positions_provenance_check
            CHECK (provenance IS NULL OR provenance IN ('PRINCIPAL_REPORTED', 'BROKER_VERIFIED',
                                                        'IMPORTED', 'UNKNOWN'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'unified_positions_verified_needs_evidence') THEN
        ALTER TABLE unified_positions ADD CONSTRAINT unified_positions_verified_needs_evidence
            CHECK (provenance <> 'BROKER_VERIFIED'
                   OR (broker_ref IS NOT NULL AND verified_event IS NOT NULL
                       AND verified_at IS NOT NULL));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_unified_positions_broker_ref
    ON unified_positions (broker_ref) WHERE broker_ref IS NOT NULL;

-- DOWN
-- DROP INDEX IF EXISTS idx_unified_positions_broker_ref;
-- ALTER TABLE unified_positions DROP CONSTRAINT IF EXISTS unified_positions_verified_needs_evidence;
-- ALTER TABLE unified_positions DROP CONSTRAINT IF EXISTS unified_positions_provenance_check;
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS verified_event;
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS verified_at;
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS provenance;
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS exit_broker_ref;
-- ALTER TABLE unified_positions DROP COLUMN IF EXISTS broker_ref;
-- (A DOWN returns every reference to prose, and with it every verification's only evidence.)
