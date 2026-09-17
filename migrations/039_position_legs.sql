-- 039: a multi-leg position gets legs (R-IV.444(b)).
--
-- Two strike columns can describe a vertical and nothing else. A three-leg structure therefore
-- had to be split across rows (XLF 300 holds 45P/40P, 301 holds 30P) or written into prose
-- (NVDA 415's third leg lives in a note), and a screen reading those rows renders one position
-- two or three times -- which is what the principal's screenshot showed.
--
-- THE DDL IS HERE; THE EXPANSION IS IN backend/database/legs_migration.py, which runs at boot
-- and owns the classification, so the rule that decides an outcome exists once and is testable
-- without a database. Every option row gets an outcome and none is silently dropped
-- (R-IV.432(c)): MIGRATED, MERGED_INTO, or one of four named reasons it cannot become legs.
--
-- THE MAPPING IS MEASURED, not assumed: across all 280 option rows `long_strike` is the BOUGHT
-- leg and `short_strike` is the SOLD one -- put debit spreads hold long > short in all 148 rows
-- carrying both, call debit spreads hold long < short in all 90, and the single put credit
-- spread holds the sold (higher) put in short_strike. The side is the column; the right is the
-- structure's name.
--
-- PRICES ARE NOT INVENTED. A vertical stores its NET and never the split, so a leg's price is
-- NULL unless a fill recorded it -- the same rule the lots table keeps for an unpriced lot.
--
-- Also created at boot from backend/database/postgres_client.py (keep the two in sync).

CREATE TABLE IF NOT EXISTS position_legs (
    id            BIGSERIAL   PRIMARY KEY,
    position_id   TEXT        NOT NULL REFERENCES unified_positions(position_id) ON DELETE CASCADE,
    leg_seq       INTEGER     NOT NULL,
    option_type   TEXT        NOT NULL CHECK (option_type IN ('CALL', 'PUT')),
    side          TEXT        NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    strike        NUMERIC     NOT NULL,
    expiry        DATE        NOT NULL,
    qty           NUMERIC     NOT NULL,
    price         NUMERIC,
    provenance    TEXT        NOT NULL
                  CHECK (provenance IN ('PRINCIPAL_REPORTED', 'BROKER_VERIFIED', 'IMPORTED',
                                        'UNKNOWN')),
    broker_ref    TEXT,
    migrated_from TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (position_id, leg_seq)
);
CREATE INDEX IF NOT EXISTS idx_position_legs_position ON position_legs (position_id);

-- Every option row's outcome, including the ones that produced no legs. This table is also the
-- migration's idempotence guard: a row with an outcome is never reconsidered.
CREATE TABLE IF NOT EXISTS position_legs_migration (
    position_id   TEXT        PRIMARY KEY
                  REFERENCES unified_positions(position_id) ON DELETE CASCADE,
    outcome       TEXT        NOT NULL,
    detail        TEXT,
    legs_written  INTEGER     NOT NULL DEFAULT 0,
    merged_into   TEXT,
    migrated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- DOWN
-- DROP TABLE IF EXISTS position_legs_migration;
-- DROP TABLE IF EXISTS position_legs;
-- (Reversible only in shape. The legs themselves are derived from the rows they were read
--  from, so re-running the expansion rebuilds them; the XLF group's merge record is not
--  derivable a second time from rows that may have moved on.)
