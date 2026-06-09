"""
Phase 1 (canonical model) — normalize structure + direction vocabulary in
unified_positions, the canonical table Olympus reads.

Verified mappings (every case checked against strikes/structure first):

STRUCTURE -> canonical (*_debit_spread / *_credit_spread):
  BEAR_PUT_SPREAD  -> put_debit_spread   (2 rows; long>short put, debit)
  BULL_CALL_SPREAD -> call_debit_spread  (1 row; long<short call, debit)
  put_spread       -> put_debit_spread   (4 rows; all long>short put, BEARISH = debit)
  NULL             -> left as-is          (3 rows: SMH/ONON/IWM, no strikes — flagged)

DIRECTION -> canonical LONG/SHORT (bias axis: LONG=bullish, SHORT=bearish, as the
existing 132 LONG/SHORT rows already use it — put_debit_spread is SHORT, call_debit
is LONG):
  BULLISH, bullish -> LONG
  BEARISH, bearish -> SHORT
  MIXED            -> LONG  (1 row; its structure is call_debit_spread = bullish)

Pure relabel: no realized_pnl / row-count change. Idempotent. Reversible.

Run: python scripts/migrate_unified_vocab.py
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

STRUCTURE_MAP = {
    "BEAR_PUT_SPREAD": "put_debit_spread",
    "BULL_CALL_SPREAD": "call_debit_spread",
    "put_spread": "put_debit_spread",
}
DIRECTION_MAP = {
    "BULLISH": "LONG",
    "bullish": "LONG",
    "BEARISH": "SHORT",
    "bearish": "SHORT",
    "MIXED": "LONG",
}


async def dist(conn, col):
    rows = await conn.fetch(
        f"SELECT {col} AS v, COUNT(*) AS n FROM unified_positions GROUP BY {col} ORDER BY n DESC"
    )
    return {(r["v"] if r["v"] is not None else "NULL"): r["n"] for r in rows}


async def main():
    conn = await asyncpg.connect(**DB)
    try:
        print("=== unified_positions vocab normalization ===\n")

        total_before = await conn.fetchval("SELECT COUNT(*) FROM unified_positions")
        pnl_before = await conn.fetchval(
            "SELECT ROUND(SUM(realized_pnl)::numeric,2) FROM unified_positions WHERE status='CLOSED'"
        )
        print(f"Rows: {total_before} | CLOSED realized_pnl: ${pnl_before} (must be unchanged after)\n")

        print("STRUCTURE before:", await dist(conn, "structure"))
        print("DIRECTION before:", await dist(conn, "direction"))

        # Apply structure mappings
        struct_changed = 0
        for old, new in STRUCTURE_MAP.items():
            n = await conn.fetchval(
                "WITH u AS (UPDATE unified_positions SET structure=$2, updated_at=NOW() "
                "WHERE structure=$1 RETURNING 1) SELECT COUNT(*) FROM u",
                old, new,
            )
            if n:
                print(f"  structure {old} -> {new}: {n}")
            struct_changed += n

        # Apply direction mappings
        dir_changed = 0
        for old, new in DIRECTION_MAP.items():
            n = await conn.fetchval(
                "WITH u AS (UPDATE unified_positions SET direction=$2, updated_at=NOW() "
                "WHERE direction=$1 RETURNING 1) SELECT COUNT(*) FROM u",
                old, new,
            )
            if n:
                print(f"  direction {old} -> {new}: {n}")
            dir_changed += n

        print(f"\nStructure rows relabeled: {struct_changed} | Direction rows relabeled: {dir_changed}")
        print("\nSTRUCTURE after:", await dist(conn, "structure"))
        print("DIRECTION after:", await dist(conn, "direction"))

        total_after = await conn.fetchval("SELECT COUNT(*) FROM unified_positions")
        pnl_after = await conn.fetchval(
            "SELECT ROUND(SUM(realized_pnl)::numeric,2) FROM unified_positions WHERE status='CLOSED'"
        )
        print(f"\nRows: {total_after} (was {total_before}) | "
              f"CLOSED realized_pnl: ${pnl_after} (was ${pnl_before})")
        assert total_after == total_before, "row count changed!"
        assert pnl_after == pnl_before, "P&L changed!"

        nulls = await conn.fetch(
            "SELECT id, ticker, direction FROM unified_positions WHERE structure IS NULL ORDER BY id"
        )
        if nulls:
            print("\n!! Structure still NULL (no strikes — needs manual classification):")
            for r in nulls:
                print(f"   id {r['id']}  {r['ticker']}  {r['direction']}")
        print("\nDone.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
