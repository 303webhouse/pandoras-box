-- Migration 018: create signal_forward_returns
-- A3's forward-return grades — one row per (signal_id, horizon_days).
-- Direction-adjusted: positive = correct call regardless of LONG/SHORT.
-- Truth table: signals.outcome_source='FWD_RETURN' is a secondary label;
-- these rows are the actual grade data.
--
-- Rollback:
--   DROP TABLE IF EXISTS signal_forward_returns;
--   (No FK-dependent tables; drops cleanly.)

BEGIN;

CREATE TABLE IF NOT EXISTS signal_forward_returns (
    id                  SERIAL PRIMARY KEY,
    signal_id           TEXT NOT NULL
                            REFERENCES signals(signal_id) ON DELETE CASCADE,
    horizon_days        INTEGER NOT NULL CHECK (horizon_days IN (1, 5)),
    reference_price     NUMERIC(12, 4) NOT NULL,  -- signals.entry_price at grade time
    horizon_close_price NUMERIC(12, 4),            -- UW bar close on Nth trading day; NULL until available
    fwd_return_pct      NUMERIC(10, 6),            -- direction-adjusted; NULL until horizon bar exists
    computed_at         TIMESTAMPTZ,               -- when fwd_return_pct was last written
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (signal_id, horizon_days)               -- one grade per signal per horizon
);

CREATE INDEX IF NOT EXISTS idx_sfr_signal_id
    ON signal_forward_returns(signal_id);

CREATE INDEX IF NOT EXISTS idx_sfr_pending
    ON signal_forward_returns(horizon_days)
    WHERE fwd_return_pct IS NULL;                  -- hot scan: unresolved grades awaiting their bar

COMMIT;
