"""
Migration: fix rh_trade_history dedup so genuine identical same-day fills persist.

Root cause: UNIQUE(activity_date, ticker, description, trans_code, quantity, price)
physically prevents storing two real fills that are identical (same day, same
price). Robinhood CSVs carry no fill/order ID, so the importer's ON CONFLICT
DO NOTHING silently dropped the 2nd+ copy. Confirmed: 79 fills dropped across
~40 positions (e.g. XLY 6/18 100/90 showed 5x, real is 6x).

Fix: add an `occurrence` column (0-indexed copy number within an import batch)
and move the UNIQUE constraint to include it. Existing rows are all effectively
occurrence 0 (the old constraint guaranteed at most one per content-tuple), so
DEFAULT 0 is correct and no row rewrite is needed. A subsequent re-import then
inserts ONLY the previously-dropped fills (occurrence >= 1) and skips everything
already present — non-destructive and idempotent.

Idempotent: safe to run multiple times.

Run: python scripts/migrate_rh_occurrence.py
"""

import asyncio
import os

import asyncpg

# Public Railway Postgres proxy (same endpoint the import CLI uses locally)
DB = {
    "host": os.getenv("DB_HOST") or "trolley.proxy.rlwy.net",
    "port": int(os.getenv("DB_PORT") or 25012),
    "database": os.getenv("DB_NAME") or "railway",
    "user": os.getenv("DB_USER") or "postgres",
    "password": os.getenv("DB_PASSWORD") or "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",
}

OLD_CONSTRAINT = "rh_trade_history_activity_date_ticker_description_trans_cod_key"
NEW_CONSTRAINT = "rh_trade_history_dedup_key"


async def column_exists(conn, table, col) -> bool:
    return await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = $1 AND column_name = $2
        )
        """,
        table, col,
    )


async def constraint_exists(conn, name) -> bool:
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = $1)", name
    )


async def main():
    conn = await asyncpg.connect(**DB)
    try:
        print("=== rh_trade_history dedup migration ===\n")

        before = await conn.fetchval("SELECT COUNT(*) FROM rh_trade_history")
        print(f"Rows before: {before}")
        print("Constraints before:")
        for r in await conn.fetch(
            "SELECT conname FROM pg_constraint WHERE conrelid='rh_trade_history'::regclass ORDER BY conname"
        ):
            print(f"  - {r['conname']}")

        # 1. Add occurrence column (idempotent)
        if await column_exists(conn, "rh_trade_history", "occurrence"):
            print("\n[1] occurrence column already exists — skipping add")
        else:
            await conn.execute(
                "ALTER TABLE rh_trade_history ADD COLUMN occurrence SMALLINT NOT NULL DEFAULT 0"
            )
            print("\n[1] Added occurrence column (DEFAULT 0)")

        # 2. Drop old constraint (idempotent)
        if await constraint_exists(conn, OLD_CONSTRAINT):
            await conn.execute(
                f'ALTER TABLE rh_trade_history DROP CONSTRAINT "{OLD_CONSTRAINT}"'
            )
            print(f"[2] Dropped old constraint {OLD_CONSTRAINT}")
        else:
            print(f"[2] Old constraint {OLD_CONSTRAINT} not present — skipping")

        # 3. Add new constraint including occurrence (idempotent)
        if await constraint_exists(conn, NEW_CONSTRAINT):
            print(f"[3] New constraint {NEW_CONSTRAINT} already exists — skipping")
        else:
            await conn.execute(
                f"""
                ALTER TABLE rh_trade_history
                ADD CONSTRAINT {NEW_CONSTRAINT}
                UNIQUE (activity_date, ticker, description, trans_code, quantity, price, occurrence)
                """
            )
            print(f"[3] Added new constraint {NEW_CONSTRAINT} (+occurrence)")

        print("\nConstraints after:")
        for r in await conn.fetch(
            "SELECT conname FROM pg_constraint WHERE conrelid='rh_trade_history'::regclass ORDER BY conname"
        ):
            print(f"  - {r['conname']}")
        after = await conn.fetchval("SELECT COUNT(*) FROM rh_trade_history")
        print(f"\nRows after: {after} (unchanged — migration is non-destructive)")
        print("\nMigration complete. Re-run the import to recover dropped fills.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
