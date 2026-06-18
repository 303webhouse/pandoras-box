"""
Migration 012 — drop the deprecated `open_positions` table.

Context (2026-06-17): `open_positions` was superseded by `unified_positions`
(migration 011). Nick confirmed `unified_positions` (via the Pandora MCP) is the
single source of truth. Reads were already migrated; the remaining writers were
the legacy `/api/portfolio/positions/{sync,close}` endpoints (removed in this
change) and a startup `CREATE TABLE IF NOT EXISTS` in postgres_client.py (also
removed, so the drop is not resurrected on boot). Table had been write-silent
since 2026-03-09; all VPS price/sync jobs disabled since 2026-02-25.

Backup of the 56 archived rows: backend/database/archive/open_positions_backup_2026-06-17.json

This is NOT auto-run. The operational drop (with backup + FK safety check) is
performed by scripts/drop_open_positions.py --commit, AFTER the code that removes
the recreate-DDL is deployed. This file is the canonical schema-change record and
is safe to re-run.

See docs/codex-briefs/2026-06-17-deprecate-open-positions-table.md
"""
import asyncio, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


async def run():
    from database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    existing = await pool.fetchval("SELECT to_regclass('public.open_positions')")
    if not existing:
        print("open_positions already absent — nothing to do.")
        return
    # FK safety
    fks = await pool.fetch(
        """SELECT conrelid::regclass::text AS t FROM pg_constraint
           WHERE contype='f' AND confrelid='public.open_positions'::regclass"""
    )
    if fks:
        raise SystemExit(f"Refusing to drop: inbound FKs from {[r['t'] for r in fks]}")
    await pool.execute("DROP TABLE open_positions")
    print("Dropped table open_positions.")


if __name__ == "__main__":
    asyncio.run(run())
