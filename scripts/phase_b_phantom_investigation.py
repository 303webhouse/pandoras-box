"""Phantom-WIN investigation: walk today's yfinance for 5 impossible WINs to
determine yfinance drift vs. residual bug in patched resolver.

For each phantom WIN:
  1. Pull yfinance bars from signal_ts onward (matching patched resolver behavior)
  2. Walk bars with the post-signal-only filter
  3. Find the bar (if any) where target was actually hit by today's data
  4. Compare to signal_outcomes.max_favorable

Outcomes per row:
  - DRIFT: today's yfinance shows target hit (resolver was right at write time;
    signal_outcomes.MFE is computed from older yfinance snapshot showing less)
  - RESIDUAL_BUG: today's yfinance does NOT show target hit (resolver wrote
    a phantom WIN even after the patches; deeper issue exists)
  - DATA_GAP: yfinance returns no bars (delisted, etc.)
"""
from __future__ import annotations
import os, sys
from datetime import datetime, timedelta, timezone
import psycopg2, psycopg2.extras
import yfinance as yf
import pandas as pd

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL: sys.exit("FATAL")

conn = psycopg2.connect(DB_URL, connect_timeout=15)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""
    SELECT s.signal_id, s.ticker, s.direction, s.timestamp,
           s.entry_price, s.target_1, s.stop_loss,
           s.outcome_pnl_pct, s.outcome_resolved_at,
           so.max_favorable AS mfe, so.max_adverse AS mae,
           CASE WHEN s.direction = 'LONG' THEN s.target_1 - s.entry_price
                ELSE s.entry_price - s.target_1 END AS needed_move
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
    ORDER BY s.timestamp ASC
    LIMIT 5;
""")
phantoms = cur.fetchall()
print(f"Investigating {len(phantoms)} phantom WINs against today's yfinance")
print()

drift = 0; bug = 0; gap = 0
for p in phantoms:
    print("=" * 78)
    print(f"  {p['signal_id']}  {p['direction']} {p['ticker']}")
    print(f"  signal_ts = {p['timestamp']}, entry={p['entry_price']}, target={p['target_1']}")
    print(f"  needed_move = {float(p['needed_move']):.4f}, signal_outcomes MFE = {float(p['mfe']):.4f}")
    print()

    signal_ts = p['timestamp'].replace(tzinfo=timezone.utc) if p['timestamp'].tzinfo is None else p['timestamp']
    signal_age_days = (datetime.now(timezone.utc) - signal_ts).days
    interval = "15m" if signal_age_days < 55 else "1d"
    try:
        bars = yf.download(p['ticker'], start=signal_ts, interval=interval,
                           progress=False, auto_adjust=False, prepost=False)
    except Exception as e:
        print(f"  yfinance error: {e}")
        gap += 1; continue
    if isinstance(bars.columns, pd.MultiIndex):
        bars.columns = bars.columns.get_level_values(0)
    if bars.empty:
        print(f"  yfinance returned 0 bars (interval={interval})")
        gap += 1; continue

    print(f"  Pulled {len(bars)} {interval} bars from yfinance today")
    target_f = float(p['target_1']); stop_f = float(p['stop_loss']); entry_f = float(p['entry_price'])
    direction = p['direction']
    target_hit_bar = None; stop_hit_bar = None; max_high = None; min_low = None

    for bar_ts, bar in bars.iterrows():
        try: high = float(bar["High"]); low = float(bar["Low"])
        except Exception: continue
        try:
            bar_utc = bar_ts.tz_convert("UTC") if getattr(bar_ts, "tzinfo", None) else bar_ts.tz_localize("UTC")
        except Exception: bar_utc = bar_ts
        if bar_utc < signal_ts: continue
        max_high = high if max_high is None else max(max_high, high)
        min_low = low if min_low is None else min(min_low, low)
        if direction == "LONG":
            if target_hit_bar is None and high >= target_f: target_hit_bar = (bar_utc, high)
            if stop_hit_bar is None and low <= stop_f: stop_hit_bar = (bar_utc, low)
        else:
            if target_hit_bar is None and low <= target_f: target_hit_bar = (bar_utc, low)
            if stop_hit_bar is None and high >= stop_f: stop_hit_bar = (bar_utc, high)
        if target_hit_bar and stop_hit_bar: break

    if max_high is not None and min_low is not None:
        post_mfe = (max_high - entry_f) if direction == "LONG" else (entry_f - min_low)
        print(f"  Today's max_high = {max_high:.4f}, min_low = {min_low:.4f}")
        print(f"  Today's post-signal MFE = {post_mfe:.4f}  (vs signal_outcomes MFE = {float(p['mfe']):.4f})")
    if target_hit_bar:
        print(f"  Target HIT today at {target_hit_bar[0]}  (price={target_hit_bar[1]:.4f})")
        if stop_hit_bar and stop_hit_bar[0] <= target_hit_bar[0]:
            print(f"  Stop also hit at {stop_hit_bar[0]} (before/same bar) - LOSS by conservative rule")
            print(f"  VERDICT: today's data shows LOSS, but resolver wrote WIN -> RESIDUAL_BUG")
            bug += 1
        else:
            print(f"  VERDICT: today's data confirms WIN -> DRIFT (signal_outcomes MFE is stale)")
            drift += 1
    else:
        print(f"  Target NOT hit on today's data")
        print(f"  VERDICT: RESIDUAL_BUG (resolver wrote WIN, today's data does not support)")
        bug += 1
    print()

print("=" * 78)
print(f"SUMMARY ({len(phantoms)} sampled)")
print(f"  DRIFT (today's yfinance still confirms WIN, signal_outcomes MFE stale): {drift}")
print(f"  RESIDUAL_BUG (today's yfinance does NOT support WIN claim)            : {bug}")
print(f"  DATA_GAP (yfinance returned nothing usable)                           : {gap}")
print()
if bug == 0:
    print("  Conclusion: 28 phantoms appear to be yfinance drift. ACCEPTABLE for Phase B.")
    print("  Phase C will project from signal_outcomes anyway, self-cleaning the residue.")
elif bug >= 3:
    print("  Conclusion: residual resolver bug exists. Phase B.1 brief required.")
else:
    print("  Conclusion: mixed signal. Recommend expanding sample to 10-15 before deciding.")

cur.close(); conn.close()
