-- Migration 019: create committee_passes
-- A4's durable structured committee-pass log.
-- Always written regardless of signal linkage; signal_id set only when pass
-- maps to a specific signal. signals.outcome_source='COMMITTEE_REVIEW' is a
-- secondary label under IS-NULL guard; this table is the source of truth.
--
-- Supersedes the dead committee_recommendations table (code existed,
-- migration was never run, always silently failing). committee_passes is
-- the canonical store going forward.
--
-- Rollback:
--   DROP TABLE IF EXISTS committee_passes;
--   (No dependents; drops cleanly.)

BEGIN;

CREATE TABLE IF NOT EXISTS committee_passes (
    id               SERIAL PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Market context at pass time
    ticker           VARCHAR(16) NOT NULL,
    pass_ts          TIMESTAMPTZ NOT NULL,          -- when the pass ran (from committee output)
    spot             NUMERIC(12, 4),                -- underlying price at pass time

    -- Per-agent reads (JSONB — flexible; keyed by agent name)
    -- Expected keys: toro, ursa, pythia, pythagoras, thales, daedalus
    -- Each value: {read: str, conviction: str, ...}
    agent_reads      JSONB,

    -- PIVOT synthesis + decision
    pivot_synthesis  TEXT,
    conviction       VARCHAR(16),                   -- HIGH / MEDIUM / LOW / WAIT

    -- Recommended levels (from PIVOT output)
    entry            NUMERIC(12, 4),
    stop             NUMERIC(12, 4),
    target           NUMERIC(12, 4),
    invalidation     NUMERIC(12, 4),

    -- Signal linkage (nullable — passes may have no matching signal)
    signal_id        TEXT REFERENCES signals(signal_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_cp_ticker
    ON committee_passes(ticker);

CREATE INDEX IF NOT EXISTS idx_cp_signal_id
    ON committee_passes(signal_id)
    WHERE signal_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cp_pass_ts
    ON committee_passes(pass_ts DESC);

COMMIT;
