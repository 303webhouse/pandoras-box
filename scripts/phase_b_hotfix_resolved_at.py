"""Phase B hotfix: update outcome_resolved_at = NOW() for the 110 backward-ts
BAR_WALK rows that the original backfill skipped (outcome unchanged, so no diff
was written, so resolved_at stayed bar-aligned and pre-signal).

Single transaction. Per-row diff_log entry with new backfill_run_id for rollback.
Dry-run by default; --apply to commit.
"""
from __future__ import annotations
import argparse, os, sys, uuid
from datetime import datetime, timezone
import psycopg2, psycopg2.extras

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")


def main(apply: bool):
    run_id = f"phase_b_hotfix_b_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    print(f"backfill_run_id = {run_id}")
    print(f"mode            = {'APPLY (writes)' if apply else 'DRY RUN (no writes)'}")
    print()

    conn = psycopg2.connect(DB_URL, connect_timeout=15)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT signal_id, outcome, outcome_pnl_pct, outcome_resolved_at, timestamp
        FROM signals
        WHERE outcome_source = 'BAR_WALK'
          AND outcome IS NOT NULL
          AND outcome_resolved_at IS NOT NULL
          AND outcome_resolved_at < timestamp
        ORDER BY timestamp ASC
    """)
    rows = cur.fetchall()
    print(f"Loaded {len(rows)} backward-ts BAR_WALK rows to fix")
    print()

    if not rows:
        print("Nothing to do.")
        cur.close(); conn.close()
        return

    if not apply:
        print("Sample 5 (showing impact):")
        for r in rows[:5]:
            ts_aware = r['timestamp'].replace(tzinfo=timezone.utc) if r['timestamp'].tzinfo is None else r['timestamp']
            delta_min = (ts_aware - r['outcome_resolved_at']).total_seconds() / 60
            print(f"  {r['signal_id']}: {r['outcome']} resolved_at={r['outcome_resolved_at']} "
                  f"(signal_ts={r['timestamp']}, {delta_min:.1f} min before signal)")
        print()
        print(f"DRY RUN - would update {len(rows)} rows + write {len(rows)} diff_log entries.")
        print("Re-run with --apply to commit.")
        cur.close(); conn.close()
        return

    print("APPLY mode: writing diff_log + UPDATE in single transaction...")
    try:
        for r in rows:
            cur.execute("""
                INSERT INTO signal_outcome_diff_log
                    (signal_id, old_outcome, new_outcome,
                     old_outcome_source, new_outcome_source,
                     old_pnl_pct, new_pnl_pct,
                     old_resolved_at, new_resolved_at,
                     backfill_run_id)
                VALUES (%(signal_id)s, %(outcome)s, %(outcome)s,
                        'BAR_WALK', 'BAR_WALK',
                        %(outcome_pnl_pct)s, %(outcome_pnl_pct)s,
                        %(outcome_resolved_at)s, NOW(),
                        %(run_id)s)
            """, {**r, "run_id": run_id})
            cur.execute("""
                UPDATE signals
                SET outcome_resolved_at = NOW()
                WHERE signal_id = %s
            """, (r["signal_id"],))
        conn.commit()
        print(f"COMMITTED {len(rows)} resolved_at updates.")
        print(f"Rollback handle: backfill_run_id = {run_id}")
    except Exception as e:
        conn.rollback()
        print(f"FAILED: {e}")
        raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    main(apply=p.parse_args().apply)
