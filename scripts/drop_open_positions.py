"""
Retire the deprecated `open_positions` table.

Default (no flag): dump the table to backend/database/archive/ as JSON (backup) and
report what WOULD be dropped — no DDL executed.
With --commit: verify no inbound FKs, then DROP TABLE open_positions.

Run order: deploy the code that removes the `CREATE TABLE IF NOT EXISTS open_positions`
startup DDL FIRST, otherwise the next boot recreates the table after the drop.

Connection string read from .mcp.json (never printed).
"""
import json, sys, os
import psycopg2, psycopg2.extras
from datetime import date

COMMIT = "--commit" in sys.argv
ARCHIVE = "backend/database/archive"
STAMP = "2026-06-17"

def conn_url():
    d = json.load(open(".mcp.json"))
    for a in d["mcpServers"]["postgres"].get("args", []):
        if isinstance(a, str) and a.startswith(("postgres://", "postgresql://")):
            return a
    raise SystemExit("no pg url in .mcp.json")

def main():
    c = psycopg2.connect(conn_url()); c.autocommit = False
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # exists?
    cur.execute("SELECT to_regclass('public.open_positions') AS t")
    if not cur.fetchone()["t"]:
        print("open_positions does not exist — nothing to do."); return

    # 1) dump (always)
    cur.execute("SELECT * FROM open_positions ORDER BY id")
    rows = cur.fetchall()
    os.makedirs(ARCHIVE, exist_ok=True)
    path = f"{ARCHIVE}/open_positions_backup_{STAMP}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump([dict(r) for r in rows], f, indent=2, default=str)
    print(f"Backed up {len(rows)} rows -> {path}")

    # 2) FK safety check (anything referencing open_positions?)
    cur.execute("""
        SELECT conrelid::regclass AS referencing_table, conname
        FROM pg_constraint
        WHERE contype='f' AND confrelid='public.open_positions'::regclass
    """)
    fks = cur.fetchall()
    if fks:
        print("FK references found — refusing to drop:")
        for f in fks: print("  ", dict(f))
        c.rollback(); return
    print("No inbound FK references.")

    if COMMIT:
        cur.execute("DROP TABLE open_positions")
        c.commit()
        print("DROPPED TABLE open_positions.")
    else:
        c.rollback()
        print("DRY-RUN: would DROP TABLE open_positions. Re-run with --commit (after code deploy).")
    cur.close(); c.close()

if __name__ == "__main__":
    main()
