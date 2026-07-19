#!/usr/bin/env python3
"""One-time migration: create catalyst_events + system_config tables."""
import asyncio
import json
import asyncpg


async def main():
    pool = await asyncpg.create_pool(
        host="trolley.proxy.rlwy.net",
        port=25012,
        database="railway",
        user="postgres",
        password="sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",
        min_size=1,
        max_size=2,
    )
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS catalyst_events (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                event_type TEXT NOT NULL DEFAULT 'velocity_breach',
                tier INTEGER NOT NULL DEFAULT 1 CHECK (tier BETWEEN 1 AND 3),
                trigger_ticker TEXT NOT NULL,
                trigger_move_pct NUMERIC(6,2),
                trigger_timeframe TEXT DEFAULT '30min',
                correlated_tickers JSONB DEFAULT '[]'::jsonb,
                headline_summary TEXT,
                catalyst_category TEXT,
                pivot_analysis TEXT,
                sector_velocity JSONB DEFAULT '{}'::jsonb,
                trip_wire_status JSONB DEFAULT '{}'::jsonb,
                dismissed BOOLEAN DEFAULT FALSE,
                dismissed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print("catalyst_events: OK")

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalyst_events_created ON catalyst_events (created_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalyst_events_tier ON catalyst_events (tier)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalyst_events_dismissed ON catalyst_events (dismissed)"
        )
        print("indexes: OK")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print("system_config: OK")

        config = json.dumps({
            "tickers": {
                "SPY": {"threshold_pct": 1.0, "timeframe_min": 30, "category": "broad_market"},
                "QQQ": {"threshold_pct": 1.0, "timeframe_min": 30, "category": "tech"},
                "SMH": {"threshold_pct": 1.5, "timeframe_min": 30, "category": "semis"},
                "XLF": {"threshold_pct": 1.0, "timeframe_min": 30, "category": "financials"},
                "HYG": {"threshold_pct": 0.5, "timeframe_min": 30, "category": "credit"},
                "IYR": {"threshold_pct": 1.0, "timeframe_min": 30, "category": "real_estate"},
                "TLT": {"threshold_pct": 1.0, "timeframe_min": 30, "category": "bonds"},
                "USO": {"threshold_pct": 2.0, "timeframe_min": 30, "category": "oil"},
                "GLD": {"threshold_pct": 1.0, "timeframe_min": 30, "category": "safe_haven"},
                "IBIT": {"threshold_pct": 2.0, "timeframe_min": 30, "category": "crypto"},
            },
            "correlation_groups": {
                "credit_event": ["XLF", "HYG", "IYR"],
                "risk_off": ["SPY", "QQQ", "SMH"],
                "deescalation": ["USO", "GLD", "TLT"],
                "full_reversal": ["SPY", "QQQ", "SMH", "XLF", "HYG"],
            },
            "correlation_window_minutes": 5,
            "correlation_min_tickers": 2,
            "vps_trigger_url": "http://188.245.250.2:8000/api/hermes/trigger",
            "vps_api_key": "FFlSBL-YT-69cLMa8G_NtMOMYYMMo89vnQL-Az8AqI0",
            "cooldown_minutes": 15,
        })
        await conn.execute(
            "INSERT INTO system_config (key, value) VALUES ('hermes_watchlist', $1::jsonb) ON CONFLICT (key) DO NOTHING",
            config,
        )
        print("hermes_watchlist config: OK")

    await pool.close()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(main())
