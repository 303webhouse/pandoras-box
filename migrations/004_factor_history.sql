CREATE TABLE IF NOT EXISTS factor_history (
    id SERIAL PRIMARY KEY,
    factor_name VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL,
    bias VARCHAR(20) NOT NULL,
    data JSONB,
    collected_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_factor_history_name_time
    ON factor_history (factor_name, collected_at DESC);
