"""Stress tests on the audit before writing verdict."""
import os
import sys

import psycopg2
from statistics import mean, median, stdev
from collections import defaultdict, Counter
import math, random

DSN = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DSN:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")

def main():
    conn = psycopg2.connect(DSN, connect_timeout=15)
    cur = conn.cursor()

    print("=" * 78)
    print("STRESS TESTS — disagreement, 4/24 leverage, sector lookup")
    print("=" * 78)
    print()

    # Test A: Disagreement between signals.outcome (BAR_WALK) and signal_outcomes
    cur.execute("""
        SELECT s.gate_type,
               s.outcome AS sig_outcome,
               so.outcome AS so_outcome,
               COUNT(*) AS n
        FROM signals s
        JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.strategy = 'Holy_Grail'
          AND s.outcome_source = 'BAR_WALK'
          AND s.outcome IS NOT NULL
          AND so.outcome IS NOT NULL
        GROUP BY s.gate_type, s.outcome, so.outcome
        ORDER BY s.gate_type, n DESC;
    """)
    print("--- A. signals.outcome vs signal_outcomes by gate_type ---")
    print(f"  {'gate':<8} {'sig.outcome':<12} {'so.outcome':<14} {'n':>5}")
    for gt, sig_o, so_o, n in cur.fetchall():
        agree = "AGREE" if (sig_o == 'WIN' and so_o in ('HIT_T1', 'HIT_T2')) \
                          or (sig_o == 'LOSS' and so_o == 'STOPPED_OUT') \
                          else "DISAGREE"
        marker = "" if agree == "AGREE" else "  <-- DISAGREE"
        print(f"  {(gt or 'NULL'):<8} {sig_o:<12} {so_o:<14} {n:>5}  {agree}{marker}")
    print()

    # Test B: Drop 4/24 from `both` and re-test
    cur.execute("""
        SELECT s.signal_id, s.gate_type, s.ticker, s.timestamp,
               s.outcome_pnl_pct, so.outcome
        FROM signals s
        LEFT JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.strategy = 'Holy_Grail'
          AND s.outcome_source = 'BAR_WALK'
          AND s.outcome_pnl_pct IS NOT NULL
          AND s.gate_type IN ('rsi', 'both');
    """)
    rsi_pnls_full = []
    rsi_pnls_no424 = []
    both_pnls_full = []
    both_pnls_no424 = []
    for sid, gt, tkr, ts, pnl, so_o in cur.fetchall():
        pnl = float(pnl)
        date = ts.date() if ts else None
        is_424 = (date and date.isoformat() == '2026-04-24')
        if gt == 'rsi':
            rsi_pnls_full.append(pnl)
            if not is_424:
                rsi_pnls_no424.append(pnl)
        elif gt == 'both':
            both_pnls_full.append(pnl)
            if not is_424:
                both_pnls_no424.append(pnl)

    def welch(a, b):
        if len(a) < 2 or len(b) < 2:
            return None, None, None
        ma, mb = mean(a), mean(b)
        va, vb = stdev(a) ** 2, stdev(b) ** 2
        na, nb = len(a), len(b)
        se = math.sqrt(va / na + vb / nb)
        if se == 0:
            return None, None, None
        t = (mb - ma) / se
        df_num = (va / na + vb / nb) ** 2
        df_den = ((va / na) ** 2 / (na - 1)) + ((vb / nb) ** 2 / (nb - 1))
        df = df_num / df_den if df_den > 0 else None
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
        return t, df, p

    def boot(a, b, n_iter=10000):
        random.seed(42)
        diffs = []
        na, nb = len(a), len(b)
        for _ in range(n_iter):
            sa = [a[random.randrange(na)] for _ in range(na)]
            sb = [b[random.randrange(nb)] for _ in range(nb)]
            diffs.append(mean(sb) - mean(sa))
        diffs.sort()
        return diffs[int(n_iter * 0.025)], diffs[int(n_iter * 0.975)]

    print("--- B. Sensitivity: full vs ex-4/24 ---")
    for label, rsi, both in (
        ("FULL", rsi_pnls_full, both_pnls_full),
        ("EX-4/24", rsi_pnls_no424, both_pnls_no424),
    ):
        t, df, p = welch(rsi, both)
        lo, hi = boot(rsi, both)
        print(f"  {label}")
        print(f"    rsi:  n={len(rsi):>3}  mean={mean(rsi):>+6.3f}%")
        print(f"    both: n={len(both):>3}  mean={mean(both):>+6.3f}%")
        print(f"    delta={mean(both)-mean(rsi):>+6.3f}%  t={t:>+.3f}  p={p:.4f}")
        print(f"    bootstrap 95% CI: [{lo:+.3f}%, {hi:+.3f}%]")
        print(f"    CI includes zero? {'YES' if lo < 0 < hi else 'NO'}")
        print()

    # Test C: How many shadow signals have fired since 5/3?
    cur.execute("""
        SELECT s.gate_type, COUNT(*) AS new_signals,
               COUNT(*) FILTER (WHERE so.outcome IS NOT NULL
                                AND so.outcome <> 'PENDING') AS resolved
        FROM signals s
        LEFT JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.strategy = 'Holy_Grail'
          AND s.timestamp > '2026-05-03'
        GROUP BY s.gate_type
        ORDER BY new_signals DESC;
    """)
    print("--- C. New shadow signals since 5/3 audit ---")
    print(f"  {'gate':<10} {'new':>5} {'resolved':>9}")
    for gt, n, r in cur.fetchall():
        print(f"  {(gt or 'NULL'):<10} {n:>5} {r:>9}")
    print()

    # Test D: Real sector lookup via signals.sector or enrichment_data
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'signals' AND column_name IN ('sector', 'sector_etf', 'enrichment_data');
    """)
    print("--- D. Available sector columns on signals ---")
    cols = [r[0] for r in cur.fetchall()]
    print(f"  {cols}")
    print()

    # If enrichment_data exists, sample what's in it
    if 'enrichment_data' in cols:
        cur.execute("""
            SELECT enrichment_data
            FROM signals
            WHERE strategy = 'Holy_Grail'
              AND outcome_source = 'BAR_WALK'
              AND enrichment_data IS NOT NULL
            LIMIT 1;
        """)
        row = cur.fetchone()
        print("--- D2. Sample enrichment_data (top-level keys) ---")
        if row and row[0]:
            ed = row[0]
            if isinstance(ed, dict):
                print(f"  Keys: {list(ed.keys())[:20]}")
            else:
                print(f"  Type: {type(ed)}")

    # Test E: For the 110-row disagreement cluster, was it concentrated by gate_type?
    cur.execute("""
        SELECT s.gate_type, COUNT(*)
        FROM signals s
        JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.strategy = 'Holy_Grail'
          AND s.outcome_source = 'BAR_WALK'
          AND s.outcome = 'WIN'
          AND so.outcome = 'STOPPED_OUT'
        GROUP BY s.gate_type
        ORDER BY 2 DESC;
    """)
    print()
    print("--- E. WIN/STOPPED_OUT disagreement by gate_type ---")
    for gt, n in cur.fetchall():
        print(f"  {(gt or 'NULL'):<10} {n}")

    # Test F: The single resolved 3-10-only signal — full disagreement detail
    cur.execute("""
        SELECT s.signal_id, s.ticker, s.timestamp, s.outcome, s.outcome_pnl_pct,
               s.outcome_resolved_at,
               so.outcome, so.outcome_at, so.max_favorable, so.max_adverse
        FROM signals s
        LEFT JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.strategy = 'Holy_Grail'
          AND s.gate_type = '3-10';
    """)
    print()
    print("--- F. All 3-10-only signals: full row dump (both tables) ---")
    for r in cur.fetchall():
        print(f"  signal_id={r[0]}")
        print(f"    ticker={r[1]}, ts={r[2]}")
        print(f"    signals: outcome={r[3]}, pnl={r[4]}, resolved_at={r[5]}")
        print(f"    signal_outcomes: outcome={r[6]}, at={r[7]}, mfe={r[8]}, mae={r[9]}")

    cur.close()
    conn.close()
    print()
    print("=" * 78)

if __name__ == "__main__":
    main()
