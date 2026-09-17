-- 037: position_lots -- the RULED shape, reached by ALTER from the live one
-- (R-IV.310(b) schema, R-IV.416(b) build rules, R-IV.441(a) tonight).
--
-- MEASURED AGAINST THE DATABASE FIRST, not against the source tree. The table has existed in
-- production since 2026-08-26, created by scripts/feat_position_lifecycle_phase1.py outside
-- migrations/, holding 330 lots over 380 positions. A plain CREATE would have done nothing and
-- every later INSERT naming qty / fill_time / provenance would then have failed. That reading
-- is verification-laws addendum 3, instance 3, and this file is what it bought.
--
--   LIVE   2026-09-17   position_lots (position_id, quantity, price, fill_date, fees, source)
--   RULED  R-IV.310(b)  position_lots (position_id, qty,      price, fill_time, provenance, source)
--
-- fees is KEPT. It is absent from the ruled line, but the gross/net census needs a fee delta
-- per row and this is the only column that carries one; dropping it would discard the
-- measurement the normalization depends on.
--
-- fill_date -> fill_time is a PURE RENAME. The brief expected a date -> timestamp conversion;
-- the live column is already TIMESTAMPTZ (measured, information_schema). Recorded so the next
-- reader does not plan around a conversion that is not there.
--
-- WHAT THIS MIGRATION DOES NOT DO: it writes no lot. "Every position has >= 1 lot and
-- SUM(lot qty) == row qty" is FALSE in production -- 50 of 380 positions carry no lot at all,
-- 20 of them among the 34 OPEN -- and that false reading is the STARTING STATE, recorded
-- rather than papered over. A lot invented here would satisfy the invariant by construction
-- and measure nothing. GET /v2/positions/lots/coverage reports the gap live, and the probe
-- showing that surface can read non-zero is that it already does.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

-- 1. A database that has never seen the table gets it in the ruled shape directly.
CREATE TABLE IF NOT EXISTS position_lots (
    id           SERIAL PRIMARY KEY,
    position_id  TEXT        NOT NULL REFERENCES unified_positions(position_id) ON DELETE CASCADE,
    fill_time    TIMESTAMPTZ NOT NULL,
    qty          NUMERIC     NOT NULL,
    price        NUMERIC,
    fees         NUMERIC     NOT NULL DEFAULT 0,
    source       TEXT        NOT NULL DEFAULT 'MANUAL'
                 CHECK (source IN ('MANUAL', 'IMPORT', 'LEGACY-SINGLE-LOT')),
    provenance   TEXT,
    broker_ref   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_position_lots_position ON position_lots (position_id);

-- 2. A database that has the 2026-08-26 shape is renamed into the ruled one. Each rename is
--    conditioned on BOTH names -- the old one present and the new one absent -- so a partial
--    earlier run cannot make this fail, and a second run is a no-op.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name = 'position_lots' AND column_name = 'quantity')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name = 'position_lots' AND column_name = 'qty') THEN
        ALTER TABLE position_lots RENAME COLUMN quantity TO qty;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name = 'position_lots' AND column_name = 'fill_date')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name = 'position_lots' AND column_name = 'fill_time') THEN
        ALTER TABLE position_lots RENAME COLUMN fill_date TO fill_time;
    END IF;
END $$;

ALTER TABLE position_lots ADD COLUMN IF NOT EXISTS provenance TEXT;
ALTER TABLE position_lots ADD COLUMN IF NOT EXISTS broker_ref TEXT;

-- 3. Provenance is INHERITED FROM THE PARENT POSITION, per row, and never defaulted
--    (T6d, R-IV.416(b)). unified_positions carries no provenance column of its own, so the
--    inheritance reads the parent's `source` -- how that row got into the book -- through the
--    mapping below. Measured parent sources over the 330 existing lots:
--
--      MANUAL 208 | IMPORTED_HISTORICAL 70 | CSV_IMPORT 14 | CSV_RECONCILE 12
--      CSV_SYNC 9 | SCREENSHOT_SYNC 9 | fidelity_confirm 4 | SIGNAL 4
--
--    NOTHING BECOMES BROKER_VERIFIED HERE. That value is reachable only through a broker
--    record arriving and being matched, which no path in this build performs; writing it from
--    a backfill would be an assertion about an assertion.
--
--    A lot with NO PRICE is UNKNOWN whatever its parent says: the quantity is real, the price
--    is absent, and every figure derived from it has to be unknown too -- which is only
--    possible if the unknown is representable. Four such lots exist.
--
--    The ELSE is deliberately the WEAKEST value in the vocabulary: an unmapped source means
--    nothing is known to have checked the row, and PRINCIPAL_REPORTED says exactly that.
--    Guarded on provenance IS NULL, so a later run cannot overwrite a value something else set.
UPDATE position_lots l
   SET provenance = CASE
        WHEN l.price IS NULL THEN 'UNKNOWN'
        WHEN p.source IN ('IMPORTED_HISTORICAL', 'CSV_IMPORT', 'CSV_SYNC', 'CSV_RECONCILE',
                          'fidelity_confirm') THEN 'IMPORTED'
        ELSE 'PRINCIPAL_REPORTED'
   END
  FROM unified_positions p
 WHERE p.position_id = l.position_id
   AND l.provenance IS NULL;

-- A lot whose parent is missing cannot inherit anything. The foreign key makes that
-- impossible, and this line is here so the NOT NULL below is reached by a stated value rather
-- than by a quiet default if it ever becomes possible.
UPDATE position_lots SET provenance = 'UNKNOWN' WHERE provenance IS NULL;

ALTER TABLE position_lots ALTER COLUMN provenance SET NOT NULL;

-- 4. The vocabulary, and the one constraint that makes a verification claim falsifiable:
--    BROKER_VERIFIED requires a reference it was verified AGAINST. The column is free text, so
--    it accepts either identity the fill-identity rule allows -- a confirmation number, or an
--    export line written as its own identity -- and forecloses neither.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'position_lots_provenance_check') THEN
        ALTER TABLE position_lots ADD CONSTRAINT position_lots_provenance_check
            CHECK (provenance IN ('PRINCIPAL_REPORTED', 'BROKER_VERIFIED', 'IMPORTED', 'UNKNOWN'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'position_lots_verified_needs_ref') THEN
        ALTER TABLE position_lots ADD CONSTRAINT position_lots_verified_needs_ref
            CHECK (provenance <> 'BROKER_VERIFIED' OR broker_ref IS NOT NULL);
    END IF;
END $$;

-- DOWN
-- ALTER TABLE position_lots DROP CONSTRAINT IF EXISTS position_lots_verified_needs_ref;
-- ALTER TABLE position_lots DROP CONSTRAINT IF EXISTS position_lots_provenance_check;
-- ALTER TABLE position_lots ALTER COLUMN provenance DROP NOT NULL;
-- ALTER TABLE position_lots DROP COLUMN IF EXISTS broker_ref;
-- ALTER TABLE position_lots DROP COLUMN IF EXISTS provenance;
-- ALTER TABLE position_lots RENAME COLUMN fill_time TO fill_date;
-- ALTER TABLE position_lots RENAME COLUMN qty TO quantity;
-- (The renames reverse without loss. The two dropped columns do not: a DOWN discards every
--  provenance and every broker reference recorded after this migration ran.)
