-- Migration 024: crypto_dual_write_shadow
-- Stater Swap v2 S-1 Phase 4 (F-4). Shadow-write evidence table: for every
-- crypto signal the bias_scheduler.py "Crypto Scanner" bypass logs via
-- log_signal directly, also run process_signal_unified(shadow=True) on a
-- COPY (distinct signal_id, zero real side effects -- see
-- backend/signals/pipeline.py's `shadow` param) and record what the real
-- governance chokepoint WOULD have decided, for the ≥48h/n≥30 diff report
-- gating the F-4 cutover decision. NOTHING reads this table for scoring or
-- the live pipeline -- inert evidence data, mirrors migrations/021's
-- triton_flow_shadow precedent.
--
-- NOTE ON APPLICATION: this repo has no migration runner; tables are
-- created at boot via backend/database/postgres_client.py::init_database()
-- (CREATE TABLE IF NOT EXISTS). This file is the human record; the
-- authoritative DDL is mirrored verbatim in init_database(). Keep in sync.

BEGIN;

CREATE TABLE IF NOT EXISTS crypto_dual_write_shadow (
    id                      SERIAL PRIMARY KEY,
    shadow_signal_id        TEXT UNIQUE NOT NULL,
    real_signal_id          TEXT NOT NULL,
    ticker                  TEXT NOT NULL,
    direction               TEXT,
    signal_type             TEXT,
    fired_at                TIMESTAMPTZ NOT NULL,
    real_score              NUMERIC,
    real_status             TEXT,
    shadow_score            NUMERIC,
    shadow_score_v2         NUMERIC,
    shadow_status            TEXT,
    l0_shadow_decision      JSONB,
    l1_shadow_decision      JSONB,
    feed_tier_v1            TEXT,
    feed_tier_v2            TEXT,
    feed_tier_v2_path       TEXT,
    confluence_badge        TEXT,
    would_flag_committee    BOOLEAN,
    raw_shadow_signal_data  JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crypto_dual_write_shadow_fired
    ON crypto_dual_write_shadow (fired_at DESC);

CREATE INDEX IF NOT EXISTS idx_crypto_dual_write_shadow_ticker
    ON crypto_dual_write_shadow (ticker, fired_at DESC);

COMMIT;

-- DOWN
-- BEGIN;
-- DROP INDEX IF EXISTS idx_crypto_dual_write_shadow_ticker;
-- DROP INDEX IF EXISTS idx_crypto_dual_write_shadow_fired;
-- DROP TABLE IF EXISTS crypto_dual_write_shadow;
-- COMMIT;
