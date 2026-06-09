"""
Migration 2: make rh_trade_history dedup NULL-safe (fixes OEXP duplication).

Pre-existing bug, separate from the occurrence fix: OEXP (expiration) rows carry
price = NULL. Under a default UNIQUE constraint Postgres treats NULLs as DISTINCT,
so two OEXP rows with identical content but NULL price never conflict — every
import re-inserts all expirations. Result: 59 OEXP rows for 29 real events.

Fix:
  1. De-duplicate existing OEXP rows (keep lowest id per distinct event).
  2. Re-create the dedup constraint as UNIQUE NULLS NOT DISTINCT so NULL-bearing
     rows (OEXP) collide correctly and stay idempotent. Non-NULL rows (option
     legs, stock) are unaffected — their occurrence-based dedup still holds.

Requires PostgreSQL 15+ (NULLS NOT DISTINCT). Idempotent: safe to re-run.

Run: python scripts/migrate_rh_oexp_nulls.py
"""

import asyncio
import os

import asyncpg

DB = {
    "host": os.getenv("DB_HOST") or "trolley.proxy.rlwy.net",
    "port": int(os.getenv("DB_PORT") or 25012),
    "database": os.getenv("DB_NAME") or "railway",
    "user": os.getenv("DB_USER") or "postgres",
    "password": os.getenv("DB_PASSWORD") or "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",
}

CONSTRAINT = "rh_trade_history_dedup_key"


async def main():
    conn = await asyncpg.connect(**DB)
    try:
        print("=== rh_trade_history NULL-safe dedup migration ===\n")

        oexp_before = await conn.fetchval(
            "SELECT COUNT(*) FROM rh_trade_history WHERE trans_code = 'OEXP'"
        )
        distinct_before = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT (activity_date, ticker, description, trans_code, quantity, occurrence))
            FROM rh_trade_history WHERE trans_code = 'OEXP'
            """
        )
        print(f"OEXP rows before: {oexp_before} ({distinct_before} distinct events)")

        # 1. De-duplicate OEXP rows: keep the lowest id per distinct event.
        deleted = await conn.fetchval(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                         PARTITION BY activity_date, ticker, description, trans_code, quantity, occurrence
                         ORDER BY id
                       ) AS rn
                FROM rh_trade_history
                WHERE trans_code = 'OEXP'
            )
            DELETE FROM rh_trade_history
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            RETURNING id
            """
        )
        # fetchval returns first id only; use a count query instead
        oexp_after = await conn.fetchval(
            "SELECT COUNT(*) FROM rh_trade_history WHERE trans_code = 'OEXP'"
        )
        print(f"[1] De-duplicated OEXP rows: {oexp_before} -> {oexp_after} "
              f"(removed {oexp_before - oexp_after})")

        # 2. Re-create constraint as NULLS NOT DISTINCT
        await conn.execute(
            f'ALTER TABLE rh_trade_history DROP CONSTRAINT IF EXISTS {CONSTRAINT}'
        )
        await conn.execute(
            f"""
            ALTER TABLE rh_trade_history
            ADD CONSTRAINT {CONSTRAINT}
            UNIQUE NULLS NOT DISTINCT
            (activity_date, ticker, description, trans_code, quantity, price, occurrence)
            """
        )
        print(f"[2] Re-created {CONSTRAINT} as UNIQUE NULLS NOT DISTINCT")

        # Verify
        defn = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = $1",
            CONSTRAINT,
        )
        print(f"\nConstraint now: {defn}")

        total = await conn.fetchval("SELECT COUNT(*) FROM rh_trade_history")
        opt = await conn.fetchval(
            "SELECT COUNT(*) FROM rh_trade_history WHERE is_option AND trans_code IN ('BTO','STO','BTC','STC')"
        )
        print(f"\nFinal: {total} total rows | {opt} option-leg rows | {oexp_after} OEXP rows")
        print("Migration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
