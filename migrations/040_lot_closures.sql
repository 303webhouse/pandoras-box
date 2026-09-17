-- 040: a reduction is an event that ALLOCATES against the fills it consumes (R-IV.444(c)).
--
-- Reducing a position does not edit the lots it sells out of. A lot is a record that something
-- happened on a day at a price, and rewriting it to make today's arithmetic simpler destroys
-- the only evidence of what was bought and when. So a disposal is its own lot, with a negative
-- quantity, and this table records which acquisitions it consumed, oldest first, and what each
-- allocation realized.
--
-- SUM(qty) still equals the position's quantity afterwards -- the disposal is in the sum --
-- so the lots invariant survives selling, which it would not if reductions were deletions.
--
-- realized is NULL when either side of the pair carries no price. A gain measured against a
-- cost nobody recorded is not a number, and writing 0 there would book a fiction as a result.
--
-- broker_ref becomes UNIQUE where it is present: a confirmation number is the broker's own
-- identity for one fill, so the same one arriving twice is the same fill arriving twice, which
-- is DEF-INGEST-DUPLICATE-LOT from the direction that inflates a position. It stays NULLABLE
-- and unconstrained when absent, because one broker issues no references at all and NULL there
-- is a property of that export rather than a gap.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

CREATE TABLE IF NOT EXISTS position_lot_closures (
    id               BIGSERIAL   PRIMARY KEY,
    position_id      TEXT        NOT NULL
                     REFERENCES unified_positions(position_id) ON DELETE CASCADE,
    disposal_lot_id  INTEGER     NOT NULL REFERENCES position_lots(id) ON DELETE CASCADE,
    acquired_lot_id  INTEGER     NOT NULL REFERENCES position_lots(id) ON DELETE CASCADE,
    qty              NUMERIC     NOT NULL,
    cost_per_unit    NUMERIC,
    proceeds_per_unit NUMERIC,
    realized         NUMERIC,
    multiplier       INTEGER     NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lot_closures_position
    ON position_lot_closures (position_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lot_closures_disposal
    ON position_lot_closures (disposal_lot_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_position_lots_broker_ref
    ON position_lots (broker_ref) WHERE broker_ref IS NOT NULL;

-- DOWN
-- DROP INDEX IF EXISTS uq_position_lots_broker_ref;
-- DROP TABLE IF EXISTS position_lot_closures;
