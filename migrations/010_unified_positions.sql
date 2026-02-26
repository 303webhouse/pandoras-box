-- Brief 10: Unified positions table
-- Replaces fragmented positions + open_positions + options_positions system
-- Safe to run multiple times (CREATE IF NOT EXISTS)

CREATE TABLE IF NOT EXISTS unified_positions (
    id              SERIAL PRIMARY KEY,
    position_id     TEXT UNIQUE NOT NULL,

    -- What
    ticker          TEXT NOT NULL,
    asset_type      TEXT NOT NULL DEFAULT 'OPTION',
    structure       TEXT,
    direction       TEXT NOT NULL,
    legs            JSONB,

    -- Entry
    entry_price     NUMERIC,
    entry_date      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    quantity        INTEGER NOT NULL DEFAULT 1,
    cost_basis      NUMERIC,

    -- Risk (auto-calculated for spreads, user-provided for equity)
    max_loss        NUMERIC,
    max_profit      NUMERIC,
    stop_loss       NUMERIC,
    target_1        NUMERIC,
    target_2        NUMERIC,
    breakeven       NUMERIC[],

    -- Current state
    current_price   NUMERIC,
    unrealized_pnl  NUMERIC,
    price_updated_at TIMESTAMPTZ,

    -- Options-specific
    expiry          DATE,
    dte             INTEGER,
    long_strike     NUMERIC,
    short_strike    NUMERIC,

    -- Metadata
    source          TEXT NOT NULL DEFAULT 'MANUAL',
    signal_id       TEXT,
    account         TEXT DEFAULT 'ROBINHOOD',
    notes           TEXT,
    tags            TEXT[],

    -- Lifecycle
    status          TEXT NOT NULL DEFAULT 'OPEN',
    exit_price      NUMERIC,
    exit_date       TIMESTAMPTZ,
    realized_pnl    NUMERIC,
    trade_outcome   TEXT,
    trade_id        INTEGER,

    -- Housekeeping
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unified_positions_status ON unified_positions(status);
CREATE INDEX IF NOT EXISTS idx_unified_positions_ticker ON unified_positions(ticker);
CREATE INDEX IF NOT EXISTS idx_unified_positions_signal ON unified_positions(signal_id);
