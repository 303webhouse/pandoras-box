"""One-time migration: create squeeze_scores table."""
import asyncio
import asyncpg
import os

DB_CONFIG = {
    "host": "trolley.proxy.rlwy.net",
    "port": 25012,
    "database": "railway",
    "user": "postgres",
    "password": "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",
}

DDL = """
CREATE TABLE IF NOT EXISTS squeeze_scores (
    ticker VARCHAR(10) PRIMARY KEY,
    short_pct_float FLOAT DEFAULT 0,
    days_to_cover FLOAT DEFAULT 0,
    shares_short BIGINT DEFAULT 0,
    short_trend VARCHAR(20) DEFAULT 'stable',
    price_vs_short_entry_pct FLOAT DEFAULT 0,
    uw_call_flow_score FLOAT DEFAULT 0,
    uw_put_call_ratio FLOAT DEFAULT 1.0,
    sector_velocity FLOAT DEFAULT 0,
    composite_score FLOAT DEFAULT 0,
    squeeze_tier VARCHAR(20) DEFAULT 'low',
    nick_has_position BOOLEAN DEFAULT FALSE,
    nick_position_direction VARCHAR(10),
    nick_position_id VARCHAR(50),
    data_source VARCHAR(20) DEFAULT 'unknown',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_squeeze_composite ON squeeze_scores (composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_squeeze_tier ON squeeze_scores (squeeze_tier);
"""

async def main():
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute(DDL)
    print("squeeze_scores table created successfully")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
