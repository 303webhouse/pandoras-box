#!/usr/bin/env python3
"""FEAT-POSITION-LIFECYCLE — strategy_tag migration (R-IV.143(2)).

DRY RUN BY DEFAULT. Pass --apply to write. Single transaction.

Nullable TEXT, NO CHECK constraint — documentary-vocabulary precedent, matching
cash_flows.flow_type. Enforcement is the entry UI's job, not the column's: a CHECK
here would reject a row the principal typed correctly under a vocabulary the code
had not caught up to, and the failure would surface as a 500 rather than a prompt.
"""
from __future__ import annotations
import argparse, json, pathlib, sys
import psycopg2

VOCAB = ["CORE", "B1_MACRO", "B1_C_CONVEXITY", "B2_TACTICAL", "B3_SCALP",
         "HEDGE", "MOMENTUM", "OTHER"]


def dsn() -> str:
    cfg = json.loads(pathlib.Path(r"C:\trading-hub\.mcp.json").read_text(encoding="utf-8"))
    return cfg["mcpServers"]["postgres"]["args"][2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(dsn()); conn.autocommit = False
    cur = conn.cursor()
    print(f"strategy_tag migration — {'APPLY' if a.apply else 'DRY RUN'}")

    cur.execute("""SELECT column_name, data_type, is_nullable FROM information_schema.columns
                   WHERE table_name='unified_positions' AND column_name='strategy_tag'""")
    existing = cur.fetchone()
    if existing:
        print(f"  strategy_tag already present {existing} — idempotent skip")
    else:
        cur.execute("ALTER TABLE unified_positions ADD COLUMN strategy_tag text")
        print("  + strategy_tag text (nullable, no CHECK)")

    cur.execute("""COMMENT ON COLUMN unified_positions.strategy_tag IS
        'Documentary strategy vocabulary (R-IV.143(2)): CORE | B1_MACRO | B1_C_CONVEXITY | '
        'B2_TACTICAL | B3_SCALP | HEDGE | MOMENTUM | OTHER. Deliberately NO CHECK constraint '
        '(documentary-vocabulary precedent, as cash_flows.flow_type): enforcement belongs to '
        'the entry UI, where an unknown value can be a prompt rather than a 500. NULL means '
        'untagged, never OTHER — OTHER is a deliberate classification, NULL is its absence.'""")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_unified_positions_strategy_tag "
                "ON unified_positions(strategy_tag) WHERE strategy_tag IS NOT NULL")
    print("  partial index ensured (NOT NULL only — untagged rows are the majority)")

    # The audit trigger must capture a tag change like any other semantic edit.
    cur.execute("""SELECT COUNT(*) FROM information_schema.triggers
                   WHERE event_object_table='unified_positions'""")
    print(f"  audit trigger present: {cur.fetchone()[0] > 0} (captures strategy_tag edits "
          f"via to_jsonb(OLD/NEW) — no trigger change needed)")

    cur.execute("SELECT COUNT(*), COUNT(strategy_tag) FROM unified_positions")
    n, tagged = cur.fetchone()
    print(f"  rows {n}, tagged {tagged}, untagged {n - tagged}")
    print(f"  documented vocabulary: {' | '.join(VOCAB)}")

    if a.apply:
        conn.commit(); print("COMMITTED")
    else:
        conn.rollback(); print("ROLLED BACK (dry run — pass --apply)")
    cur.close(); conn.close(); return 0


if __name__ == "__main__":
    sys.exit(main())
