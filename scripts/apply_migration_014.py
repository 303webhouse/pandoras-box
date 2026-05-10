"""One-shot applier for migration 014_phase_c_projection.sql."""
import os, sys, psycopg2

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")

MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "014_phase_c_projection.sql")
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
        for idx in ("idx_signal_outcomes_resolved", "idx_signals_outcome_source_projectable"):
            cur.execute("""
                SELECT 1 FROM pg_indexes WHERE indexname = %s;
            """, (idx,))
            print(f"  {idx}: {'OK' if cur.fetchone() else 'MISSING'}")
finally:
    conn.close()
