"""One-shot applier for migration 013_outcome_source_phase_a.sql.

Connects via DATABASE_PUBLIC_URL or DATABASE_URL. Reads the migration SQL,
executes it as a single multi-statement script (psycopg2 handles this).
Migration is purely additive (ADD COLUMN IF NOT EXISTS, CREATE TABLE IF NOT
EXISTS, CREATE INDEX IF NOT EXISTS, CREATE OR REPLACE VIEW), so re-runs are
safe.
"""
import os
import sys
import psycopg2

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")

MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "migrations", "013_outcome_source_phase_a.sql"
)

with open(MIGRATION_PATH, "r", encoding="utf-8") as f:
    sql = f.read()

print(f"Applying migration: {MIGRATION_PATH}")
print(f"Size: {len(sql)} bytes")
conn = psycopg2.connect(DB_URL, connect_timeout=15)
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Migration applied successfully.")

    # Verify
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'signals' AND column_name = 'outcome_source';
        """)
        print(f"  outcome_source column: {'OK' if cur.fetchone() else 'MISSING'}")

        cur.execute("""
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'outcome_source_valid' AND table_name = 'signals';
        """)
        print(f"  outcome_source_valid constraint: {'OK' if cur.fetchone() else 'MISSING'}")

        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'signal_outcome_diff_log';
        """)
        print(f"  signal_outcome_diff_log table: {'OK' if cur.fetchone() else 'MISSING'}")

        cur.execute("""
            SELECT 1 FROM information_schema.views WHERE table_name = 'v_outcome_drift';
        """)
        print(f"  v_outcome_drift view: {'OK' if cur.fetchone() else 'MISSING'}")
finally:
    conn.close()
