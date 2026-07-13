"""One-shot applier for migration 023_crypto_vendor_health_audit.sql."""
import os, sys, psycopg2

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")

MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "023_crypto_vendor_health_audit.sql")
sql = open(MIGRATION, "r", encoding="utf-8").read()
# Strip the trailing "-- DOWN" rollback block (documentation only, never executed here).
sql = sql.split("\n-- DOWN\n")[0]

print(f"Applying: {MIGRATION}")
print(f"Size: {len(sql)} bytes")

if DB_URL:
    conn = psycopg2.connect(DB_URL, connect_timeout=15)
else:
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST") or "localhost",
        port=int(os.environ.get("DB_PORT") or 5432),
        dbname=os.environ.get("DB_NAME") or "pandoras_box",
        user=os.environ.get("DB_USER") or "postgres",
        password=os.environ.get("DB_PASSWORD") or "postgres",
        connect_timeout=15,
    )
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Migration applied.")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'crypto_vendor_health_audit';
        """)
        print(f"  crypto_vendor_health_audit table: {'OK' if cur.fetchone() else 'MISSING'}")

        for idx in (
            "idx_crypto_vendor_health_latest",
            "idx_crypto_vendor_health_dead",
        ):
            cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s;", (idx,))
            print(f"  {idx}: {'OK' if cur.fetchone() else 'MISSING'}")
finally:
    conn.close()
