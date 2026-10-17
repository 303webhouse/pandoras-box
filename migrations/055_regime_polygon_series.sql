-- 055: the designated settled-close series, and room for two seeds (R-IV.1203(b))
--
-- MIRRORS the DDL in backend/database/postgres_client.py init_database(). Nothing in the app
-- executes migrations/*.sql; this file is the reviewable copy. Keep the two in sync.
--
-- WHY A SECOND BAR TABLE instead of repairing stable_daily_bars and reusing it. They answer
-- different questions and R-IV.1203 rules on both separately. stable_daily_bars is
-- FULLY ADJUSTED (splits and dividends) and stays that way, because that is correct for moving
-- averages and breadth -- (c) says so explicitly. This series is SPLIT-ADJUSTED AND NOT
-- DIVIDEND-ADJUSTED, which is the basis a settled close has to be on. One table cannot be both
-- bases at once, and a column that silently means either is worse than two tables.

CREATE TABLE IF NOT EXISTS regime_daily_bars (
    ticker        TEXT NOT NULL,
    date          DATE NOT NULL,          -- the SESSION, read in UTC from Polygon's stamp
    o             DOUBLE PRECISION,
    h             DOUBLE PRECISION,
    l             DOUBLE PRECISION,
    c             DOUBLE PRECISION,
    v             BIGINT,
    close_source  TEXT NOT NULL,          -- 'polygon'
    -- TRUE only when this row's close was checked against the UW chart close BEFORE it was
    -- written. FALSE on backfilled history, which is the honest record: the chart route serves
    -- only its newest reading, so two years of history has nothing to be checked against, and
    -- a TRUE there would be a claim nobody verified.
    uw_verified   BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_regime_daily_bars_date
    ON regime_daily_bars (date DESC);

-- ── regime_snapshots: hold BOTH seeds ───────────────────────────────────────
--
-- R-IV.1203(b)2: "Keep the old seed rows, marked superseded; do not delete them." The old
-- unique key was (as_of, rules_version), which makes a second row for the same session
-- impossible -- so the key has to include the source the row was computed from. Without this,
-- re-seeding could only happen by deleting, which the ruling forbids.

ALTER TABLE regime_snapshots
    ADD COLUMN IF NOT EXISTS close_source TEXT;

ALTER TABLE regime_snapshots
    ADD COLUMN IF NOT EXISTS superseded BOOLEAN NOT NULL DEFAULT FALSE;

-- The 321 rows already there came from stable_daily_bars, and the ruling marks them superseded.
-- Guarded on close_source IS NULL so a re-run cannot re-mark rows written since, which would
-- supersede the NEW seed with its own marker.
UPDATE regime_snapshots
   SET close_source = 'stable_daily_bars',
       superseded   = TRUE
 WHERE close_source IS NULL;

-- The table-level UNIQUE from migration 053 gets this auto-generated name.
ALTER TABLE regime_snapshots
    DROP CONSTRAINT IF EXISTS regime_snapshots_as_of_rules_version_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_regime_snapshots_asof_rules_source
    ON regime_snapshots (as_of, rules_version, close_source);

-- Reads serve the CURRENT seed, so this is the index they travel on.
CREATE INDEX IF NOT EXISTS idx_regime_snapshots_current
    ON regime_snapshots (as_of DESC) WHERE superseded = FALSE;
