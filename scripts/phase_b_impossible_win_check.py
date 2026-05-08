"""Phase B impossible-WIN check + fixed-acceptance reframing."""
import os, sys
import psycopg2, psycopg2.extras

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL: sys.exit("FATAL")

conn = psycopg2.connect(DB_URL, connect_timeout=15)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("=" * 78)
print("IMPOSSIBLE-WIN check: BAR_WALK says WIN, but signal_outcomes' MFE < needed_move")
print("(MFE is computed from daily High.max() over full history. If MFE < target-entry,")
print(" no 15m bar in any day reached target. WIN claim is structurally impossible.)")
print("=" * 78)
cur.execute("""
    SELECT
      COUNT(*) AS impossible_wins,
      COUNT(*) FILTER (WHERE s.signal_id IN (
          SELECT signal_id FROM signal_outcome_diff_log
          WHERE backfill_run_id = 'phase_b_20260508_200423_d8df1731'
      )) AS impossible_in_diff,
      COUNT(*) FILTER (WHERE s.signal_id NOT IN (
          SELECT signal_id FROM signal_outcome_diff_log
          WHERE backfill_run_id = 'phase_b_20260508_200423_d8df1731'
      )) AS impossible_unchanged
    FROM signals s
    JOIN signal_outcomes so ON so.signal_id = s.signal_id
    WHERE s.outcome_source = 'BAR_WALK'
      AND s.outcome = 'WIN'
      AND s.entry_price IS NOT NULL
      AND s.target_1 IS NOT NULL
      AND so.max_favorable IS NOT NULL
      AND (
        (s.direction = 'LONG'  AND so.max_favorable < (s.target_1 - s.entry_price))
        OR
        (s.direction = 'SHORT' AND so.max_favorable < (s.entry_price - s.target_1))
      );
""")
r = cur.fetchone()
print(f"  Total impossible WINs              : {r['impossible_wins']}")
print(f"    of which CHANGED in backfill     : {r['impossible_in_diff']}")
print(f"    of which UNCHANGED by backfill   : {r['impossible_unchanged']}")
print()

print("=" * 78)
print("Sample 5 impossible WINs (for diagnosis)")
print("=" * 78)
cur.execute("""
    SELECT s.signal_id, s.ticker, s.direction, s.timestamp,
           s.entry_price, s.target_1, s.stop_loss,
           s.outcome, s.outcome_pnl_pct, s.outcome_resolved_at,
           so.max_favorable AS mfe,
           CASE WHEN s.direction = 'LONG' THEN s.target_1 - s.entry_price
                ELSE s.entry_price - s.target_1 END AS needed_move,
           s.signal_id IN (
              SELECT signal_id FROM signal_outcome_diff_log
              WHERE backfill_run_id = 'phase_b_20260508_200423_d8df1731'
           ) AS in_diff
    FROM signals s
    JOIN signal_outcomes so ON so.signal_id = s.signal_id
    WHERE s.outcome_source = 'BAR_WALK'
      AND s.outcome = 'WIN'
      AND so.max_favorable IS NOT NULL
      AND (
        (s.direction = 'LONG'  AND so.max_favorable < (s.target_1 - s.entry_price))
        OR
        (s.direction = 'SHORT' AND so.max_favorable < (s.entry_price - s.target_1))
      )
    ORDER BY s.outcome_resolved_at DESC
    LIMIT 5;
""")
for r in cur.fetchall():
    print(f"  {r['signal_id']}  ({'CHANGED' if r['in_diff'] else 'UNCHANGED'} by backfill)")
    print(f"    {r['direction']} {r['ticker']}: entry={r['entry_price']}, target={r['target_1']}, stop={r['stop_loss']}")
    print(f"    needed_move = {r['needed_move']:.4f}, MFE = {r['mfe']:.4f}  (MFE < needed → impossible)")
    print(f"    BAR_WALK: WIN {r['outcome_pnl_pct']:.2f}%, resolved={r['outcome_resolved_at']}")
    print()

print("=" * 78)
print("Reframed acceptance: 'Phantom WIN rate' (impossible WINs / total WINs)")
print("=" * 78)
cur.execute("""
    SELECT
      COUNT(*) AS total_wins,
      COUNT(*) FILTER (WHERE
        so.max_favorable IS NOT NULL AND (
          (s.direction = 'LONG'  AND so.max_favorable < (s.target_1 - s.entry_price))
          OR (s.direction = 'SHORT' AND so.max_favorable < (s.entry_price - s.target_1))
        )
      ) AS impossible_wins
    FROM signals s
    JOIN signal_outcomes so ON so.signal_id = s.signal_id
    WHERE s.outcome_source = 'BAR_WALK' AND s.outcome = 'WIN';
""")
r = cur.fetchone()
phantom_rate = (r['impossible_wins'] / r['total_wins'] * 100) if r['total_wins'] else 0
print(f"  Total BAR_WALK WINs : {r['total_wins']}")
print(f"  Impossible (phantom): {r['impossible_wins']}")
print(f"  Phantom rate        : {phantom_rate:.1f}%")
print()
print("  (Phase A audit reported 60-72% Holy_Grail-specific WIN-disagreement pre-fix.")
print("   Post-fix phantom rate should be ~0% if Phase B is structurally complete.)")

cur.close(); conn.close()
