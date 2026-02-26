"""
Brief 10 — One-time data migration script.
Moves existing data from 3 old position tables into unified_positions.
Deduplicates by (ticker, strike, expiry, direction).

Run once on VPS:
    cd /opt/pivot && python migrations/011_migrate_position_data.py

Safe to re-run (skips existing position_ids via ON CONFLICT DO NOTHING).
"""

import asyncio
import os
import sys
import json
from datetime import datetime, date, timezone

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


async def migrate():
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    migrated = {"positions": 0, "open_positions": 0, "options_positions": 0, "skipped": 0}

    async with pool.acquire() as conn:
        # 1. Migrate from positions table (signal pipeline)
        try:
            rows = await conn.fetch("""
                SELECT * FROM positions WHERE status = 'OPEN' OR status = 'open'
            """)
            for row in rows:
                position_id = f"MIG_SIG_{row['id']}"
                try:
                    await conn.execute("""
                        INSERT INTO unified_positions (
                            position_id, ticker, asset_type, structure, direction,
                            entry_price, quantity, stop_loss, target_1, target_2,
                            signal_id, source, account, notes, status,
                            entry_date, created_at
                        ) VALUES (
                            $1, $2, 'EQUITY', $3, $4,
                            $5, $6, $7, $8, $9,
                            $10, 'SIGNAL', $11, $12, 'OPEN',
                            COALESCE($13, NOW()), COALESCE($14, NOW())
                        )
                        ON CONFLICT (position_id) DO NOTHING
                    """,
                        position_id,
                        row["ticker"],
                        row.get("strategy"),
                        row.get("direction", "LONG"),
                        float(row["actual_entry_price"] or row["entry_price"] or 0),
                        int(row.get("quantity") or 1),
                        float(row["stop_loss"]) if row.get("stop_loss") else None,
                        float(row["target_1"]) if row.get("target_1") else None,
                        float(row["target_2"]) if row.get("target_2") else None,
                        row.get("signal_id"),
                        row.get("broker", "ROBINHOOD"),
                        row.get("notes"),
                        row.get("entry_time"),
                        row.get("created_at"),
                    )
                    migrated["positions"] += 1
                except Exception as e:
                    print(f"  Skip positions row {row['id']}: {e}")
                    migrated["skipped"] += 1
        except Exception as e:
            print(f"  positions table error: {e}")

        # 2. Migrate from open_positions table (brokerage sync)
        try:
            rows = await conn.fetch("""
                SELECT * FROM open_positions WHERE is_active = TRUE
            """)
            for row in rows:
                position_id = f"MIG_BROK_{row['id']}"
                try:
                    structure = row.get("spread_type") or ("stock" if row.get("position_type") == "STOCK" else "long_call")
                    await conn.execute("""
                        INSERT INTO unified_positions (
                            position_id, ticker, asset_type, structure, direction,
                            entry_price, quantity, cost_basis, current_price,
                            unrealized_pnl, long_strike, short_strike, expiry,
                            source, status, created_at
                        ) VALUES (
                            $1, $2, $3, $4, $5,
                            $6, $7, $8, $9,
                            $10, $11, $12, $13,
                            'SCREENSHOT_SYNC', 'OPEN', COALESCE($14, NOW())
                        )
                        ON CONFLICT (position_id) DO NOTHING
                    """,
                        position_id,
                        row["ticker"],
                        row.get("position_type", "OPTION"),
                        structure,
                        row.get("direction", "LONG"),
                        float(row["cost_per_unit"]) if row.get("cost_per_unit") else None,
                        int(row.get("quantity") or 1),
                        float(row["cost_basis"]) if row.get("cost_basis") else None,
                        float(row["current_value"]) if row.get("current_value") else None,
                        float(row["unrealized_pnl"]) if row.get("unrealized_pnl") else None,
                        float(row["strike"]) if row.get("strike") else None,
                        float(row["short_strike"]) if row.get("short_strike") else None,
                        row.get("expiry"),
                        row.get("opened_at"),
                    )
                    migrated["open_positions"] += 1
                except Exception as e:
                    print(f"  Skip open_positions row {row['id']}: {e}")
                    migrated["skipped"] += 1
        except Exception as e:
            print(f"  open_positions table error: {e}")

        # 3. Migrate from options_positions table
        try:
            rows = await conn.fetch("""
                SELECT * FROM options_positions WHERE status = 'OPEN'
            """)
            for row in rows:
                position_id = f"MIG_OPT_{row['position_id']}"
                try:
                    legs = None
                    if row.get("legs"):
                        legs = row["legs"] if isinstance(row["legs"], str) else json.dumps(row["legs"])

                    await conn.execute("""
                        INSERT INTO unified_positions (
                            position_id, ticker, asset_type, structure, direction,
                            legs, entry_price, quantity, max_loss, max_profit,
                            signal_id, source, notes, status,
                            expiry, created_at
                        ) VALUES (
                            $1, $2, 'SPREAD', $3, $4,
                            $5::jsonb, $6, 1, $7, $8,
                            $9, 'MANUAL', $10, 'OPEN',
                            $11, COALESCE($12, NOW())
                        )
                        ON CONFLICT (position_id) DO NOTHING
                    """,
                        position_id,
                        row["underlying"],
                        row.get("strategy_type"),
                        row.get("direction", "LONG"),
                        legs,
                        float(row["net_premium"]) if row.get("net_premium") else None,
                        float(row["max_loss"]) if row.get("max_loss") else None,
                        float(row["max_profit"]) if row.get("max_profit") else None,
                        row.get("signal_id"),
                        row.get("notes"),
                        row.get("entry_date"),
                        row.get("created_at"),
                    )
                    migrated["options_positions"] += 1
                except Exception as e:
                    print(f"  Skip options_positions row {row.get('position_id')}: {e}")
                    migrated["skipped"] += 1
        except Exception as e:
            print(f"  options_positions table error: {e}")

    print(f"\nMigration complete:")
    print(f"  From positions:         {migrated['positions']}")
    print(f"  From open_positions:    {migrated['open_positions']}")
    print(f"  From options_positions: {migrated['options_positions']}")
    print(f"  Skipped (dupes/errors): {migrated['skipped']}")
    print(f"  Total migrated:         {sum(v for k, v in migrated.items() if k != 'skipped')}")


if __name__ == "__main__":
    asyncio.run(migrate())
