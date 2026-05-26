"""One-shot applier for migration 015_position_sync_audit.sql."""
import os, sys, psycopg2

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")

MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "015_position_sync_audit.sql")
sql = open(MIGRATION, "r", encoding="utf-8").read()

print(f"Applying: {MIGRATION}")
print(f"Size: {len(sql)} bytes")

conn = psycopg2.connect(DB_URL, connect_timeout=15)
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Migration applied.")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'position_sync_audit';
        """)
        print(f"  position_sync_audit table: {'OK' if cur.fetchone() else 'MISSING'}")

        for idx in (
            "idx_position_sync_audit_run",
            "idx_position_sync_audit_position",
            "idx_position_sync_audit_ticker",
        ):
            cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s;", (idx,))
            print(f"  {idx}: {'OK' if cur.fetchone() else 'MISSING'}")
finally:
    conn.close()
