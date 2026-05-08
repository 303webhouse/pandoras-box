"""Phase B acceptance verification — runs the 4 SQL queries from the brief."""
import os
import sys
import psycopg2
import psycopg2.extras

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")

conn = psycopg2.connect(DB_URL, connect_timeout=15)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("=" * 78)
print("ACCEPTANCE QUERY A — WIN-claim agreement with signal_outcomes")
print("Pass criterion: agreement_pct >= 95")
print("=" * 78)
cur.execute("""
    WITH bar_walk_wins AS (
        SELECT s.signal_id, so.outcome AS so_outcome
        FROM signals s
        JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.outcome_source = 'BAR_WALK'
          AND s.outcome = 'WIN'
    )
    SELECT COUNT(*) AS total_wins,
           COUNT(*) FILTER (WHERE so_outcome IN ('HIT_T1', 'HIT_T2')) AS agreeing_wins,
           ROUND(100.0 * COUNT(*) FILTER (WHERE so_outcome IN ('HIT_T1', 'HIT_T2'))
                 / NULLIF(COUNT(*), 0), 1) AS agreement_pct
    FROM bar_walk_wins;
""")
r = cur.fetchone()
print(f"  total_wins      = {r['total_wins']}")
print(f"  agreeing_wins   = {r['agreeing_wins']}")
print(f"  agreement_pct   = {r['agreement_pct']}%")
result_a = float(r['agreement_pct']) if r['agreement_pct'] is not None else 0
print(f"  RESULT: {'PASS' if result_a >= 95 else 'FAIL'} ({'>=' if result_a >= 95 else '<'} 95%)")
print()

print("=" * 78)
print("ACCEPTANCE QUERY B — Zero backward timestamps among BAR_WALK rows")
print("Pass criterion: backward_ts_count = 0")
print("=" * 78)
cur.execute("""
    SELECT COUNT(*) AS backward_ts_count,
           COUNT(*) FILTER (WHERE outcome_resolved_at < timestamp) AS confirmed_backward
    FROM signals
    WHERE outcome_source = 'BAR_WALK'
      AND outcome IS NOT NULL
      AND outcome_resolved_at IS NOT NULL
      AND outcome_resolved_at < timestamp;
""")
r = cur.fetchone()
print(f"  backward_ts_count = {r['backward_ts_count']}")
result_b = r['backward_ts_count']
print(f"  RESULT: {'PASS' if result_b == 0 else 'FAIL'} ({'=' if result_b == 0 else '!='} 0)")
print()

print("=" * 78)
print("ACCEPTANCE QUERY C — v_outcome_drift row count (Phase A reported 212)")
print("Pass criterion: materially lower than 212")
print("=" * 78)
cur.execute("SELECT COUNT(*) AS drift_rows FROM v_outcome_drift;")
r = cur.fetchone()
print(f"  drift_rows = {r['drift_rows']}  (Phase A baseline: 212)")
result_c = r['drift_rows']
print(f"  RESULT: {'PASS' if result_c < 212 else 'FAIL'} ({'reduced' if result_c < 212 else 'NOT reduced'})")
print()

print("=" * 78)
print("ACCEPTANCE QUERY D — NXTS smoking-gun row")
print("Pass criterion: outcome no longer 'WIN +19.44%'")
print("=" * 78)
cur.execute("""
    SELECT signal_id, outcome, outcome_pnl_pct, outcome_resolved_at, timestamp
    FROM signals
    WHERE signal_id = 'HG_NXTS_20260423_192057_3-10';
""")
r = cur.fetchone()
print(f"  signal_id           = {r['signal_id']}")
print(f"  outcome             = {r['outcome']}")
print(f"  outcome_pnl_pct     = {r['outcome_pnl_pct']}")
print(f"  outcome_resolved_at = {r['outcome_resolved_at']}")
print(f"  timestamp           = {r['timestamp']}")
nxts_pass = (r['outcome'] != 'WIN' or
             (r['outcome_pnl_pct'] is not None and abs(float(r['outcome_pnl_pct']) - 19.44) > 1.0))
print(f"  RESULT: {'PASS' if nxts_pass else 'FAIL'} (no longer WIN +19.44%)")
print()

print("=" * 78)
print("SUMMARY")
print("=" * 78)
all_pass = (result_a >= 95) and (result_b == 0) and (result_c < 212) and nxts_pass
print(f"  A. WIN-claim agreement >= 95%   : {'PASS' if result_a >= 95 else 'FAIL'} ({result_a}%)")
print(f"  B. backward_ts_count = 0         : {'PASS' if result_b == 0 else 'FAIL'} ({result_b})")
print(f"  C. v_outcome_drift < 212         : {'PASS' if result_c < 212 else 'FAIL'} ({result_c})")
print(f"  D. NXTS no longer WIN +19.44%    : {'PASS' if nxts_pass else 'FAIL'}")
print()
print(f"  OVERALL: {'PHASE B ACCEPTED' if all_pass else 'PHASE B FAILED — INVESTIGATE'}")

cur.close()
conn.close()
