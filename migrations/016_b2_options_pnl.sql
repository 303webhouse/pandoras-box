-- Migration 016: B2 Options-P&L Measurement Layer
-- Creates signal_options_expressions table for grading signals in options terms.
-- Does NOT modify any existing table or constraint.
--
-- Rollback:
--   DROP TABLE IF EXISTS signal_options_expressions;
--   (cascades the FK and drops all 3 indexes automatically)

BEGIN;

CREATE TABLE IF NOT EXISTS signal_options_expressions (
    id                          SERIAL PRIMARY KEY,
    signal_id                   TEXT NOT NULL
                                    REFERENCES signals(signal_id) ON DELETE CASCADE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Expression computed at signal creation time
    option_type                 VARCHAR(4)    NOT NULL CHECK (option_type IN ('call', 'put')),
    long_strike                 NUMERIC(10,2) NOT NULL,
    short_strike                NUMERIC(10,2) NOT NULL,
    expiry                      DATE          NOT NULL,
    spread_width                NUMERIC(10,2) NOT NULL,
    iv_rank_at_entry            NUMERIC(5,2),           -- stored 0-100 (UW 0-1 × 100)
    underlying_price_at_entry   NUMERIC(10,2),

    b2_status                   VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                                    CHECK (b2_status IN (
                                        'PENDING', 'ENTERED', 'EXITED',
                                        'NO_CHAIN', 'NO_EXPIRY', 'NO_SHORT_LEG',
                                        'EXPIRED_UNRESOLVED'
                                    )),

    -- Entry mark captured at signal creation (or first successful chain read)
    entry_mark                  NUMERIC(10,4),          -- spread mid (debit paid per share)
    entry_captured_at           TIMESTAMPTZ,
    max_profit                  NUMERIC(12,4),          -- (spread_width - entry_mark) × 100
    max_loss                    NUMERIC(12,4),          -- entry_mark × 100

    -- Exit mark captured when signals.outcome_source = 'BAR_WALK' resolves
    exit_mark                   NUMERIC(10,4),
    exit_captured_at            TIMESTAMPTZ,
    exit_trigger                VARCHAR(10) CHECK (exit_trigger IN ('TARGET_1', 'STOP_LOSS')),
    options_pnl                 NUMERIC(12,4),          -- (exit_mark - entry_mark) × 100

    -- Audit
    outcome_source              VARCHAR(30) NOT NULL DEFAULT 'OPTIONS_PNL',
    resolution_notes            TEXT,

    UNIQUE (signal_id)          -- one expression per signal in Phase 1
);

CREATE INDEX IF NOT EXISTS idx_soe_signal_id
    ON signal_options_expressions(signal_id);

CREATE INDEX IF NOT EXISTS idx_soe_status_entered
    ON signal_options_expressions(b2_status)
    WHERE b2_status = 'ENTERED';

CREATE INDEX IF NOT EXISTS idx_soe_expiry
    ON signal_options_expressions(expiry);

COMMIT;
