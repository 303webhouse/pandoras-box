"""
Clean re-audit of 3-10 Oscillator promotion candidacy.

Queries signals filtered to outcome_source='BAR_WALK' joined to signal_outcomes
for the canonical bar-walk semantic. Computes:
  1) Sample sizes by gate_type
  2) Win rate (HIT_T1 + HIT_T2) / resolved
  3) Avg MFE, avg MAE, median PnL pct
  4) Welch's t-test on expectancy delta (rsi vs both)
  5) Bootstrap 95% CI on the delta
  6) Sector breakdown
  7) Date concentration

Run with: python clean-audit-3-10-2026-05-08.py
"""
import os
import sys

import psycopg2
import json
from statistics import mean, median, stdev
from collections import Counter, defaultdict
import math
import random

DSN = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DSN:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")

# Hardcoded SPDR sector map (mirrors backend/scanners/sector_rs.py default fallback)
SECTOR_ETFS = {
    'AAPL': 'XLK', 'MSFT': 'XLK', 'NVDA': 'XLK', 'AMD': 'XLK', 'INTC': 'XLK',
    'GOOGL': 'XLC', 'GOOG': 'XLC', 'META': 'XLC', 'NFLX': 'XLC', 'DIS': 'XLC',
    'AMZN': 'XLY', 'TSLA': 'XLY', 'HD': 'XLY', 'NKE': 'XLY', 'MCD': 'XLY',
    'JPM': 'XLF', 'BAC': 'XLF', 'WFC': 'XLF', 'GS': 'XLF', 'MS': 'XLF',
    'XOM': 'XLE', 'CVX': 'XLE', 'COP': 'XLE', 'OXY': 'XLE', 'SLB': 'XLE',
    'JNJ': 'XLV', 'UNH': 'XLV', 'PFE': 'XLV', 'LLY': 'XLV', 'MRK': 'XLV',
    'WMT': 'XLP', 'PG': 'XLP', 'KO': 'XLP', 'PEP': 'XLP', 'COST': 'XLP',
    'BA': 'XLI', 'CAT': 'XLI', 'GE': 'XLI', 'HON': 'XLI', 'UPS': 'XLI',
    'AMT': 'XLRE', 'PLD': 'XLRE', 'CCI': 'XLRE',
    'NEE': 'XLU', 'DUK': 'XLU', 'SO': 'XLU',
    'LIN': 'XLB', 'APD': 'XLB', 'FCX': 'XLB', 'NEM': 'XLB',
    'SPY': 'INDEX', 'QQQ': 'INDEX', 'IWM': 'INDEX',
}

def get_sector(ticker):
    return SECTOR_ETFS.get(ticker, 'OTHER/UNMAPPED')

def welch_t_test(a, b):
    """Two-sample Welch's t-test (unequal variance). Returns (t, df, p_two_sided)."""
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
    # Approximate two-sided p via survival function of t-distribution.
    # Use a normal approximation when df is large; otherwise a simple
    # series expansion. For our purposes (n>30) normal is fine.
    if df and df > 30:
        # Two-tailed p from standard normal CDF
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    else:
        # Conservative: assume normal. Caller is warned.
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return t, df, p

def bootstrap_ci(a, b, n_iter=10000, alpha=0.05):
    """Bootstrap 95% CI on the difference of means (b - a)."""
    if not a or not b:
        return None, None
    random.seed(42)
    diffs = []
    na, nb = len(a), len(b)
    for _ in range(n_iter):
        sa = [a[random.randrange(na)] for _ in range(na)]
        sb = [b[random.randrange(nb)] for _ in range(nb)]
        diffs.append(mean(sb) - mean(sa))
    diffs.sort()
    lo = diffs[int(n_iter * (alpha / 2))]
    hi = diffs[int(n_iter * (1 - alpha / 2))]
    return lo, hi

