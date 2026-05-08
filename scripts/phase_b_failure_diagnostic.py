"""Phase B failure diagnostic — root-cause A and B failures."""
import os
import sys
import psycopg2
import psycopg2.extras

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: no DB URL")

conn = psycopg2.connect(DB_URL, connect_timeout=15)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("=" * 78)
print("DIAGNOSTIC 1 — Are the 110 backward-ts rows the ones the backfill SKIPPED?")
print("=" * 78)
# A row was 'in diffs' if it appears in signal_outcome_diff_log for run phase_b_20260508_200423
cur.execute("""
    WITH backfill_run AS (
        SELECT signal_id FROM signal_outcome_diff_log
        WHERE backfill_run_id = 'phase_b_20260508_200423_d8df1731'
    )
    SELECT
      COUNT(*) AS total_backward,
      COUNT(*) FILTER (WHERE s.signal_id IN (SELECT signal_id FROM backfill_run)) AS in_backfill_diffs,
      COUNT(*) FILTER (WHERE s.signal_id NOT IN (SELECT signal_id FROM backfill_run)) AS skipped_by_backfill
    FROM signals s
    WHERE s.outcome_source = 'BAR_WALK'
      AND s.outcome IS NOT NULL
      AND s.outcome_resolved_at IS NOT NULL
      AND s.outcome_resolved_at < s.timestamp;
""")
r = cur.fetchone()
print(f"  Total backward-ts BAR_WALK rows (post-backfill): {r['total_backward']}")
print(f"    of which appeared in diff_log (changed)     : {r['in_backfill_diffs']}")
print(f"    of which did NOT appear in diff_log (skipped): {r['skipped_by_backfill']}")
print()
if r['skipped_by_backfill'] == r['total_backward']:
    print("  CONFIRMED: 100% of backward-ts rows are 'outcome unchanged' rows that")
    print("  the script's skip-if-unchanged logic missed. Hotfix = update")
    print("  outcome_resolved_at = NOW() for ALL BAR_WALK rows, not just changed ones.")
print()

print("=" * 78)
print("DIAGNOSTIC 2 -- Breakdown of 116 BAR_WALK WIN vs signal_outcomes disagreements")
print("=" * 78)
cur.execute("""
    WITH bw_wins AS (
        SELECT s.signal_id, s.outcome_resolved_at AS sig_resolved,
               so.outcome AS so_outcome, so.outcome_at AS so_resolved
        FROM signals s
        JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.outcome_source = 'BAR_WALK'
          AND s.outcome = 'WIN'
    )
    SELECT
      COUNT(*) FILTER (WHERE so_outcome IN ('HIT_T1','HIT_T2')) AS agreeing,
      COUNT(*) FILTER (WHERE so_outcome = 'STOPPED_OUT')  AS disagree_stop,
      COUNT(*) FILTER (WHERE so_outcome = 'PENDING')      AS disagree_pending,
      COUNT(*) FILTER (WHERE so_outcome = 'EXPIRED')      AS disagree_expired,
      COUNT(*) FILTER (WHERE so_outcome = 'INVALIDATED')  AS disagree_invalidated
    FROM bw_wins;
""")
r = cur.fetchone()
print(f"  Agreeing (HIT_T1/HIT_T2) : {r['agreeing']}")
print(f"  Disagree STOPPED_OUT     : {r['disagree_stop']}")
print(f"  Disagree PENDING         : {r['disagree_pending']}")
print(f"  Disagree EXPIRED         : {r['disagree_expired']}")
print(f"  Disagree INVALIDATED     : {r['disagree_invalidated']}")
print()

print("=" * 78)
print("DIAGNOSTIC 3 — Of the 32 LOSS->WIN flips, how many DISAGREE with signal_outcomes?")
print("=" * 78)
cur.execute("""
    SELECT
      COUNT(*) AS total_flips,
      COUNT(*) FILTER (WHERE so.outcome IN ('HIT_T1','HIT_T2')) AS flips_agree,
      COUNT(*) FILTER (WHERE so.outcome = 'STOPPED_OUT')  AS flips_disagree_stop,
      COUNT(*) FILTER (WHERE so.outcome NOT IN ('HIT_T1','HIT_T2','STOPPED_OUT')) AS flips_other
    FROM signal_outcome_diff_log d
    JOIN signal_outcomes so ON so.signal_id = d.signal_id
    WHERE d.backfill_run_id = 'phase_b_20260508_200423_d8df1731'
      AND d.old_outcome = 'LOSS'
      AND d.new_outcome = 'WIN';
""")
r = cur.fetchone()
print(f"  LOSS->WIN flips total     : {r['total_flips']}")
print(f"  ...where so agrees (WIN)  : {r['flips_agree']}")
print(f"  ...where so disagrees (LOSS): {r['flips_disagree_stop']}")
print(f"  ...where so other         : {r['flips_other']}")
print()
print("  If flips_disagree_stop is non-trivial: legitimate 15m-vs-daily granularity")
print("  disagreement (resolver's 15m walk sees target hit first; signal_outcomes'")
print("  daily walk sees Low<=stop AND High>=target on same day, defaults to STOPPED_OUT).")

print()
print("=" * 78)
print("DIAGNOSTIC 4 — Sample 5 still-disagreeing BAR_WALK WINs (for manual review)")
print("=" * 78)
cur.execute("""
    SELECT s.signal_id, s.ticker, s.timestamp, s.outcome, s.outcome_pnl_pct,
           s.outcome_resolved_at, so.outcome AS so_outcome,
           so.outcome_at AS so_resolved,
           so.max_favorable AS so_mfe, so.max_adverse AS so_mae
    FROM signals s
    JOIN signal_outcomes so ON so.signal_id = s.signal_id
    WHERE s.outcome_source = 'BAR_WALK'
      AND s.outcome = 'WIN'
      AND so.outcome NOT IN ('HIT_T1', 'HIT_T2')
    ORDER BY s.outcome_resolved_at DESC
    LIMIT 5;
""")
for r in cur.fetchall():
    print(f"  {r['signal_id']}")
    print(f"    ticker={r['ticker']}, ts={r['timestamp']}")
    print(f"    BAR_WALK: WIN {r['outcome_pnl_pct']:.2f}%, resolved={r['outcome_resolved_at']}")
    print(f"    so:       {r['so_outcome']} at={r['so_resolved']}, MFE={r['so_mfe']}, MAE={r['so_mae']}")
    print()

cur.close()
conn.close()
