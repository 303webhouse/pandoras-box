"""One-time migration: create trade_watchlist table."""
import asyncio
import asyncpg

DB_CONFIG = {
    "host": "trolley.proxy.rlwy.net",
    "port": 25012,
    "database": "railway",
    "user": "postgres",
    "password": "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",
}

async def main():
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_watchlist (
            id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
            entry_target NUMERIC(10,2),
            current_price NUMERIC(10,2),
            distance_to_target_pct NUMERIC(6,2),
            thesis_note TEXT,
            committee_grade TEXT CHECK (committee_grade IN ('A', 'A-', 'B+', 'B', 'B-', 'C', NULL)),
            source TEXT DEFAULT 'MANUAL' CHECK (source IN ('MANUAL', 'UW_FLOW', 'SCANNER', 'COMMITTEE')),
            bucket TEXT CHECK (bucket IN ('THESIS', 'TACTICAL', NULL)),
            next_earnings_date DATE,
            earnings_timing TEXT CHECK (earnings_timing IN ('BMO', 'AMC', 'TNS', NULL)),
            alert_fired BOOLEAN DEFAULT FALSE,
            alert_fired_at TIMESTAMPTZ,
            is_active BOOLEAN DEFAULT TRUE,
            added_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_watchlist_ticker UNIQUE (ticker)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_active ON trade_watchlist (is_active) WHERE is_active = TRUE")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_direction ON trade_watchlist (direction)")
    print("trade_watchlist table created successfully")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
