"""One-time migration: create earnings_calendar table."""
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
        CREATE TABLE IF NOT EXISTS earnings_calendar (
            id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            ticker TEXT NOT NULL,
            company_name TEXT,
            report_date DATE NOT NULL,
            fiscal_period TEXT,
            fiscal_year INTEGER,
            timing TEXT CHECK (timing IN ('BMO', 'AMC', 'TNS', NULL)),
            eps_estimate NUMERIC(10,4),
            eps_actual NUMERIC(10,4),
            revenue_estimate BIGINT,
            revenue_actual BIGINT,
            market_cap BIGINT,
            in_position_book BOOLEAN DEFAULT FALSE,
            in_watchlist BOOLEAN DEFAULT FALSE,
            position_overlap_details JSONB,
            last_updated TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_earnings_ticker_date UNIQUE (ticker, report_date)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_calendar (report_date)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_book ON earnings_calendar (in_position_book) WHERE in_position_book = TRUE")
    print("earnings_calendar table created successfully")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
