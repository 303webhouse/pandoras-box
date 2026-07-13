-- Migration 023: crypto_vendor_health_audit
-- Stater Swap v2 S-1 Phase 1 (F-1, tasks 1.5 / A3). Audit trail for crypto
-- vendor client health-state transitions (LIVE <-> DEGRADED <-> DEAD) and
-- sanction/replace decisions, per AEGIS A3 requirement. Append-only on
-- TRANSITIONS only (not every poll) — this is an event log, not a snapshot
-- table. See docs/strategy-reviews/stater-swap-redesign/symbol-capability-matrix.md
-- for the live-test evidence this schema supports.
--
-- NOTE ON APPLICATION: this repo has no migration runner; tables are created
-- at boot via backend/database/postgres_client.py::init_database() (CREATE
-- TABLE IF NOT EXISTS). This file is the human record; the authoritative DDL
-- is mirrored verbatim in init_database(). Keep the two in sync.

BEGIN;

CREATE TABLE IF NOT EXISTS crypto_vendor_health_audit (
    id                  SERIAL PRIMARY KEY,
    vendor              TEXT NOT NULL,        -- 'coinalyze' | 'deribit' | 'binance_futures' | 'binance_spot' | 'okx_fallback' | 'defillama' | 'uw_crypto' | 'hyperliquid'
    feed_type           TEXT NOT NULL,         -- 'funding_rate' | 'open_interest' | 'liquidations' | 'term_structure' | 'skew_25d' | 'orderbook_skew' | 'quarterly_basis' | 'stablecoin_aprs' | 'crypto_quote' | 'crypto_ohlc'
    symbol              TEXT NOT NULL,         -- 'BTC', 'ETH', 'SOL', 'HYPE', 'ZEC', 'FARTCOIN'
    status              TEXT NOT NULL,         -- 'LIVE' | 'DEGRADED' | 'DEAD'
    previous_status     TEXT,                  -- NULL on first-ever observation for this (vendor, feed_type, symbol)
    reason              TEXT,                  -- e.g. 'bounds_violation: price 999999999 outside [10000,500000]', 'no_successful_read_in_900s', 'http_451_geo_block'
    as_of               TIMESTAMPTZ,           -- timestamp of the underlying data point (NULL if DEAD with no data at all)
    data_age_seconds    NUMERIC,
    sanction_decision   TEXT,                  -- 'SANCTIONED' | 'REPLACED' | 'NOT_SANCTIONED' | NULL (only set on F-1-style vendor decisions, not routine health flips)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crypto_vendor_health_latest
    ON crypto_vendor_health_audit (vendor, feed_type, symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crypto_vendor_health_dead
    ON crypto_vendor_health_audit (created_at DESC)
    WHERE status = 'DEAD';

COMMIT;

-- DOWN
-- BEGIN;
-- DROP INDEX IF EXISTS idx_crypto_vendor_health_dead;
-- DROP INDEX IF EXISTS idx_crypto_vendor_health_latest;
-- DROP TABLE IF EXISTS crypto_vendor_health_audit;
-- COMMIT;