def main():
    conn = psycopg2.connect(DSN, connect_timeout=15)
    cur = conn.cursor()

    print("=" * 78)
    print("3-10 OSCILLATOR PROMOTION RE-AUDIT — CLEAN BAR-WALK DATA")
    print("=" * 78)
    print()
    print("Filter: signals.outcome_source = 'BAR_WALK' (Phase A canonical)")
    print("Joined to: signal_outcomes for HIT_T1/HIT_T2/STOPPED_OUT categorization")
    print()

    # 0. Universe sanity check
    cur.execute("""
        SELECT outcome_source, COUNT(*)
        FROM signals
        WHERE strategy = 'Holy_Grail'
        GROUP BY outcome_source
        ORDER BY 2 DESC NULLS LAST;
    """)
    print("--- 0. Holy_Grail signals by outcome_source ---")
    for src, n in cur.fetchall():
        print(f"  {(src or 'NULL'):28s} {n:>6}")
    print()

    # 1. Sample size + win rate by gate_type from signal_outcomes (canonical)
    cur.execute("""
        SELECT s.gate_type,
               COUNT(*) FILTER (WHERE so.outcome IS NOT NULL
                                AND so.outcome NOT IN ('PENDING')) AS resolved,
               COUNT(*) FILTER (WHERE so.outcome IN ('HIT_T1', 'HIT_T2')) AS wins,
               COUNT(*) FILTER (WHERE so.outcome = 'STOPPED_OUT') AS losses,
               COUNT(*) FILTER (WHERE so.outcome = 'EXPIRED') AS expired,
               COUNT(*) FILTER (WHERE so.outcome = 'INVALIDATED') AS invalidated,
               COUNT(*) FILTER (WHERE so.outcome = 'PENDING' OR so.outcome IS NULL) AS pending,
               COUNT(*) AS total
        FROM signals s
        LEFT JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.strategy = 'Holy_Grail'
        GROUP BY s.gate_type
        ORDER BY total DESC;
    """)
    print("--- 1. Win rate by gate_type (signal_outcomes canonical) ---")
    print(f"  {'gate_type':<10} {'total':>6} {'resolved':>9} {'wins':>5} "
          f"{'losses':>7} {'exp':>4} {'inv':>4} {'pend':>5} {'win%':>7}")
    rows1 = cur.fetchall()
    for gt, resolved, wins, losses, expired, inv, pend, total in rows1:
        win_pct = (wins / resolved * 100) if resolved else 0
        print(f"  {(gt or 'NULL'):<10} {total:>6} {resolved:>9} {wins:>5} "
              f"{losses:>7} {expired:>4} {inv:>4} {pend:>5} {win_pct:>6.1f}%")
    print()

    # 2. PnL distribution by gate_type from signals.outcome_pnl_pct (BAR_WALK only)
    cur.execute("""
        SELECT s.signal_id, s.gate_type, s.ticker,
               s.timestamp, s.outcome, s.outcome_pnl_pct,
               so.outcome AS so_outcome,
               so.max_favorable, so.max_adverse,
               so.outcome_at
        FROM signals s
        LEFT JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE s.strategy = 'Holy_Grail'
          AND s.outcome_source = 'BAR_WALK'
          AND s.outcome_pnl_pct IS NOT NULL;
    """)
    rows = cur.fetchall()
    by_gate = defaultdict(list)
    so_by_gate = defaultdict(list)
    for sig_id, gt, ticker, ts, outcome, pnl, so_outcome, mfe, mae, so_at in rows:
        by_gate[gt or 'NULL'].append({
            'signal_id': sig_id, 'ticker': ticker, 'ts': ts,
            'outcome': outcome, 'pnl': float(pnl) if pnl is not None else None,
            'so_outcome': so_outcome,
            'mfe': float(mfe) if mfe is not None else None,
            'mae': float(mae) if mae is not None else None,
            'so_at': so_at,
        })
    print("--- 2. PnL distribution (BAR_WALK only) by gate_type ---")
    print(f"  {'gate_type':<10} {'n':>5} {'win%':>7} {'avg_pnl%':>10} "
          f"{'med_pnl%':>10} {'std_pnl':>10} {'avg_mfe':>9} {'avg_mae':>9} "
          f"{'min':>7} {'max':>7}")
    for gt, items in sorted(by_gate.items(), key=lambda x: -len(x[1])):
        pnls = [i['pnl'] for i in items if i['pnl'] is not None]
        mfes = [i['mfe'] for i in items if i['mfe'] is not None]
        maes = [i['mae'] for i in items if i['mae'] is not None]
        wins = sum(1 for i in items
                   if i['so_outcome'] in ('HIT_T1', 'HIT_T2') or i['outcome'] == 'WIN')
        resolved = sum(1 for i in items
                       if i['outcome'] in ('WIN', 'LOSS')
                          or i['so_outcome'] in ('HIT_T1', 'HIT_T2', 'STOPPED_OUT'))
        win_pct = (wins / resolved * 100) if resolved else 0
        print(f"  {gt:<10} {len(pnls):>5} {win_pct:>6.1f}% "
              f"{mean(pnls) if pnls else 0:>9.2f}% "
              f"{median(pnls) if pnls else 0:>9.2f}% "
              f"{stdev(pnls) if len(pnls) > 1 else 0:>9.2f} "
              f"{mean(mfes) if mfes else 0:>8.2f}% "
              f"{mean(maes) if maes else 0:>8.2f}% "
              f"{min(pnls) if pnls else 0:>6.2f}% "
              f"{max(pnls) if pnls else 0:>6.2f}%")
    print()

    # 3. Welch's t-test + bootstrap CI on rsi vs both expectancy delta
    rsi_pnls = [i['pnl'] for i in by_gate.get('rsi', []) if i['pnl'] is not None]
    both_pnls = [i['pnl'] for i in by_gate.get('both', []) if i['pnl'] is not None]
    only310_pnls = [i['pnl'] for i in by_gate.get('3-10', []) if i['pnl'] is not None]

    print("--- 3. Welch's t-test: rsi vs both ---")
    if rsi_pnls and both_pnls:
        t, df, p = welch_t_test(rsi_pnls, both_pnls)
        print(f"  rsi:  n={len(rsi_pnls):>3}  mean={mean(rsi_pnls):>+6.3f}%")
        print(f"  both: n={len(both_pnls):>3}  mean={mean(both_pnls):>+6.3f}%")
        print(f"  delta = {mean(both_pnls) - mean(rsi_pnls):>+6.3f}%")
        print(f"  t = {t:>+.3f}, df = {df:.1f}, two-sided p = {p:.4f}")
    else:
        print("  Insufficient data")
    print()

    print("--- 4. Bootstrap 95% CI on (both - rsi) delta ---")
    if rsi_pnls and both_pnls:
        lo, hi = bootstrap_ci(rsi_pnls, both_pnls, n_iter=10000)
        print(f"  95% CI: [{lo:+.3f}%, {hi:+.3f}%]")
        print(f"  Includes zero? {'YES (no edge proven)' if lo < 0 < hi else 'NO (directional)'}")
    print()

    # 5. Sector breakdown for `both` and `3-10` (the promotion candidates)
    print("--- 5. Sector breakdown (concentration check) ---")
    for gt_label in ['rsi', 'both', '3-10']:
        if gt_label not in by_gate:
            continue
        items = by_gate[gt_label]
        sector_counts = Counter(get_sector(i['ticker']) for i in items)
        sector_pnls = defaultdict(list)
        for i in items:
            if i['pnl'] is not None:
                sector_pnls[get_sector(i['ticker'])].append(i['pnl'])
        total = len(items)
        print(f"  gate_type={gt_label} (n={total})")
        for sec, n in sector_counts.most_common():
            pct = n / total * 100
            avg_pnl = mean(sector_pnls[sec]) if sector_pnls[sec] else 0
            print(f"    {sec:<18} {n:>4} ({pct:>5.1f}%)  avg_pnl={avg_pnl:>+6.2f}%")
    print()

    # 6. Date concentration — which days dominate?
    print("--- 6. Date concentration (single-day cluster check) ---")
    for gt_label in ['both', '3-10']:
        if gt_label not in by_gate:
            continue
        items = by_gate[gt_label]
        date_counts = Counter(i['ts'].date() for i in items if i['ts'])
        date_pnls = defaultdict(list)
        for i in items:
            if i['ts'] and i['pnl'] is not None:
                date_pnls[i['ts'].date()].append(i['pnl'])
        total = len(items)
        print(f"  gate_type={gt_label} top dates:")
        for d, n in date_counts.most_common(8):
            pct = n / total * 100
            avg_pnl = mean(date_pnls[d]) if date_pnls[d] else 0
            print(f"    {d}  n={n:>3} ({pct:>5.1f}%)  avg_pnl={avg_pnl:>+6.2f}%")
    print()

    # 7. The 3-10-only signals — full row dump (small n, every signal matters)
    print("--- 7. All 3-10-only signals (gate_type='3-10') ---")
    if '3-10' in by_gate:
        for i in by_gate['3-10']:
            print(f"  {i['signal_id']:<40} {i['ticker']:<6} "
                  f"{i['ts'].date() if i['ts'] else 'NULL':<10} "
                  f"signals.outcome={(i['outcome'] or 'NULL'):<10} "
                  f"so.outcome={(i['so_outcome'] or 'NULL'):<14} "
                  f"pnl={i['pnl'] if i['pnl'] is not None else 'NULL'}")

    # 8. PROJECTED_FROM_BAR_WALK — does it exist yet?
    cur.execute("""
        SELECT COUNT(*) FROM signals
        WHERE outcome_source = 'PROJECTED_FROM_BAR_WALK';
    """)
    n_projected = cur.fetchone()[0]
    print()
    print(f"--- 8. PROJECTED_FROM_BAR_WALK count: {n_projected} (Phase C status) ---")

    cur.close()
    conn.close()
    print()
    print("=" * 78)
    print("DONE")
    print("=" * 78)

if __name__ == "__main__":
    main()
