-- Migration 015: position_sync_audit
-- Audit table for scripts/sync_rh_csv.py. One row per INSERT/UPDATE/CLOSE
-- applied to unified_positions by a sync run, capturing before/after state
-- so any sync can be reviewed or rolled back.
-- See brief: docs/codex-briefs/rh-csv-sync-2026-05-26.md (Brief E)

BEGIN;

CREATE TABLE IF NOT EXISTS position_sync_audit (
    id              SERIAL PRIMARY KEY,
    sync_run_id     UUID NOT NULL,
    csv_paths       TEXT NOT NULL,       -- comma-joined source CSV paths
    csv_sha256      TEXT NOT NULL,       -- sha256 of the concatenated CSV contents
    operation       TEXT NOT NULL,       -- INSERT, UPDATE, CLOSE, NO_OP_FLAG
    position_id     TEXT,                -- unified_positions.position_id (NULL for INSERT-pending rows)
    ticker          TEXT NOT NULL,
    structure       TEXT,
    before_state    JSONB,
    after_state     JSONB,
    notes           TEXT,
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_position_sync_audit_run
    ON position_sync_audit(sync_run_id, executed_at);

CREATE INDEX IF NOT EXISTS idx_position_sync_audit_position
    ON position_sync_audit(position_id)
    WHERE position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_position_sync_audit_ticker
    ON position_sync_audit(ticker, executed_at DESC);

COMMIT;
