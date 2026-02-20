-- Historical factor readings for weekly audit and backtesting support.

CREATE TABLE IF NOT EXISTS factor_readings (
    id SERIAL PRIMARY KEY,
    factor_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    score FLOAT NOT NULL,
    signal TEXT,
    source TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_factor_readings_factor_time
    ON factor_readings (factor_id, timestamp DESC);
