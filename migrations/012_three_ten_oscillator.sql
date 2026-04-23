-- Migration 012: 3-10 Oscillator infrastructure
-- Adds gate_type column to signals table for Holy Grail shadow-mode A/B comparison.
-- Creates divergence_events table for persisted 3-10 divergence firings.
-- Idempotent: safe to re-run.

-- 1. signals.gate_type — tags which gate (RSI, 3-10, or both) qualified a signal.
--    VARCHAR(20) accommodates future gate labels beyond "rsi"/"3-10"/"both".
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS gate_type VARCHAR(20);

CREATE INDEX IF NOT EXISTS idx_signals_gate_type
    ON signals(gate_type) WHERE gate_type IS NOT NULL;

-- 2. divergence_events — persistent log of 3-10 divergence firings for analysis.
CREATE TABLE IF NOT EXISTS divergence_events (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_timestamp TIMESTAMPTZ NOT NULL,
    div_type TEXT NOT NULL CHECK (div_type IN ('bull', 'bear')),
    fast_pivot_prev NUMERIC(12, 6),
    fast_pivot_curr NUMERIC(12, 6),
    price_pivot_prev NUMERIC(12, 6),
    price_pivot_curr NUMERIC(12, 6),
    threshold_used NUMERIC(5, 4),
    lookback_used INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, timeframe, bar_timestamp, div_type)
);

CREATE INDEX IF NOT EXISTS idx_divergence_events_ticker_time
    ON divergence_events(ticker, bar_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_divergence_events_type
    ON divergence_events(div_type, bar_timestamp DESC);
