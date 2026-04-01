"""One-time migration: create lightning_cards table."""
import asyncio
import asyncpg

DB_CONFIG = {
    "host": "trolley.proxy.rlwy.net",
    "port": 25012,
    "database": "railway",
    "user": "postgres",
    "password": "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",
}

DDL = """
CREATE TABLE IF NOT EXISTS lightning_cards (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    catalyst_event_id UUID,
    ticker VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('bullish', 'bearish')),
    squeeze_composite_score FLOAT DEFAULT 0,
    squeeze_tier VARCHAR(20),

    -- Position relationship
    position_relationship VARCHAR(20) DEFAULT 'UNRELATED'
        CHECK (position_relationship IN ('CONFIRMING', 'OPPOSING', 'UNRELATED')),
    related_position_id VARCHAR(50),
    related_position_details TEXT,
    action_hint TEXT,

    -- Catalyst context
    catalyst_headline TEXT,
    catalyst_category VARCHAR(30),
    thesis_impact TEXT,

    -- Lifecycle
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'dismissed', 'acted_on', 'expired')),
    expired_at TIMESTAMPTZ,

    -- Post-mortem
    price_at_generation FLOAT,
    price_at_expiry FLOAT,
    actual_move_pct FLOAT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lightning_status ON lightning_cards (status);
CREATE INDEX IF NOT EXISTS idx_lightning_created ON lightning_cards (created_at DESC);
"""

async def main():
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute(DDL)
    print("lightning_cards table created successfully")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
