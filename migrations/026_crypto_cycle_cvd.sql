-- Migration 026: Crypto Cycle Extremes + CVD tape-health tables
-- S-3 Phase 2 (§4.1). Brief: docs/codex-briefs/2026-07-16-stater-swap-s3-keep-list-upgrades-brief.md
-- DDL is also mirrored in backend/database/postgres_client.py per project convention.

-- ── UP ──────────────────────────────────────────────────────────────────────

-- crypto_cycle_config: append-only hot-reload config versions (FA-6).
-- Never UPDATE rows — INSERT new versions; rollback = re-INSERT an older payload.
CREATE TABLE IF NOT EXISTS crypto_cycle_config (
    id          SERIAL      PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  TEXT        NOT NULL,
    note        TEXT,
    config      JSONB       NOT NULL
);

-- crypto_cycle_log: per-evaluation composite + per-cell staleness records.
-- Mirrors crypto_regime_log shape; symbol-keyed; stores full JSONB cells payload.
CREATE TABLE IF NOT EXISTS crypto_cycle_log (
    id               BIGSERIAL   PRIMARY KEY,
    computed_at      TIMESTAMPTZ NOT NULL,
    symbol           TEXT        NOT NULL,
    tier             SMALLINT    NOT NULL,
    composite_score  NUMERIC,
    composite_method TEXT,
    degraded         BOOLEAN     NOT NULL DEFAULT FALSE,
    degrade_reason   TEXT,
    live_cell_count  INTEGER,
    min_live_cells   INTEGER,
    cells            JSONB       NOT NULL,
    config_version   INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crypto_cycle_log_symbol_computed
    ON crypto_cycle_log (symbol, computed_at DESC);

CREATE INDEX IF NOT EXISTS idx_crypto_cycle_log_degraded
    ON crypto_cycle_log (degraded) WHERE degraded;

-- crypto_tape_health_log: 5-min CVD tape-health state per covered symbol.
CREATE TABLE IF NOT EXISTS crypto_tape_health_log (
    id                BIGSERIAL   PRIMARY KEY,
    computed_at       TIMESTAMPTZ NOT NULL,
    symbol            TEXT        NOT NULL,
    state             TEXT,           -- SPOT_LED | PERP_LED | MIXED | NA
    slope             NUMERIC,
    spot_cvd          NUMERIC,
    perp_cvd          NUMERIC,
    degraded          BOOLEAN     NOT NULL DEFAULT FALSE,
    degrade_reason    TEXT,
    stale             BOOLEAN     NOT NULL DEFAULT FALSE,
    staleness_seconds INTEGER,
    config_version    INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crypto_tape_health_log_symbol_computed
    ON crypto_tape_health_log (symbol, computed_at DESC);


-- ── DOWN ─────────────────────────────────────────────────────────────────────
-- DROP TABLE IF EXISTS crypto_tape_health_log;
-- DROP TABLE IF EXISTS crypto_cycle_log;
-- DROP TABLE IF EXISTS crypto_cycle_config;
