"""
Read-only audit script for rh-mcp-integration-audit-2026-05-27.
SELECT-only queries against price_history. No writes, no DDL.
Run via: railway run --service pandoras-box -- python scripts/audit_price_history_inspect.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import asyncpg


async def _connect():
    public_url = os.getenv("DATABASE_PUBLIC_URL")
    if public_url:
        return await asyncpg.create_pool(dsn=public_url, min_size=1, max_size=2)
    # Fall back to discrete vars (in-Railway-network only)
    return await asyncpg.create_pool(
        host=os.getenv("DB_HOST") or "localhost",
        port=int(os.getenv("DB_PORT") or 5432),
        database=os.getenv("DB_NAME") or "pandoras_box",
        user=os.getenv("DB_USER") or "postgres",
        password=os.getenv("DB_PASSWORD") or "postgres",
        min_size=1,
        max_size=2,
    )


async def main() -> None:
    pool = await _connect()
    async with pool.acquire() as conn:
        # 1. Schema
        print("=== SCHEMA: price_history ===")
        cols = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'price_history'
            ORDER BY ordinal_position
            """
        )
        for c in cols:
            print(f"  {c['column_name']:25} {c['data_type']:25} nullable={c['is_nullable']:3} default={c['column_default']}")

        # 2. Indexes
        print("=== INDEXES: price_history ===")
        idx = await conn.fetch(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'price_history'"
        )
        for i in idx:
            print(f"  {i['indexname']}")
            print(f"    {i['indexdef']}")

        # 3. Sizes
        print("=== SIZES ===")
        table_size_bytes = await conn.fetchval("SELECT pg_total_relation_size('price_history')")
        table_size_pretty = await conn.fetchval("SELECT pg_size_pretty(pg_total_relation_size('price_history'))")
        db_size_bytes = await conn.fetchval("SELECT pg_database_size(current_database())")
        db_size_pretty = await conn.fetchval("SELECT pg_size_pretty(pg_database_size(current_database()))")
        print(f"  price_history table: {table_size_pretty} ({table_size_bytes:,} bytes)")
        print(f"  whole database:      {db_size_pretty} ({db_size_bytes:,} bytes)")

        # 4. Total row count
        row_count = await conn.fetchval("SELECT COUNT(*) FROM price_history")
        print(f"  total rows:          {row_count:,}")

        # 5. Min/max timestamps
        print("=== TIMESTAMP RANGE ===")
        ts_min = await conn.fetchval("SELECT MIN(timestamp) FROM price_history")
        ts_max = await conn.fetchval("SELECT MAX(timestamp) FROM price_history")
        print(f"  oldest: {ts_min}")
        print(f"  newest: {ts_max}")

        # 6. By-timeframe breakdown
        print("=== ROWS BY TIMEFRAME ===")
        tf = await conn.fetch(
            """
            SELECT timeframe, COUNT(*) AS rows, MIN(timestamp) AS oldest, MAX(timestamp) AS newest,
                   COUNT(DISTINCT ticker) AS tickers
            FROM price_history
            GROUP BY timeframe
            ORDER BY rows DESC
            """
        )
        for r in tf:
            print(
                f"  tf={r['timeframe']:6} rows={r['rows']:>10,} tickers={r['tickers']:>4} "
                f"oldest={r['oldest']} newest={r['newest']}"
            )

        # 7. Recent write rate (last hour, last 24h, last 7d) — use timestamp column
        #    since price_history has no inserted_at column (per schema 1).
        print("=== RECENT ROWS BY TIMESTAMP (proxy for write rate) ===")
        windows = [
            ("last 1h", "1 hour"),
            ("last 24h", "24 hours"),
            ("last 7d", "7 days"),
        ]
        for label, span in windows:
            n = await conn.fetchval(
                f"SELECT COUNT(*) FROM price_history WHERE timestamp > NOW() - INTERVAL '{span}'"
            )
            print(f"  {label}: {n:,} rows")

        # 8. Top tickers by row count (top 15)
        print("=== TOP 15 TICKERS BY ROW COUNT ===")
        tops = await conn.fetch(
            """
            SELECT ticker, COUNT(*) AS rows
            FROM price_history
            GROUP BY ticker
            ORDER BY rows DESC
            LIMIT 15
            """
        )
        for r in tops:
            print(f"  {r['ticker']:8} {r['rows']:>10,}")

        # 9. Total distinct tickers
        n_tickers = await conn.fetchval("SELECT COUNT(DISTINCT ticker) FROM price_history")
        print(f"=== DISTINCT TICKERS: {n_tickers} ===")

        # 10. Avg row width estimate via pg_class.relpages * 8KB / reltuples
        print("=== AVG ROW SIZE (pg_class estimate) ===")
        row_size = await conn.fetchrow(
            """
            SELECT relpages, reltuples,
                   CASE WHEN reltuples > 0
                        THEN (relpages * 8192.0 / reltuples)::numeric(10,1)
                        ELSE NULL END AS avg_bytes_per_row
            FROM pg_class
            WHERE relname = 'price_history'
            """
        )
        if row_size:
            print(
                f"  relpages={row_size['relpages']} reltuples={row_size['reltuples']:.0f} "
                f"avg_bytes_per_row={row_size['avg_bytes_per_row']}"
            )

        # 11. Top 5 tables by size (to put price_history in context)
        print("=== TOP 5 LARGEST TABLES IN DB ===")
        bigtab = await conn.fetch(
            """
            SELECT relname AS table_name,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size_pretty,
                   pg_total_relation_size(c.oid) AS size_bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname = 'public'
            ORDER BY pg_total_relation_size(c.oid) DESC
            LIMIT 5
            """
        )
        for r in bigtab:
            print(f"  {r['table_name']:30} {r['size_pretty']:12} ({r['size_bytes']:,} bytes)")

        # 12. Row-distribution by day for last 14 days
        print("=== ROWS BY DAY (last 14d, by timestamp not insert-time) ===")
        days = await conn.fetch(
            """
            SELECT DATE_TRUNC('day', timestamp)::date AS day,
                   COUNT(*) AS rows
            FROM price_history
            WHERE timestamp > NOW() - INTERVAL '14 days'
            GROUP BY 1
            ORDER BY 1 DESC
            """
        )
        for r in days:
            print(f"  {r['day']}  rows={r['rows']:,}")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
