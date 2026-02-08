-- Watchlist v2: Migrate from JSON file to PostgreSQL
-- Run once. Safe to run multiple times (uses IF NOT EXISTS / ON CONFLICT).
--
-- Location: migrations/003_watchlist_config.sql

CREATE TABLE IF NOT EXISTS watchlist_config (
    id SERIAL PRIMARY KEY,
    sector_name VARCHAR(100) NOT NULL,
    tickers JSONB NOT NULL DEFAULT '[]',
    etf VARCHAR(10),
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_watchlist_sector_name
ON watchlist_config(sector_name);

-- Seed with default watchlist (matches DEFAULT_WATCHLIST in watchlist.py)
INSERT INTO watchlist_config (sector_name, tickers, etf, sort_order) VALUES
    ('Technology',              '["AAPL","MSFT","NVDA","GOOGL","AMD","META"]', 'XLK', 1),
    ('Consumer Discretionary',  '["AMZN","TSLA","NFLX"]',                     'XLY', 2),
    ('Financials',              '["JPM","BAC","GS"]',                         'XLF', 3),
    ('Healthcare',              '["UNH","JNJ","PFE"]',                        'XLV', 4),
    ('Energy',                  '["XOM","CVX"]',                              'XLE', 5),
    ('Industrials',             '["CAT","BA","UPS"]',                         'XLI', 6),
    ('Index ETFs',              '["SPY","QQQ","IWM"]',                        NULL,  7)
ON CONFLICT (sector_name) DO NOTHING;
