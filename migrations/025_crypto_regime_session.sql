-- Migration 025: crypto_regime_log, crypto_gate_shadow, crypto_gate_config
-- Stater Swap v2 S-2 (R-1 Regime & Session Layer). Three new, additive tables --
-- no changes to signals, signal_outcomes, unified_positions, or any existing
-- table. All shadow/config data; gating_enabled=false at seed and through S-2
-- closure (hard rule 1) -- nothing here can block, dismiss, rescore, or alter
-- a live signal.
--
-- crypto_regime_log: append-only heartbeat row per symbol per hourly
--   evaluation (TREND_UP/CHOP/TREND_DOWN/UNKNOWN + session context at compute
--   time). crypto_gate_shadow: one row per shadow gate evaluation of a real
--   crypto signal (WOULD_PASS/WOULD_BLOCK verdict, never mutates the signal).
--   crypto_gate_config: append-only config versions (INSERT-only hot-reload --
--   never UPDATE in place; rollback = re-INSERT an older payload). Loader
--   contract: read the max-id row, 60s in-process TTL cache.
--
-- NOTE ON APPLICATION: this repo has no migration runner; tables are created
-- at boot via backend/database/postgres_client.py::init_database() (CREATE
-- TABLE IF NOT EXISTS). This file is the human record; the authoritative DDL
-- is mirrored verbatim in init_database(). Keep in sync.

BEGIN;

CREATE TABLE IF NOT EXISTS crypto_regime_log (
    id                      BIGSERIAL PRIMARY KEY,
    computed_at             TIMESTAMPTZ NOT NULL,
    symbol                  TEXT NOT NULL,
    tier                    SMALLINT NOT NULL,
    is_master               BOOLEAN NOT NULL DEFAULT FALSE,
    regime_state            TEXT NOT NULL,
    price                   NUMERIC,
    dma50                   NUMERIC,
    price_vs_dma50_pct      NUMERIC,
    adx14                   NUMERIC,
    dma50_slope_pct         NUMERIC,
    bars_source             TEXT,
    bars_as_of              TIMESTAMPTZ,
    bar_count               INTEGER,
    data_age_seconds        INTEGER,
    degraded                BOOLEAN NOT NULL DEFAULT FALSE,
    degrade_reason          TEXT,
    session_partition       TEXT,
    event_windows           TEXT[],
    weekend_holiday_flag    BOOLEAN NOT NULL DEFAULT FALSE,
    config_version          INTEGER,
    changed                 BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crypto_regime_log_symbol_computed
    ON crypto_regime_log (symbol, computed_at DESC);

CREATE INDEX IF NOT EXISTS idx_crypto_regime_log_changed
    ON crypto_regime_log (changed) WHERE changed;

CREATE TABLE IF NOT EXISTS crypto_gate_shadow (
    id                      BIGSERIAL PRIMARY KEY,
    evaluated_at            TIMESTAMPTZ NOT NULL,
    signal_id               TEXT NOT NULL,
    symbol                  TEXT NOT NULL,
    tier                    SMALLINT,
    strategy                TEXT,
    strategy_canonical      TEXT,
    direction               TEXT,
    regime_master           TEXT,
    regime_symbol           TEXT,
    session_partition       TEXT,
    event_windows           TEXT[],
    weekend_holiday_flag    BOOLEAN NOT NULL DEFAULT FALSE,
    alt_gate                TEXT,
    verdict                 TEXT NOT NULL,
    reasons                 TEXT[],
    config_version          INTEGER,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crypto_gate_shadow_evaluated
    ON crypto_gate_shadow (evaluated_at DESC);

CREATE INDEX IF NOT EXISTS idx_crypto_gate_shadow_strategy_verdict
    ON crypto_gate_shadow (strategy, verdict);

CREATE TABLE IF NOT EXISTS crypto_gate_config (
    id                      SERIAL PRIMARY KEY,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by              TEXT NOT NULL,
    note                    TEXT,
    config                  JSONB NOT NULL
);

COMMIT;

-- DOWN
-- BEGIN;
-- DROP INDEX IF EXISTS idx_crypto_gate_shadow_strategy_verdict;
-- DROP INDEX IF EXISTS idx_crypto_gate_shadow_evaluated;
-- DROP TABLE IF EXISTS crypto_gate_shadow;
-- DROP INDEX IF EXISTS idx_crypto_regime_log_changed;
-- DROP INDEX IF EXISTS idx_crypto_regime_log_symbol_computed;
-- DROP TABLE IF EXISTS crypto_regime_log;
-- DROP TABLE IF EXISTS crypto_gate_config;
-- COMMIT;
