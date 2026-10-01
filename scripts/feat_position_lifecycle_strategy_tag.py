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

# The vocabulary moved to backend/models/strategy_tag.py (R-IV.624(d)2). It was declared here
# as a list AND retyped into the COMMENT below, in this same file — two copies, so one edit
# made the file disagree with itself. Both now come from the one author.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from models.strategy_tag import TAGS, all_recognised, column_comment  # noqa: E402


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

    cur.execute("COMMENT ON COLUMN unified_positions.strategy_tag IS %s", (column_comment(),))
    print(f"  COMMENT generated from models.strategy_tag: canonical {list(TAGS)}")

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
    print(f"  canonical vocabulary: {' | '.join(TAGS)}")
    print(f"  also recognised:      {' | '.join(w for w in all_recognised() if w not in TAGS)}")

    # The stored values are reported against the vocabulary, because for three months the two
    # were disjoint but for CORE and nothing was looking (R-IV.624(d)2).
    cur.execute("""SELECT strategy_tag, COUNT(*) FROM unified_positions
                   WHERE strategy_tag IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""")
    from models.strategy_tag import is_known
    for tag, cnt in cur.fetchall():
        mark = "ok" if is_known(tag) else "NOT IN THE VOCABULARY"
        print(f"    {tag:18} {cnt:4}  {mark}")

    if a.apply:
        conn.commit(); print("COMMITTED")
    else:
        conn.rollback(); print("ROLLED BACK (dry run — pass --apply)")
    cur.close(); conn.close(); return 0


if __name__ == "__main__":
    sys.exit(main())
