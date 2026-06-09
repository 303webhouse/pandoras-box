"""
Migration 3: de-duplicate cash_flows and make CSV cash-flow import idempotent.

Same root pattern as the trade-history bug: the importer's cash_flows INSERT had
no ON CONFLICT guard and no unique constraint, so every CSV import re-inserted
all ACH rows. Result: 39 csv rows for 12 distinct events (3-4 copies each).

Fix:
  1. De-duplicate csv-sourced cash_flows (keep lowest id per distinct event).
     Manual-sourced rows are left untouched.
  2. Add a NULLS NOT DISTINCT unique constraint keyed on the natural event so
     re-imports skip. imported_from is part of the key, so a manual and a csv
     copy of the same withdrawal are allowed to coexist (that cross-source
     overlap is a reconciliation judgment, not a mechanical dupe).

Note surfaced for Nick: 2026-03-06 and 2026-03-11 (both -$400) exist in BOTH
csv ('ACH Withdrawal') and manual ('Withdrawal') sources — same real events,
double-counted across sources. Not auto-merged here; decide which to keep.

Idempotent: safe to re-run.

Run: python scripts/migrate_rh_cashflows.py
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

CONSTRAINT = "cash_flows_dedup_key"


async def main():
    conn = await asyncpg.connect(**DB)
    try:
        print("=== cash_flows de-dup + idempotency migration ===\n")

        before = await conn.fetchval("SELECT COUNT(*) FROM cash_flows")
        csv_before = await conn.fetchval(
            "SELECT COUNT(*) FROM cash_flows WHERE imported_from = 'csv'"
        )
        print(f"Rows before: {before} (csv: {csv_before})")

        # 1. De-duplicate csv-sourced rows only (keep lowest id per distinct event)
        await conn.execute(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                         PARTITION BY account_name, flow_type, amount, description, activity_date
                         ORDER BY id
                       ) AS rn
                FROM cash_flows
                WHERE imported_from = 'csv'
            )
            DELETE FROM cash_flows
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            """
        )
        csv_after = await conn.fetchval(
            "SELECT COUNT(*) FROM cash_flows WHERE imported_from = 'csv'"
        )
        print(f"[1] De-duplicated csv cash_flows: {csv_before} -> {csv_after} "
              f"(removed {csv_before - csv_after})")

        # 2. Add NULLS NOT DISTINCT unique constraint (idempotent)
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = $1)", CONSTRAINT
        )
        if exists:
            print(f"[2] Constraint {CONSTRAINT} already exists — skipping")
        else:
            await conn.execute(
                f"""
                ALTER TABLE cash_flows
                ADD CONSTRAINT {CONSTRAINT}
                UNIQUE NULLS NOT DISTINCT
                (account_name, flow_type, amount, description, activity_date, imported_from)
                """
            )
            print(f"[2] Added {CONSTRAINT} (UNIQUE NULLS NOT DISTINCT)")

        after = await conn.fetchval("SELECT COUNT(*) FROM cash_flows")
        print(f"\nRows after: {after}")

        # Surface the cross-source overlap for Nick
        overlap = await conn.fetch(
            """
            SELECT activity_date::date AS d, amount,
                   COUNT(*) FILTER (WHERE imported_from='csv') AS csv,
                   COUNT(*) FILTER (WHERE imported_from='manual') AS manual
            FROM cash_flows
            GROUP BY activity_date, amount
            HAVING COUNT(*) FILTER (WHERE imported_from='csv') > 0
               AND COUNT(*) FILTER (WHERE imported_from='manual') > 0
            ORDER BY d
            """
        )
        if overlap:
            print("\n!! csv <-> manual overlap (same event in both sources — decide which to keep):")
            for r in overlap:
                print(f"   {r['d']}  ${r['amount']}  (csv x{r['csv']}, manual x{r['manual']})")
        print("\nMigration complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
