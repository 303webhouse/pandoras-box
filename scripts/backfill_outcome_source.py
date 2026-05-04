"""Phase A: backfill signals.outcome_source via writer-provenance heuristics.

Pure labeling — does NOT modify outcome, outcome_pnl_pct, or outcome_resolved_at.
Re-runs are idempotent (each step guards on outcome_source IS NULL).

Usage:
    python scripts/backfill_outcome_source.py             # dry-run
    python scripts/backfill_outcome_source.py --apply     # writes labels

See docs/codex-briefs/outcome-tracking-unification-2026-05-03-v2.md
"""
import sys
import os
import psycopg2

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")


STEPS = [
    ("counterfactual", """
        UPDATE signals
        SET outcome_source = 'COUNTERFACTUAL'
        WHERE outcome IN ('COUNTERFACTUAL_WIN', 'COUNTERFACTUAL_LOSS')
          AND outcome_source IS NULL;
    """),
    ("actual_trade", """
        UPDATE signals s
        SET outcome_source = 'ACTUAL_TRADE'
        FROM unified_positions up
        WHERE up.signal_id = s.signal_id
          AND up.status IN ('CLOSED', 'EXPIRED')
          AND s.outcome IN ('WIN', 'LOSS')
          AND s.outcome_source IS NULL;
    """),
    ("bar_walk", """
        UPDATE signals
        SET outcome_source = 'BAR_WALK'
        WHERE outcome IN ('WIN', 'LOSS')
          AND outcome_source IS NULL;
    """),
    ("expired", """
        UPDATE signals s
        SET outcome_source = 'EXPIRED'
        FROM signal_outcomes so
        WHERE so.signal_id = s.signal_id
          AND so.outcome = 'EXPIRED'
          AND s.outcome IS NULL
          AND s.outcome_source IS NULL;
    """),
    ("invalidated", """
        UPDATE signals s
        SET outcome_source = 'INVALIDATED'
        FROM signal_outcomes so
        WHERE so.signal_id = s.signal_id
          AND so.outcome = 'INVALIDATED'
          AND s.outcome IS NULL
          AND s.outcome_source IS NULL;
    """),
]

DRY_RUN_SELECTS = [
    ("counterfactual", "SELECT COUNT(*) FROM signals WHERE outcome IN ('COUNTERFACTUAL_WIN','COUNTERFACTUAL_LOSS') AND outcome_source IS NULL"),
    ("actual_trade",   "SELECT COUNT(*) FROM signals s JOIN unified_positions up ON up.signal_id = s.signal_id WHERE up.status IN ('CLOSED','EXPIRED') AND s.outcome IN ('WIN','LOSS') AND s.outcome_source IS NULL"),
    ("bar_walk",       "SELECT COUNT(*) FROM signals WHERE outcome IN ('WIN','LOSS') AND outcome_source IS NULL"),
    ("expired",        "SELECT COUNT(*) FROM signals s JOIN signal_outcomes so ON so.signal_id = s.signal_id WHERE so.outcome = 'EXPIRED' AND s.outcome IS NULL AND s.outcome_source IS NULL"),
    ("invalidated",    "SELECT COUNT(*) FROM signals s JOIN signal_outcomes so ON so.signal_id = s.signal_id WHERE so.outcome = 'INVALIDATED' AND s.outcome IS NULL AND s.outcome_source IS NULL"),
]


def main(dry_run: bool):
    conn = psycopg2.connect(DB_URL, connect_timeout=10)
    cur = conn.cursor()

    if dry_run:
        print("DRY RUN — counts only, no writes")
        total = 0
        for label, sql in DRY_RUN_SELECTS:
            cur.execute(sql)
            n = cur.fetchone()[0]
            total += n
            print(f"  {label:15s} would tag {n:6d} rows")
        print(f"  ---")
        print(f"  TOTAL would tag {total:6d} rows")
        cur.close()
        conn.close()
        return

    for label, sql in STEPS:
        cur.execute(sql)
        n = cur.rowcount
        print(f"  {label:15s} tagged {n:6d} rows")
    conn.commit()

    cur.execute("""
        SELECT outcome_source, COUNT(*)
        FROM signals
        GROUP BY outcome_source
        ORDER BY 2 DESC NULLS LAST;
    """)
    print()
    print("Final outcome_source distribution:")
    for source, n in cur.fetchall():
        print(f"  {(source or 'NULL'):30s} {n}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    dry = "--apply" not in sys.argv
    main(dry)
