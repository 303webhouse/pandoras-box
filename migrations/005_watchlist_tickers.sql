CREATE TABLE IF NOT EXISTS watchlist_tickers (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    sector VARCHAR(100) NOT NULL DEFAULT 'Uncategorized',
    source VARCHAR(20) NOT NULL DEFAULT 'manual',
    muted BOOLEAN NOT NULL DEFAULT false,
    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    added_at TIMESTAMP DEFAULT NOW(),
    muted_at TIMESTAMP,
    position_id INTEGER,
    notes VARCHAR(200),
    UNIQUE(symbol)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_sector ON watchlist_tickers(sector);
CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_source ON watchlist_tickers(source);
CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_muted ON watchlist_tickers(muted);
CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_priority ON watchlist_tickers(priority);
